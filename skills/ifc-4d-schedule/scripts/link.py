#!/usr/bin/env python3
"""Link schedule activities to IFC elements and write a LinkML LinkDataset (links.json).

    python link.py --xer schedule.json --ifc model.json --config map.4d.json [--prior links.json] [--proposals agent.json] -o links.json

Inputs are the JSON of xer_read.py and ifc_read.py, the X-ray 4D configuration (the same .4d.json the viewer uses:
schedule location/trade/zone sources, value mapping, tradeQueries in the criteria language, per-activity overrides,
split rules), optionally an earlier links.json (accepted links and assignments are kept) and agent proposals (a JSON list
of {activity, role, elements, reasons, confidence} that become status 'proposed' links for a person to review).

Tiers, strongest first: links already in the IFC (IfcTask assignments: 'native') > per-activity overrides ('override') >
attributes (location, trade, zone of the activity matched against the elements: more attributes = more specific).
An element claimed by two building activities with equal strength is a tie and goes to neither. Milestones, LOE and WBS
summaries never get elements. Prints a coverage summary; exit 4 when element coverage is below --min-coverage.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys

from criteria import QueryError, compile_query

NO_GEOMETRY = ('milestone', 'finishMilestone', 'loe', 'wbsSummary')


def attr_from_sources(act: dict, sources: list[dict]) -> str | None:
    for s in sources or []:
        if 'code' in s and act['codes'].get(s['code']):
            return act['codes'][s['code']]
        if 'udf' in s and act['udfs'].get(s['udf']) not in (None, ''):
            return str(act['udfs'][s['udf']])
        if 'wbsLevel' in s and len(act['wbsPath']) > s['wbsLevel']:
            return act['wbsPath'][s['wbsLevel']]
        for key, text in (('wbsPattern', '/'.join(act['wbsPath'])), ('namePattern', act['name'])):
            if key in s:
                m = re.search(s[key], text)
                if m:
                    return m.group(s.get('group', 1) if m.groups() else 0)
    return None


def map_value(v: str | None, table: dict | None) -> str | None:
    if v is None or not table:
        return v
    for k, out in table.items():
        if k.startswith('/') and k.endswith('/') and len(k) > 1:
            m = re.fullmatch(k[1:-1], v)
            if m:
                return m.expand(out.replace('$', '\\'))
        elif k.lower() == v.lower():
            return out
    return v


def element_attr(el: dict, sources: list[dict], assigned: dict[str, dict[str, str]], attr: str) -> str | None:
    if el['globalId'] in assigned and attr in assigned[el['globalId']]:
        return assigned[el['globalId']][attr]
    for s in sources or []:
        if 'property' in s and (el.get('props') or {}).get(s['property']) not in (None, ''):
            return str(el['props'][s['property']])
        if s.get('storey') and el.get('storey'):
            return el['storey']
        if s.get('zone') and el.get('zones'):
            return el['zones'][0]
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description='Link schedule activities to IFC elements (LinkML LinkDataset).')
    ap.add_argument('--xer', required=True, help='xer_read.py JSON')
    ap.add_argument('--ifc', required=True, help='ifc_read.py JSON')
    ap.add_argument('--config', required=True, help='.4d.json configuration')
    ap.add_argument('--prior', help='earlier links.json: accepted links and assignments are kept')
    ap.add_argument('--proposals', help='agent proposals JSON list -> status proposed')
    ap.add_argument('--dates', choices=['planned', 'actual'], default=None, help='dates written for activities (default: the config view)')
    ap.add_argument('--min-coverage', type=float, default=0.0)
    ap.add_argument('-o', '--out', required=True)
    a = ap.parse_args()
    xer = json.load(open(a.xer, encoding='utf-8'))
    model = json.load(open(a.ifc, encoding='utf-8'))
    cfg = json.load(open(a.config, encoding='utf-8'))
    prior = json.load(open(a.prior, encoding='utf-8')) if a.prior else {}
    view = a.dates or (cfg.get('style') or {}).get('view', 'planned')
    els = model['elements']
    by_gid = {e['globalId']: e for e in els}
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()

    # accepted assignments (prior dataset) by element and attribute, newest first
    assigned: dict[str, dict[str, str]] = {}
    for s in sorted(prior.get('assignments', []), key=lambda s: s.get('created_at') or ''):
        if s.get('status') == 'accepted':
            assigned.setdefault(s['element'], {})[s['attribute']] = s['value']
    msrc = cfg.get('model', {})
    loc_of = {e['globalId']: element_attr(e, msrc.get('location', []), assigned, 'location') for e in els}
    trade_of = {e['globalId']: element_attr(e, msrc.get('trade', []), assigned, 'trade') for e in els}
    zone_of = {e['globalId']: element_attr(e, msrc.get('zone', []), assigned, 'zone') for e in els}
    queries: dict[str, set[str]] = {}
    for trade, q in (cfg.get('tradeQueries') or {}).items():
        try:
            fn = compile_query(q)
        except QueryError as err:
            raise SystemExit(f'tradeQueries[{trade}]: {err}')
        queries[trade] = {e['globalId'] for e in els if fn(e)}
    existing = set()
    if msrc.get('existing'):
        fn = compile_query(msrc['existing'])
        existing = {e['globalId'] for e in els if fn(e)}

    scfg, vals = cfg.get('schedule', {}), cfg.get('values', {})
    claims: dict[str, list[tuple[int, str, str, list[str]]]] = {}  # gid -> [(strength, code, source, reasons)]
    split_of: dict[str, str] = {}
    acts = {x['code']: x for x in xer['activities']}
    act_attrs = {}
    for code, act in acts.items():
        loc = map_value(attr_from_sources(act, scfg.get('location', [])), vals.get('location'))
        trade = map_value(attr_from_sources(act, scfg.get('trade', [])), vals.get('trade'))
        zone = map_value(attr_from_sources(act, scfg.get('zone', [])), vals.get('zone'))
        act_attrs[code] = (loc, trade, zone)
        if act['type'] in NO_GEOMETRY:
            continue
        ov = (cfg.get('activities') or {}).get(code)
        if ov:
            gids = set(ov.get('globalIds') or [])
            if ov.get('query'):
                fn = compile_query(ov['query'])
                gids |= {e['globalId'] for e in els if fn(e)}
            for g in gids:
                claims.setdefault(g, []).append((9, code, 'override', [f'override for {code}']))
            if ov.get('split'):
                split_of[code] = ov['split']
            continue
        # attributes: the activity's location / trade / zone must match the element's (each optional)
        cand = None
        reasons, n = [], 0
        if loc is not None:
            cand = {g for g, v in loc_of.items() if v is not None and v.lower() == loc.lower()}
            reasons.append(f'location {loc}')
            n += 1
        if trade is not None:
            by_trade = {g for g, v in trade_of.items() if v is not None and v.lower() == trade.lower()} | queries.get(trade, set())
            if not by_trade and trade not in queries:
                continue  # a trade that builds nothing in this model (services, finishes, drying)
            cand = by_trade if cand is None else cand & by_trade
            reasons.append(f'trade {trade}')
            n += 1
        if zone is not None:
            by_zone = {g for g, v in zone_of.items() if v is not None and v.lower() == zone.lower()}
            cand = by_zone if cand is None else cand & by_zone
            reasons.append(f'zone {zone}')
            n += 1
        if not cand or n == 0:
            continue
        for g in cand:
            if g not in existing:
                claims.setdefault(g, []).append((n, code, 'attributes', [', '.join(reasons)]))
        sp = (cfg.get('split') or {})
        split_of[code] = sp.get(trade or '', sp.get('*', 'none'))
    # links already in the IFC win over everything
    for e in els:
        for t in e.get('tasks', []) or []:
            if t['task'] in acts:
                claims.setdefault(e['globalId'], []).append((10, t['task'], 'native', ['IfcTask assignment in the IFC']))

    owner: dict[str, tuple[str, str, list[str]]] = {}
    ties = []
    for g, cs in claims.items():
        best = max(c[0] for c in cs)
        top = {c[1]: c for c in cs if c[0] == best}
        if len(top) == 1:
            c = next(iter(top.values()))
            owner[g] = (c[1], c[2], c[3])
        else:
            ties.append({'element': g, 'candidates': sorted(top)})
    # decisions win: accepted links a person or an agent made earlier stay, and their elements leave the rule links;
    # rule-made links (native, override, attributes) are always rebuilt from the current files and configuration
    links: dict[str, dict] = {}
    decided_sources = ('manual', 'agent', 'suggested', 'classifier', 'property')
    for l in prior.get('links', []):
        if l.get('status') == 'accepted' and l.get('source') in decided_sources:
            links[l['id']] = dict(l)
            if l.get('role', 'build') == 'build':
                for g in l.get('elements', []):
                    owner.pop(g, None)
                    ties[:] = [t for t in ties if t['element'] != g]
    for g, (code, source, reasons) in sorted(owner.items()):
        lid = f'ln-{code}-build'
        l = links.setdefault(lid, {'id': lid, 'activity': code, 'role': 'build', 'elements': [], 'source': source,
                                   'confidence': 1.0 if source in ('native', 'override') else 0.8, 'reasons': reasons,
                                   'split': split_of.get(code, 'none'), 'status': 'accepted', 'created_at': now})
        if g not in l['elements']:
            l['elements'].append(g)
    for p in (json.load(open(a.proposals, encoding='utf-8')) if a.proposals else []):
        lid = f"ln-{p['activity']}-{p.get('role', 'build')}-proposed"
        links[lid] = {'id': lid, 'activity': p['activity'], 'role': p.get('role', 'build'), 'elements': sorted(set(p['elements'])),
                      'source': 'agent', 'confidence': float(p.get('confidence', 0.5)), 'reasons': p.get('reasons', []), 'status': 'proposed', 'created_at': now}

    def dates(act):
        d = act['dates']
        if view == 'actual':
            return d.get('actualStart') or d.get('remainingStart') or d.get('earlyStart'), d.get('actualEnd') or d.get('remainingEnd') or d.get('earlyEnd')
        return d.get('earlyStart') or d.get('targetStart'), d.get('earlyEnd') or d.get('targetEnd')

    crit_hours = (cfg.get('style') or {}).get('criticalFloatHours', 0)
    activities = []
    for code, act in acts.items():
        s, f = dates(act)
        loc, trade, zone = act_attrs[code]
        row = {'task_code': code, 'name': act['name'], 'wbs_path': '/'.join(act['wbsPath']), 'activity_type': act['type'],
               'activity_status': act['status'], 'start': s, 'finish': f, 'location': loc, 'trade': trade, 'zone': zone,
               'critical': bool(act.get('driving')) or (crit_hours is not None and act.get('totalFloatHours') is not None and act['totalFloatHours'] <= crit_hours and act['status'] != 'complete')}
        activities.append({k: v for k, v in row.items() if v is not None})
    accepted = [l for l in links.values() if l.get('status') == 'accepted' and l['role'] == 'build']
    linked = {g for l in accepted for g in l['elements']}
    unlinked_el = sorted(g for g in by_gid if g not in linked and g not in existing)
    linked_acts = {l['activity'] for l in accepted}
    model_rows = [{k: v for k, v in {'global_id': e['globalId'], 'ifc_class': e['class'], 'name': e.get('name'), 'storey': e.get('storey'),
                   'location': loc_of[e['globalId']], 'trade': trade_of[e['globalId']], 'zone': zone_of[e['globalId']],
                   'existing': e['globalId'] in existing or None}.items() if v is not None} for e in els]
    ds = {
        'id': f"{model['file']}|{xer['project']['shortName']}|{xer['sourceHash'][:12]}", 'created_at': now, 'tool': 'ifc-4d-schedule skill',
        'model': {'identity_key': f"file:{model['file']}", 'name': model['file'].rsplit('.', 1)[0], 'file_name': model['file'], 'file_hash': model['fileHash'],
                  'ifc_schema': model['ifcSchema'] if model['ifcSchema'] in ('IFC2X3', 'IFC4', 'IFC4X3') else None},
        'schedule': {'source_hash': xer['sourceHash'], 'project': xer['project']['shortName'], 'data_date': xer['project'].get('dataDate'), 'file_name': xer['file'].rsplit('/', 1)[-1]},
        'activities': activities, 'model_elements': model_rows, 'assignments': prior.get('assignments', []),
        'links': sorted(links.values(), key=lambda l: l['id']), 'ties': ties,
        'unlinked_activities': sorted(c for c, x in acts.items() if x['type'] not in NO_GEOMETRY and c not in linked_acts),
        'unlinked_elements': unlinked_el,
    }
    ds['model'] = {k: v for k, v in ds['model'].items() if v is not None}
    ds['schedule'] = {k: v for k, v in ds['schedule'].items() if v is not None}
    open(a.out, 'w', encoding='utf-8').write(json.dumps(ds, indent=2, ensure_ascii=False) + '\n')
    cov = len(linked) / max(1, len(by_gid) - len(existing))
    summary = {'output': a.out, 'links_accepted': len(accepted), 'links_proposed': sum(1 for l in links.values() if l.get('status') == 'proposed'),
               'elements': len(by_gid), 'elements_linked': len(linked), 'coverage': round(cov, 4), 'ties': len(ties),
               'unlinked_elements': len(unlinked_el), 'activities_without_elements': ds['unlinked_activities']}
    print(json.dumps(summary, indent=2))
    return 4 if cov < a.min_coverage else 0


if __name__ == '__main__':
    sys.exit(main())
