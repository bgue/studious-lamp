import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Tour, buildTourSteps, parseStoredSets, storeyFocusSteps } from '../src/cinematic/tour';
import type { TourStep } from '../src/cinematic/tour';
import type { ElementRecord, SceneModel } from '../src/types';

const steps = (n: number): TourStep[] => Array.from({ length: n }, (_, i) => ({ name: `s${i}`, ids: [i, i + 10] }));

describe('Tour sequencing', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  function make(opts: { hold?: number; loop?: boolean } = {}) {
    const applied: string[] = [];
    const stops: string[] = [];
    const state = { hold: opts.hold ?? 3000, loop: opts.loop ?? false };
    const tour = new Tour({
      holdMs: () => state.hold,
      flyMs: () => 900,
      loop: () => state.loop,
      apply: (s, i) => applied.push(`${i}:${s.name}`),
      onStop: (r) => stops.push(r),
    });
    return { tour, applied, stops, state };
  }

  it('applies the first step immediately, then one per fly + hold', () => {
    const { tour, applied } = make();
    expect(tour.start(steps(3))).toBe(true);
    expect(applied).toEqual(['0:s0']);
    vi.advanceTimersByTime(3899);
    expect(applied).toEqual(['0:s0']);
    vi.advanceTimersByTime(1);
    expect(applied).toEqual(['0:s0', '1:s1']);
    vi.advanceTimersByTime(3900);
    expect(applied).toEqual(['0:s0', '1:s1', '2:s2']);
  });

  it('stops after the last step when not looping', () => {
    const { tour, applied, stops } = make();
    tour.start(steps(2));
    vi.advanceTimersByTime(3900 * 5);
    expect(applied).toEqual(['0:s0', '1:s1']);
    expect(tour.running).toBe(false);
    expect(stops).toEqual(['done']);
  });

  it('loops back to the first step when loop is on', () => {
    const { tour, applied, stops } = make({ loop: true });
    tour.start(steps(2));
    vi.advanceTimersByTime(3900 * 4);
    expect(applied).toEqual(['0:s0', '1:s1', '0:s0', '1:s1', '0:s0']);
    expect(tour.running).toBe(true);
    expect(stops).toEqual([]);
  });

  it('reads the hold time when each step is scheduled, so the slider works while running', () => {
    const { tour, applied, state } = make({ hold: 1000 });
    tour.start(steps(3));
    state.hold = 5000; // step 0 was scheduled with 1000; step 1 will use 5000
    vi.advanceTimersByTime(1900);
    expect(applied).toHaveLength(2);
    vi.advanceTimersByTime(5899);
    expect(applied).toHaveLength(2);
    vi.advanceTimersByTime(1);
    expect(applied).toHaveLength(3);
  });

  it('stop() cancels the pending step and reports once', () => {
    const { tour, applied, stops } = make();
    tour.start(steps(3));
    tour.stop();
    vi.advanceTimersByTime(60000);
    expect(applied).toHaveLength(1);
    expect(stops).toEqual(['stopped']);
    tour.stop();
    expect(stops).toEqual(['stopped']);
  });

  it('restarting begins again from step 0 without double timers', () => {
    const { tour, applied } = make();
    tour.start(steps(3));
    vi.advanceTimersByTime(4000);
    tour.start(steps(3));
    expect(applied.slice(-1)).toEqual(['0:s0']);
    vi.advanceTimersByTime(3900);
    expect(applied.slice(-1)).toEqual(['1:s1']);
    expect(applied.filter((a) => a === '1:s1')).toHaveLength(2); // once per run, never twice in one
  });

  it('does nothing without steps', () => {
    const { tour, applied } = make();
    expect(tour.start([])).toBe(false);
    expect(tour.start([{ name: 'empty', ids: [] }])).toBe(false);
    expect(applied).toEqual([]);
    expect(tour.running).toBe(false);
  });
});

function fakeModel(): SceneModel {
  const el = (id: number, gid: string, cls: string, storey: number | null): ElementRecord => ({
    id, globalId: gid, ifcClass: cls, storey, color: [1, 1, 1, 1], bounds: [0, 0, 0, 1, 1, 1],
  });
  const elements = [
    el(0, 'A', 'IfcDuctSegment', 1),
    el(1, 'B', 'IfcSlab', 0),
    el(2, 'C', 'IfcPipeSegment', 0),
    el(3, 'D', 'IfcDuctSegment', 0),
    el(4, 'E', 'IfcDuctSegment', null),
  ];
  return {
    schema: 'xray-model/1',
    units: 'm',
    originShift: [0, 0, 0],
    storeys: [{ id: 1, name: 'Level 2', elevation: 4 }, { id: 0, name: 'Level 1', elevation: 0 }, { id: 2, name: 'Roof', elevation: 8 }],
    elements,
    relations: { voids: [], fills: [], hosts: [], ports: [], systems: [] },
    byGlobalId: new Map(elements.map((e) => [e.globalId, e.id])),
  };
}

describe('tour steps', () => {
  const focus = new Set(['IfcDuctSegment', 'IfcPipeSegment']);
  const model = fakeModel();

  it('parses the sidebar format and drops unknown ids and empty sets', () => {
    const raw = JSON.stringify([
      { name: 'Supply', globalIds: ['A', 'C', 'nope'] },
      { name: 'Ghost', globalIds: ['zzz'] },
      { name: 'Bad' },
      { globalIds: ['D'] },
      42,
    ]);
    expect(parseStoredSets(raw, model.byGlobalId)).toEqual([
      { name: 'Supply', ids: [0, 2] },
      { name: 'Set 2', ids: [3] },
    ]);
  });

  it('tolerates missing or broken storage', () => {
    expect(parseStoredSets(null, model.byGlobalId)).toEqual([]);
    expect(parseStoredSets('{oops', model.byGlobalId)).toEqual([]);
    expect(parseStoredSets('{"a":1}', model.byGlobalId)).toEqual([]);
  });

  it('falls back to storeys ordered by elevation, focus classes only', () => {
    expect(storeyFocusSteps(model, focus)).toEqual([
      { name: 'Level 1', ids: [2, 3] },
      { name: 'Level 2', ids: [0] },
    ]);
  });

  it('prefers the stored sets under xray.sets.<modelName>', () => {
    const store = new Map([['xray.sets.building', JSON.stringify([{ name: 'Mine', globalIds: ['E'] }])]]);
    const storage = { getItem: (k: string) => store.get(k) ?? null };
    expect(buildTourSteps(model, 'building', focus, storage)).toEqual([{ name: 'Mine', ids: [4] }]);
    // another model name has nothing stored: storeys
    expect(buildTourSteps(model, 'other', focus, storage)).toHaveLength(2);
    expect(buildTourSteps(model, 'building', focus, null)).toHaveLength(2);
    const throwing = { getItem: () => { throw new Error('denied'); } };
    expect(buildTourSteps(model, 'building', focus, throwing)).toHaveLength(2);
  });
});
