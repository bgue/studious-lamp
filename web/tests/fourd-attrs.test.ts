import { describe, expect, it } from 'vitest';
import { acceptedAssignments, elementAttributes, mapValue, readTaskAttr, readTaskSource, taskAttributes } from '../src/schedule/attrs';
import type { Assignment, ScheduleTask } from '../src/schedule/types';
import { buildConfig, buildModel, task } from './fourd-fixtures';

const t: ScheduleTask = task('X1', 'L3 Slab pour (zone B)', { codes: { Level: 'L03', Trade: 'CONC', Empty: '  ' }, wbs: ['P', 'STR', 'L3'], udfs: { Area: 'B', Num: 7 } });

describe('schedule attribute sources', () => {
  it('reads each source kind', () => {
    expect(readTaskSource(t, { code: 'Level' })).toBe('L03');
    expect(readTaskSource(t, { udf: 'Area' })).toBe('B');
    expect(readTaskSource(t, { udf: 'Num' })).toBe('7');
    expect(readTaskSource(t, { wbsLevel: 0 })).toBe('P');
    expect(readTaskSource(t, { wbsLevel: 2 })).toBe('L3');
    expect(readTaskSource(t, { wbsPattern: 'STR/L(\\d)' })).toBe('3');
    expect(readTaskSource(t, { wbsPattern: '(STR)/(L\\d)', group: 2 })).toBe('L3');
    expect(readTaskSource(t, { namePattern: 'zone ([A-Z])' })).toBe('B');
    expect(readTaskSource(t, { namePattern: 'Zone ([A-Z])' })).toBeUndefined(); // case sensitive
    expect(readTaskSource(t, { namePattern: '\\(zone ([A-Z])\\)' })).toBe('B');
    expect(readTaskSource(t, { namePattern: 'Slab' })).toBe('Slab'); // no capture group: the whole match
  });
  it('treats missing, blank and bad patterns as no value', () => {
    expect(readTaskSource(t, { code: 'Nope' })).toBeUndefined();
    expect(readTaskSource(t, { code: 'Empty' })).toBeUndefined();
    expect(readTaskSource(t, { wbsLevel: 9 })).toBeUndefined();
    expect(readTaskSource(t, { namePattern: '(' })).toBeUndefined();
  });
  it('first hit wins', () => {
    expect(readTaskAttr(t, [{ code: 'Nope' }, { udf: 'Area' }, { code: 'Level' }])).toBe('B');
    expect(readTaskAttr(t, [{ code: 'Level' }, { udf: 'Area' }])).toBe('L03');
    expect(readTaskAttr(t, [])).toBeUndefined();
    expect(readTaskAttr(t, undefined)).toBeUndefined();
  });
});

describe('value mapping', () => {
  const table = { L00: 'Ground', '/^L(\\d\\d)$/': 'Level $1', '/^blk-(\\w+)$/i': 'Block $1 ($&)', conc: 'Concrete' };
  it('exact keys win over regex keys, then case-insensitive exact', () => {
    expect(mapValue('L00', table)).toBe('Ground');
    expect(mapValue('CONC', table)).toBe('Concrete');
  });
  it('regex keys substitute groups', () => {
    expect(mapValue('L03', table)).toBe('Level 03');
    expect(mapValue('BLK-a', table)).toBe('Block a (BLK-a)');
  });
  it('passes unmapped values through and keeps undefined', () => {
    expect(mapValue('ZZ', table)).toBe('ZZ');
    expect(mapValue(undefined, table)).toBeUndefined();
    expect(mapValue('x', undefined)).toBe('x');
    expect(mapValue('x', { '/(/': 'bad' })).toBe('x');
  });
  it('maps a task through the config', () => {
    const cfg = buildConfig();
    expect(taskAttributes(t, cfg)).toEqual({ location: 'Level 3', trade: 'CONC' });
    const withZone = { ...cfg, schedule: { ...cfg.schedule, zone: [{ udf: 'Area' }] } };
    expect(taskAttributes(t, withZone).zone).toBe('Zone B');
  });
});

describe('element attributes', () => {
  const cfg = buildConfig();
  const model = buildModel();
  const col = model.elements.find((e) => e.globalId === 'COLA2')!;
  const duct = model.elements.find((e) => e.globalId === 'DUCT2')!;

  it('reads property, storey, zone and discipline sources, first hit wins', () => {
    expect(elementAttributes(col, cfg)).toEqual({ location: 'Level 2', trade: 'CONC', zone: 'Zone A' });
    expect(elementAttributes(duct, cfg)).toEqual({ location: 'Level 2' });
    const other = { ...cfg, model: { ...cfg.model, trade: [{ discipline: true as const }, { property: 'Xray_4D.Trade' }] } };
    expect(elementAttributes({ ...col, discipline: 'Structure' }, other).trade).toBe('Structure');
    expect(elementAttributes(col, other).trade).toBe('CONC');
    const loc = { ...cfg, model: { ...cfg.model, location: [{ property: 'pset_x.area' }, { storey: true as const }] } };
    expect(elementAttributes({ ...col, props: { 'Pset_X.Area': 'Core' } }, loc).location).toBe('Core'); // property keys match any case
  });

  const a = (id: string, value: string, status: Assignment['status'], extra: Partial<Assignment> = {}): Assignment => ({ id, element: 'COLA2', attribute: 'trade', value, status, ...extra });
  it('accepted assignments win over model properties; other statuses are ignored', () => {
    const acc = acceptedAssignments([a('1', 'STEEL', 'accepted'), a('2', 'GLASS', 'proposed'), a('3', 'WOOD', 'rejected'), a('4', 'OLD', 'superseded')]);
    expect(elementAttributes(col, cfg, acc).trade).toBe('STEEL');
    const none = acceptedAssignments([a('2', 'GLASS', 'proposed'), a('3', 'WOOD', 'rejected'), a('4', 'OLD', 'superseded'), a('5', 'X', undefined)]);
    expect(elementAttributes(col, cfg, none).trade).toBe('CONC');
  });
  it('assignments also give attributes the element lacks, and the latest accepted row wins', () => {
    const acc = acceptedAssignments([
      a('1', 'STEEL', 'accepted', { created_at: '2027-01-01T00:00:00Z' }), a('2', 'TIMBER', 'accepted', { created_at: '2027-02-01T00:00:00Z' }),
      { id: '3', element: 'DUCT2', attribute: 'trade', value: 'MEP', status: 'accepted' },
      { id: '4', element: 'DUCT2', attribute: 'zone', value: 'Zone A', status: 'accepted' },
    ]);
    expect(elementAttributes(col, cfg, acc).trade).toBe('TIMBER');
    expect(elementAttributes(duct, cfg, acc)).toEqual({ location: 'Level 2', trade: 'MEP', zone: 'Zone A' });
  });
});
