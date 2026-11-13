// Following reshaped elements (src/bcf/reproject.ts): a surface outline is projected back onto the current surface of its
// elements when a revised model lengthens, thickens, moves or removes them. The scene is a set of axis aligned boxes.

import { describe, expect, it } from 'vitest';
import type { Box6, SurfaceData, SurfacePoint } from '../src/bcf/attach';
import { REPROJECT, expectedPoint, reprojectSurface, sameBounds, targetsChanged } from '../src/bcf/reproject';
import type { ElementProbe, ProbeHit } from '../src/bcf/reproject';
import { SurfaceResolver } from '../src/markup/reprojectScene';
import type { Vec3 } from '../src/bcf/model';
import { cleanAttachment, describeAttachment } from '../src/bcf/attach';
import { boundsToIfc, toSurfaceData } from '../src/bcf/surface';

type Boxes = Record<string, Box6>;

/** Axis aligned boxes as solid elements: a ray test (both sides) and the nearest surface point. */
function boxProbe(boxes: Boxes): ElementProbe & { casts: number } {
  const probe = {
    casts: 0,
    bounds: (g: string): Box6 | null => boxes[g] ?? null,
    cast(g: string, o: Vec3, d: Vec3): ProbeHit | null {
      probe.casts++;
      const b = boxes[g];
      if (!b) return null;
      let t0 = -Infinity, t1 = Infinity, axis0 = 0, axis1 = 0;
      for (let k = 0; k < 3; k++) {
        if (Math.abs(d[k]!) < 1e-12) { if (o[k]! < b[k]! || o[k]! > b[k + 3]!) return null; continue; }
        const a = (b[k]! - o[k]!) / d[k]!, c = (b[k + 3]! - o[k]!) / d[k]!;
        const lo = Math.min(a, c), hi = Math.max(a, c);
        if (lo > t0) { t0 = lo; axis0 = k; }
        if (hi < t1) { t1 = hi; axis1 = k; }
      }
      if (t0 > t1 || t1 < 0) return null;
      const entering = t0 >= 0;
      const t = entering ? t0 : t1;
      const axis = entering ? axis0 : axis1;
      const n: Vec3 = [0, 0, 0];
      n[axis] = d[axis]! > 0 ? -1 : 1; // facing the ray origin
      if (!entering) n[axis] = -n[axis]!;
      return { point: [o[0] + d[0] * t, o[1] + d[1] * t, o[2] + d[2] * t], normal: n, distance: t };
    },
    nearest(g: string, p: Vec3): ProbeHit | null {
      const b = boxes[g];
      if (!b) return null;
      const q: Vec3 = [Math.min(Math.max(p[0], b[0]), b[3]), Math.min(Math.max(p[1], b[1]), b[4]), Math.min(Math.max(p[2], b[2]), b[5])];
      let axis = 0, worst = -1;
      for (let k = 0; k < 3; k++) {
        const ex = Math.max(b[k]! - p[k]!, p[k]! - b[k + 3]!);
        if (ex > worst) { worst = ex; axis = k; }
      }
      const n: Vec3 = [0, 0, 0];
      n[axis] = p[axis]! < b[axis]! ? -1 : 1;
      return { point: q, normal: n, distance: Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]) };
    },
  };
  return probe;
}

