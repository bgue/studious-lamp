#!/usr/bin/env python3
"""Write X-ray 4D link data (a LinkML LinkDataset JSON) into an IFC with IfcOpenShell.

    python apply_links.py --ifc model.ifc --links links.json [--xer schedule.xer] -o model.4d.ifc
    python apply_links.py --ifc model.ifc --links links.json --dry-run

Writes one IfcWorkSchedule "Xray 4D" (replacing an earlier one of that name only), an IfcTask per linked activity and per
milestone (all activities with --all-activities) with IfcTaskTime, IfcRelAssignsToProduct for built elements,
IfcRelAssignsToProcess for removed ones, IfcRelSequence from the XER's relationships, and the Xray_4D property set
(Location, Trade, Zone, ActivityIds). Only accepted rows are used. The input file is never overwritten. Mapping:
../reference/ifc-mapping.md. Needs ifcopenshell 0.8.x. Prints a JSON summary on stdout.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

# stdout carries only the JSON summary: ifcopenshell prints notes (on import and on first API use), so they go to stderr
OUT = sys.stdout
sys.stdout = sys.stderr
import ifcopenshell
import ifcopenshell.api
import ifcopenshell.util.element

SCHEDULE_NAME = 'Xray 4D'
SEQ_TYPES = {'FS': 'FINISH_START', 'SS': 'START_START', 'FF': 'FINISH_FINISH', 'SF': 'START_FINISH'}


def api(usecase: str, f, **kw):
    return ifcopenshell.api.run(usecase, f, **kw)


def iso(local: str | None) -> str | None:
    """'2027-03-15T08:00' -> '2027-03-15T08:00:00' (IfcDateTime, no zone)."""
    if not local:
        return None
    return local if len(local) > 16 else local + ':00'


def read_xer_relations(path: str) -> list[tuple[str, str, str, float]]:
    """(predecessor code, successor code, FS|SS|FF|SF, lag days) from TASK and TASKPRED of an XER file."""
    data = open(path, 'rb').read()
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        text = data.decode('cp1252')
    table, fields, codes, preds, hours_per_day = None, [], {}, [], 8.0
    for line in text.splitlines():
        parts = line.split('\t')
        if parts[0] == '%T':
            table = parts[1]
        elif parts[0] == '%F':
            fields = parts[1:]
        elif parts[0] == '%R':
            row = dict(zip(fields, parts[1:]))
            if table == 'TASK':
                codes[row.get('task_id')] = row.get('task_code')
            elif table == 'TASKPRED':
                preds.append(row)
            elif table == 'CALENDAR' and row.get('default_flag') == 'Y' and row.get('day_hr_cnt'):
                hours_per_day = float(row['day_hr_cnt']) or 8.0
    out = []
    for r in preds:
        a, b = codes.get(r.get('pred_task_id')), codes.get(r.get('task_id'))
        if a and b:
            lag = float(r.get('lag_hr_cnt') or 0) / hours_per_day
            out.append((a, b, (r.get('pred_type') or 'PR_FS')[3:], lag))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--ifc', required=True)
    ap.add_argument('--links', required=True, help='LinkML LinkDataset JSON')
    ap.add_argument('--xer', help='schedule for logic links (TASKPRED)')
    ap.add_argument('-o', '--out', help='output IFC (never the input)')
    ap.add_argument('--dry-run', action='store_true', help='check and report, write nothing')
    ap.add_argument('--all-activities', action='store_true', help='also write activities without elements')
    ap.add_argument('--actual', action='store_true', help='schedule type ACTUAL and actual dates for complete activities')
    args = ap.parse_args()
    if not args.dry_run:
        if not args.out:
            ap.error('-o is required unless --dry-run')
        if os.path.abspath(args.out) == os.path.abspath(args.ifc):
            ap.error('the output must be a new file, not the input')

    ds = json.load(open(args.links, encoding='utf-8'))
    f = ifcopenshell.open(args.ifc)
    schema = f.schema
    summary: dict = {'schema': schema, 'input': args.ifc, 'skipped': {}}

    links = [l for l in ds.get('links', []) if l.get('status') == 'accepted']
    skipped_links = [l['id'] for l in ds.get('links', []) if l.get('status') != 'accepted']
    acts = {a['task_code']: a for a in ds.get('activities', [])}
    by_gid = {}
    for gid in {g for l in links for g in l.get('elements', [])} | {s['element'] for s in ds.get('assignments', [])}:
        try:
            by_gid[gid] = f.by_guid(gid)
        except RuntimeError:
            pass
    missing = sorted({g for l in links for g in l.get('elements', [])} - set(by_gid))
    summary['skipped'] = {'links_not_accepted': skipped_links, 'missing_global_ids': missing}
    used = {l['activity'] for l in links}
    milestones = {c for c, a in acts.items() if a.get('activity_type') in ('milestone', 'finishMilestone')}
    to_write = sorted(used | milestones | (set(acts) if args.all_activities else set()))
    unknown = sorted(c for c in used if c not in acts)
    if unknown:
        summary['skipped']['activities_without_rows'] = unknown
    summary.update({'tasks': len([c for c in to_write if c in acts]), 'build_links': sum(1 for l in links if l['role'] == 'build'),
                    'remove_links': sum(1 for l in links if l['role'] == 'remove')})
    if args.dry_run:
        summary['dry_run'] = True
        print(json.dumps(summary, indent=2), file=OUT)
        return 0 if not missing else 3

    # 1. replace an earlier Xray 4D schedule (only that one)
    for ws in f.by_type('IfcWorkSchedule'):
        if ws.Name == SCHEDULE_NAME:
            api('sequence.remove_work_schedule', f, work_schedule=ws)
    # 2. the schedule
    ws = api('sequence.add_work_schedule', f, name=SCHEDULE_NAME, predefined_type='ACTUAL' if args.actual else 'PLANNED')
    ws.CreationDate = dt.datetime.now().replace(microsecond=0).isoformat()
    # 3. tasks and their times
    roles = {}
    for l in links:
        roles.setdefault(l['activity'], set()).add(l['role'])
    tasks = {}
    for code in to_write:
        a = acts.get(code)
        if not a:
            continue
        r = roles.get(code, set())
        ptype = 'CONSTRUCTION' if 'build' in r else ('DEMOLITION' if 'remove' in r else 'NOTDEFINED')
        t = api('sequence.add_task', f, work_schedule=ws, identification=code, name=a.get('name') or code, predefined_type=ptype)
        if a.get('wbs_path'):
            t.Description = a['wbs_path']
        t.IsMilestone = a.get('activity_type') in ('milestone', 'finishMilestone')
        if schema != 'IFC2X3' and (a.get('start') or a.get('finish')):
            tt = api('sequence.add_task_time', f, task=t)
            attrs = {'DurationType': 'WORKTIME'}
            if a.get('start'):
                attrs['ScheduleStart'] = iso(a['start'])
            if a.get('finish'):
                attrs['ScheduleFinish'] = iso(a['finish'])
            if args.actual and a.get('activity_status') == 'complete':
                attrs['ActualStart'], attrs['ActualFinish'] = iso(a.get('start')), iso(a.get('finish'))
            for k, v in attrs.items():
                setattr(tt, k, v)
        tasks[code] = t
    # 4. element assignments: built elements are task outputs, removed ones are inputs
    for l in links:
        t = tasks.get(l['activity'])
        if not t:
            continue
        for gid in l.get('elements', []):
            el = by_gid.get(gid)
            if el is None:
                continue
            if l['role'] == 'build':
                api('sequence.assign_product', f, relating_product=el, related_object=t)
            else:
                api('sequence.assign_process', f, relating_process=t, related_object=el)
    # 5. logic links between written tasks
    seqs = 0
    merged: list[str] = []
    seen_pairs: set[tuple[str, str]] = set()
    if args.xer:
        for a_code, b_code, typ, lag in read_xer_relations(args.xer):
            if a_code in tasks and b_code in tasks:
                # P6 allows two links between one pair (SS + FF); IFC tools keep one IfcRelSequence per pair: keep the first
                if (a_code, b_code) in seen_pairs:
                    merged.append(f'{a_code}->{b_code} {typ}')
                    continue
                seen_pairs.add((a_code, b_code))
                rel = api('sequence.assign_sequence', f, relating_process=tasks[a_code], related_process=tasks[b_code])
                rel.SequenceType = SEQ_TYPES.get(typ, 'FINISH_START')
                if lag:
                    api('sequence.assign_lag_time', f, rel_sequence=rel, lag_value=f'P{lag:g}D', duration_type='WORKTIME')
                seqs += 1
    summary['sequences'] = seqs
    if merged:
        summary['skipped']['second_link_between_same_pair'] = merged
    # 6. Xray_4D property set
    per_el: dict[str, dict] = {}
    newest: dict[tuple[str, str], str] = {}
    for s in ds.get('assignments', []):
        if s.get('status') != 'accepted':
            continue
        key = (s['element'], s['attribute'])
        if key in newest and (s.get('created_at') or '') < newest[key]:
            continue
        newest[key] = s.get('created_at') or ''
        per_el.setdefault(s['element'], {})[s['attribute'].capitalize()] = s['value']
    for l in links:
        if l['role'] != 'build':
            continue
        for gid in l.get('elements', []):
            ids = per_el.setdefault(gid, {}).setdefault('ActivityIds', [])
            if l['activity'] not in ids:
                ids.append(l['activity'])
    written = 0
    for gid, props in per_el.items():
        el = by_gid.get(gid)
        if el is None:
            continue
        values = {k: (', '.join(sorted(v)) if isinstance(v, list) else v) for k, v in props.items()}
        pset = next((p for p in ifcopenshell.util.element.get_psets(el, psets_only=True).items() if p[0] == 'Xray_4D'), None)
        pset_entity = f.by_id(pset[1]['id']) if pset else api('pset.add_pset', f, product=el, name='Xray_4D')
        api('pset.edit_pset', f, pset=pset_entity, properties=values)
        written += 1
    summary['xray_4d_psets'] = written
    f.write(args.out)
    summary['output'] = args.out
    print(json.dumps(summary, indent=2), file=OUT)
    return 0


if __name__ == '__main__':
    sys.exit(main())
