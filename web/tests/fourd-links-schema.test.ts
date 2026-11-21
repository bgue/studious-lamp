// The TypeScript 4D link types (src/schedule/types.ts) and the LinkML schema (schema/linkml/xray_4d.yaml, via its generated
// JSON Schema) must name the same fields and allow the same enum values.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { ActivityLink, Assignment, FourDLinks, LinkActivity, LinkElement, LinkModelRef, LinkScheduleRef, LinkSource, LinkTie, ReviewStatus, SplitRule } from '../src/schedule/types';

const schema = JSON.parse(readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../../schema/linkml/xray_4d.schema.json'), 'utf8')) as { $defs: Record<string, { properties?: Record<string, unknown>; enum?: string[] }> };
const props = (name: string): string[] => Object.keys(schema.$defs[name]?.properties ?? {}).sort();
const enumOf = (name: string): string[] => [...(schema.$defs[name]?.enum ?? [])].sort();

// one object per type with EVERY field, so a field added on one side only fails here
const model: Required<LinkModelRef> = { identity_key: 'k', name: 'n', file_name: 'f', file_hash: 'h', ifc_schema: 'IFC4' };
const sched: Required<LinkScheduleRef> = { source_hash: 'h', project: 'p', data_date: 'd', file_name: 'f' };
const activity: Required<LinkActivity> = { task_code: 'A', name: 'n', wbs_path: 'w', activity_type: 'task', activity_status: 'active', start: 's', finish: 'f', location: 'l', trade: 't', zone: 'z', critical: false };
const element: Required<LinkElement> = { global_id: 'g', ifc_class: 'IfcSlab', name: 'n', storey: 's', location: 'l', trade: 't', zone: 'z', existing: false };
const assignment: Required<Assignment> = { id: 'i', element: 'g', attribute: 'trade', value: 'v', source: 'manual', confidence: 1, reasons: [], status: 'accepted', reviewed_by: 'r', reviewed_at: 'a', created_at: 'c' };
const link: Required<ActivityLink> = { id: 'i', activity: 'A', role: 'build', elements: [], source: 'agent', confidence: 1, reasons: [], split: 'none', rule: 'r', status: 'proposed', reviewed_by: 'r', reviewed_at: 'a', created_at: 'c' };
const tie: Required<LinkTie> = { element: 'g', candidates: [] };
const dataset: Required<FourDLinks> = { id: 'i', model, schedule: sched, created_at: 'c', tool: 't', activities: [], model_elements: [], assignments: [], links: [], ties: [], unlinked_activities: [], unlinked_elements: [] };

describe('4D links: TypeScript types match the LinkML schema', () => {
  it.each([
    ['ModelRef', model], ['ScheduleRef', sched], ['Activity', activity], ['Element', element], ['Assignment', assignment],
    ['ActivityLink', link], ['Tie', tie], ['LinkDataset', dataset],
  ] as const)('%s has the same fields', (name, obj) => {
    expect(Object.keys(obj).sort()).toEqual(props(name));
  });

  it('has the same enum values', () => {
    const sources: Record<LinkSource, true> = { native: true, property: true, attributes: true, override: true, suggested: true, manual: true, agent: true, classifier: true };
    const statuses: Record<ReviewStatus, true> = { proposed: true, accepted: true, rejected: true, superseded: true };
    const splits: Record<SplitRule, true> = { none: true, sweep_x: true, sweep_minus_x: true, sweep_y: true, sweep_minus_y: true, sweep_z: true, sweep_minus_z: true, by_storey: true, by_name: true };
    expect(Object.keys(sources).sort()).toEqual(enumOf('LinkSource'));
    expect(Object.keys(statuses).sort()).toEqual(enumOf('ReviewStatus'));
    expect(Object.keys(splits).sort()).toEqual(enumOf('SplitRule'));
  });
});
