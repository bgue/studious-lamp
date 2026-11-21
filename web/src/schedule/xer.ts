// Primavera P6 XER export -> Schedule (the contract in ./types.ts). Pure: no DOM, no fs, no async.
// Format: an `ERMHDR` header line, then per table `%T <name>`, `%F <field names>`, `%R <values>` rows and `%E`.
// Fields are looked up by name, so the column order of a P6 version does not matter. Data problems go to `warnings`;
// only a file that is not an XER, a file without a PROJECT table, and a project choice that cannot be made throw.
// Design: docs/design/4d-xer-animation.md (section 2). Usage and the fields read: web/docs-features/xray-4d.md.

import { sha256Hex } from './sha256';
import type {
  RelationType, Schedule, ScheduleCalendar, ScheduleProject, ScheduleRelation, ScheduleTask, ScheduleWbs, TaskStatus, TaskType,
} from './types';

export interface ParseXerOptions {
  /** Short name of the project to read, when the file holds several. */
  project?: string;
}

export type XerEncoding = 'utf-8' | 'windows-1252' | 'text';

export interface DecodedXer {
  text: string;
  encoding: XerEncoding;
  bom: boolean;
}

/** A parenthesised calendar group: its own text (outside child groups) and the raw source including children. */
export interface CalendarGroup {
  text: string;
  raw: string;
  children: CalendarGroup[];
}

export interface ParsedCalendarData {
  /** Working hours per weekday, Sunday first; [startHour, endHour] pairs with decimal hours. */
  week: Array<Array<[number, number]>>;
  /** Exception hours by ISO date (empty = holiday). */
  exceptions: Record<string, Array<[number, number]>>;
  /** Number of weekday entries that were read (0 means nothing usable). */
  days: number;
}

type Row = Record<string, string>;
interface Table {
  name: string;
  fields: string[];
  rows: Row[];
}

// ---------------------------------------------------------------- bytes and text

/** Windows-1252 code points for bytes 0x80..0x9F (the other bytes map to the same code point). Written out here because
 *  TextDecoder('windows-1252') is not reliable across runtimes (node returns the C1 controls for these bytes). */
const CP1252_HIGH = [
  0x20ac, 0x0081, 0x201a, 0x0192, 0x201e, 0x2026, 0x2020, 0x2021, 0x02c6, 0x2030, 0x0160, 0x2039, 0x0152, 0x008d, 0x017d, 0x008f,
  0x0090, 0x2018, 0x2019, 0x201c, 0x201d, 0x2022, 0x2013, 0x2014, 0x02dc, 0x2122, 0x0161, 0x203a, 0x0153, 0x009d, 0x017e, 0x0178,
];

function decodeWindows1252(bytes: Uint8Array): string {
  const chunks: string[] = [];
  const CHUNK = 8192;
  for (let i = 0; i < bytes.length; i += CHUNK) {
    const codes: number[] = [];
    for (let k = i; k < Math.min(bytes.length, i + CHUNK); k++) {
      const b = bytes[k]!;
      codes.push(b >= 0x80 && b <= 0x9f ? CP1252_HIGH[b - 0x80]! : b);
    }
    chunks.push(String.fromCharCode(...codes));
  }
  return chunks.join('');
}

/** Text of an XER file: UTF-8 when the bytes are valid UTF-8, else Windows-1252 (what P6 writes). A byte order mark is removed. */
export function decodeXer(input: string | Uint8Array): DecodedXer {
  if (typeof input === 'string') return { text: input.replace(/^﻿/, ''), encoding: 'text', bom: input.startsWith('﻿') };
  let bytes = input;
  const bom = bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf;
  if (bom) bytes = bytes.subarray(3);
  try {
    return { text: new TextDecoder('utf-8', { fatal: true }).decode(bytes), encoding: 'utf-8', bom };
  } catch {
    return { text: decodeWindows1252(bytes), encoding: 'windows-1252', bom };
  }
}

