// Field AR maths (src/xr/field.ts): registration by point pairs, nudges, anchor following, storeys, the cut box, the field
// looks and the saved site format.
import { describe, expect, it } from 'vitest';
import {
  CUT_BELOW_FLOOR, FIELD_OTHER_ALPHA, FIELD_STRUCTURE_ALPHA, SITE_SCHEMA, fieldClassStyles, fieldCutBox, followAnchor, loadSites, modelKeyOf, nudgeRotate,
  nudgeTranslate, parseSite, rigFromMatrix, saveSiteTo, setFloorHeight, siteStorageKey, snapToVertexInPlan, solveFieldRegistration, storeyAt, storeyFloors,
  viewAxes, yawOfQuat,
} from '../src/xr/field';
import type { FieldPair, SiteRegistration } from '../src/xr/field';
import { rigLocalPoint, rigMatrix, rigPoint, rotateY, yawQuat } from '../src/xr/maths';
import type { Q4, Rig, V3 } from '../src/xr/maths';

const near = (a: readonly number[], b: readonly number[], eps = 1e-9): boolean => a.every((v, i) => Math.abs(v - b[i]!) <= eps);
const dist = (a: V3, b: V3): number => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);

/** A small deterministic random generator. */
function rng(seed: number): () => number {
  let s = seed >>> 0;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 2 ** 32);
}

const TRUE_RIG: Rig = { position: [3.2, -2.55, 7.1], yaw: 0.7, scale: 1 };
const REAL: V3[] = [
  [0.4, -1.45, -2.1],
  [3.9, -1.45, -1.2],
  [2.2, 0.8, -5.6],
  [-1.5, -0.2, -3.3],
];

describe('solveFieldRegistration', () => {
  it('recovers yaw and translation exactly from 2 exact pairs', () => {
    const pairs: FieldPair[] = REAL.slice(0, 2).map((r) => ({ model: rigPoint(TRUE_RIG, r), real: r }));
    const s = solveFieldRegistration(pairs);
    expect(s.ok).toBe(true);
    expect(s.used).toBe(2);
    expect(s.rig.yaw).toBeCloseTo(0.7, 10);
    expect(near(s.rig.position, TRUE_RIG.position, 1e-9)).toBe(true);
    expect(Math.max(...s.residuals)).toBeLessThan(1e-9);
  });

  it('matches three.js-style rig matrices (local -> world)', () => {
    expect(rigFromMatrix(rigMatrix(TRUE_RIG)).yaw).toBeCloseTo(0.7, 12);
    expect(near(rigFromMatrix(rigMatrix(TRUE_RIG)).position, TRUE_RIG.position)).toBe(true);
  });

  it('with 1 cm tap noise on 4 pairs: residuals of about 1 cm and the model within 2 cm at a check point', () => {
    const r = rng(7);
    const noise = (): V3 => [(r() - 0.5) * 0.02, (r() - 0.5) * 0.02, (r() - 0.5) * 0.02];
    const pairs: FieldPair[] = REAL.map((p) => {
      const n = noise();
      return { model: rigPoint(TRUE_RIG, p), real: [p[0] + n[0], p[1] + n[1], p[2] + n[2]] };
    });
    const s = solveFieldRegistration(pairs);
    expect(s.ok).toBe(true);
    expect(s.rms).toBeGreaterThan(0.001);
    expect(s.rms).toBeLessThan(0.02);
    expect(s.horizontal.length).toBe(4);
    for (let i = 0; i < 4; i++) expect(s.residuals[i]!).toBeCloseTo(Math.hypot(s.horizontal[i]!, s.vertical[i]!), 12);
    const check: V3 = [1.5, -1.45, -3];
    expect(dist(rigPoint(s.rig, check), rigPoint(TRUE_RIG, check))).toBeLessThan(0.02);
  });

  it('refuses fewer than 2 complete pairs and points above each other', () => {
    expect(solveFieldRegistration([{ model: [0, 0, 0], real: [0, 0, 0] }, { model: [1, 0, 0], real: null }]).ok).toBe(false);
    const stacked = solveFieldRegistration([
      { model: [0, 0, 0], real: [1, 0, 1] },
      { model: [0, 2, 0], real: [1, 2, 1] },
    ]);
    expect(stacked.ok).toBe(false);
    expect(stacked.warnings.join(' ')).toMatch(/above each other/);
  });
});

