import { describe, expect, it } from 'vitest';
import { analyse, boxGap, defaultRules, meshVolumeOf, summarise } from '../src/cleanup/analysis';
import type { CleanupElement, CleanupRules } from '../src/cleanup/analysis';
import { CleanupHides } from '../src/cleanup/hides';
import { makeCleanupScene } from './fixtures/cleanup-scene';

// Timing budgets are strict only when XRAY_PERF=1 (same convention as tests/performance.test.ts).
const SLACK = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env?.['XRAY_PERF'] === '1' ? 1 : 5;

const scene = makeCleanupScene();
const { ids } = scene;

/** Only the given rule on, everything else off. */
function only(rule: keyof CleanupRules, patch: Record<string, unknown> = {}): CleanupRules {
  const r = defaultRules();
  r.floating.enabled = false;
  r.tiny.enabled = false;
  r.strays.enabled = false;
  r.duplicates.enabled = false;
  r.degenerate.enabled = false;
  Object.assign(r[rule], { enabled: true }, patch);
  return r;
}

const idsOf = (rules: CleanupRules, geo = scene.geometry): number[] => analyse(scene.elements, rules, geo).ids;

describe('floating elements', () => {
  it('single elements: lone small boxes only', () => {
    const res = analyse(scene.elements, only('floating'), scene.geometry);
    // lone small boxes, the far stray's 0.8 m is above 0.5 m, cluster members are not lone, the diagonal one touches by bounds
    expect(res.ids).toEqual([...ids.loneSmall].sort((a, b) => a - b));
    expect(res.counts.floating).toBe(3);
    expect(res.matches.get(ids.loneSmall[0]!)!.reasons[0]).toMatch(/lone element, no contacts: largest dimension 0\.300 m < 0\.500 m/);
  });

  it('never matches a large floating element or the main structure', () => {
    const res = analyse(scene.elements, only('floating', { mode: 'small clusters' }), scene.geometry);
    expect(res.matches.has(ids.largeFloating)).toBe(false);
    for (const m of ids.main) expect(res.matches.has(m)).toBe(false);
    expect(res.matches.has(ids.stray)).toBe(false);
  });

  it('small clusters: the three-box cluster matches as a whole, measured by its union', () => {
    const res = analyse(scene.elements, only('floating', { mode: 'small clusters' }), scene.geometry);
    expect(res.ids).toEqual([...ids.loneSmall, ...ids.cluster].sort((a, b) => a - b));
    expect(res.matches.get(ids.cluster[1]!)!.reasons[0]).toMatch(/cluster of 3 touching elements: largest dimension 0\.300 m/);
    // a smaller threshold than the union (0.3) leaves the cluster alone although each box is 0.1 m
    const small = analyse(scene.elements, only('floating', { mode: 'small clusters', threshold: 0.25 }), scene.geometry);
    expect(small.ids).toEqual([]);
  });

  it('threshold decides: a larger threshold catches the 0.8 m stray and the 1.5 m element', () => {
    const r = analyse(scene.elements, only('floating', { threshold: 2 }), scene.geometry);
    expect(r.matches.has(ids.largeFloating)).toBe(true);
    expect(r.matches.has(ids.stray)).toBe(true);
    expect(r.matches.has(ids.proxy)).toBe(true); // lone 0.6 m proxy
  });

  it('contact tolerance joins elements with a small gap', () => {
    const els: CleanupElement[] = [
      { id: 0, ifcClass: 'IfcSlab', bounds: [0, 0, 0, 10, 1, 10] },
      { id: 1, ifcClass: 'IfcBeam', bounds: [10.008, 0, 0, 10.2, 0.2, 0.2] },
      { id: 2, ifcClass: 'IfcBeam', bounds: [10.5, 0, 0, 10.7, 0.2, 0.2] },
    ];
    const r = analyse(els, only('floating'));
    expect(r.ids).toEqual([2]); // 8 mm gap is within the 10 mm default, 0.3 m is not
    const strict = analyse(els, only('floating', { contactTolerance: 0.005 }));
    expect(strict.ids).toEqual([1, 2]);
  });

  it('bounds volume metric', () => {
    // lone small boxes are 0.027 m3, the cluster union 0.027 m3, the proxy 0.216, the large element 3.375
    const r = analyse(scene.elements, only('floating', { metric: 'bounds volume (m³)', threshold: 0.1, mode: 'small clusters' }), scene.geometry);
    expect(r.ids).toEqual([...ids.loneSmall, ...ids.cluster].sort((a, b) => a - b));
    expect(r.matches.get(ids.loneSmall[0]!)!.reasons[0]).toMatch(/bounds volume 0\.027 m³ < 0\.100 m³/);
  });

  it('mesh volume metric uses the callback and falls back to the bounds volume when it returns null', () => {
    const geo = { ...scene.geometry, meshVolume: (id: number) => (id === ids.loneSmall[0] ? 0.001 : id === ids.loneSmall[1] ? null : 5) };
    const r = analyse(scene.elements, only('floating', { metric: 'mesh volume (m³)', threshold: 0.01 }), geo);
    expect(r.ids).toEqual([ids.loneSmall[0]!]); // #1 falls back to 0.027 (>= 0.01), the others report 5
  });

  it('triangle count metric', () => {
    const geo = { ...scene.geometry, triangleCount: (id: number) => (id === ids.loneSmall[2] ? 6 : 12) };
    const r = analyse(scene.elements, only('floating', { metric: 'triangle count', threshold: 10 }), geo);
    expect(r.ids).toEqual([ids.loneSmall[2]!]);
  });

  it('diagonal contact: AABB mode joins it to the structure, precise mode (mesh distance) floats it', () => {
    expect(idsOf(only('floating')).includes(ids.diagonal)).toBe(false);
    const precise = analyse(scene.elements, only('floating', { precise: true }), scene.geometry);
    expect(precise.matches.has(ids.diagonal)).toBe(true);
    expect(precise.matches.get(ids.diagonal)!.reasons[0]).toMatch(/lone element/);
    // precise without a surfaceDistance callback quietly stays on bounds
    const noDist = analyse(scene.elements, only('floating', { precise: true }), { triangleCount: scene.geometry.triangleCount });
    expect(noDist.matches.has(ids.diagonal)).toBe(false);
    // a precise run keeps the genuine contacts
    expect(precise.matches.has(ids.tinyTouching)).toBe(false);
    expect(precise.matches.has(ids.furniture)).toBe(false);
  });

  it('the main component is the one with the largest total bounds volume', () => {
    const r = analyse(scene.elements, only('floating'), scene.geometry);
    expect(r.components.mainElements).toBeGreaterThanOrEqual(ids.main.length);
    expect(r.components.count).toBeGreaterThan(5);
  });
});

