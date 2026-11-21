// The P6 XER parser (src/schedule/xer.ts) and the SHA-256 it uses (src/schedule/sha256.ts): field lookup by name, dates,
// WBS paths, codes, user fields, relations, statuses, milestones, project choice, encodings, calendars and warnings.
import { createHash, randomBytes } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { decodeXer, parseCalendarData, parseXer } from '../src/schedule/xer';
import { sha256Hex } from '../src/schedule/sha256';
import type { Schedule } from '../src/schedule/types';

const fixture = (name: string): Uint8Array => new Uint8Array(readFileSync(resolve(__dirname, 'fixtures/xer', name)));

/** A minimal XER around the given tables (tab-separated, P6 layout). */
function xer(tables: Array<{ name: string; fields: string[]; rows: Array<Record<string, string>> }>): string {
  const lines = ['ERMHDR\t20.12\t2027-03-12\tProject Management\tadmin\tadmin\tPC\tOracle\tProject Management\tUSD'];
  for (const t of tables) {
    lines.push(`%T\t${t.name}`, `%F\t${t.fields.join('\t')}`);
    for (const r of t.rows) lines.push(`%R\t${t.fields.map((f) => r[f] ?? '').join('\t')}`);
    lines.push('%E');
  }
  return lines.join('\r\n') + '\r\n';
}

const project = (id: string, short: string, dataDate = '2027-03-12 08:00', clndr = '1') => ({ proj_id: id, proj_short_name: short, last_recalc_date: dataDate, clndr_id: clndr });
const wbsRoot = (id: string, proj: string, short: string) => ({ wbs_id: id, proj_id: proj, parent_wbs_id: '', wbs_short_name: short, wbs_name: short, proj_node_flag: 'Y', seq_num: '0' });
const task = (id: string, proj: string, wbs: string, code: string, extra: Record<string, string> = {}) => ({
  task_id: id, proj_id: proj, wbs_id: wbs, clndr_id: '1', task_code: code, task_name: `Activity ${code}`, task_type: 'TT_Task', status_code: 'TK_NotStart', ...extra,
});

