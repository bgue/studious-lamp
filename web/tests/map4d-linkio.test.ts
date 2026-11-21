import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { Assignment } from '../src/schedule/types';
import { acceptedValues } from '../src/map4d/assignments';
import { PLACEHOLDER_SCHEDULE, exportDataset, importDataset, parseDataset, plainGuid } from '../src/map4d/linkio';

interface Def { properties?: Record<string, { pattern?: string; minimum?: number; maximum?: number; $ref?: string }>; required?: string[]; additionalProperties?: boolean; enum?: string[] }
const schema = JSON.parse(readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../../schema/linkml/xray_4d.schema.json'), 'utf8')) as { $defs: Record<string, Def> };
const D = schema.$defs;

/** A small validator for what the export writes: field names, required fields, patterns, enums, numeric bounds. */
function check(defName: string, row: Record<string, unknown>, path: string, errors: string[]): void {
  const def = D[defName]!;
  for (const r of def.required ?? []) if (row[r] === undefined) errors.push(`${path}: missing ${r}`);
  for (const [k, v] of Object.entries(row)) {
    const p = def.properties?.[k];
    if (!p) { errors.push(`${path}: unknown field ${k}`); continue; }
    if (p.pattern && typeof v === 'string' && !new RegExp(p.pattern).test(v)) errors.push(`${path}.${k}: ${String(v)} does not match ${p.pattern}`);
    if (typeof v === 'number' && ((p.minimum !== undefined && v < p.minimum) || (p.maximum !== undefined && v > p.maximum))) errors.push(`${path}.${k}: out of range`);
    const ref = p.$ref?.split('/').pop();
    if (ref && D[ref]?.enum && !D[ref]!.enum!.includes(v as string)) errors.push(`${path}.${k}: ${String(v)} not in ${ref}`);
    if (ref && D[ref]?.properties && v && typeof v === 'object') check(ref, v as Record<string, unknown>, `${path}.${k}`, errors);
  }
}
const validate = (d: Record<string, unknown>): string[] => {
  const errors: string[] = [];
  check('LinkDataset', d, 'dataset', errors);
  for (const [i, a] of ((d.assignments as Record<string, unknown>[] | undefined) ?? []).entries()) check('Assignment', a, `assignments[${i}]`, errors);
  for (const [i, e] of ((d.model_elements as Record<string, unknown>[] | undefined) ?? []).entries()) check('Element', e, `model_elements[${i}]`, errors);
  return errors;
};

const G1 = '0123456789abcdefghijkA';
const G2 = '0123456789abcdefghijkB';
const rows: Assignment[] = [
  { id: 'a1', element: G1, attribute: 'location', value: 'Level 1', source: 'manual', status: 'accepted', created_at: '2027-01-01T00:00:00Z', reviewed_at: '2027-01-01T00:00:00Z', reviewed_by: 'Alice Reviewer' },
  { id: 'a2', element: G1, attribute: 'trade', value: 'CONC', source: 'suggested', confidence: 0.8, reasons: ['IfcSlab gives CONC'], status: 'proposed', created_at: '2027-01-01T00:00:00Z' },
  { id: 'a3', element: G2, attribute: 'zone', value: 'Zone A', source: 'classifier', status: 'accepted', created_at: '2027-01-02T00:00:00Z' },
  { id: 'a4', element: 'short', attribute: 'zone', value: 'x', status: 'accepted' },
];
const input = { model: { identity_key: 'fzk|10|abc', name: 'FZK' }, elements: [{ globalId: G1, ifcClass: 'IfcSlab', name: 'S', storey: 'Level 1' }, { globalId: G2, ifcClass: 'IfcWall' }, { globalId: 'x'.repeat(22 + 1) }], assignments: rows, now: '2027-03-01T00:00:00Z' };

describe('export as a LinkML LinkDataset', () => {
  const r = exportDataset(input);
  it('uses only the schema fields, with valid patterns, enums and required fields', () => {
    expect(validate(r.dataset as unknown as Record<string, unknown>)).toEqual([]);
    expect(Object.keys(r.dataset).sort()).toEqual(['assignments', 'created_at', 'id', 'model', 'model_elements', 'schedule', 'tool']);
  });
  it('writes a clearly marked placeholder schedule (the schema requires one)', () => {
    expect(r.dataset.schedule).toEqual(PLACEHOLDER_SCHEDULE);
    expect(r.dataset.schedule.project).toContain('no schedule');
    expect(r.dataset.schedule.source_hash).toMatch(/^0{64}$/);
  });
  it('leaves reviewed_by out by default and keeps it on opt-in; skips rows without a GlobalId', () => {
    expect(r.json).not.toContain('Alice Reviewer');
    expect(r.skipped).toBe(1);
    expect(r.assignments).toBe(3);
    expect(exportDataset({ ...input, includeReviewers: true }).json).toContain('Alice Reviewer');
  });
  it('lists elements with their accepted location, trade and zone and keeps all statuses', () => {
    expect(r.dataset.model_elements!.find((e) => e.global_id === G1)).toEqual({ global_id: G1, ifc_class: 'IfcSlab', name: 'S', storey: 'Level 1', location: 'Level 1' });
    expect(r.dataset.assignments!.map((a) => a.status)).toEqual(['accepted', 'proposed', 'accepted']);
    expect(exportDataset({ ...input, statuses: ['accepted'] }).assignments).toBe(2);
  });
  it('cuts a federation suffix from a GlobalId', () => {
    expect(plainGuid(`${G1}~2`)).toBe(G1);
    expect(plainGuid('nope')).toBeNull();
  });
});

describe('import', () => {
  const exported = exportDataset(input).json;
  it('reads an export back, round trip', () => {
    const r = importDataset([], exported, 'fzk|10|abc');
    expect(r.read).toBe(3);
    expect(r.added).toBe(3);
    expect(r.otherModel).toBe(false);
    expect(acceptedValues(r.list).get(G1)).toEqual({ location: 'Level 1' });
  });
  it('merges: a newer accepted record supersedes the stored one, an older one does not; a second import changes nothing', () => {
    const stored: Assignment[] = [{ id: 'mine', element: G2, attribute: 'zone', value: 'Zone B', status: 'accepted', reviewed_at: '2027-06-01T00:00:00Z' }];
    const r = importDataset(stored, exported);
    expect(acceptedValues(r.list).get(G2)!.zone).toBe('Zone B'); // a3 (January) is older
    const newer = importDataset([{ ...stored[0]!, reviewed_at: '2026-01-01T00:00:00Z' }], exported);
    expect(acceptedValues(newer.list).get(G2)!.zone).toBe('Zone A');
    expect(newer.superseded).toBe(1);
    expect(importDataset(r.list, exported).list).toEqual(r.list);
  });
  it('warns about another model and lists bad rows without stopping', () => {
    const doc = { model: { identity_key: 'other' }, assignments: [...rows.slice(0, 1), { id: 'b', element: G1, attribute: 'floor', value: 'x' }, { id: 'c', element: G1, attribute: 'zone', value: '  ' }, { id: 'd', element: G1, attribute: 'zone', value: 'Z', confidence: 2 }, 5] };
    const r = importDataset([], doc, 'fzk|10|abc');
    expect(r.read).toBe(1);
    expect(r.problems).toHaveLength(4);
    expect(r.otherModel).toBe(true);
  });
  it('rejects text that is not a dataset', () => {
    expect(parseDataset('{{').problems[0]).toContain('Not JSON');
    expect(parseDataset([1]).problems[0]).toContain('expected an object');
    expect(parseDataset({ assignments: 3 }).problems[0]).toContain('not a list');
    expect(parseDataset({}).assignments).toEqual([]);
  });
});
