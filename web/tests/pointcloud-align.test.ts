import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { applyFrame, autoAlign, cloudFrame, mapAxes, mapPositions, projectToViewer, viewerToProject } from '../src/pointcloud/align';
import type { Vec3 } from '../src/pointcloud/types';

const side = JSON.parse(readFileSync(new URL('../public/models/building.json', import.meta.url).pathname, 'utf8')) as {
  originShift: Vec3;
  elements: Array<{ id: number; ifcClass: string; bounds: number[] }>;
};
const SHIFT = side.originShift;
const duct = side.elements.find((e) => e.ifcClass === 'IfcDuctSegment')!;

describe('coordinate mapping (IFC project <-> viewer)', () => {
  it('maps project coordinates to the viewer as v = (x - sx, z - sz, -(y - sy))', () => {
    expect(projectToViewer([10, 20, 30], [1, 2, 3])).toEqual([9, 27, -18]);
    expect(mapAxes([1, 2, 3], 'project')).toEqual([1, 3, -2]);
    expect(mapAxes([1, 2, 3], 'viewer')).toEqual([1, 2, 3]);
  });
  it('round trips', () => {
    const p: Vec3 = [123.456, -78.9, 4.25];
    const back = viewerToProject(projectToViewer(p, SHIFT), SHIFT);
    back.forEach((v, i) => expect(v).toBeCloseTo(p[i]!, 12));
  });
  it('matches a real element: the duct bounds, written in project coordinates, land on its viewer bounds', () => {
    const b = duct.bounds; // viewer frame, from the converter
    // project-frame corners of the element as an IFC tool would report them
    const proj: Vec3[] = [];
    for (const x of [b[0]!, b[3]!]) for (const y of [b[1]!, b[4]!]) for (const z of [b[2]!, b[5]!]) proj.push(viewerToProject([x, y, z], SHIFT));
    // independent expectation of the IFC bounds: x + sx, -z + sy, y + sz
    const ifcMin: Vec3 = [b[0]! + SHIFT[0], -b[5]! + SHIFT[1], b[1]! + SHIFT[2]];
    const ifcMax: Vec3 = [b[3]! + SHIFT[0], -b[2]! + SHIFT[1], b[4]! + SHIFT[2]];
    expect(Math.min(...proj.map((p) => p[1]))).toBeCloseTo(ifcMin[1], 9);
    expect(Math.max(...proj.map((p) => p[2]))).toBeCloseTo(ifcMax[2], 9);
    // a cloud of those corners, as a reader gives it: double origin + Float32 relative positions
    const origin = proj[0]!;
    const rel = new Float32Array(proj.length * 3);
    proj.forEach((p, i) => rel.set([p[0] - origin[0], p[1] - origin[1], p[2] - origin[2]], i * 3));
    const mn: Vec3 = [Math.min(...proj.map((p) => p[0])), Math.min(...proj.map((p) => p[1])), Math.min(...proj.map((p) => p[2]))];
    const mx: Vec3 = [Math.max(...proj.map((p) => p[0])), Math.max(...proj.map((p) => p[1])), Math.max(...proj.map((p) => p[2]))];
    const frame = cloudFrame({ origin, boundsMin: mn, boundsMax: mx }, { mode: 'project', shift: SHIFT, offset: [0, 0, 0], rotationDeg: 0 });
    const g = mapPositions(rel, 'project');
    const out: Vec3[] = proj.map((_, i) => applyFrame(frame, [g[i * 3]!, g[i * 3 + 1]!, g[i * 3 + 2]!]));
    const vmin = [0, 1, 2].map((a) => Math.min(...out.map((p) => p[a]!)));
    const vmax = [0, 1, 2].map((a) => Math.max(...out.map((p) => p[a]!)));
    vmin.forEach((v, a) => expect(v).toBeCloseTo(b[a]!, 5));
    vmax.forEach((v, a) => expect(v).toBeCloseTo(b[3 + a]!, 5));
  });
  it('viewer mode leaves coordinates alone', () => {
    const frame = cloudFrame({ origin: [1, 2, 3], boundsMin: [1, 2, 3], boundsMax: [3, 4, 5] }, { mode: 'viewer', shift: SHIFT, offset: [0, 0, 0], rotationDeg: 0 });
    expect(applyFrame(frame, [1, 1, 1])).toEqual([2, 3, 4]);
  });
  it('offset translates and rotation turns about the vertical axis through the bounds centre', () => {
    const info = { origin: [0, 0, 0] as Vec3, boundsMin: [0, 0, 0] as Vec3, boundsMax: [2, 2, 2] as Vec3 };
    const f = cloudFrame(info, { mode: 'viewer', shift: SHIFT, offset: [0.5, 0.25, -1], rotationDeg: 90 });
    // centre (1,1,1) stays at centre + offset; (2,1,1) turns to centre + (0,0,-1) (rotation about +Y, right handed)
    const c = applyFrame(f, [1, 1, 1]);
    [1.5, 1.25, 0].forEach((v, i) => expect(c[i]).toBeCloseTo(v, 12));
    const e = applyFrame(f, [2, 1, 1]);
    [1.5, 1.25, -1].forEach((v, i) => expect(e[i]).toBeCloseTo(v, 12));
    // rotating a project cloud by +90 about IFC Z sends IFC +x to IFC +y, which is viewer -z
    const p = cloudFrame({ origin: [0, 0, 0], boundsMin: [0, 0, 0], boundsMax: [0, 0, 0] }, { mode: 'project', shift: [0, 0, 0], offset: [0, 0, 0], rotationDeg: 90 });
    const x = applyFrame(p, mapAxes([1, 0, 0], 'project'));
    [0, 0, -1].forEach((v, i) => expect(x[i]).toBeCloseTo(v, 12));
  });
  it('keeps float precision for a georeferenced cloud: the 6-digit offset never enters the Float32 positions', () => {
    const origin: Vec3 = [2_600_000.001, 1_200_000.002, 500];
    const world = (dx: number): Vec3 => [origin[0] + dx, origin[1], origin[2]];
    const rel = new Float32Array([0, 0, 0, 0.003, 0, 0]); // 3 mm apart
    const frame = cloudFrame({ origin, boundsMin: origin, boundsMax: world(0.003) }, { mode: 'viewer', shift: SHIFT, offset: [-origin[0], -origin[1], -origin[2]], rotationDeg: 0 });
    const a = applyFrame(frame, [rel[0]!, rel[1]!, rel[2]!]);
    const b = applyFrame(frame, [rel[3]!, rel[4]!, rel[5]!]);
    expect(b[0] - a[0]).toBeCloseTo(0.003, 6);
    expect(Math.abs(a[0]) + Math.abs(a[1]) + Math.abs(a[2])).toBeLessThan(1e-6);
  });
});