describe('SHA-256 (pure JavaScript)', () => {
  it('matches node:crypto on fixed inputs and on the padding boundaries', () => {
    const cases = [new Uint8Array(0), new TextEncoder().encode('abc'), new TextEncoder().encode('a'.repeat(1000))];
    for (const len of [55, 56, 63, 64, 65, 119, 120]) cases.push(new Uint8Array(len).fill(len));
    for (const bytes of cases) {
      expect(sha256Hex(bytes)).toBe(createHash('sha256').update(bytes).digest('hex'));
    }
    expect(sha256Hex(new TextEncoder().encode('abc'))).toBe('ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
  });
  it('matches node:crypto on random input', () => {
    for (let i = 0; i < 5; i++) {
      const bytes = new Uint8Array(randomBytes(1000 + i * 37));
      expect(sha256Hex(bytes)).toBe(createHash('sha256').update(bytes).digest('hex'));
    }
  });
});

describe('decoding', () => {
  it('reads UTF-8 and removes a byte order mark', () => {
    const bytes = new TextEncoder().encode('﻿ERMHDR\tx\nKöln');
    const d = decodeXer(bytes);
    expect(d.encoding).toBe('utf-8');
    expect(d.bom).toBe(true);
    expect(d.text).toBe('ERMHDR\tx\nKöln');
  });
  it('reads Windows-1252 when the bytes are not valid UTF-8, including the 0x80..0x9F range', () => {
    const d = decodeXer(Uint8Array.from([0x41, 0xe9, 0x80, 0x96, 0x9f, 0xd8]));
    expect(d.encoding).toBe('windows-1252');
    expect([...d.text].map((c) => c.codePointAt(0))).toEqual([0x41, 0xe9, 0x20ac, 0x2013, 0x0178, 0xd8]);
  });
  it('takes a string as it is', () => {
    expect(decodeXer('﻿abc').text).toBe('abc');
  });
  it('the cp1252 fixture gives the same names as UTF-8 would', () => {
    const s = parseXer(fixture('windows-1252-names.xer'));
    expect(s.project.shortName).toBe('LEP-OST');
    expect(s.wbs.find((w) => w.shortName === 'FASS')?.name).toBe('Fassade Nord – Südseite');
    expect(s.wbs.find((w) => w.shortName === 'DACH')?.name).toBe('Dach & Abdichtung (Ø 90 mm)');
    expect(s.tasks.find((t) => t.code === 'D200')?.name).toBe('Dämmung und Abdichtung für Flachdach (Kosten 5 € pro m²) – Übergabe');
    expect(decodeXer(fixture('windows-1252-names.xer')).encoding).toBe('windows-1252');
  });
});

describe('the building fixture', () => {
  const s: Schedule = parseXer(fixture('building.xer'));

  it('reads the project, data date and the file hash', () => {
    expect(s.schema).toBe('xray-schedule/1');
    expect(s.project).toMatchObject({ id: '101', shortName: 'BLD-A', name: 'Tower A', dataDate: '2027-03-12T08:00', calendarId: '1' });
    expect(s.projects.map((p) => p.shortName)).toEqual(['BLD-A']);
    expect(s.sourceHash).toBe(createHash('sha256').update(fixture('building.xer')).digest('hex'));
    expect(s.warnings).toEqual([]);
  });

  it('reads every activity with its type and status', () => {
    expect(s.tasks).toHaveLength(41);
    const byType = (type: string) => s.tasks.filter((t) => t.type === type).length;
    expect(byType('task')).toBe(32);
    expect(byType('milestone')).toBe(2);
    expect(byType('finishMilestone')).toBe(4);
    expect(byType('loe')).toBe(2);
    expect(byType('wbsSummary')).toBe(1);
    expect(s.tasks.filter((t) => t.status === 'complete')).toHaveLength(15);
    expect(s.tasks.filter((t) => t.status === 'active')).toHaveLength(4);
    expect(s.tasks.filter((t) => t.status === 'notStarted')).toHaveLength(22);
  });

  it('converts P6 dates to ISO local and reads actuals, remaining dates and percent complete', () => {
    const t = s.tasks.find((x) => x.code === 'A1220')!;
    expect(t.dates).toMatchObject({
      earlyStart: '2027-01-25T08:00', earlyEnd: '2027-03-19T17:00', actualStart: '2027-01-25T08:00',
      remainingStart: '2027-03-12T08:00', remainingEnd: '2027-03-19T17:00',
    });
    expect(t.dates.actualEnd).toBeUndefined();
    expect(t.percentComplete).toBe(60);
    expect(t.totalFloatHours).toBe(40);
    const done = s.tasks.find((x) => x.code === 'A1100')!;
    expect(done.dates.actualEnd).toBe('2026-10-16T17:00');
    expect(done.percentComplete).toBe(100);
  });

  it('builds WBS paths from the top WBS under the project and leaves the project root out', () => {
    expect(s.wbs.find((w) => w.parentId === null)?.shortName).toBe('BLD-A');
    expect(s.tasks.find((t) => t.code === 'A1220')!.wbsPath).toEqual(['L01', 'MEP']);
    expect(s.tasks.find((t) => t.code === 'A1100')!.wbsPath).toEqual(['L00', 'STR']);
    expect(s.tasks.find((t) => t.code === 'M1040')!.wbsPath).toEqual(['EXT', 'FAC']);
    expect(s.tasks.find((t) => t.code === 'A1020')!.wbsPath).toEqual(['PRE']);
  });

  it('reads activity codes by type name, and lists the values of each type', () => {
    const t = s.tasks.find((x) => x.code === 'A1220')!;
    expect(t.codes).toEqual({ Level: 'L01', Area: 'A', Trade: 'MEP' });
    expect(s.codeTypes.Level).toEqual(['SITE', 'L00', 'L01', 'L02', 'ROOF', 'EXT']);
    expect(s.codeTypes.Trade).toHaveLength(6);
  });

  it('reads the activity user field and not the project one', () => {
    expect(s.udfLabels).toEqual(['Crew Size']);
    expect(s.tasks.find((x) => x.code === 'A1100')!.udfs).toEqual({ 'Crew Size': 6 });
    expect(s.tasks.find((x) => x.code === 'A1000')!.udfs).toEqual({ 'Crew Size': 4 });
    for (const t of s.tasks) expect(Object.keys(t.udfs)).not.toContain('Client Reference');
    expect(s.tasks.filter((x) => x.udfs['Crew Size'] !== undefined)).toHaveLength(31);
  });

  it('reads relations with their types and lags, and drops none', () => {
    expect(s.relations).toHaveLength(38);
    expect(s.relations.filter((r) => r.type === 'SS')).toHaveLength(9);
    expect(s.relations.filter((r) => r.type === 'FF')).toHaveLength(1);
    const a1220 = s.tasks.find((x) => x.code === 'A1220')!;
    expect(s.relations.find((r) => r.taskId === a1220.id)).toEqual({ taskId: a1220.id, predecessorId: s.tasks.find((x) => x.code === 'A1210')!.id, type: 'FS', lagHours: 16 });
    expect(s.relations.find((r) => r.taskId === s.tasks.find((x) => x.code === 'A1215')!.id)).toMatchObject({ type: 'SS', lagHours: 80 });
  });

  it('reads the calendars: working week, split days, holidays and part days', () => {
    const std = s.calendars.find((c) => c.id === '1')!;
    expect(std.name).toBe('Standard 5 Day');
    expect(std.hoursPerDay).toBe(8);
    expect(std.week[0]).toEqual([]);
    expect(std.week[1]).toEqual([[8, 12], [13, 17]]);
    expect(std.week[6]).toEqual([]);
    expect(std.exceptions['2026-12-25']).toEqual([]);
    expect(std.exceptions['2027-01-01']).toEqual([]);
    expect(std.exceptions['2026-12-24']).toEqual([[8, 12]]);
    const site = s.calendars.find((c) => c.id === '2')!;
    expect(site.week[6]).toEqual([[7, 12], [12.5, 15.5]]);
  });

  it('reads the milestone and activity codes of an activity without a value as absent', () => {
    expect(s.tasks.find((x) => x.code === 'M1010')!.codes.Trade).toBe('GEN');
    expect(s.tasks.find((x) => x.code === 'S1000')!.type).toBe('wbsSummary');
  });
});

describe('field lookup by name', () => {
  it('reads columns in any order and ignores unknown ones; missing fields are fine', () => {
    const text = xer([
      { name: 'PROJECT', fields: ['clndr_id', 'proj_short_name', 'proj_id', 'last_recalc_date', 'unknown_field'], rows: [{ clndr_id: '1', proj_short_name: 'X', proj_id: '7', last_recalc_date: '2027-03-14 08:00', unknown_field: 'z' }] },
      { name: 'PROJWBS', fields: ['proj_node_flag', 'wbs_short_name', 'wbs_id', 'proj_id'], rows: [{ proj_node_flag: 'Y', wbs_short_name: 'X', wbs_id: '1', proj_id: '7' }, { proj_node_flag: 'N', wbs_short_name: 'L1', wbs_id: '2', proj_id: '7' }] },
      { name: 'TASK', fields: ['task_name', 'wbs_id', 'proj_id', 'task_code', 'task_id', 'task_type'], rows: [{ task_name: 'Pour', wbs_id: '2', proj_id: '7', task_code: 'A1', task_id: '11', task_type: 'TT_Task' }] },
    ]);
    const s = parseXer(text);
    expect(s.project).toMatchObject({ id: '7', shortName: 'X', dataDate: '2027-03-14T08:00' });
    expect(s.tasks).toEqual([expect.objectContaining({ code: 'A1', name: 'Pour', status: 'notStarted', type: 'task', wbsPath: ['L1'], dates: {} })]);
    expect(s.warnings).toEqual([]);
  });
});

describe('dates', () => {
  it('turns P6 dates into ISO local, date-only as midnight, and warns about bad ones', () => {
    const text = xer([
      { name: 'PROJECT', fields: ['proj_id', 'proj_short_name', 'last_recalc_date'], rows: [project('1', 'P', '2027-02-28 17:30')] },
      { name: 'TASK', fields: ['task_id', 'proj_id', 'task_code', 'early_start_date', 'early_end_date', 'act_start_date'], rows: [
        { task_id: '1', proj_id: '1', task_code: 'A', early_start_date: '2027-03-01', early_end_date: '2027-02-31 08:00', act_start_date: '2027-03-01 08:00:00' },
      ] },
    ]);
    const s = parseXer(text);
    expect(s.project.dataDate).toBe('2027-02-28T17:30');
    expect(s.tasks[0]!.dates).toEqual({ earlyStart: '2027-03-01T00:00', actualStart: '2027-03-01T08:00' });
    expect(s.warnings.join('\n')).toMatch(/impossible date "2027-02-31 08:00"/);
  });
});

describe('WBS and project shape', () => {
  it('keeps a task directly under the project root with an empty path, and warns about a WBS that is missing', () => {
    const text = xer([
      { name: 'PROJECT', fields: ['proj_id', 'proj_short_name'], rows: [{ proj_id: '1', proj_short_name: 'P' }] },
      { name: 'PROJWBS', fields: ['wbs_id', 'proj_id', 'parent_wbs_id', 'wbs_short_name', 'proj_node_flag'], rows: [wbsRoot('10', '1', 'ROOT')] },
      { name: 'TASK', fields: ['task_id', 'proj_id', 'wbs_id', 'task_code'], rows: [{ task_id: '1', proj_id: '1', wbs_id: '10', task_code: 'A' }, { task_id: '2', proj_id: '1', wbs_id: '99', task_code: 'B' }] },
    ]);
    const s = parseXer(text);
    expect(s.tasks.find((t) => t.code === 'A')!.wbsPath).toEqual([]);
    expect(s.tasks.find((t) => t.code === 'B')!.wbsPath).toEqual([]);
    expect(s.warnings.join('\n')).toMatch(/activity B has a WBS that is not in this project/);
  });
});

describe('choosing a project', () => {
  const two = parseXer(fixture('two-projects.xer'), { project: 'BLD-B' });

  it('throws with the list of projects when the file holds several and none is chosen', () => {
    expect(() => parseXer(fixture('two-projects.xer'))).toThrow(/2 projects.*BLD-A, BLD-B/);
  });
  it('reads the chosen project only: its activities, WBS and relations', () => {
    expect(two.project).toMatchObject({ shortName: 'BLD-B', dataDate: '2027-03-05T17:00' });
    expect(two.projects.map((p) => p.shortName)).toEqual(['BLD-A', 'BLD-B']);
    expect(two.tasks.map((t) => t.code)).toEqual(['B1000', 'B1010', 'B1020', 'BM100']);
    expect(two.wbs.every((w) => w.id.startsWith('5'))).toBe(true);
    expect(two.relations).toHaveLength(3);
    expect(two.tasks.find((t) => t.code === 'B1010')!.wbsPath).toEqual(['L00', 'STR']);
  });
  it('matches the short name without regard to case', () => {
    expect(parseXer(fixture('two-projects.xer'), { project: 'bld-b' }).project.shortName).toBe('BLD-B');
  });
  it('throws for a name that is not in the file, listing the projects', () => {
    expect(() => parseXer(fixture('two-projects.xer'), { project: 'NOPE' })).toThrow(/"NOPE" is not in this file. Projects: BLD-A, BLD-B/);
  });
  it('uses the only project of a single-project file', () => {
    expect(parseXer(fixture('building.xer')).project.shortName).toBe('BLD-A');
    expect(() => parseXer(fixture('building.xer'), { project: 'BLD-Z' })).toThrow(/not in this file/);
  });
  it('drops a relation whose predecessor is in another project, with a warning', () => {
    const text = xer([
      { name: 'PROJECT', fields: ['proj_id', 'proj_short_name'], rows: [{ proj_id: '1', proj_short_name: 'P' }, { proj_id: '2', proj_short_name: 'Q' }] },
      { name: 'TASK', fields: ['task_id', 'proj_id', 'task_code'], rows: [{ task_id: '1', proj_id: '1', task_code: 'A' }, { task_id: '2', proj_id: '2', task_code: 'Z' }] },
      { name: 'TASKPRED', fields: ['task_id', 'pred_task_id', 'pred_type', 'lag_hr_cnt'], rows: [{ task_id: '1', pred_task_id: '2', pred_type: 'PR_FS', lag_hr_cnt: '0' }] },
    ]);
    const s = parseXer(text, { project: 'P' });
    expect(s.relations).toEqual([]);
    expect(s.warnings.join('\n')).toMatch(/outside this project/);
  });
});

describe('codes, user fields and relation types', () => {
  it('reads activity codes, user fields of other tables, and TASKACTV rows of other projects are ignored', () => {
    const text = xer([
      { name: 'PROJECT', fields: ['proj_id', 'proj_short_name'], rows: [{ proj_id: '1', proj_short_name: 'P' }] },
      { name: 'TASK', fields: ['task_id', 'proj_id', 'task_code'], rows: [{ task_id: '1', proj_id: '1', task_code: 'A' }] },
      { name: 'ACTVTYPE', fields: ['actv_code_type_id', 'actv_code_type'], rows: [{ actv_code_type_id: '5', actv_code_type: 'Phase' }] },
      { name: 'ACTVCODE', fields: ['actv_code_id', 'actv_code_type_id', 'short_name', 'actv_code_name'], rows: [
        { actv_code_id: '50', actv_code_type_id: '5', short_name: 'FND', actv_code_name: 'Foundations' },
        { actv_code_id: '51', actv_code_type_id: '999', short_name: 'X', actv_code_name: 'Orphan' },
      ] },
      { name: 'TASKACTV', fields: ['task_id', 'actv_code_id'], rows: [{ task_id: '1', actv_code_id: '50' }, { task_id: '1', actv_code_id: '51' }] },
      { name: 'UDFTYPE', fields: ['udf_type_id', 'table_name', 'udf_type_label'], rows: [{ udf_type_id: '1', table_name: 'TASK', udf_type_label: 'Fire Rating' }, { udf_type_id: '2', table_name: 'PROJECT', udf_type_label: 'Ref' }] },
      { name: 'UDFVALUE', fields: ['udf_type_id', 'fk_id', 'udf_text', 'udf_number'], rows: [{ udf_type_id: '1', fk_id: '1', udf_text: 'REI 60', udf_number: '' }, { udf_type_id: '2', fk_id: '1', udf_text: 'ignored', udf_number: '' }] },
      { name: 'TASKPRED', fields: ['task_id', 'pred_task_id', 'pred_type', 'lag_hr_cnt'], rows: [{ task_id: '1', pred_task_id: '1', pred_type: 'PR_SF', lag_hr_cnt: '-8' }, { task_id: '1', pred_task_id: '1', pred_type: 'PR_XX', lag_hr_cnt: '' }] },
    ]);
    const s = parseXer(text);
    expect(s.tasks[0]!.codes).toEqual({ Phase: 'FND' });
    expect(s.codeTypes).toEqual({ Phase: ['FND'] });
    expect(s.tasks[0]!.udfs).toEqual({ 'Fire Rating': 'REI 60' });
    expect(s.udfLabels).toEqual(['Fire Rating']);
    expect(s.relations.map((r) => [r.type, r.lagHours])).toEqual([['SF', -8], ['FS', 0]]);
    expect(s.warnings.join('\n')).toMatch(/unknown relation type "PR_XX"/);
  });
});

describe('statuses and types when the data is odd', () => {
  it('derives the status from the actual dates when the code is missing and keeps unknown types as other, with warnings', () => {
    const text = xer([
      { name: 'PROJECT', fields: ['proj_id', 'proj_short_name'], rows: [{ proj_id: '1', proj_short_name: 'P' }] },
      { name: 'TASK', fields: ['task_id', 'proj_id', 'task_code', 'task_type', 'status_code', 'act_start_date', 'act_end_date', 'phys_complete_pct'], rows: [
        { task_id: '1', proj_id: '1', task_code: 'A', task_type: 'TT_Task', status_code: '', act_start_date: '', act_end_date: '2027-01-01 17:00', phys_complete_pct: '120' },
        { task_id: '2', proj_id: '1', task_code: 'B', task_type: 'TT_Odd', status_code: 'TK_Maybe', act_start_date: '2027-01-02 08:00', act_end_date: '', phys_complete_pct: 'n/a' },
      ] },
    ]);
    const s = parseXer(text);
    const a = s.tasks.find((t) => t.code === 'A')!;
    const b = s.tasks.find((t) => t.code === 'B')!;
    expect(a.status).toBe('complete');
    expect(a.percentComplete).toBe(100);
    expect(b.type).toBe('other');
    expect(b.status).toBe('active');
    expect(s.warnings.join('\n')).toMatch(/unknown task type "TT_Odd"/);
    expect(s.warnings.join('\n')).toMatch(/unknown status "TK_Maybe"/);
    expect(s.warnings.join('\n')).toMatch(/unreadable number "n\/a"/);
  });

  it('keeps the first of a duplicate activity, warns, and records extra values per row', () => {
    const text = xer([
      { name: 'PROJECT', fields: ['proj_id', 'proj_short_name'], rows: [{ proj_id: '1', proj_short_name: 'P' }] },
      { name: 'TASK', fields: ['task_id', 'proj_id', 'task_code'], rows: [{ task_id: '1', proj_id: '1', task_code: 'A' }, { task_id: '1', proj_id: '1', task_code: 'A2' }] },
    ]).replace('%R\t1\t1\tA\r\n', '%R\t1\t1\tA\textra\r\n');
    const s = parseXer(text);
    expect(s.tasks.map((t) => t.code)).toEqual(['A']);
    expect(s.warnings.join('\n')).toMatch(/task_id 1 \(A2\) appears twice/);
    expect(s.warnings.join('\n')).toMatch(/extra values/);
  });

  it('ignores tables it does not know', () => {
    const text = xer([
      { name: 'PROJECT', fields: ['proj_id', 'proj_short_name'], rows: [{ proj_id: '1', proj_short_name: 'P' }] },
      { name: 'XYZ_CUSTOM', fields: ['a'], rows: [{ a: 'b' }] },
    ]);
    expect(parseXer(text).warnings).toEqual(['project P has no activities']);
  });
});

describe('not an XER', () => {
  it('throws for a file without the header', () => {
    expect(() => parseXer('hello\tworld\n')).toThrow(/not an XER file/);
    expect(() => parseXer(new TextEncoder().encode('%T\tPROJECT\n'))).toThrow(/not an XER file/);
  });
  it('throws for a header with no PROJECT table', () => {
    expect(() => parseXer('ERMHDR\t20.12\n%T\tTASK\n%F\ttask_id\n%E\n')).toThrow(/no PROJECT table/);
  });
});

describe('calendar data', () => {
  it('reads the week, the exceptions (holidays and part days) and tolerates spacing', () => {
    const data = '(0||CalendarData()( (0||DaysOfWeek()( (0||1()()) (0||2()( (0||0(s|08:00|f|12:00)()) (0||1(s|13:00|f|17:00)()))) (0||3()()) (0||4()()) (0||5()()) (0||6()()) (0||7()()) )) (0||Exceptions()( (0||0(d|45291)()) (0||1(d|45292)( (0||0(s|08:00|f|12:00)())) ) )))';
    const p = parseCalendarData(data)!;
    expect(p.days).toBe(7);
    expect(p.week[1]).toEqual([[8, 12], [13, 17]]);
    expect(p.week[0]).toEqual([]);
    expect(p.exceptions).toEqual({ '2023-12-31': [], '2024-01-01': [[8, 12]] });
  });
  it('gives null for data it cannot read, and the fallback is used with a warning', () => {
    expect(parseCalendarData('')).toBeNull();
    expect(parseCalendarData('(0||Other()())')).toBeNull();
    const text = xer([
      { name: 'PROJECT', fields: ['proj_id', 'proj_short_name'], rows: [{ proj_id: '1', proj_short_name: 'P' }] },
      { name: 'CALENDAR', fields: ['clndr_id', 'clndr_name', 'clndr_data'], rows: [{ clndr_id: '1', clndr_name: 'Broken', clndr_data: '(0||CalendarData()(' }] },
    ]);
    const s = parseXer(text);
    const cal = s.calendars[0]!;
    expect(cal.week).toEqual([[], [[8, 17]], [[8, 17]], [[8, 17]], [[8, 17]], [[8, 17]], []]);
    expect(cal.exceptions).toEqual({});
    expect(s.warnings.join('\n')).toMatch(/calendar Broken: clndr_data could not be read; Mon-Fri 08:00-17:00 assumed/);
  });
  it('uses day_hr_cnt for the fallback hours', () => {
    const text = xer([
      { name: 'PROJECT', fields: ['proj_id', 'proj_short_name'], rows: [{ proj_id: '1', proj_short_name: 'P' }] },
      { name: 'CALENDAR', fields: ['clndr_id', 'clndr_name', 'day_hr_cnt', 'clndr_data'], rows: [{ clndr_id: '1', clndr_name: 'Six', day_hr_cnt: '6', clndr_data: '' }] },
    ]);
    const cal = parseXer(text).calendars[0]!;
    expect(cal.hoursPerDay).toBe(6);
    expect(cal.week[1]).toEqual([[8, 14]]);
  });
});
