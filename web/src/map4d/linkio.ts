// Export and import of the assignments as a LinkML `LinkDataset` (schema/linkml/xray_4d.yaml, JSON form): `model`, `model_elements` and
// `assignments` only. A mapping-only export has no schedule yet, so it leaves `schedule` out (optional in the schema). Files written
// by earlier versions carry a placeholder schedule (`PLACEHOLDER_SCHEDULE`); reading treats it as no schedule.
// `reviewed_by` is personal data: the export leaves it out unless `includeReviewers` is set. Pure. Tested in tests/map4d-linkio.test.ts.

import type { Assignment, AttributeKind, FourDLinks, LinkElement, LinkModelRef, LinkSource, ReviewStatus } from '../schedule/types';
import { ATTRIBUTES, acceptedValues, mergeAssignments } from './assignments';
import type { MergeResult } from './assignments';

export const PLACEHOLDER_SCHEDULE = { source_hash: '0'.repeat(64), project: '(no schedule yet)', file_name: 'placeholder: the 4D mapping tool exports assignments before any schedule is linked' } as const;
export const TOOL_NAME = 'xray-viewer 4D mapping';

const GID = /^[0-9A-Za-z_$]{22}$/;
const SOURCES: readonly LinkSource[] = ['native', 'property', 'attributes', 'override', 'suggested', 'manual', 'agent', 'classifier'];
const STATUSES: readonly ReviewStatus[] = ['proposed', 'accepted', 'rejected', 'superseded'];

/** The IFC GlobalId of a model element: a federation suffix `~n` is cut off. Null when what is left is not a GlobalId. */
export function plainGuid(g: string): string | null {
  const s = g.replace(/~\d+$/, '');
  return GID.test(s) ? s : null;
}

export interface ExportElement { globalId: string; ifcClass?: string; name?: string; storey?: string | null }

export interface ExportInput {
  model: LinkModelRef;
  elements: readonly ExportElement[];
  assignments: readonly Assignment[];
  /** Default false: `reviewed_by` is dropped. */
  includeReviewers?: boolean;
  /** Which review states to write. Default all (the statuses are part of the data). */
  statuses?: readonly ReviewStatus[];
  now?: string;
  id?: string;
}

export interface ExportResult { dataset: FourDLinks; json: string; assignments: number; elements: number; skipped: number }

export function exportDataset(i: ExportInput): ExportResult {
  const now = i.now ?? new Date().toISOString();
  const keep = new Set(i.statuses ?? STATUSES);
  const values = acceptedValues(i.assignments);
  let skipped = 0;
  const assignments: Assignment[] = [];
  for (const a of i.assignments) {
    if (!keep.has(a.status ?? 'proposed')) continue;
    const g = plainGuid(a.element);
    if (!g) { skipped++; continue; }
    const row: Assignment = { id: a.id, element: g, attribute: a.attribute, value: a.value };
    if (a.source) row.source = a.source;
    if (a.confidence !== undefined) row.confidence = a.confidence;
    if (a.reasons?.length) row.reasons = [...a.reasons];
    if (a.status) row.status = a.status;
    if (i.includeReviewers && a.reviewed_by) row.reviewed_by = a.reviewed_by;
    if (a.reviewed_at) row.reviewed_at = a.reviewed_at;
    if (a.created_at) row.created_at = a.created_at;
    assignments.push(row);
  }
  const used = new Set(assignments.map((a) => a.element));
  const model_elements: LinkElement[] = [];
  const seen = new Set<string>();
  for (const e of i.elements) {
    const g = plainGuid(e.globalId);
    if (!g || seen.has(g)) continue;
    const v = values.get(e.globalId);
    if (!used.has(g) && !v) continue;
    seen.add(g);
    model_elements.push({
      global_id: g,
      ...(e.ifcClass && /^Ifc[A-Za-z]+$/.test(e.ifcClass) ? { ifc_class: e.ifcClass } : {}),
      ...(e.name ? { name: e.name } : {}),
      ...(e.storey ? { storey: e.storey } : {}),
      ...(v?.location ? { location: v.location } : {}),
      ...(v?.trade ? { trade: v.trade } : {}),
      ...(v?.zone ? { zone: v.zone } : {}),
    });
  }
  const dataset: FourDLinks = {
    id: i.id ?? `map-${now.replace(/[^0-9]/g, '').slice(0, 14)}`,
    model: i.model,
    created_at: now,
    tool: TOOL_NAME,
    model_elements,
    assignments,
  };
  return { dataset, json: JSON.stringify(dataset, null, 2), assignments: assignments.length, elements: model_elements.length, skipped };
}