describe('nudges, floor and anchors', () => {
  it('nudgeTranslate moves the model by delta in the room', () => {
    const w: V3 = [5, 1, -2];
    const before = rigLocalPoint(TRUE_RIG, w);
    const after = rigLocalPoint(nudgeTranslate(TRUE_RIG, [0.01, -0.1, 0.02]), w);
    expect(near(after, [before[0] + 0.01, before[1] - 0.1, before[2] + 0.02], 1e-12)).toBe(true);
  });

  it('nudgeRotate turns the model about the vertical through the pivot', () => {
    const pivot: V3 = [1, 0, -2];
    const w: V3 = [5, 1, -2];
    const a = 0.1;
    const next = nudgeRotate(TRUE_RIG, pivot, a);
    expect(near(rigLocalPoint(next, rigPoint(TRUE_RIG, pivot)), pivot, 1e-12)).toBe(true);
    const l0 = rigLocalPoint(TRUE_RIG, w);
    const l1 = rigLocalPoint(next, w);
    const turned = rotateY([l0[0] - pivot[0], l0[1] - pivot[1], l0[2] - pivot[2]], a);
    expect(near(l1, [pivot[0] + turned[0], pivot[1] + turned[1], pivot[2] + turned[2]], 1e-12)).toBe(true);
  });

  it('setFloorHeight puts a model height at a room height', () => {
    const r = setFloorHeight(TRUE_RIG, -1.42, -3.06);
    expect(rigPoint(r, [2, -1.42, 3])[1]).toBeCloseTo(-3.06, 12);
    expect(r.yaw).toBe(TRUE_RIG.yaw);
  });

  it('followAnchor keeps the room around the anchor on the model after a map correction', () => {
    // the device's map shifts and turns: every local point L becomes T(L)
    const tYaw = 0.05;
    const tShift: V3 = [0.12, -0.01, -0.07];
    const T = (p: V3): V3 => {
      const q = rotateY(p, tYaw);
      return [q[0] + tShift[0], q[1] + tShift[1], q[2] + tShift[2]];
    };
    const then = { position: [1, -1.4, -2] as V3, quaternion: [0, 0, 0, 1] as Q4 };
    const now = { position: T(then.position), quaternion: yawQuat(tYaw) };
    const rig = followAnchor(TRUE_RIG, then, now);
    for (const L of REAL) expect(dist(rigPoint(rig, T(L)), rigPoint(TRUE_RIG, L))).toBeLessThan(1e-9);
    // no movement: same rig
    const same = followAnchor(TRUE_RIG, then, then);
    expect(near(same.position, TRUE_RIG.position, 1e-12) && Math.abs(same.yaw - TRUE_RIG.yaw) < 1e-12).toBe(true);
  });

  it('yawOfQuat and viewAxes', () => {
    expect(yawOfQuat(yawQuat(0.3))).toBeCloseTo(0.3, 12);
    const ax = viewAxes(yawQuat(Math.PI / 2)); // looking along -X
    expect(near(ax.forward, [-1, 0, 0], 1e-12)).toBe(true);
    expect(near(ax.right, [0, 0, -1], 1e-12)).toBe(true);
  });
});

describe('snapping a model point', () => {
  it('snaps in plan to the nearest vertex within the radius and keeps the height', () => {
    const pos = [0, 0, 0, 1, 0, 0, 1, 3, 0, 0, 3, 2];
    const s = snapToVertexInPlan(pos, 0, 4, [0.96, 1.7, 0.05], 0.1);
    expect(s.point).toEqual([1, 1.7, 0]);
    expect(s.snapped).toBe(true);
    expect(s.distance).toBeCloseTo(Math.hypot(0.04, 0.05), 12);
    expect(snapToVertexInPlan(pos, 0, 4, [0.5, 1.7, 0.5], 0.1).snapped).toBe(false);
  });
});