describe('auto align', () => {
  // The "model": a 6 x 2 x 3 m hollow box (only its surface matters). Distance to its surface:
  const MIN: Vec3 = [-3, 0, -1];
  const MAX: Vec3 = [3, 3, 1];
  const dist = (x: number, y: number, z: number): number => {
    const inside = x >= MIN[0] && x <= MAX[0] && y >= MIN[1] && y <= MAX[1] && z >= MIN[2] && z <= MAX[2];
    const dx = Math.max(MIN[0] - x, 0, x - MAX[0]), dy = Math.max(MIN[1] - y, 0, y - MAX[1]), dz = Math.max(MIN[2] - z, 0, z - MAX[2]);
    if (!inside) return Math.hypot(dx, dy, dz);
    return Math.min(x - MIN[0], MAX[0] - x, y - MIN[1], MAX[1] - y, z - MIN[2], MAX[2] - z);
  };
  /** Points on the surface of the box, rotated about the vertical by `deg` and moved by `move`. */
  const cloud = (deg: number, move: Vec3): Float32Array => {
    const pts: number[] = [];
    const c = Math.cos((deg * Math.PI) / 180), s = Math.sin((deg * Math.PI) / 180);
    for (let i = 0; i <= 24; i++) for (let j = 0; j <= 12; j++) {
      const u = MIN[0] + (i / 24) * 6, w = MIN[2] + (j / 12) * 2;
      for (const y of [0, 3]) pts.push(u, y, w); // floor and ceiling
    }
    for (let i = 0; i <= 24; i++) for (let k = 0; k <= 8; k++) for (const z of [-1, 1]) pts.push(MIN[0] + (i / 24) * 6, (k / 8) * 3, z);
    for (let j = 0; j <= 12; j++) for (let k = 0; k <= 8; k++) for (const x of [-3, 3]) pts.push(x, (k / 8) * 3, MIN[2] + (j / 12) * 2);
    const out = new Float32Array(pts.length);
    for (let i = 0; i < pts.length; i += 3) {
      const x = pts[i]!, y = pts[i + 1]!, z = pts[i + 2]!;
      out[i] = c * x + s * z + move[0];
      out[i + 1] = y + move[1];
      out[i + 2] = -s * x + c * z + move[2];
    }
    return out;
  };
  const centreOf = (a: Float32Array): Vec3 => {
    const mn = [Infinity, Infinity, Infinity], mx = [-Infinity, -Infinity, -Infinity];
    for (let i = 0; i < a.length; i += 3) for (let k = 0; k < 3; k++) { mn[k] = Math.min(mn[k]!, a[i + k]!); mx[k] = Math.max(mx[k]!, a[i + k]!); }
    return [0, 1, 2].map((k) => (mn[k]! + mx[k]!) / 2) as Vec3;
  };
  const relTo = (a: Float32Array, c: Vec3): Float32Array => a.map((v, i) => v - c[i % 3]!);

  it('matches bounds centres for a pure shift', () => {
    const a = cloud(0, [100, 5, -40]);
    const c = centreOf(a);
    const r = autoAlign({ pivot: c, samplesRelPivot: relTo(a, c), modelMin: MIN, modelMax: MAX, distance: dist, rotate: true });
    expect(r.rotationDeg).toBe(0);
    expect(r.offset[0]).toBeCloseTo(0 - c[0], 9);
    expect(r.offset[1]).toBeCloseTo(1.5 - c[1], 9);
    expect(r.scores.map((s) => s.deg)).toEqual([0, 90, 180, 270]);
    expect(r.scores[0]!.median).toBeLessThan(1e-5);
    expect(r.description).toMatch(/bounds centre/);
  });
  it('finds a quarter turn', () => {
    for (const deg of [90, 270]) {
      const a = cloud(deg, [7, 0, 9]);
      const c = centreOf(a);
      const r = autoAlign({ pivot: c, samplesRelPivot: relTo(a, c), modelMin: MIN, modelMax: MAX, distance: dist, rotate: true });
      // 90 and 270 look the same for a box with a 180 degree symmetry; either undoes the cloud's rotation
      expect([90, 270]).toContain(r.rotationDeg);
      expect(r.scores.find((s) => s.deg === r.rotationDeg)!.median).toBeLessThan(1e-3);
    }
  });
  it('skips the rotation search when asked', () => {
    const a = cloud(90, [0, 0, 0]);
    const c = centreOf(a);
    const r = autoAlign({ pivot: c, samplesRelPivot: relTo(a, c), modelMin: MIN, modelMax: MAX, distance: dist, rotate: false });
    expect(r.rotationDeg).toBe(0);
    expect(r.scores).toEqual([]);
  });
});