describe('tiny, strays, duplicates, degenerate, classes', () => {
  it('tiny matches regardless of contact', () => {
    const r = analyse(scene.elements, only('tiny'), scene.geometry);
    expect(r.ids).toContain(ids.tinyTouching);
    expect(r.matches.get(ids.tinyTouching)!.reasons[0]).toMatch(/tiny: largest dimension 0\.030 m < 0\.050 m/);
    expect(r.ids).not.toContain(ids.loneSmall[0]);
    expect(analyse(scene.elements, only('tiny', { maxSize: 0.2 }), scene.geometry).ids).toContain(ids.fastener);
  });

  it('distant strays: the object 600 m away, nothing else', () => {
    const r = analyse(scene.elements, only('strays'), scene.geometry);
    expect(r.ids).toEqual([ids.stray]);
    expect(r.matches.get(ids.stray)!.reasons[0]).toMatch(/distant stray/);
    expect(analyse(scene.elements, only('strays', { factor: 1 }), scene.geometry).ids.length).toBeGreaterThan(1);
  });

  it('distant strays: min gap (m) and max size (m) narrow the matches', () => {
    // The stray lies about 600 m out; a 1000 m gap drops it, a 100 m gap keeps it and says so.
    const kept = analyse(scene.elements, only('strays', { minGap: 100 }), scene.geometry);
    expect(kept.ids).toEqual([ids.stray]);
    expect(kept.matches.get(ids.stray)!.reasons[0]).toMatch(/m outside the main model >= 100 m/);
    expect(analyse(scene.elements, only('strays', { minGap: 1000 }), scene.geometry).ids).toEqual([]);
    // It is 0.8 m wide: a 0.5 m size limit drops it, 1 m keeps it, 0 means any size.
    expect(analyse(scene.elements, only('strays', { maxSize: 0.5 }), scene.geometry).ids).toEqual([]);
    expect(analyse(scene.elements, only('strays', { maxSize: 1 }), scene.geometry).ids).toEqual([ids.stray]);
    expect(analyse(scene.elements, only('strays', { maxSize: 0 }), scene.geometry).ids).toEqual([ids.stray]);
    // A low factor matches main elements too, but none of them lies 100 m outside the main box.
    expect(analyse(scene.elements, only('strays', { factor: 1, minGap: 100 }), scene.geometry).ids).toEqual([ids.stray]);
  });

  it('boxGap measures the Euclidean gap to a box and is 0 on overlap', () => {
    expect(boxGap([3, 0, 0, 4, 1, 1], [0, 0, 0], [1, 1, 1])).toBeCloseTo(2);
    expect(boxGap([4, 5, 0, 5, 6, 1], [0, 0, 0], [1, 1, 1])).toBeCloseTo(5);
    expect(boxGap([0.5, 0.5, 0.5, 2, 2, 2], [0, 0, 0], [1, 1, 1])).toBe(0);
    expect(boxGap([0, 0, 0, 1, 1, 1], [Infinity, Infinity, Infinity], [-Infinity, -Infinity, -Infinity])).toBe(Infinity);
  });

  it('duplicates keep the lowest id', () => {
    const r = analyse(scene.elements, only('duplicates'), scene.geometry);
    expect(r.ids).toEqual([ids.duplicate]);
    expect(r.matches.get(ids.duplicate)!.reasons[0]).toBe(`duplicate of #${ids.duplicateOriginal} (same class, bounds within 2 mm)`);
  });

  it('duplicates need the same class and triangle count', () => {
    const geo = { ...scene.geometry, triangleCount: (id: number) => (id === ids.duplicate ? 24 : 12) };
    expect(analyse(scene.elements, only('duplicates'), geo).ids).toEqual([]);
    const els = scene.elements.map((e) => (e.id === ids.duplicate ? { ...e, ifcClass: 'IfcSlab' } : e));
    expect(analyse(els, only('duplicates'), scene.geometry).ids).toEqual([]);
  });

  it('degenerate: zero thickness, no triangles, non-finite, non-physical class', () => {
    const els: CleanupElement[] = [
      ...scene.elements,
      { id: scene.elements.length, ifcClass: 'IfcWall', bounds: [0, 0, 0, NaN, 1, 1] },
      { id: scene.elements.length + 1, ifcClass: 'IfcWall', bounds: [0, 0, 0, 1, 1, 1] },
      { id: scene.elements.length + 2, ifcClass: 'IfcAnnotation', bounds: [0, 0, 0, 1, 1, 1] },
    ];
    const geo = { ...scene.geometry, triangleCount: (id: number) => (id === scene.elements.length + 1 ? 0 : 12) };
    const r = analyse(els, only('degenerate'), geo);
    expect(r.ids).toEqual([ids.degenerate, els.length - 3, els.length - 2, els.length - 1]);
    expect(r.matches.get(ids.degenerate)!.reasons[0]).toMatch(/zero-thickness/);
    expect(r.matches.get(els.length - 3)!.reasons[0]).toMatch(/non-finite/);
    expect(r.matches.get(els.length - 2)!.reasons[0]).toMatch(/no triangles/);
    expect(r.matches.get(els.length - 1)!.reasons[0]).toMatch(/non-physical class IfcAnnotation/);
  });

  it('class groups', () => {
    const c = (k: string): number[] => idsOf(only('classes', { [k]: true }));
    expect(c('proxies')).toEqual([ids.proxy, ids.stray].sort((a, b) => a - b));
    expect(c('furniture')).toEqual([ids.furniture]);
    expect(c('accessories')).toEqual([ids.fastener, ids.tinyTouching].sort((a, b) => a - b));
    expect(idsOf(only('classes', { enabled: undefined }))).toEqual([]);
  });
});