/** Groups the warnings by kind: the first message of a kind, with how many more there were. */
class Issues {
  private seen = new Map<string, { count: number; first: string }>();
  add(kind: string, message: string): void {
    const e = this.seen.get(kind);
    if (e) e.count++;
    else this.seen.set(kind, { count: 1, first: message });
  }
  list(): string[] {
    return [...this.seen.values()].map((e) => (e.count > 1 ? `${e.first} (and ${e.count - 1} more)` : e.first));
  }
}

// ---------------------------------------------------------------- tables

function readTables(text: string, issues: Issues): Map<string, Table> {
  const lines = text.split('\n');
  let i = 0;
  while (i < lines.length && lines[i]!.trim() === '') i++;
  if (!(lines[i] ?? '').replace(/\r$/, '').startsWith('ERMHDR')) {
    throw new Error('not an XER file: the first line is not an ERMHDR header');
  }
  const tables = new Map<string, Table>();
  let cur: Table | null = null;
  for (; i < lines.length; i++) {
    const line = lines[i]!.replace(/\r$/, '');
    if (line.trim() === '') continue;
    const cells = line.split('\t');
    switch (cells[0]) {
      case '%T': {
        const name = (cells[1] ?? '').trim();
        if (tables.has(name)) {
          issues.add('duplicate table', `table ${name} appears twice; the second copy is ignored`);
          cur = { name, fields: [], rows: [] }; // detached: its rows are dropped
        } else {
          cur = { name, fields: [], rows: [] };
          tables.set(name, cur);
        }
        break;
      }
      case '%F':
        if (cur) cur.fields = cells.slice(1).map((s) => s.trim());
        break;
      case '%R': {
        if (!cur || cur.fields.length === 0) break;
        const row: Row = {};
        cur.fields.forEach((f, k) => {
          row[f] = cells[k + 1] ?? '';
        });
        if (cells.slice(cur.fields.length + 1).some((s) => s !== '')) {
          issues.add('extra values', `${cur.name}: rows with more values than fields (extra values ignored)`);
        }
        cur.rows.push(row);
        break;
      }
      case '%E':
        cur = null;
        break;
      default:
        break;
    }
  }
  return tables;
}

// ---------------------------------------------------------------- values

const v = (r: Row, field: string): string => r[field] ?? '';

function numOf(s: string, issues: Issues, where: string): number | undefined {
  if (s.trim() === '') return undefined;
  const n = Number(s);
  if (Number.isFinite(n)) return n;
  issues.add('unreadable number', `unreadable number "${s}" in ${where}`);
  return undefined;
}

const DATE_RE = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{1,2}):(\d{2})(?::\d{2}(?:\.\d+)?)?)?$/;

/** P6 date ('2027-03-14 08:00') to ISO local ('2027-03-14T08:00'). Empty gives undefined; a date without a time gets 00:00. */
function isoDate(s: string, issues: Issues, where: string): string | undefined {
  if (s.trim() === '') return undefined;
  const m = DATE_RE.exec(s.trim());
  const hh = Number(m?.[4] ?? 0);
  const mm = Number(m?.[5] ?? 0);
  if (!m || hh > 23 || mm > 59) {
    issues.add('unreadable date', `unreadable date "${s}" in ${where}`);
    return undefined;
  }
  const y = Number(m[1]);
  const mo = Number(m[2]);
  const d = Number(m[3]);
  const check = new Date(Date.UTC(y, mo - 1, d));
  if (check.getUTCMonth() !== mo - 1 || check.getUTCDate() !== d) {
    issues.add('unreadable date', `impossible date "${s}" in ${where}`);
    return undefined;
  }
  return `${m[1]}-${m[2]}-${m[3]}T${String(hh).padStart(2, '0')}:${String(mm).padStart(2, '0')}`;
}

/** Removes keys whose value is undefined, so optional fields are absent rather than undefined. */
function clean<T extends object>(o: T): T {
  const r = o as Record<string, unknown>;
  for (const k of Object.keys(r)) if (r[k] === undefined) delete r[k];
  return o;
}

