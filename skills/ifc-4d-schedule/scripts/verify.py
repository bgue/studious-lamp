#!/usr/bin/env python3
"""Check that an IFC carries the accepted links of a LinkML LinkDataset (as written by apply_links.py or an IFC MCP server).

    python verify.py --ifc model.4d.ifc --links links.json

Checks: one IfcWorkSchedule "Xray 4D"; a task per linked activity (Identification = Activity ID); every accepted build link
as IfcRelAssignsToProduct (element -> task) and every remove link as IfcRelAssignsToProcess (task -> element); task dates
(IFC4 and later); Xray_4D.ActivityIds equal to the accepted build links of each element. Prints a JSON report; exit 1 on
any failure.
"""
from __future__ import annotations

import argparse
import json
import sys

# stdout carries only the JSON summary: ifcopenshell prints notes (on import and on first API use), so they go to stderr
OUT = sys.stdout
sys.stdout = sys.stderr
import ifcopenshell
import ifcopenshell.util.element


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--ifc', required=True)
    ap.add_argument('--links', required=True)
    a = ap.parse_args()
    ds = json.load(open(a.links, encoding='utf-8'))
    f = ifcopenshell.open(a.ifc)
    problems: list[str] = []

    schedules = [w for w in f.by_type('IfcWorkSchedule') if w.Name == 'Xray 4D']
    if len(schedules) != 1:
        problems.append(f'expected one IfcWorkSchedule "Xray 4D", found {len(schedules)}')
    tasks = {t.Identification: t for t in f.by_type('IfcTask')}
    built: dict[str, set[str]] = {}
    removed: dict[str, set[str]] = {}
    for rel in f.by_type('IfcRelAssignsToProduct'):
        for t in rel.RelatedObjects:
            if t.is_a('IfcTask'):
                built.setdefault(t.Identification, set()).add(rel.RelatingProduct.GlobalId)
    for rel in f.by_type('IfcRelAssignsToProcess'):
        t = rel.RelatingProcess
        if t.is_a('IfcTask'):
            removed.setdefault(t.Identification, set()).update(o.GlobalId for o in rel.RelatedObjects)

    want_ids: dict[str, set[str]] = {}
    links = [l for l in ds.get('links', []) if l.get('status') == 'accepted']
    for l in links:
        code = l['activity']
        if code not in tasks:
            problems.append(f'no IfcTask for {code}')
            continue
        have = built if l['role'] == 'build' else removed
        miss = set(l.get('elements', [])) - have.get(code, set())
        if miss:
            problems.append(f'{code} {l["role"]}: {len(miss)} element(s) not assigned, e.g. {sorted(miss)[0]}')
        if l['role'] == 'build':
            for g in l.get('elements', []):
                want_ids.setdefault(g, set()).add(code)
        if f.schema != 'IFC2X3':
            tt = tasks[code].TaskTime
            if not tt or not (tt.ScheduleStart and tt.ScheduleFinish):
                problems.append(f'{code}: no schedule dates')
    for g, codes in want_ids.items():
        try:
            el = f.by_guid(g)
        except RuntimeError:
            continue
        got = ifcopenshell.util.element.get_psets(el).get('Xray_4D', {}).get('ActivityIds', '')
        got_set = {c.strip() for c in str(got).split(',') if c.strip()}
        if got_set != codes:
            problems.append(f'{g}: Xray_4D.ActivityIds is "{got}", expected {sorted(codes)}')
    report = {'ifc': a.ifc, 'tasks': len(tasks), 'links_checked': len(links), 'sequences': len(f.by_type('IfcRelSequence')),
              'ok': not problems, 'problems': problems[:50]}
    print(json.dumps(report, indent=2), file=OUT)
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main())