const WALL: Box6 = [0, 0, 0, 4, 0.3, 3];
const centre = (b: Box6): Vec3 => [(b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2];
const LIFT = 0.01;

/** An outline on the front face (y = 0, normal -y) of the wall, lifted by 0.01: a rectangle of `n` points per side. */
function outline(opts: { withNormals?: boolean; withFp?: boolean; line?: boolean } = {}): SurfaceData {
  const c = centre(WALL);
  const pts: SurfacePoint[] = [];
  const add = (x: number, z: number): void => {
    const p: Vec3 = [x, -LIFT, z];
    const sp: SurfacePoint = { e: 0, p, l: [p[0] - c[0], p[1] - c[1], p[2] - c[2]] };
    if (opts.withNormals !== false) { sp.n = [0, -1, 0]; sp.g = LIFT; }
    pts.push(sp);
  };
  if (opts.line) for (let i = 0; i < 20; i++) add(0.5 + (3 * i) / 19, 1.5);
  else {
    for (let i = 0; i < 5; i++) add(0.5 + (3 * i) / 5, 0.5);
    for (let i = 0; i < 5; i++) add(3.5, 0.5 + (2 * i) / 5);
    for (let i = 0; i < 5; i++) add(3.5 - (3 * i) / 5, 2.5);
    for (let i = 0; i < 5; i++) add(0.5, 2.5 - (2 * i) / 5);
  }
  const s: SurfaceData = { guids: ['wall'], pts, closed: !opts.line };
  if (opts.withFp !== false) s.fp = [[...WALL] as Box6];
  return s;
}

const onFace = (s: SurfaceData, y: number): boolean => s.pts.every((p) => Math.abs(p.p[1] - y) < 1e-3);
const sameP = (a: SurfaceData, b: SurfaceData): boolean => a.pts.every((p, i) => Math.hypot(p.p[0] - b.pts[i]!.p[0], p.p[1] - b.pts[i]!.p[1], p.p[2] - b.pts[i]!.p[2]) < 1e-3);
/** Where the layout puts a point: the current bounds centre plus the stored offset (anchorPoint). */
const drawn = (s: SurfaceData, b: Box6): Vec3[] => s.pts.map((p) => [centre(b)[0] + p.l![0], centre(b)[1] + p.l![1], centre(b)[2] + p.l![2]] as Vec3);

describe('expectedPoint', () => {
  const p: Vec3 = [2, 0, 1];
  it('keeps a point where it was when a side of the element stayed', () => {
    expect(expectedPoint(p, WALL, [0, 0, 0, 7, 0.3, 3])).toEqual(p);
    expect(expectedPoint(p, WALL, [-3, 0, 0, 4, 0.3, 3])).toEqual(p);
  });
  it('moves it with an element that moved as a whole', () => {
    expect(expectedPoint(p, WALL, [1, 0, 0.5, 5, 0.3, 3.5])).toEqual([3, 0, 1.5]);
  });
  it('stretches it with bounds that changed on both sides by different amounts', () => {
    const q = expectedPoint([2, 0, 1], WALL, [-1, 0, 0, 7, 0.3, 3]); // 4 m -> 8 m, centre of the old wall
    expect(q[0]).toBeCloseTo(3, 6);
  });
});

describe('targetsChanged and sameBounds', () => {
  it('compares the stored fingerprint with the current bounds', () => {
    const s = outline();
    expect(targetsChanged(s, boxProbe({ wall: WALL }))).toBe(false);
    expect(targetsChanged(s, boxProbe({ wall: [0, 0, 0, 4.001, 0.3, 3] }))).toBe(false); // within 5 mm
    expect(targetsChanged(s, boxProbe({ wall: [0, 0, 0, 7, 0.3, 3] }))).toBe(true);
    expect(targetsChanged(s, boxProbe({}))).toBe(true); // gone
    expect(targetsChanged(outline({ withFp: false }), boxProbe({ wall: [0, 0, 0, 7, 0.3, 3] }))).toBe(false); // nothing to compare
    expect(sameBounds(WALL, [...WALL] as Box6)).toBe(true);
  });
});

describe('reprojectSurface', () => {
  it('leaves an unchanged element alone', () => {
    const r = reprojectSurface(outline(), boxProbe({ wall: WALL }));
    expect(r.state).toBe('ok');
    expect(r.surface).toBeUndefined();
    expect(r.landed).toBe(r.total);
  });

  it('keeps the points on the surface of a lengthened box (the old part did not move)', () => {
    const src = outline();
    const longer: Box6 = [0, 0, 0, 7, 0.3, 3];
    const r = reprojectSurface(src, boxProbe({ wall: longer }));
    expect(r.state).toBe('ok');
    expect(r.landed).toBe(r.total);
    expect(r.surface).toBeDefined();
    expect(sameP(r.surface!, src)).toBe(true); // the outline stays around what it was drawn around
    expect(onFace(r.surface!, -LIFT)).toBe(true);
    // The offsets are in the frame of the new bounds, so the layout draws the points where they are.
    r.surface!.pts.forEach((p, i) => expect(Math.hypot(...(drawn(r.surface!, longer)[i]!.map((v, k) => v - p.p[k]!) as Vec3))).toBeLessThan(1e-3));
    expect(r.surface!.fp![0]).toEqual(longer);
    // The old way (follow the bounds centre) would have put the outline 1.5 m off along the wall.
    const rigid = drawn(src, longer);
    expect(Math.abs(rigid[0]![0] - src.pts[0]!.p[0])).toBeCloseTo(1.5, 6);
  });

  it('handles a box lengthened at both ends and one stretched unevenly', () => {
    for (const b of [[-1.5, 0, 0, 5.5, 0.3, 3], [-1, 0, 0, 7, 0.3, 3]] as Box6[]) {
      const r = reprojectSurface(outline(), boxProbe({ wall: b }));
      expect(r.state).toBe('ok');
      expect(r.landed).toBe(r.total);
      expect(onFace(r.surface!, -LIFT)).toBe(true);
    }
  });

  it('moves the points onto the face of a thicker wall', () => {
    const r = reprojectSurface(outline(), boxProbe({ wall: [0, -0.1, 0, 4, 0.3, 3] }));
    expect(r.state).toBe('ok');
    expect(r.landed).toBe(r.total);
    expect(onFace(r.surface!, -0.1 - LIFT)).toBe(true);
  });

  it('follows an element that moved a little (rigid move)', () => {
    const moved: Box6 = [0.5, 0, 0.2, 4.5, 0.3, 3.2];
    const r = reprojectSurface(outline(), boxProbe({ wall: moved }));
    expect(r.state).toBe('ok');
    expect(r.landed).toBe(r.total);
    expect(r.surface!.pts[0]!.p[0]).toBeCloseTo(1.0, 3);
    expect(r.surface!.pts[0]!.p[2]).toBeCloseTo(0.7, 3);
  });

  it('detaches an outline whose element was removed', () => {
    const r = reprojectSurface(outline(), boxProbe({}));
    expect(r.state).toBe('detached');
    expect(r.missing).toEqual(['wall']);
    expect(r.surface).toBeUndefined();
  });

  it('detaches an outline whose element moved far away', () => {
    const far: Box6 = [100, 0, 0, 104, 0.3, 3];
    const r = reprojectSurface(outline(), boxProbe({ wall: far }));
    expect(r.state).toBe('detached');
    expect(r.landed).toBe(0);
  });

  it('keeps an outline when up to 30% of the points cannot land, detaches it beyond that', () => {
    // 20 points along x from 0.5 to 3.5; the wall now ends at x = 2.9: the points past about 3.05 do not land (15%).
    const few = reprojectSurface(outline({ line: true }), boxProbe({ wall: [0, 0, 0, 2.9, 0.3, 3] }));
    expect(few.state).toBe('ok');
    expect(few.landed / few.total).toBeGreaterThan(0.7);
    expect(few.landed).toBeLessThan(few.total);
    // The wall ends at x = 2: 45% of the points are off it.
    const many = reprojectSurface(outline({ line: true }), boxProbe({ wall: [0, 0, 0, 2, 0.3, 3] }));
    expect(many.state).toBe('detached');
    expect(many.landed / many.total).toBeLessThan(1 - REPROJECT.maxLost);
  });

  it('casts along the authoring camera direction for data without stored normals', () => {
    const longer: Box6 = [0, 0, 0, 7, 0.3, 3];
    const r = reprojectSurface(outline({ withNormals: false }), boxProbe({ wall: longer }), { fallbackDir: [0, 1, 0] });
    expect(r.state).toBe('ok');
    expect(r.landed).toBe(r.total);
    expect(onFace(r.surface!, -LIFT)).toBe(true);
  });

  it('data without a fingerprint follows the bounds centre as before when that lands, and still detaches a removed element', () => {
    const longer: Box6 = [0, 0, 0, 7, 0.3, 3];
    const old = outline({ withFp: false });
    const r = reprojectSurface(old, boxProbe({ wall: longer }));
    expect(r.state).toBe('ok');
    expect(r.surface!.pts[0]!.p[0]).toBeCloseTo(old.pts[0]!.p[0] + 1.5, 3);
    expect(reprojectSurface(old, boxProbe({})).state).toBe('detached');
  });
});

describe('SurfaceResolver', () => {
  const appOf = (loaded: object | null) => ({ loaded }) as never;
  it('caches the result per model load: no ray is cast again for the same outline', () => {
    const probe = boxProbe({ wall: [0, 0, 0, 7, 0.3, 3] });
    const app = appOf({});
    const res = new SurfaceResolver(app, () => probe);
    const s = outline();
    const a = res.resolve(s, { revised: false });
    expect(a).not.toBe(s);
    const casts = probe.casts;
    expect(casts).toBeGreaterThan(0);
    for (let i = 0; i < 5; i++) expect(res.resolve(s, { revised: false })).toBe(a);
    expect(probe.casts).toBe(casts);
    // A new model load starts a new cache (and a new probe).
    (app as unknown as { loaded: object }).loaded = {};
    res.resolve(s, { revised: false });
    expect(probe.casts).toBeGreaterThan(casts);
  });

  it('does nothing for an unchanged outline on the same model, and re-projects on a revised model', () => {
    const probe = boxProbe({ wall: WALL });
    const res = new SurfaceResolver(appOf({}), () => probe);
    const s = outline();
    expect(res.resolve(s, { revised: false })).toBe(s);
    expect(probe.casts).toBe(0);
    res.resolve(s, { revised: true });
    expect(probe.casts).toBeGreaterThan(0);
  });

  it('answers null (detached) for a removed element and returns the stored data without a model', () => {
    const s = outline();
    expect(new SurfaceResolver(appOf({}), () => boxProbe({})).resolve(s, { revised: true })).toBeNull();
    expect(new SurfaceResolver(appOf(null), () => boxProbe({})).resolve(s, { revised: true })).toBe(s);
  });
});

describe('what is stored at attach time (additive, backward compatible)', () => {
  it('toSurfaceData stores the normal, the lift and the bounds of each target (IFC frame)', () => {
    const shift: Vec3 = [10, 20, 1];
    // Viewer frame: x right, y up, z towards the viewer; the wall is 4 m long in x, 3 m high, 0.3 m deep in z.
    const bounds = [0, 0, -0.3, 4, 3, 0];
    const cleaned = { bad: 0, pts: [0.5, 1, 2].map((x) => ({ point: [x, 1.5, 0] as Vec3, normal: [0, 0, 1] as Vec3, element: 7, distance: 5, snapped: false })) };
    const sd = toSurfaceData(cleaned, { guidOf: () => 'wall', centreOf: () => [2, 1.5, -0.15], boundsOf: () => bounds, shift }, false)!;
    expect(sd.guids).toEqual(['wall']);
    expect(sd.pts[0]!.n).toEqual([0, -1, 0]); // viewer +z is IFC -y
    expect(sd.pts[0]!.g).toBeCloseTo(0.01, 4);
    expect(sd.fp).toEqual([boundsToIfc(bounds, shift)]);
    expect(sd.fp![0]).toEqual([10, 20, 1, 14, 20.3, 4]);
    // Without a bounds lookup the data is what it was before.
    const old = toSurfaceData(cleaned, { guidOf: () => 'wall', centreOf: () => [2, 1.5, -0.15], shift }, false)!;
    expect(old.fp).toBeUndefined();
  });

  it('cleanAttachment keeps the new fields and accepts data without them', () => {
    const base = { kind: 'surface', surface: { guids: ['a'], closed: false, pts: [{ e: 0, p: [1, 2, 3], l: [0, 0, 1] }, { e: 0, p: [2, 2, 3], l: [1, 0, 1] }] } };
    const old = cleanAttachment(base)!;
    expect(old.surface!.fp).toBeUndefined();
    expect(old.surface!.pts[0]!.n).toBeUndefined();
    const full = cleanAttachment({ ...base, surface: { ...base.surface, fp: [[0, 0, 0, 1, 1, 1]], pts: base.surface.pts.map((q) => ({ ...q, n: [0, 0, 1], g: 0.01 })) } })!;
    expect(full.surface!.fp).toEqual([[0, 0, 0, 1, 1, 1]]);
    expect(full.surface!.pts[1]).toMatchObject({ n: [0, 0, 1], g: 0.01 });
    // A fingerprint that does not fit the element list is dropped, not trusted.
    expect(cleanAttachment({ ...base, surface: { ...base.surface, fp: [[0, 0, 0, 1, 1, 1], [0, 0, 0, 1, 1, 1]] } })!.surface!.fp).toBeUndefined();
    expect(cleanAttachment({ ...base, surface: { ...base.surface, fp: [[0, 0, 'x', 1, 1, 1]] } })!.surface!.fp).toBeUndefined();
  });
});

describe('the words of a detached outline', () => {
  const att = { kind: 'surface' as const, surface: outline() };
  it('says the surface changed, and on a revised model that it may already be designed', () => {
    const plain = describeAttachment(att, { surfaceLost: true });
    expect(plain).toMatchObject({ attached: false, detached: true });
    expect(plain.text).toContain('surface changed');
    expect(plain.text).not.toContain('already be designed');
    expect(describeAttachment(att, { surfaceLost: true, revised: true }).text).toContain('may already be designed');
    expect(describeAttachment(att, { missing: ['a'], revised: true }).text).toContain('1 element missing');
    expect(describeAttachment(att, { missing: ['a'] }).text).toBe('Detached, 1 element missing. View-locked');
    expect(describeAttachment(att, {}).attached).toBe(true);
  });
});