const TASK_TYPES: Record<string, TaskType> = {
  TT_Task: 'task', TT_Rsrc: 'resource', TT_Mile: 'milestone', TT_FinMile: 'finishMilestone', TT_LOE: 'loe', TT_WBS: 'wbsSummary',
};
const TASK_STATUS: Record<string, TaskStatus> = { TK_NotStart: 'notStarted', TK_Active: 'active', TK_Complete: 'complete' };
const RELATION_TYPES: Record<string, RelationType> = { PR_FS: 'FS', PR_SS: 'SS', PR_FF: 'FF', PR_SF: 'SF' };

// ---------------------------------------------------------------- calendars

/** Parses a P6 `clndr_data` string into groups: each `( ... )` with its own text and its children. Tolerant of damage. */
export function calendarGroups(data: string): CalendarGroup {
  const root: CalendarGroup = { text: '', raw: data, children: [] };
  const stack: Array<{ node: CalendarGroup; start: number }> = [{ node: root, start: 0 }];
  for (let i = 0; i < data.length; i++) {
    const c = data[i]!;
    const top = stack[stack.length - 1]!;
    if (c === '(') {
      const node: CalendarGroup = { text: '', raw: '', children: [] };
      top.node.children.push(node);
      stack.push({ node, start: i });
    } else if (c === ')') {
      if (stack.length > 1) {
        const frame = stack.pop()!;
        frame.node.raw = data.slice(frame.start, i + 1);
      }
    } else {
      top.node.text += c;
    }
  }
  for (const frame of stack.slice(1)) frame.node.raw = data.slice(frame.start);
  return root;
}

function findGroup(node: CalendarGroup, test: (g: CalendarGroup) => boolean): CalendarGroup | undefined {
  for (const ch of node.children) {
    if (test(ch)) return ch;
    const inner = findGroup(ch, test);
    if (inner) return inner;
  }
  return undefined;
}

const DAY_MS = 86400000;
const HOUR_RE = /s\|(\d{1,2}:\d{2})\|f\|(\d{1,2}:\d{2})/g;
const toHours = (hhmm: string): number => {
  const [h, m] = hhmm.split(':');
  return Number(h) + Number(m) / 60;
};
function hoursIn(raw: string, from = 0, to = raw.length): Array<[number, number]> {
  return [...raw.slice(from, to).matchAll(HOUR_RE)].map((m) => [toHours(m[1]!), toHours(m[2]!)] as [number, number]);
}

/** P6 day serial (days since 1899-12-30) to ISO date. */
function dateOfSerial(serial: number): string {
  return new Date(Date.UTC(1899, 11, 30) + Math.floor(serial) * DAY_MS).toISOString().slice(0, 10);
}
/**
 * Reads the working week and the exceptions of a P6 calendar, e.g.
 * `(0||CalendarData()( (0||DaysOfWeek()( (0||1()()) (0||2()( (0||0(s|08:00|f|12:00)()) (0||1(s|13:00|f|17:00)()))) ...))
 *    (0||Exceptions()( (0||0(d|45291)()) ...)))`. Day 1 is Sunday. Returns null when no weekday entry can be read.
 */
export function parseCalendarData(data: string): ParsedCalendarData | null {
  if (data.trim() === '') return null;
  const root = calendarGroups(data);
  const daysNode = findGroup(root, (g) => /DaysOfWeek/.test(g.text));
  if (!daysNode) return null;
  const week: Array<Array<[number, number]>> = [[], [], [], [], [], [], []];
  const seen = new Set<number>();
  // a weekday entry is a group whose text is `<n>||<day 1..7>`; its hour entries sit inside it, so the walk stops there
  const walk = (g: CalendarGroup): void => {
    for (const ch of g.children) {
      const m = /(\d+)\|\|([1-7])$/.exec(ch.text.trim());
      if (m) {
        const idx = Number(m[2]) - 1;
        if (!seen.has(idx)) {
          seen.add(idx);
          week[idx] = hoursIn(ch.raw);
        }
      } else {
        walk(ch);
      }
    }
  };
  walk(daysNode);
  if (seen.size === 0) return null;
  const exceptions: Record<string, Array<[number, number]>> = {};
  const exNode = findGroup(root, (g) => /Exceptions/.test(g.text));
  if (exNode) {
    // each exception starts at `d|<serial>`; its hours are the s|f pairs up to the next exception
    const hits = [...exNode.raw.matchAll(/d\|(\d+(?:\.\d+)?)/g)];
    hits.forEach((hit, k) => {
      const from = hit.index! + hit[0].length;
      const to = k + 1 < hits.length ? hits[k + 1]!.index! : exNode.raw.length;
      exceptions[dateOfSerial(Number(hit[1]))] = hoursIn(exNode.raw, from, to);
    });
  }
  return { week, exceptions, days: seen.size };
}

