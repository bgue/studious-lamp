// The 4D mapping tool's assignment records: pure functions over `Assignment` (src/schedule/types.ts, schema/linkml/xray_4d.yaml).
// An assignment gives one element one value of one attribute (location, trade or zone). For each element and attribute at most one
// accepted record is current; a newer accepted record supersedes the older one (the older one stays in the list as history).
// Proposed, rejected and superseded records never drive the 4D plan and are never written into the IFC. No DOM, no three.js.
// Tested in tests/map4d-assignments.test.ts.

import type { Assignment, AttributeKind, LinkSource, ReviewStatus } from '../schedule/types';

export const ATTRIBUTES: readonly AttributeKind[] = ['location', 'trade', 'zone'];
export const ATTRIBUTE_LABEL: Record<AttributeKind, string> = { location: 'Location', trade: 'Trade', zone: 'Zone' };

/** The accepted values of one element. */
export type ElementValues = Partial<Record<AttributeKind, string>>;

let counter = 0;
/** A fresh record key: time, a counter and a random tail. Unique across sessions and tools. */
export function newId(): string {
  counter = (counter + 1) % 1679616;
  const rnd = Math.floor(Math.random() * 1679616).toString(36).padStart(4, '0');
  return `m4-${Date.now().toString(36)}${counter.toString(36).padStart(2, '0')}${rnd}`;
}

/** When a record was last decided: `reviewed_at`, else `created_at`; 0 when it has neither. */
export function timeOf(a: Pick<Assignment, 'reviewed_at' | 'created_at'>): number {
  const t = Date.parse(a.reviewed_at ?? a.created_at ?? '');
  return Number.isFinite(t) ? t : 0;
}

export const keyOf = (a: Pick<Assignment, 'element' | 'attribute'>): string => `${a.element}|${a.attribute}`;

/** Mark all but the newest accepted record of each element and attribute as superseded. Ties go to the later record. Returns a new list. */
export function normalise(list: readonly Assignment[]): Assignment[] {
  const winner = new Map<string, number>();
  for (let i = 0; i < list.length; i++) {
    const a = list[i]!;
    if (a.status !== 'accepted') continue;
    const k = keyOf(a);
    const w = winner.get(k);
    if (w === undefined || timeOf(a) >= timeOf(list[w]!)) winner.set(k, i);
  }
  return list.map((a, i) => (a.status === 'accepted' && winner.get(keyOf(a)) !== i ? { ...a, status: 'superseded' as ReviewStatus } : a));
}

export interface MergeResult {
  list: Assignment[];
  /** Incoming records with a new id. */
  added: number;
  /** Records of the existing list that an incoming record replaced (same id, newer). */
  updated: number;
  /** Records that became superseded because of the merge. */
  superseded: number;
}

/**
 * Add `incoming` to `existing`. A record with a known id replaces the old one when it is newer. Then the newest accepted record of
 * each element and attribute stays accepted and the rest are superseded: an older accepted record in `incoming` is stored as superseded.
 */
export function mergeAssignments(existing: readonly Assignment[], incoming: readonly Assignment[]): MergeResult {
  const out = existing.slice();
  const at = new Map<string, number>();
  out.forEach((a, i) => at.set(a.id, i));
  let added = 0;
  let updated = 0;
  for (const a of incoming) {
    const i = at.get(a.id);
    if (i === undefined) {
      at.set(a.id, out.length);
      out.push(a);
      added++;
    } else if (timeOf(a) > timeOf(out[i]!)) {
      out[i] = a;
      updated++;
    }
  }
  const before = new Map(existing.map((a) => [a.id, a.status] as const));
  const list = normalise(out);
  let superseded = 0;
  for (const a of list) if (a.status === 'superseded' && before.get(a.id) !== 'superseded') superseded++;
  return { list, added, updated, superseded };
}

/** The current accepted values by GlobalId. */
export function acceptedValues(list: readonly Assignment[]): Map<string, ElementValues> {
  const out = new Map<string, ElementValues>();
  for (const a of list) {
    if (a.status !== 'accepted') continue;
    let v = out.get(a.element);
    if (!v) out.set(a.element, (v = {}));
    v[a.attribute] = a.value;
  }
  return out;
}