describe('storeys and the cut', () => {
  const model = {
    originShift: [6, 5, 3.0588],
    storeys: [
      { id: 0, name: 'Erdgeschoss', elevation: 0 },
      { id: 1, name: 'Dachgeschoss', elevation: 2.7 },
    ],
    elements: [
      { storey: 0, bounds: [0, -3.06, 0, 1, -0.4, 1] },
      { storey: 0, bounds: [0, -3.26, 0, 1, -3.06, 1] },
      { storey: 1, bounds: [0, -0.36, 0, 1, 2, 1] },
    ],
  };

  it('turns IFC elevations into viewer heights with the vertical origin shift', () => {
    const lv = storeyFloors(model);
    expect(lv.map((l) => l.name)).toEqual(['Erdgeschoss', 'Dachgeschoss']);
    expect(lv[0]!.floorY).toBeCloseTo(-3.0588, 9);
    expect(lv[1]!.floorY).toBeCloseTo(2.7 - 3.0588, 9);
  });

  it('falls back to the median element bottom when the shift does not fit', () => {
    const lv = storeyFloors({ ...model, originShift: [0, 0, 0] });
    expect(lv[0]!.floorY).toBeCloseTo(-3.16, 9);
    expect(lv[1]!.floorY).toBeCloseTo(-0.36, 9);
  });

  it('finds the storey from the feet height, with a tolerance', () => {
    const lv = storeyFloors(model);
    expect(storeyAt(lv, -3.0).level!.name).toBe('Erdgeschoss');
    expect(storeyAt(lv, -3.0).ceilingY).toBeCloseTo(-0.3588, 9);
    expect(storeyAt(lv, -0.7).level!.name).toBe('Dachgeschoss'); // 0.34 m below the next floor: within 0.5 m
    expect(storeyAt(lv, -1.5).level!.name).toBe('Erdgeschoss');
    expect(storeyAt(lv, 5).ceilingY).toBeNull();
    expect(storeyAt(lv, -10).index).toBe(0);
    expect(storeyAt([], 0).index).toBe(-1);
  });

  it('builds the cut box around the head and between the storey floors', () => {
    const b: [V3, V3] = [[-5, -3.3, -4], [5, 3.3, 4]];
    const box = fieldCutBox([1, -1.5, 2], { radius: 3, storeyCut: true }, { floorY: -3.06, ceilingY: -0.36 }, b)!;
    expect(box.min).toEqual([-2, -3.06 - CUT_BELOW_FLOOR, -1]);
    expect(box.max).toEqual([4, -0.36, 5]);
    const noRadius = fieldCutBox([1, -1.5, 2], { radius: 0, storeyCut: true }, { floorY: -3.06, ceilingY: null }, b)!;
    expect(noRadius.min[0]).toBe(-6);
    expect(noRadius.max[1]).toBe(4.3);
    expect(fieldCutBox([0, 0, 0], { radius: 0, storeyCut: false }, null, b)).toBeNull();
  });
});