describe('combinations', () => {
  it('defaults: per-rule counts and per-id reasons', () => {
    const r = analyse(scene.elements, defaultRules(), scene.geometry);
    expect(r.counts).toEqual({ floating: 3, tiny: 1, strays: 1, duplicates: 1, degenerate: 1, classes: 0 });
    expect(summarise(r.counts)).toBe('Floating 3, Tiny 1, Strays 1, Duplicates 1, Degenerate 1, Classes 0');
    expect(r.ids).toEqual([...ids.loneSmall, ids.stray, ids.duplicate, ids.degenerate, ids.tinyTouching].sort((a, b) => a - b));
    expect(r.matches.get(ids.tinyTouching)!.rules).toEqual(['tiny']);
  });

  it('an element matched by several rules lists each reason once per rule', () => {
    const els: CleanupElement[] = [
      ...Array.from({ length: 10 }, (_, i): CleanupElement => ({ id: i, ifcClass: 'IfcSlab', bounds: [i, 0, 0, i + 1, 1, 1] })),
      { id: 10, ifcClass: 'IfcBuildingElementProxy', bounds: [900, 0, 0, 900.02, 0.02, 0.02] },
    ];
    const rules = defaultRules();
    rules.classes.proxies = true;
    const r = analyse(els, rules);
    const m = r.matches.get(10)!;
    expect(m.rules.sort()).toEqual(['classes', 'floating', 'strays', 'tiny']);
    expect(m.reasons).toHaveLength(4);
    expect(r.counts).toMatchObject({ floating: 1, tiny: 1, strays: 1, classes: 1 });
    expect(r.ids).toEqual([10]);
  });

  it('everything off: nothing matches', () => {
    const r = defaultRules();
    r.floating.enabled = r.tiny.enabled = r.strays.enabled = r.duplicates.enabled = r.degenerate.enabled = false;
    expect(analyse(scene.elements, r, scene.geometry).ids).toEqual([]);
  });
});

