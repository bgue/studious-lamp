#!/usr/bin/env python3
"""Write an X-ray animation script (.xrayanim) that animates part of a build in schedule order.

    python anim_write.py --links links.json [--ifc model.json] [selection] [style] -o build.xrayanim

Selection (all optional, combined with AND): --activities A1200,A1210  --trade MASON-EXT,WINDOWS  --location Erdgeschoss
--wbs SHELL  --from 2027-04-01 --to 2027-06-30  --critical  --status notStarted,active
Style: --length 60 (seconds) | --days-per-second 2;  --camera follow|fixed;  --captions/--no-captions;  --labels N
(label the first N activities' elements);  --mode ghost|solid|radiograph|glow|cutaway;  --context built|hidden (work
finished before the window is shown at the start, or everything starts hidden);  --chunks N (progressive reveal steps
per activity, swept along the building when --ifc gives positions).
Modes:
  default            statements of the current language (show/hide with fades, fly to, caption, label, together, wait):
                     plays in any viewer with a Script tab. Dates appear in captions.
  --plan NAME        uses the 4D statements (schedule "NAME" ... over N, at date, at milestone, focus, explode): the
                     schedule clock, HUD date and S-curve come from the plan NAME, which the viewer or `xray-4d plan`
                     must have built from the same schedule.

Activities and elements come from the accepted links of a LinkML LinkDataset (link.py or the viewer's 4D tab). Check the
result with `node xrayanim_check.mjs build.xrayanim` (compiles it with the viewer's own compiler).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys


def parse_date(s: str | None) -> dt.datetime | None:
    if not s:
        return None
    s = s.strip()
    return dt.datetime.fromisoformat(s if 'T' in s else s + 'T00:00')


def q(s: str) -> str:
    return '"' + s.replace('"', "'") + '"'


def elements(gids: list[str]) -> str:
    return 'elements ' + ', '.join(q(g) for g in gids)


def nice_date(d: dt.datetime) -> str:
    return f'{d.day} {d.strftime("%b %Y")}'


def main() -> int:
    ap = argparse.ArgumentParser(description='Write an animation script for part of a build, in schedule order.')
    ap.add_argument('--links', required=True)
    ap.add_argument('--ifc', help='ifc_read.py JSON (element positions for the sweep order)')
    ap.add_argument('--activities')
    ap.add_argument('--trade')
    ap.add_argument('--location')
    ap.add_argument('--wbs')
    ap.add_argument('--from', dest='date_from')
    ap.add_argument('--to', dest='date_to')
    ap.add_argument('--critical', action='store_true')
    ap.add_argument('--status')
    ap.add_argument('--length', type=float, default=60.0)
    ap.add_argument('--days-per-second', type=float)
    ap.add_argument('--camera', choices=['follow', 'fixed'], default='follow')
    ap.add_argument('--captions', dest='captions', action='store_true', default=True)
    ap.add_argument('--no-captions', dest='captions', action='store_false')
    ap.add_argument('--labels', type=int, default=0)
    ap.add_argument('--mode', choices=['ghost', 'solid', 'radiograph', 'glow', 'cutaway'], default='solid')
    ap.add_argument('--context', choices=['built', 'hidden'], default='built')
    ap.add_argument('--chunks', type=int, default=3)
    ap.add_argument('--plan', help='use the 4D statements with this plan name')
    ap.add_argument('--name', default='Build sequence')
    ap.add_argument('--as-param', action='store_true', help='declare the film title as a script parameter (param title default "...") and show it as a caption; the viewer shows it in the Parameters form')
    ap.add_argument('-o', '--out', required=True)
    a = ap.parse_args()

    ds = json.load(open(a.links, encoding='utf-8'))
    pos = {}
    if a.ifc:
        for e in json.load(open(a.ifc, encoding='utf-8')).get('elements', []):
            if e.get('bbox'):
                b = e['bbox']
                pos[e['globalId']] = ((b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2)
    acts = {x['task_code']: x for x in ds.get('activities', [])}
    builds: dict[str, list[str]] = {}
    for l in ds.get('links', []):
        if l.get('status') == 'accepted' and l.get('role') == 'build':
            builds.setdefault(l['activity'], []).extend(g for g in l.get('elements', []) if g not in builds.get(l['activity'], []))

    def keep(code: str) -> bool:
        x = acts.get(code, {})
        if a.activities and code not in {c.strip() for c in a.activities.split(',')}:
            return False
        if a.trade and (x.get('trade') or '') not in {t.strip() for t in a.trade.split(',')}:
            return False
        if a.location and (x.get('location') or '').lower() != a.location.lower():
            return False
        if a.wbs and a.wbs.upper() not in (x.get('wbs_path') or '').upper().split('/'):
            return False
        if a.critical and not x.get('critical'):
            return False
        if a.status and x.get('activity_status') not in {s.strip() for s in a.status.split(',')}:
            return False
        s, f = parse_date(x.get('start')), parse_date(x.get('finish'))
        if a.date_from and f and f < parse_date(a.date_from):
            return False
        if a.date_to and s and s > parse_date(a.date_to):
            return False
        return bool(s and f)

    chosen = sorted((c for c in builds if c in acts and keep(c)), key=lambda c: (acts[c]['start'], c))
    if not chosen:
        raise SystemExit('no activity with linked elements matches the selection')
    t0 = parse_date(a.date_from) if a.date_from else min(parse_date(acts[c]['start']) for c in chosen)
    t1 = parse_date(a.date_to) if a.date_to else max(parse_date(acts[c]['finish']) for c in chosen)
    span_days = max((t1 - t0).total_seconds() / 86400, 0.5)
    length = span_days / a.days_per_second if a.days_per_second else a.length
    to_sec = lambda d: max(0.0, min(length, (d - t0).total_seconds() / 86400 / span_days * length))
    milestones = sorted((x for x in acts.values() if x.get('activity_type') in ('milestone', 'finishMilestone')
                         and x.get('finish') and t0 <= parse_date(x['finish']) <= t1), key=lambda x: x['finish'])
    # elements finished before the window (shown at the start in context "built")
    before = [g for c, gids in builds.items() if c in acts and acts[c].get('finish') and parse_date(acts[c]['finish']) < t0 for g in gids]
    selected = [g for c in chosen for g in builds[c]]

    lines = [f'-- {a.name}: generated by the ifc-4d-schedule skill (anim_write.py) from {ds.get("schedule", {}).get("file_name", "the schedule")}',
             f'-- model {ds.get("model", {}).get("file_name", "")}; {len(chosen)} activities, {len(selected)} elements; '
             f'{t0.date()} to {t1.date()} in {length:g} s ({span_days / length:.2f} days per second)',
             '-- selection: ' + (', '.join(f'{k}={v}' for k, v in (('activities', a.activities), ('trade', a.trade), ('location', a.location), ('wbs', a.wbs),
                                                            ('from', a.date_from), ('to', a.date_to), ('critical', a.critical or None), ('status', a.status)) if v) or 'all linked activities'),
             '']
    title = a.name + ': ' + (', '.join(f'{k}={v}' for k, v in (('trade', a.trade), ('location', a.location), ('wbs', a.wbs), ('status', a.status)) if v) or 'all linked activities')
    if a.as_param:
        lines += [f'param title default {q(title)}', '']
    events = []  # (time, order, kind, payload)
    for i, code in enumerate(chosen):
        x = acts[code]
        s, f = to_sec(parse_date(x['start'])), to_sec(parse_date(x['finish']))
        gids = builds[code]
        if pos:
            axis = max(range(3), key=lambda k: (max(pos[g][k] for g in gids if g in pos) - min(pos[g][k] for g in gids if g in pos)) if any(g in pos for g in gids) else 0)
            gids = sorted(gids, key=lambda g: pos.get(g, (0, 0, 0))[axis])
        n = max(1, min(a.chunks, len(gids)))
        for k in range(n):
            part = gids[k * len(gids) // n:(k + 1) * len(gids) // n]
            if part:
                events.append((s + (f - s) * k / n, 1, 'show', {'code': code, 'gids': part, 'first': k == 0, 'all': gids, 'label': i < a.labels}))
    for m in milestones:
        events.append((to_sec(parse_date(m['finish'])), 0, 'milestone', m))
    events.sort(key=lambda e: (e[0], e[1]))

    if a.plan:
        lines += [f'schedule {q(a.plan)} view planned from {q(str(t0.date()))} to {q(str(t1.date()))} over {length:g} seconds', 'focus active', *(['caption title for 2 seconds'] if a.as_param else []), '']
        last_date = None
        for t, _, kind, p in events:
            when = t0 + dt.timedelta(days=t / length * span_days)
            if kind == 'milestone':
                lines += [f'at milestone {q(p["name"])}', f'  caption {q(p["name"])} {q(nice_date(parse_date(p["finish"])))} for 2 seconds', '']
                continue
            if not p['first']:
                continue
            x = acts[p['code']]
            d = str(when.date())
            if d != last_date:
                lines.append(f'at date {q(d)}')
                last_date = d
            lines.append(f'  -- {p["code"]} {x["name"]} ({x.get("trade", "")}, {x.get("location", "")})')
            if a.camera == 'follow':
                lines.append(f'  fly to {elements(p["all"])} over 1.5 seconds')
            if p['label']:
                lines.append(f'  label {elements(p["all"])} with name for 3 seconds')
            lines.append('')
    else:
        lines += [f'mode {a.mode}', 'hide everything']
        if a.context == 'built' and before:
            lines.append(f'show {elements(before)}')
        if a.camera == 'follow':
            if a.as_param:
                lines += ['together', f'  fly to {elements(selected)} over 1.5 seconds', '  caption title for 1.5 seconds', 'end together']
            else:
                lines.append(f'fly to {elements(selected)} over 1.5 seconds')
        elif a.as_param:
            lines.append('caption title for 1.5 seconds')
        lines.append('')
        now = 1.5 if (a.camera == 'follow' or a.as_param) else 0.0
        slip = 0.0
        for idx, (t, _, kind, p) in enumerate(events):
            nxt = events[idx + 1][0] if idx + 1 < len(events) else length
            if t > now + 0.05:
                lines.append(f'wait {t - now:.2f} seconds')
                now = t
            slip = max(slip, now - t)
            room = max(0.0, nxt - now)
            when = t0 + dt.timedelta(days=t / length * span_days)
            if kind == 'milestone':
                if a.captions and room >= 1.0:
                    dur = min(2.0, room)
                    lines += [f'caption {q(p["name"])} {q(nice_date(parse_date(p["finish"])))} for {dur:.2f} seconds', '']
                    now += dur
                continue
            x = acts[p['code']]
            fade = max(0.3, min(0.8, room if room > 0 else 0.3))
            block = [f'  show {elements(p["gids"])} fading over {fade:.2f} seconds']
            dur = fade
            if p['first']:
                lines.append(f'-- {nice_date(when)}  {p["code"]} {x["name"]} ({x.get("trade", "")}, {x.get("location", "")})')
                if a.camera == 'follow' and room >= 1.2:
                    block.append(f'  fly to {elements(p["all"])} over {min(1.5, room):.2f} seconds')
                    dur = max(dur, min(1.5, room))
                if a.captions and room >= 1.2:
                    c = min(2.5, room)
                    block.append(f'  caption {q(nice_date(when))} {q(x["name"])} for {c:.2f} seconds')
                    dur = max(dur, c)
                if p['label'] and room >= 1.5:
                    c = min(3.0, room)
                    block.append(f'  label {elements(p["all"])} with name for {c:.2f} seconds')
                    dur = max(dur, c)
            lines += ['together', *block, 'end together', ''] if len(block) > 1 else [block[0].strip(), '']
            now += dur
        if now < length:
            lines.append(f'wait {length - now:.2f} seconds')
        lines.append('')
        lines.insert(3, f'-- timing: each statement starts at its schedule moment; the largest slip behind schedule time is {slip:.2f} s')
    open(a.out, 'w', encoding='utf-8').write('\n'.join(lines))
    print(json.dumps({'output': a.out, 'activities': chosen, 'elements': len(selected), 'from': str(t0.date()), 'to': str(t1.date()),
                      'seconds': round(length, 2), 'mode': '4d' if a.plan else 'standard', 'milestones': [m['name'] for m in milestones]}, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
