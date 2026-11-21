// Location, trade and zone: read from a schedule task (FourDConfig.schedule sources), mapped through `values`, and read from a
// model element (FourDConfig.model sources) plus accepted Assignment records. Pure.

import type { Assignment, AttributeKind, FourDConfig, ModelAttrSource, Schedule, ScheduleAttrSource, ScheduleTask } from './types';
import type { FourDElement } from './model';

export interface Attrs { location?: string; trade?: string; zone?: string }

const KINDS: AttributeKind[] = ['location', 'trade', 'zone'];

// ---------------------------------------------------------------- schedule side

function clean(v: unknown): string | undefined {
  if (v === undefined || v === null) return undefined;
  const s = String(v).trim();
  return s === '' ? undefined : s;
}

function regexOf(pattern: string): RegExp | null {
  try { return new RegExp(pattern); } catch { return null; }
}

function groupOf(m: RegExpExecArray, group: number | undefined): string | undefined {
  return clean(m[group ?? (m.length > 1 ? 1 : 0)]);
}

/** The raw value of one source for a task, or undefined. */
export function readTaskSource(task: ScheduleTask, src: ScheduleAttrSource): string | undefined {
  if ('code' in src) return clean(task.codes[src.code]);
  if ('udf' in src) return clean(task.udfs[src.udf]);
  if ('wbsLevel' in src) return clean(task.wbsPath[src.wbsLevel]);
  if ('wbsPattern' in src) {
    const re = regexOf(src.wbsPattern);
    const m = re?.exec(task.wbsPath.join('/'));
    return m ? groupOf(m, src.group) : undefined;
  }
  const re = regexOf(src.namePattern);
  const m = re?.exec(task.name);
  return m ? groupOf(m, src.group) : undefined;
}

/** First source with a value wins. */
export function readTaskAttr(task: ScheduleTask, sources: ScheduleAttrSource[] | undefined): string | undefined {
  for (const s of sources ?? []) {
    const v = readTaskSource(task, s);
    if (v !== undefined) return v;
  }
  return undefined;
}

/**
 * Map a schedule value through a `values` table: an exact key first (then the same key ignoring case), then the keys written
 * /regex/ (or /regex/flags) in table order, with $1..$9 and $& substituted into the target. No hit: the value itself.
 */
export function mapValue(raw: string | undefined, table: Record<string, string> | undefined): string | undefined {
  if (raw === undefined || !table) return raw;
  if (Object.prototype.hasOwnProperty.call(table, raw)) return table[raw]!;
  const lower = raw.toLowerCase();
  for (const k in table) if (!isRegexKey(k) && k.toLowerCase() === lower) return table[k]!;
  for (const k in table) {
    const m = isRegexKey(k);
    if (!m) continue;
    let hit: RegExpExecArray | null = null;
    try { hit = new RegExp(m.source, m.flags.replace(/[gy]/g, '')).exec(raw); } catch { /* bad key: skipped */ }
    if (hit) return table[k]!.replace(/\$(\d|&)/g, (_s, g: string) => (g === '&' ? hit[0] : hit[Number(g)] ?? ''));
  }
  return raw;
}

function isRegexKey(k: string): { source: string; flags: string } | null {
  const m = /^\/(.+)\/([a-z]*)$/s.exec(k);
  return m ? { source: m[1]!, flags: m[2]! } : null;
}

/** A task's location, trade and zone: sources, then `values`. */
export function taskAttributes(task: ScheduleTask, config: FourDConfig): Attrs {
  const s = config.schedule;
  const v = config.values ?? {};
  const out: Attrs = {};
  const loc = mapValue(readTaskAttr(task, s.location), v.location);
  const trade = mapValue(readTaskAttr(task, s.trade), v.trade);
  const zone = mapValue(readTaskAttr(task, s.zone), v.zone);
  if (loc !== undefined) out.location = loc;
  if (trade !== undefined) out.trade = trade;
  if (zone !== undefined) out.zone = zone;
  return out;
}