export interface MakeOptions {
  source?: LinkSource;
  status?: ReviewStatus;
  confidence?: number;
  reasons?: string[];
  now?: string;
  idGen?: () => string;
}

/** New records of one value for many elements. Accepted ones carry `reviewed_at` (never `reviewed_by`: that stays out unless a person opts in). */
export function makeAssignments(globalIds: Iterable<string>, attribute: AttributeKind, value: string, o: MakeOptions = {}): Assignment[] {
  const now = o.now ?? new Date().toISOString();
  const status = o.status ?? 'accepted';
  const id = o.idGen ?? newId;
  const out: Assignment[] = [];
  for (const element of globalIds) {
    out.push({
      id: id(), element, attribute, value, source: o.source ?? 'manual', status, created_at: now,
      ...(o.confidence !== undefined ? { confidence: o.confidence } : {}),
      ...(o.reasons && o.reasons.length ? { reasons: o.reasons } : {}),
      ...(status === 'accepted' ? { reviewed_at: now } : {}),
    });
  }
  return out;
}

export interface AssignResult { list: Assignment[]; assigned: number; unchanged: number }

/** Give elements an accepted value. An element that already has that value is left alone. */
export function assign(list: readonly Assignment[], globalIds: Iterable<string>, attribute: AttributeKind, value: string, o: MakeOptions = {}): AssignResult {
  const have = acceptedValues(list);
  const todo: string[] = [];
  let unchanged = 0;
  const seen = new Set<string>();
  for (const g of globalIds) {
    if (seen.has(g)) continue;
    seen.add(g);
    if (have.get(g)?.[attribute] === value) unchanged++;
    else todo.push(g);
  }
  if (todo.length === 0) return { list: list.slice(), assigned: 0, unchanged };
  const r = mergeAssignments(list, makeAssignments(todo, attribute, value, { ...o, status: 'accepted' }));
  return { list: r.list, assigned: todo.length, unchanged };
}

/** Take the accepted value of an attribute away from elements (their accepted records become rejected). */
export function unassign(list: readonly Assignment[], globalIds: Iterable<string>, attribute: AttributeKind, now: string = new Date().toISOString()): { list: Assignment[]; removed: number } {
  const set = new Set(globalIds);
  let removed = 0;
  const out = list.map((a) => {
    if (a.status === 'accepted' && a.attribute === attribute && set.has(a.element)) {
      removed++;
      return { ...a, status: 'rejected' as ReviewStatus, reviewed_at: now };
    }
    return a;
  });
  return { list: out, removed };
}

/** Accept or reject records by id. Accepting supersedes an older accepted record of the same element and attribute. */
export function decide(list: readonly Assignment[], ids: Iterable<string>, status: 'accepted' | 'rejected', now: string = new Date().toISOString()): { list: Assignment[]; changed: number } {
  const set = new Set(ids);
  let changed = 0;
  const out = list.map((a) => {
    if (!set.has(a.id) || a.status === status) return a;
    if (status === 'accepted' && a.status === 'superseded') return a;
    changed++;
    return { ...a, status, reviewed_at: now };
  });
  return { list: normalise(out), changed };
}

/** Change a value everywhere (a renamed location, trade or zone). Returns how many records changed. */
export function renameValue(list: readonly Assignment[], attribute: AttributeKind, from: string, to: string): { list: Assignment[]; changed: number } {
  let changed = 0;
  const out = list.map((a) => {
    if (a.attribute !== attribute || a.value !== from) return a;
    changed++;
    return { ...a, value: to };
  });
  return { list: out, changed };
}

/** Elements by value for one attribute, counting accepted records only. */
export function valueCounts(list: readonly Assignment[], attribute: AttributeKind): Map<string, number> {
  const out = new Map<string, number>();
  for (const a of list) if (a.status === 'accepted' && a.attribute === attribute) out.set(a.value, (out.get(a.value) ?? 0) + 1);
  return out;
}

/** Records that wait for a decision, newest suggestions last. */
export const proposed = (list: readonly Assignment[]): Assignment[] => list.filter((a) => a.status === 'proposed');