describe('field looks', () => {
  const present = ['IfcPipeSegment', 'IfcWall', 'IfcDoor', 'IfcSlab'];
  const focus = ['IfcPipeSegment', 'IfcDuctSegment'];
  const ctx = ['IfcWall', 'IfcSlab'];

  it('full returns the user styles unchanged', () => {
    const base = { IfcDoor: { color: [1, 0, 0] as [number, number, number] } };
    expect(fieldClassStyles(base, present, focus, ctx, 'full')).toBe(base);
  });

  it('ghosted keeps services, makes structure nearly invisible and the rest faint, over the user styles', () => {
    const base = { IfcDoor: { alphaMax: 0.1, color: [1, 0, 0] as [number, number, number] } };
    const s = fieldClassStyles(base, present, focus, ctx, 'ghosted');
    expect(s.IfcPipeSegment).toBeUndefined();
    expect(s.IfcWall!.alphaMax).toBe(FIELD_STRUCTURE_ALPHA);
    expect(s.IfcSlab!.alphaMax).toBe(FIELD_STRUCTURE_ALPHA);
    expect(s.IfcDoor).toEqual({ alphaMax: 0.1, color: [1, 0, 0] }); // the stricter user cap wins
    expect(fieldClassStyles({}, present, focus, ctx, 'ghosted').IfcDoor!.alphaMax).toBe(FIELD_OTHER_ALPHA);
    expect(base.IfcDoor.alphaMax).toBe(0.1); // not mutated
  });

  it('x-ray hides everything but the services', () => {
    const s = fieldClassStyles({}, present, focus, ctx, 'x-ray');
    expect(Object.keys(s).sort()).toEqual(['IfcDoor', 'IfcSlab', 'IfcWall']);
    expect(Object.values(s).every((v) => v.hidden === true)).toBe(true);
  });
});

describe('saved sites', () => {
  const site: SiteRegistration = {
    schema: SITE_SCHEMA,
    id: 'site-1',
    name: 'fzk east wing',
    model: 'fzk-haus',
    modelKey: '82:a:b',
    created: '2026-11-05T10:00:00.000Z',
    pairs: [
      { model: [1, 2, 3], real: [0.1, 0.2, 0.3] },
      { model: [4, 5, 6], real: null },
    ],
    rig: { position: [1, 2, 3], yaw: 0.5 },
    residuals: [0.01],
    rms: 0.01,
    anchor: { pose: { position: [0, 0, -1], quaternion: [0, 0, 0, 1] }, handle: 'uuid-1' },
  };

  it('round-trips through JSON', () => {
    const back = parseSite(JSON.parse(JSON.stringify(site)));
    expect(back.errors).toEqual([]);
    expect(back.site).toEqual(site);
  });

  it('reports what is wrong', () => {
    expect(parseSite(null).site).toBeNull();
    const bad = parseSite({ ...site, schema: 'x', pairs: [{ model: [1, 2] }], rig: { yaw: 'a' }, anchor: { pose: {} } });
    expect(bad.site).toBeNull();
    expect(bad.errors.join(' | ')).toMatch(/schema/);
    expect(bad.errors.join(' | ')).toMatch(/pairs\[0\]/);
    expect(bad.errors.join(' | ')).toMatch(/rig/);
    expect(bad.errors.join(' | ')).toMatch(/anchor/);
  });

  it('stores per model, newest first, and filters by model key', () => {
    const mem = new Map<string, string>();
    const st = { getItem: (k: string) => mem.get(k) ?? null, setItem: (k: string, v: string) => void mem.set(k, v) };
    expect(saveSiteTo(st, site)).toBe(true);
    expect(saveSiteTo(st, { ...site, id: 'site-2', created: '2026-11-06T10:00:00.000Z' })).toBe(true);
    expect(saveSiteTo(st, { ...site, id: 'site-2', name: 'renamed', created: '2026-11-06T10:00:00.000Z' })).toBe(true);
    const list = loadSites(st, 'fzk-haus');
    expect(list.map((s) => s.id)).toEqual(['site-2', 'site-1']);
    expect(list[0]!.name).toBe('renamed');
    expect(loadSites(st, 'fzk-haus', 'other')).toEqual([]);
    expect(mem.has(siteStorageKey('fzk-haus'))).toBe(true);
    mem.set(siteStorageKey('x'), '{not json');
    expect(loadSites(st, 'x')).toEqual([]);
    expect(loadSites(null, 'x')).toEqual([]);
    expect(saveSiteTo(null, site)).toBe(false);
  });

  it('fingerprints a model by count and first and last GlobalId', () => {
    expect(modelKeyOf({ elements: [{ globalId: 'a' }, { globalId: 'm' }, { globalId: 'b' }] })).toBe('3:a:b');
  });
});