/** Same, with the raw (unmapped) values, for reasons text. */
export function taskRawAttributes(task: ScheduleTask, config: FourDConfig): Attrs {
  const s = config.schedule;
  const out: Attrs = {};
  const loc = readTaskAttr(task, s.location);
  const trade = readTaskAttr(task, s.trade);
  const zone = readTaskAttr(task, s.zone);
  if (loc !== undefined) out.location = loc;
  if (trade !== undefined) out.trade = trade;
  if (zone !== undefined) out.zone = zone;
  return out;
}

/** Where a task attribute came from, for reasons ('code Level', 'udf Area', 'WBS level 1', ...). */
export function describeSource(task: ScheduleTask, sources: ScheduleAttrSource[] | undefined): string {
  for (const s of sources ?? []) {
    if (readTaskSource(task, s) === undefined) continue;
    if ('code' in s) return `code ${s.code}`;
    if ('udf' in s) return `udf ${s.udf}`;
    if ('wbsLevel' in s) return `WBS level ${s.wbsLevel}`;
    if ('wbsPattern' in s) return 'WBS pattern';
    return 'activity name pattern';
  }
  return 'none';
}

/** Attributes of every task by task code. */
export function scheduleAttributes(schedule: Schedule, config: FourDConfig): Map<string, Attrs> {
  const m = new Map<string, Attrs>();
  for (const t of schedule.tasks) m.set(t.code, taskAttributes(t, config));
  return m;
}

// ---------------------------------------------------------------- model side

function readProp(props: Record<string, string>, key: string): string | undefined {
  const direct = clean(props[key]);
  if (direct !== undefined) return direct;
  const l = key.toLowerCase();
  for (const k in props) if (k.toLowerCase() === l) return clean(props[k]);
  return undefined;
}

export function readElementSource(el: FourDElement, src: ModelAttrSource): string | undefined {
  if ('property' in src) return readProp(el.props, src.property);
  if ('storey' in src) return clean(el.storey);
  if ('zone' in src) return clean(el.zone);
  return clean(el.discipline);
}

export function readElementAttr(el: FourDElement, sources: ModelAttrSource[] | undefined): string | undefined {
  for (const s of sources ?? []) {
    const v = readElementSource(el, s);
    if (v !== undefined) return v;
  }
  return undefined;
}

/** The accepted assignments by element then attribute. A later accepted row (by created_at, else list order) replaces an earlier. */
export function acceptedAssignments(assignments: readonly Assignment[] | undefined): Map<string, Partial<Record<AttributeKind, Assignment>>> {
  const out = new Map<string, Partial<Record<AttributeKind, Assignment>>>();
  for (const a of assignments ?? []) {
    if (a.status !== 'accepted') continue;
    if (!KINDS.includes(a.attribute)) continue;
    if (clean(a.value) === undefined) continue;
    const slot = out.get(a.element) ?? {};
    const prev = slot[a.attribute];
    if (!prev || (a.created_at ?? '') >= (prev.created_at ?? '')) slot[a.attribute] = a;
    out.set(a.element, slot);
  }
  return out;
}

/** An element's location, trade and zone: accepted assignments win over the model properties. */
export function elementAttributes(el: FourDElement, config: FourDConfig, accepted?: Map<string, Partial<Record<AttributeKind, Assignment>>>): Attrs {
  const m = config.model;
  const out: Attrs = {};
  const a = accepted?.get(el.globalId);
  for (const kind of KINDS) {
    const assigned = clean(a?.[kind]?.value);
    const v = assigned ?? readElementAttr(el, kind === 'location' ? m.location : kind === 'trade' ? m.trade : m.zone);
    if (v !== undefined) out[kind] = v;
  }
  return out;
}

/** Equality of attribute values: trimmed, case-insensitive. */
export const sameValue = (a: string | undefined, b: string | undefined): boolean =>
  a !== undefined && b !== undefined && a.trim().toLowerCase() === b.trim().toLowerCase();
