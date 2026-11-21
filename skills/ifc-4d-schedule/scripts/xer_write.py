#!/usr/bin/env python3
"""Write 4D link status back into a copy of a P6 XER file as activity user fields, so planners see in P6 which activities
are linked to the model.

    python xer_write.py --xer schedule.xer --links links.json -o schedule.4d.xer

Adds (or updates) three activity UDFs:
  "4D Elements"   number of elements the activity's accepted build links name
  "4D Status"     linked | proposed | tie | no elements | no geometry (milestones, LOE, WBS summary)
  "4D Model"      the model file the links refer to
Every other line of the file is kept byte for byte (encoding and line endings too). Re-running replaces the earlier values.
Import the result into P6 with "Update existing project" so only the user fields change.
"""
from __future__ import annotations

import argparse
import json
import sys

LABELS = [('4D Elements', 'FT_INT', 'udf_number'), ('4D Status', 'FT_TEXT', 'udf_text'), ('4D Model', 'FT_TEXT', 'udf_text')]
UDFTYPE_FIELDS = ['udf_type_id', 'table_name', 'udf_type_name', 'udf_type_label', 'logical_data_type']
UDFVALUE_FIELDS = ['udf_type_id', 'fk_id', 'proj_id', 'udf_number', 'udf_text']


def main() -> int:
    ap = argparse.ArgumentParser(description='Write 4D link status into a P6 XER copy as activity user fields.')
    ap.add_argument('--xer', required=True)
    ap.add_argument('--links', required=True)
    ap.add_argument('-o', '--out', required=True)
    a = ap.parse_args()
    raw = open(a.xer, 'rb').read()
    try:
        text, enc = raw.decode('utf-8'), 'utf-8'
    except UnicodeDecodeError:
        text, enc = raw.decode('cp1252'), 'cp1252'
    nl = '\r\n' if '\r\n' in text else '\n'
    lines = text.split(nl)
    ds = json.load(open(a.links, encoding='utf-8'))

    # pass 1: tables, task ids, existing UDF types
    blocks: list[tuple[str | None, int, int]] = []  # (table, start line, end line exclusive)
    cur, start = None, 0
    for i, line in enumerate(lines):
        if line.startswith('%T\t') or line.startswith('%E'):
            if cur is not None:
                blocks.append((cur, start, i))
            cur, start = (line.split('\t')[1] if line.startswith('%T\t') else None), i
    rows = lambda name: [(i, dict(zip(fields_of(name), lines[i].split('\t')[1:]))) for b in blocks if b[0] == name for i in range(b[1], b[2]) if lines[i].startswith('%R\t')]

    def fields_of(name):
        for b in blocks:
            if b[0] == name:
                for i in range(b[1], b[2]):
                    if lines[i].startswith('%F\t'):
                        return lines[i].split('\t')[1:]
        return []

    tasks = {r['task_code']: r for _, r in rows('TASK')}
    proj_id = next(iter(tasks.values()), {}).get('proj_id', '')
    udf_types = {r.get('udf_type_label'): r for _, r in rows('UDFTYPE') if r.get('table_name') == 'TASK'}
    used_ids = {int(r['udf_type_id']) for _, r in rows('UDFTYPE') if r.get('udf_type_id', '').isdigit()}
    new_types, type_id = [], {}
    for label, ltype, _ in LABELS:
        if label in udf_types:
            type_id[label] = udf_types[label]['udf_type_id']
        else:
            nid = max(used_ids | {90000}) + 1
            used_ids.add(nid)
            type_id[label] = str(nid)
            new_types.append({'udf_type_id': nid, 'table_name': 'TASK', 'udf_type_name': f'user_field_{nid}', 'udf_type_label': label, 'logical_data_type': ltype})

    # the values
    accepted = [l for l in ds.get('links', []) if l.get('status') == 'accepted' and l.get('role') == 'build']
    proposed = {l['activity'] for l in ds.get('links', []) if l.get('status') == 'proposed'}
    tied = {c for t in ds.get('ties', []) for c in t.get('candidates', [])}
    count: dict[str, int] = {}
    for l in accepted:
        count[l['activity']] = count.get(l['activity'], 0) + len(set(l.get('elements', [])))
    types = {x['task_code']: x.get('activity_type') for x in ds.get('activities', [])}
    model_name = (ds.get('model') or {}).get('file_name') or (ds.get('model') or {}).get('name') or ''
    values = []
    for code, t in tasks.items():
        if types.get(code, 'task') in ('milestone', 'finishMilestone', 'loe', 'wbsSummary'):
            status = 'no geometry'
        elif count.get(code):
            status = 'linked'
        elif code in proposed:
            status = 'proposed'
        elif code in tied:
            status = 'tie'
        else:
            status = 'no elements'
        values.append({'udf_type_id': type_id['4D Elements'], 'fk_id': t['task_id'], 'proj_id': proj_id, 'udf_number': count.get(code, 0), 'udf_text': ''})
        values.append({'udf_type_id': type_id['4D Status'], 'fk_id': t['task_id'], 'proj_id': proj_id, 'udf_number': '', 'udf_text': status})
        values.append({'udf_type_id': type_id['4D Model'], 'fk_id': t['task_id'], 'proj_id': proj_id, 'udf_number': '', 'udf_text': model_name})
    ours = set(type_id.values())

    def row_line(fields, r):
        return '%R\t' + '\t'.join('' if r.get(f) in (None,) else str(r.get(f, '')) for f in fields)

    out = list(lines)
    # UDFTYPE: append our new types to the table, or create the table
    inserts: list[tuple[int, list[str]]] = []
    if new_types:
        b = next((b for b in blocks if b[0] == 'UDFTYPE'), None)
        if b:
            f = fields_of('UDFTYPE')
            inserts.append((b[2], [row_line(f, r) for r in new_types]))
        else:
            first_task = next(b for b in blocks if b[0] == 'TASK')
            inserts.append((first_task[1], ['%T\tUDFTYPE', '%F\t' + '\t'.join(UDFTYPE_FIELDS)] + [row_line(UDFTYPE_FIELDS, r) for r in new_types]))
    # UDFVALUE: drop earlier values of our types, append the new ones
    b = next((b for b in blocks if b[0] == 'UDFVALUE'), None)
    drop = set()
    if b:
        f = fields_of('UDFVALUE')
        for i in range(b[1], b[2]):
            if lines[i].startswith('%R\t') and dict(zip(f, lines[i].split('\t')[1:])).get('udf_type_id') in ours:
                drop.add(i)
        inserts.append((b[2], [row_line(f, r) for r in values]))
    else:
        end = next(i for i, l in enumerate(lines) if l.startswith('%E'))
        inserts.append((end, ['%T\tUDFVALUE', '%F\t' + '\t'.join(UDFVALUE_FIELDS)] + [row_line(UDFVALUE_FIELDS, r) for r in values]))
    result = []
    ins = {}
    for at, block in inserts:
        ins.setdefault(at, []).extend(block)
    for i, line in enumerate(out):
        if i in ins:
            result.extend(ins[i])
        if i not in drop:
            result.append(line)
    open(a.out, 'wb').write(nl.join(result).encode(enc))
    stats: dict[str, int] = {}
    for v in values:
        if v['udf_type_id'] == type_id['4D Status']:
            stats[v['udf_text']] = stats.get(v['udf_text'], 0) + 1
    print(json.dumps({'output': a.out, 'encoding': enc, 'udf_types_added': [t['udf_type_label'] for t in new_types], 'activities': len(tasks), 'status': stats}, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