function calendarOf(r: Row, issues: Issues): ScheduleCalendar {
  const id = v(r, 'clndr_id');
  const name = v(r, 'clndr_name') || id;
  const hpd = numOf(v(r, 'day_hr_cnt'), issues, `calendar ${name}`);
  const cal: ScheduleCalendar = { id, name, week: [], exceptions: {} };
  if (hpd !== undefined && hpd > 0) cal.hoursPerDay = hpd;
  let parsed: ParsedCalendarData | null = null;
  try {
    parsed = parseCalendarData(v(r, 'clndr_data'));
  } catch {
    parsed = null;
  }
  if (parsed) {
    cal.week = parsed.week;
    cal.exceptions = parsed.exceptions;
    return cal;
  }
  // fallback: Mon-Fri from 08:00 for day_hr_cnt hours (17:00 when the count is missing)
  const end = hpd !== undefined && hpd > 0 ? 8 + hpd : 17;
  cal.week = [[], [[8, end]], [[8, end]], [[8, end]], [[8, end]], [[8, end]], []];
  issues.add('calendar fallback', `calendar ${name}: clndr_data could not be read; Mon-Fri 08:00-${end}:00 assumed`);
  return cal;
}

// ---------------------------------------------------------------- the parser

/**
 * Parses a P6 XER export. `project` picks one project by short name when the file holds several; with one project it
 * is used as is. Throws for a file that is not an XER, for a file with no PROJECT table, and for a project choice that
 * cannot be made (the message lists the projects in the file).
 */