describe('provenance-safe hide and restore', () => {
  it('restore removes only what cleanup hid', () => {
    const userHides = new Set<number>([5, 7]);
    const h = new CleanupHides();
    expect(h.hide(userHides, [5, 6, 8])).toBe(2); // 5 was already hidden by the user
    expect([...userHides].sort()).toEqual([5, 6, 7, 8]);
    expect(h.restore(userHides).sort()).toEqual([6, 8]);
    expect([...userHides].sort()).toEqual([5, 7]); // the user's own hides, including the shared #5, stay hidden
    expect(h.owned.size).toBe(0);
  });

  it('an element the user unhid meanwhile is not re-claimed', () => {
    const userHides = new Set<number>();
    const h = new CleanupHides();
    h.hide(userHides, [1, 2]);
    userHides.delete(1); // user shows #1 again, then hides it again themselves
    h.prune(userHides);
    userHides.add(1);
    h.restore(userHides);
    expect([...userHides]).toEqual([1]);
  });

  it('hiding twice is idempotent', () => {
    const s = new Set<number>();
    const h = new CleanupHides();
    h.hide(s, [1, 2]);
    expect(h.hide(s, [1, 2])).toBe(0);
    expect(h.restore(s).sort()).toEqual([1, 2]);
    expect(s.size).toBe(0);
  });
});

describe('meshVolumeOf', () => {
  // unit cube, 12 triangles, counter-clockwise outward
  const cubePos = [0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0, 0, 0, 1, 1, 0, 1, 1, 1, 1, 0, 1, 1];
  const cubeIdx = [0, 2, 1, 0, 3, 2, 4, 5, 6, 4, 6, 7, 0, 1, 5, 0, 5, 4, 3, 7, 6, 3, 6, 2, 0, 4, 7, 0, 7, 3, 1, 2, 6, 1, 6, 5];

  it('unit cube is 1 and closed', () => {
    const r = meshVolumeOf(cubePos, cubeIdx, 0, 12);
    expect(r.volume).toBeCloseTo(1, 12);
    expect(r.closed).toBe(true);
  });

  it('a 2 x 3 x 4 box is 24, wherever it sits', () => {
    const pos = cubePos.map((v, i) => (i % 3 === 0 ? v * 2 : i % 3 === 1 ? v * 3 : v * 4) + (i % 3 === 0 ? 100 : 0));
    expect(meshVolumeOf(pos, cubeIdx, 0, 12).volume).toBeCloseTo(24, 9);
  });

  it('inverted winding gives the same absolute volume', () => {
    const flipped: number[] = [];
    for (let t = 0; t < 12; t++) flipped.push(cubeIdx[t * 3]!, cubeIdx[t * 3 + 2]!, cubeIdx[t * 3 + 1]!);
    expect(meshVolumeOf(cubePos, flipped, 0, 12).volume).toBeCloseTo(1, 12);
  });

  it('non-indexed soup with duplicated vertices is still closed (welded by position)', () => {
    const soup: number[] = [];
    for (const i of cubeIdx) soup.push(cubePos[i * 3]!, cubePos[i * 3 + 1]!, cubePos[i * 3 + 2]!);
    const r = meshVolumeOf(soup, null, 0, 12);
    expect(r.volume).toBeCloseTo(1, 12);
    expect(r.closed).toBe(true);
  });

  it('an open mesh (a cube without its lid) is reported as not closed', () => {
    const r = meshVolumeOf(cubePos, cubeIdx, 0, 10);
    expect(r.closed).toBe(false);
  });

  it('honours the triangle range', () => {
    const idx = [...cubeIdx, ...cubeIdx];
    expect(meshVolumeOf(cubePos, idx, 12, 12).volume).toBeCloseTo(1, 12);
  });
});

describe('performance', () => {
  it('20,000 random boxes analyse in under 1,500 ms', () => {
    let s = 12345;
    const rnd = (): number => {
      s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
      return s / 4294967296;
    };
    const els: CleanupElement[] = [];
    for (let i = 0; i < 20000; i++) {
      const x = rnd() * 200, y = rnd() * 60, z = rnd() * 200;
      els.push({ id: i, ifcClass: i % 7 === 0 ? 'IfcWall' : 'IfcBeam', bounds: [x, y, z, x + 0.1 + rnd() * 3, y + 0.1 + rnd() * 3, z + 0.1 + rnd() * 3] });
    }
    const geo = { triangleCount: () => 12 };
    const t0 = performance.now();
    const r = analyse(els, defaultRules(), geo);
    const ms = performance.now() - t0;
    expect(r.ids.length).toBeGreaterThan(0);
    console.log(`cleanup analyse 20,000 boxes: ${ms.toFixed(0)} ms, ${r.contactEdges} contacts`);
    expect(ms).toBeLessThan(1500 * SLACK);
  });
});
