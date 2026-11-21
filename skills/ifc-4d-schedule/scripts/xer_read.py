#!/usr/bin/env python3
"""Read a Primavera P6 XER file into JSON: the project, its activities (codes, WBS path, dates, status, float, user fields),
relationships, activity code types and calendars. No dependencies.

    python xer_read.py schedule.xer [--project SHORTNAME] [-o schedule.json]

Dates stay as P6 writes them, local without a zone, in ISO form ('2027-03-15T08:00'). Fields are looked up by name, so the
column order of any P6 version works. Output schema 'xray-xer-json/1' (documented in ../reference/data-formats.md).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys

TYPES = {'TT_Task': 'task', 'TT_Rsrc': 'resource', 'TT_Mile': 'milestone', 'TT_FinMile': 'finishMilestone', 'TT_LOE': 'loe', 'TT_WBS': 'wbsSummary'}
STATUS = {'TK_NotStart': 'notStarted', 'TK_Active': 'active', 'TK_Complete': 'complete'}


def decode(data: bytes) -> tuple[str, str]:
    if data.startswith(b'\xef\xbb\xbf'):
        data = data[3:]
    try:
        return data.decode('utf-8'), 'utf-8'
    except UnicodeDecodeError:
        return data.decode('cp1252', errors='replace'), 'cp1252'


def tables(text: str) -> dict[str, list[dict[str, str]]]:
    out: dict[str, list[dict[str, str]]] = {}
    name, fields = None, []
    for line in text.splitlines():
        p = line.split('\t')
        if p[0] == '%T':
            name = p[1] if len(p) > 1 else None
            out.setdefault(name, [])
        elif p[0] == '%F':
            fields = p[1:]
        elif p[0] == '%R' and name:
            out[name].append(dict(zip(fields, p[1:])))
    return out


def iso(v: str | None) -> str | None:
    return v.strip().replace(' ', 'T')[:16] if v and v.strip() else None


def num(v: str | None) -> float | None:
    try:
        return float(v) if v not in (None, '') else None
    except ValueError:
        return None


def read_xer(path: str, project: str | None = None) -> dict:
    raw = open(path, 'rb').read()
    text, enc = decode(raw)
    if not text.startswith('ERMHDR'):
        raise SystemExit(f'{path}: not an XER file (no ERMHDR header)')
    t = tables(text)
    projects = t.get('PROJECT', [])
    if project:
        sel = [p for p in projects if p.get('proj_short_name') == project]
        if not sel:
            raise SystemExit(f'project {project!r} not in the file: {", ".join(p.get("proj_short_name", "") for p in projects)}')
        proj = sel[0]
    elif len(projects) == 1:
        proj = projects[0]
    else:
        raise SystemExit('several projects in the file, choose one with --project: ' + ', '.join(p.get('proj_short_name', '') for p in projects))
    pid = proj.get('proj_id')
    wbs = {w['wbs_id']: w for w in t.get('PROJWBS', []) if w.get('proj_id') == pid}

    def wbs_path(wid: str) -> list[str]:
        path, seen = [], set()
        while wid in wbs and wid not in seen:
            seen.add(wid)
            w = wbs[wid]
            if w.get('proj_node_flag') == 'Y':
                break
            path.append(w.get('wbs_short_name', ''))
            wid = w.get('parent_wbs_id', '')
        return list(reversed(path))

    code_types = {r['actv_code_type_id']: r.get('actv_code_type', '') for r in t.get('ACTVTYPE', [])}
    codes = {r['actv_code_id']: (code_types.get(r.get('actv_code_type_id'), ''), r.get('short_name', '')) for r in t.get('ACTVCODE', [])}
    udf_types = {r['udf_type_id']: r.get('udf_type_label', '') for r in t.get('UDFTYPE', []) if r.get('table_name') == 'TASK'}
    tasks_raw = [r for r in t.get('TASK', []) if r.get('proj_id') == pid]
    by_id = {r['task_id']: r for r in tasks_raw}
    task_codes: dict[str, dict[str, str]] = {}
    for r in t.get('TASKACTV', []):
        if r.get('task_id') in by_id and r.get('actv_code_id') in codes:
            ct, short = codes[r['actv_code_id']]
            task_codes.setdefault(r['task_id'], {}).setdefault(ct, short)
    udfs: dict[str, dict] = {}
    for r in t.get('UDFVALUE', []):
        if r.get('fk_id') in by_id and r.get('udf_type_id') in udf_types:
            v = r.get('udf_text') or num(r.get('udf_number')) or iso(r.get('udf_date'))
            if v not in (None, ''):
                udfs.setdefault(r['fk_id'], {})[udf_types[r['udf_type_id']]] = v
    acts = []
    for r in tasks_raw:
        d = {k: iso(r.get(f)) for k, f in (('targetStart', 'target_start_date'), ('targetEnd', 'target_end_date'), ('earlyStart', 'early_start_date'),
             ('earlyEnd', 'early_end_date'), ('lateStart', 'late_start_date'), ('lateEnd', 'late_end_date'), ('actualStart', 'act_start_date'),
             ('actualEnd', 'act_end_date'), ('remainingStart', 'restart_date'), ('remainingEnd', 'reend_date'))}
        acts.append({
            'code': r.get('task_code', ''), 'id': r.get('task_id'), 'name': r.get('task_name', ''), 'wbsPath': wbs_path(r.get('wbs_id', '')),
            'type': TYPES.get(r.get('task_type', ''), 'other'), 'status': STATUS.get(r.get('status_code', ''), 'notStarted'),
            'dates': {k: v for k, v in d.items() if v}, 'totalFloatHours': num(r.get('total_float_hr_cnt')),
            'driving': r.get('driving_path_flag') == 'Y', 'percentComplete': num(r.get('phys_complete_pct')),
            'codes': task_codes.get(r['task_id'], {}), 'udfs': udfs.get(r['task_id'], {}),
        })
    code_of = {r['task_id']: r.get('task_code') for r in tasks_raw}
    rels = []
    for r in t.get('TASKPRED', []):
        a, b = code_of.get(r.get('pred_task_id')), code_of.get(r.get('task_id'))
        if a and b:
            rels.append({'predecessor': a, 'successor': b, 'type': (r.get('pred_type') or 'PR_FS')[3:], 'lagHours': num(r.get('lag_hr_cnt')) or 0})
    values: dict[str, list[str]] = {}
    for ct, short in codes.values():
        values.setdefault(ct, [])
        if short not in values[ct]:
            values[ct].append(short)
    cals = [{'id': c.get('clndr_id'), 'name': c.get('clndr_name'), 'hoursPerDay': num(c.get('day_hr_cnt'))} for c in t.get('CALENDAR', [])]
    return {
        'schema': 'xray-xer-json/1', 'file': path, 'encoding': enc, 'sourceHash': hashlib.sha256(raw).hexdigest(),
        'project': {'id': pid, 'shortName': proj.get('proj_short_name'), 'dataDate': iso(proj.get('last_recalc_date')), 'calendarId': proj.get('clndr_id')},
        'projects': [p.get('proj_short_name') for p in projects], 'calendars': cals, 'codeTypes': values,
        'udfLabels': sorted(set(udf_types.values())), 'activities': acts, 'relations': rels,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description='Read a P6 XER file into JSON.')
    ap.add_argument('xer')
    ap.add_argument('--project')
    ap.add_argument('-o', '--out')
    a = ap.parse_args()
    data = read_xer(a.xer, a.project)
    text = json.dumps(data, indent=2, ensure_ascii=False)
    if a.out:
        open(a.out, 'w', encoding='utf-8').write(text + '\n')
        print(json.dumps({'output': a.out, 'project': data['project'], 'activities': len(data['activities']), 'relations': len(data['relations']), 'codeTypes': {k: len(v) for k, v in data['codeTypes'].items()}}, indent=2))
    else:
        sys.stdout.write(text + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