export interface ParsedDataset {
  assignments: Assignment[];
  model?: LinkModelRef;
  /** Rows that were left out, with the reason. */
  problems: string[];
}

/** Read a LinkDataset (text or object). Only `assignments` (and `model`, for the warning) are used; bad rows are listed in `problems`. */
export function parseDataset(input: unknown): ParsedDataset {
  const problems: string[] = [];
  let v: unknown = input;
  if (typeof input === 'string') {
    try { v = JSON.parse(input); } catch (e) { return { assignments: [], problems: [`Not JSON: ${e instanceof Error ? e.message : String(e)}`] }; }
  }
  if (!v || typeof v !== 'object' || Array.isArray(v)) return { assignments: [], problems: ['Not a LinkDataset: expected an object.'] };
  const d = v as Record<string, unknown>;
  const rows = d.assignments;
  if (rows !== undefined && rows !== null && !Array.isArray(rows)) return { assignments: [], problems: ['"assignments" is not a list.'] };
  const out: Assignment[] = [];
  const list = (rows as unknown[] | null | undefined) ?? [];
  list.forEach((r, n) => {
    const bad = (why: string): void => { problems.push(`assignments[${n}]: ${why}`); };
    if (!r || typeof r !== 'object') return bad('not an object');
    const o = r as Record<string, unknown>;
    if (typeof o.id !== 'string' || !o.id) return bad('no id');
    if (typeof o.element !== 'string' || !o.element) return bad('no element');
    if (!ATTRIBUTES.includes(o.attribute as AttributeKind)) return bad(`attribute ${String(o.attribute)} is not location, trade or zone`);
    if (typeof o.value !== 'string' || !o.value.trim()) return bad('no value');
    if (o.source != null && !SOURCES.includes(o.source as LinkSource)) return bad(`unknown source ${String(o.source)}`);
    if (o.status != null && !STATUSES.includes(o.status as ReviewStatus)) return bad(`unknown status ${String(o.status)}`);
    if (o.confidence != null && (typeof o.confidence !== 'number' || o.confidence < 0 || o.confidence > 1)) return bad('confidence is not between 0 and 1');
    const a: Assignment = { id: o.id, element: o.element, attribute: o.attribute as AttributeKind, value: o.value };
    if (o.source != null) a.source = o.source as LinkSource;
    if (typeof o.confidence === 'number') a.confidence = o.confidence;
    if (Array.isArray(o.reasons)) a.reasons = o.reasons.filter((x): x is string => typeof x === 'string');
    a.status = (o.status as ReviewStatus | undefined) ?? 'proposed';
    if (typeof o.reviewed_by === 'string') a.reviewed_by = o.reviewed_by;
    if (typeof o.reviewed_at === 'string') a.reviewed_at = o.reviewed_at;
    if (typeof o.created_at === 'string') a.created_at = o.created_at;
    out.push(a);
  });
  const m = d.model;
  return { assignments: out, ...(m && typeof m === 'object' && typeof (m as { identity_key?: unknown }).identity_key === 'string' ? { model: m as LinkModelRef } : {}), problems };
}

export interface ImportOutcome extends MergeResult { read: number; problems: string[]; otherModel: boolean }

/** Merge a dataset into the assignments: records with a new id are added, a newer accepted record supersedes an older one. */
export function importDataset(existing: readonly Assignment[], input: unknown, currentKey?: string): ImportOutcome & { list: Assignment[] } {
  const p = parseDataset(input);
  const r = mergeAssignments(existing, p.assignments);
  return { ...r, read: p.assignments.length, problems: p.problems, otherModel: !!(p.model && currentKey && p.model.identity_key !== currentKey) };
}