export function parseXer(input: string | Uint8Array, opts: ParseXerOptions = {}): Schedule {
  const bytes = typeof input === 'string' ? new TextEncoder().encode(input) : input;
  const { text } = decodeXer(input);
  const issues = new Issues();
  const tables = readTables(text, issues);
  const rows = (name: string): Row[] => tables.get(name)?.rows ?? [];

  // ---- projects
  const projects: ScheduleProject[] = rows('PROJECT').map((r) => {
    const p: ScheduleProject = { id: v(r, 'proj_id'), shortName: v(r, 'proj_short_name') };
    if (v(r, 'proj_name')) p.name = v(r, 'proj_name');
    const dd = isoDate(v(r, 'last_recalc_date'), issues, `project ${p.shortName} last_recalc_date`);
    if (dd) p.dataDate = dd;
    if (v(r, 'clndr_id')) p.calendarId = v(r, 'clndr_id');
    return p;
  });
  if (projects.length === 0) throw new Error('not a usable XER file: it has no PROJECT table');
  const listed = projects.map((p) => p.shortName || p.id).join(', ');
  let project: ScheduleProject | undefined;
  if (opts.project !== undefined) {
    const want = opts.project;
    project = projects.find((p) => p.shortName === want) ?? projects.find((p) => p.shortName.toLowerCase() === want.toLowerCase());
    if (!project) throw new Error(`project "${want}" is not in this file. Projects: ${listed}`);
  } else if (projects.length === 1) {
    project = projects[0];
  } else {
    throw new Error(`this file holds ${projects.length} projects; choose one with --project. Projects: ${listed}`);
  }
  const pid = project!.id;
  const where = `project ${project!.shortName}`;

  // ---- WBS
  const wbsRows = rows('PROJWBS').filter((r) => v(r, 'proj_id') === pid);
  const wbsIds = new Set(wbsRows.map((r) => v(r, 'wbs_id')));
  const rootIds = new Set<string>();
  const wbsById = new Map<string, { parentId: string | null; shortName: string }>();
  const wbs: ScheduleWbs[] = wbsRows.map((r) => {
    const id = v(r, 'wbs_id');
    const parent = v(r, 'parent_wbs_id');
    const isRoot = v(r, 'proj_node_flag') === 'Y';
    if (isRoot) rootIds.add(id);
    let parentId: string | null = parent && wbsIds.has(parent) ? parent : null;
    if (parent && !wbsIds.has(parent)) issues.add('WBS parent missing', `WBS ${v(r, 'wbs_short_name')} points at a parent that is not in this project`);
    if (isRoot) parentId = null;
    wbsById.set(id, { parentId, shortName: v(r, 'wbs_short_name') || id });
    const node: ScheduleWbs = { id, parentId, shortName: v(r, 'wbs_short_name') || id, name: v(r, 'wbs_name') || v(r, 'wbs_short_name') };
    const seq = numOf(v(r, 'seq_num'), issues, `WBS ${node.shortName}`);
    if (seq !== undefined) node.seq = seq;
    return node;
  });
  /** WBS short names from the top WBS under the project down to the node; the project root is not part of it. */
  const wbsPathOf = (wbsId: string): string[] => {
    const path: string[] = [];
    const seen = new Set<string>();
    let id: string | null = wbsId;
    while (id !== null) {
      if (seen.has(id)) {
        issues.add('WBS cycle', `WBS ${wbsId} is in a parent cycle; its path is cut short`);
        break;
      }
      seen.add(id);
      if (rootIds.has(id)) break;
      const node = wbsById.get(id);
      if (!node) break;
      path.unshift(node.shortName);
      id = node.parentId;
    }
    return path;
  };

  // ---- activity codes
  const typeName = new Map<string, string>();
  for (const r of rows('ACTVTYPE')) {
    const owner = v(r, 'proj_id');
    if (owner && owner !== pid) continue;
    typeName.set(v(r, 'actv_code_type_id'), v(r, 'actv_code_type'));
  }
  const codeOf = new Map<string, { type: string; value: string }>();
  const codeTypes: Record<string, string[]> = {};
  for (const r of rows('ACTVCODE')) {
    const type = typeName.get(v(r, 'actv_code_type_id'));
    if (!type) {
      issues.add('activity code type', `activity code ${v(r, 'short_name')} has an unknown code type and is ignored`);
      continue;
    }
    const value = v(r, 'short_name') || v(r, 'actv_code_name');
    codeOf.set(v(r, 'actv_code_id'), { type, value });
    if (!value) continue;
    const list = (codeTypes[type] ??= []);
    if (!list.includes(value)) list.push(value);
  }

  // ---- user fields (TASK only)
  const udfType = new Map<string, { table: string; label: string }>();
  const udfLabels: string[] = [];
  for (const r of rows('UDFTYPE')) {
    const table = v(r, 'table_name');
    const label = v(r, 'udf_type_label');
    udfType.set(v(r, 'udf_type_id'), { table, label });
    if (table === 'TASK' && label && !udfLabels.includes(label)) udfLabels.push(label);
  }

  // ---- tasks
  const taskById = new Map<string, ScheduleTask>();
  const taskRows = rows('TASK').filter((r) => v(r, 'proj_id') === pid);
  for (const r of taskRows) {
    const id = v(r, 'task_id');
    const code = v(r, 'task_code') || id;
    const here = `activity ${code}`;
    if (taskById.has(id)) {
      issues.add('duplicate task', `task_id ${id} (${code}) appears twice; the second copy is ignored`);
      continue;
    }
    const wbsId = v(r, 'wbs_id');
    if (!wbsIds.has(wbsId)) issues.add('task WBS missing', `activity ${code} has a WBS that is not in this project`);
    const typeCode = v(r, 'task_type');
    const type = TASK_TYPES[typeCode];
    if (!type) issues.add('task type', `activity ${code}: unknown task type "${typeCode}" (kept as other)`);
    let status = TASK_STATUS[v(r, 'status_code')];
    const actStart = v(r, 'act_start_date');
    const actEnd = v(r, 'act_end_date');
    if (!status) {
      if (v(r, 'status_code')) issues.add('task status', `activity ${code}: unknown status "${v(r, 'status_code')}"`);
      status = actEnd ? 'complete' : actStart ? 'active' : 'notStarted';
    }
    const d = (field: string): string | undefined => isoDate(v(r, field), issues, `${here} ${field}`);
    const dates: ScheduleTask['dates'] = clean({
      targetStart: d('target_start_date'),
      targetEnd: d('target_end_date'),
      earlyStart: d('early_start_date'),
      earlyEnd: d('early_end_date'),
      lateStart: d('late_start_date'),
      lateEnd: d('late_end_date'),
      actualStart: d('act_start_date'),
      actualEnd: d('act_end_date'),
      remainingStart: d('restart_date'),
      remainingEnd: d('reend_date'),
    });
    const pct = numOf(v(r, 'phys_complete_pct'), issues, here);
    const driving = v(r, 'driving_path_flag');
    const task: ScheduleTask = clean({
      id,
      code,
      name: v(r, 'task_name'),
      wbsId,
      wbsPath: wbsIds.has(wbsId) ? wbsPathOf(wbsId) : [],
      calendarId: v(r, 'clndr_id') || project!.calendarId || '',
      type: type ?? 'other',
      status,
      dates,
      totalFloatHours: numOf(v(r, 'total_float_hr_cnt'), issues, here),
      driving: driving === 'Y' ? true : driving === 'N' ? false : undefined,
      percentComplete: pct === undefined ? undefined : Math.min(100, Math.max(0, pct)),
      codes: {},
      udfs: {},
    });
    taskById.set(id, task);
  }
  if (taskById.size === 0) issues.add('no activities', `${where} has no activities`);

  // activity code assignments
  for (const r of rows('TASKACTV')) {
    const t = taskById.get(v(r, 'task_id'));
    const c = codeOf.get(v(r, 'actv_code_id'));
    if (!t || !c || !c.value) continue;
    if (!Object.hasOwn(t.codes, c.type)) t.codes[c.type] = c.value;
  }
  // user field values
  const udfValues = rows('UDFVALUE');
  for (const r of udfValues) {
    const u = udfType.get(v(r, 'udf_type_id'));
    if (!u || u.table !== 'TASK' || !u.label) continue;
    const t = taskById.get(v(r, 'fk_id'));
    if (!t) continue;
    const text = v(r, 'udf_text');
    const num = v(r, 'udf_number');
    const date = v(r, 'udf_date');
    if (text !== '') t.udfs[u.label] = text;
    else if (num !== '' && Number.isFinite(Number(num))) t.udfs[u.label] = Number(num);
    else if (date !== '') {
      const iso = isoDate(date, issues, `user field ${u.label}`);
      if (iso) t.udfs[u.label] = iso;
    }
  }

  // ---- relations
  const relations: ScheduleRelation[] = [];
  for (const r of rows('TASKPRED')) {
    const taskId = v(r, 'task_id');
    if (!taskById.has(taskId)) continue;
    const predId = v(r, 'pred_task_id');
    if (!taskById.has(predId)) {
      issues.add('relation outside project', `a relation of activity ${taskById.get(taskId)!.code} comes from a task outside this project; it is dropped`);
      continue;
    }
    const pt = v(r, 'pred_type');
    let type = RELATION_TYPES[pt];
    if (!type) {
      issues.add('relation type', `unknown relation type "${pt}" (treated as FS)`);
      type = 'FS';
    }
    relations.push({ taskId, predecessorId: predId, type, lagHours: numOf(v(r, 'lag_hr_cnt'), issues, 'relation') ?? 0 });
  }

  // ---- calendars (project-specific ones, or all shared ones)
  const calendars: ScheduleCalendar[] = rows('CALENDAR')
    .filter((r) => !v(r, 'proj_id') || v(r, 'proj_id') === pid)
    .map((r) => calendarOf(r, issues));

  const schedule: Schedule = {
    schema: 'xray-schedule/1',
    sourceHash: sha256Hex(bytes),
    project: project!,
    projects,
    calendars,
    wbs,
    tasks: [...taskById.values()],
    relations,
    codeTypes,
    udfLabels,
    warnings: issues.list(),
  };
  return schedule;
}
