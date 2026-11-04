import { describe, expect, it } from 'vitest';
import {
  EDGE_BAND, allRegions, axisDragMetres, cubeCells, faceLabelAxes, isUnrolled, naturalUp, offsetThrough, planeAxes, planeSettingsFor, regionDirection,
  regionKind, regionName, regionNear, regionView, rollView, rotateAbout, rotatePlaneAxis, ringAngle, snapAngle, turnView, turntableOffset, viewBasis, wrapAngle,
} from '../src/gizmo/maths';
import type { Region, V3, View } from '../src/gizmo/maths';
import { sectionPlane } from '../src/section/maths';
import { mergeSection, defaultSection, cloneSection } from '../src/section/config';
import { viewDirection } from '../src/input/navigation';

const close = (a: readonly number[], b: readonly number[], eps = 1e-9): void => {
  for (let i = 0; i < a.length; i++) expect(a[i]!, `component ${i} of [${a.join(', ')}] vs [${b.join(', ')}]`).toBeCloseTo(b[i]!, -Math.log10(eps));
};
const D = Math.PI / 180;

describe('cube regions', () => {
  it('has 6 faces, 12 edges and 8 corners', () => {
    const r = allRegions();
    expect(r.length).toBe(26);
    expect(r.filter((x) => regionKind(x) === 'face').length).toBe(6);
    expect(r.filter((x) => regionKind(x) === 'edge').length).toBe(12);
    expect(r.filter((x) => regionKind(x) === 'corner').length).toBe(8);
  });

  it('names regions vertical first', () => {
    expect(regionName([0, 1, 0])).toBe('Top');
    expect(regionName([0, 0, -1])).toBe('Back');
    expect(regionName([1, 0, 1])).toBe('Front Right');
    expect(regionName([-1, 1, 1])).toBe('Top Front Left');
  });

  it('gives the same face directions as the keyboard views (Y up, front on +Z)', () => {
    const faces: Array<[Region, Parameters<typeof viewDirection>[0]]> = [
      [[0, 0, 1], 'front'], [[0, 0, -1], 'back'], [[1, 0, 0], 'right'], [[-1, 0, 0], 'left'], [[0, 1, 0], 'top'], [[0, -1, 0], 'bottom'], [[1, 1, 1], 'iso'],
    ];
    for (const [r, kind] of faces) {
      const v = viewDirection(kind);
      close(regionDirection(r), [v.x, v.y, v.z]);
    }
  });

  it('maps faces, edges and corners to a direction and an up vector', () => {
    expect(regionView([0, 0, 1])).toEqual({ direction: [0, 0, 1], up: [0, 1, 0] });
    expect(regionView([1, 0, 0])).toEqual({ direction: [1, 0, 0], up: [0, 1, 0] });
    // Top: the back (north, -Z) at the top of the screen; bottom: the front at the top.
    expect(regionView([0, 1, 0])).toEqual({ direction: [0, 1, 0], up: [0, 0, -1] });
    expect(regionView([0, -1, 0])).toEqual({ direction: [0, -1, 0], up: [0, 0, 1] });
    const e = regionView([0, 1, 1]);
    close(e.direction, [0, Math.SQRT1_2, Math.SQRT1_2]);
    close(e.up, [0, Math.SQRT1_2, -Math.SQRT1_2]);
    const c = regionView([1, 1, 1]);
    const s = 1 / Math.sqrt(3);
    close(c.direction, [s, s, s]);
    expect(c.up[0]! * c.direction[0]! + c.up[1]! * c.direction[1]! + c.up[2]! * c.direction[2]!).toBeCloseTo(0, 12);
    expect(c.up[1]).toBeGreaterThan(0);
    for (const r of allRegions()) expect(isUnrolled(regionView(r)), regionName(r)).toBe(true);
  });

  it('builds a right-handed camera basis: front view looks along -Z with +X to the right', () => {
    const b = viewBasis(regionView([0, 0, 1]));
    expect(b.right).toEqual([1, 0, 0]);
    const t = viewBasis(regionView([0, 1, 0]));
    expect(t.right).toEqual([1, 0, 0]);
    expect(t.up).toEqual([0, 0, -1]);
  });

  it('finds the region of the current view', () => {
    expect(regionNear([0, 0, 1])).toEqual([0, 0, 1]);
    expect(regionNear([0.001, 1, 0.0005])).toEqual([0, 1, 0]);
    expect(regionNear([0.3, 0.2, 1])).toBeNull();
  });
});

describe('roll and quarter turns', () => {
  const front: View = { direction: [0, 0, 1], up: [0, 1, 0] };

  it('rolls the picture clockwise: the camera up turns to the screen left', () => {
    const r = rollView(front, 1);
    expect(r.direction).toEqual([0, 0, 1]);
    close(r.up, [-1, 0, 0]);
    // World up now points to the screen right: the picture turned clockwise.
    close(viewBasis(r).right, [0, 1, 0]);
    close(rollView(front, -1).up, [1, 0, 0]);
    expect(isUnrolled(r)).toBe(false);
  });

  it('comes back after 4 rolls, and a roll of a top view stays unrolled for the turntable', () => {
    let v = front;
    for (let i = 0; i < 4; i++) v = rollView(v, 1);
    close(v.up, front.up);
    const top = rollView(regionView([0, 1, 0]), 1);
    close(top.up, [-1, 0, 0]);
    expect(isUnrolled(top)).toBe(true);
    // The turntable camera sits a hair away from the screen up, so its azimuth gives that up.
    const off = turntableOffset(top);
    expect(off[0]).toBeGreaterThan(0);
    expect(off[1]).toBeGreaterThan(0.9999);
    expect(turntableOffset(front)).toEqual([0, 0, 1]);
  });

  it('turns a quarter about the vertical: front to right, top up vector follows', () => {
    const r = turnView(front, 1);
    close(r.direction, [1, 0, 0]);
    close(r.up, [0, 1, 0]);
    close(turnView(front, -1).direction, [-1, 0, 0]);
    const t = turnView(regionView([0, 1, 0]), 1);
    close(t.direction, [0, 1, 0]);
    close(t.up, [-1, 0, 0]);
  });

  it('rotates with the right hand rule', () => {
    close(rotateAbout([1, 0, 0], [0, 0, 1], Math.PI / 2), [0, 1, 0]);
    close(rotateAbout([1, 2, 3], [1, 1, 1], 2 * Math.PI), [1, 2, 3]);
  });
});

describe('cube drawing', () => {
  it('shows 1 face from the front and 3 faces from a corner, each split in 9 cells', () => {
    const b = viewBasis(regionView([0, 0, 1]));
    const cells = cubeCells(b.right, b.up, b.back);
    expect(cells.length).toBe(9);
    expect(cells.every((c) => c.face[2] === 1)).toBe(true);
    const centre = cells.find((c) => c.region[0] === 0 && c.region[1] === 0)!;
    const t = 1 - 2 * EDGE_BAND;
    expect(centre.points.map((p) => p.map((x) => +x.toFixed(9)))).toEqual([[-t, t], [t, t], [t, -t], [-t, -t]].map((p) => p.map((x) => +x.toFixed(9))));
    // The top edge strip of the front face sits above the centre on screen (y down) and belongs to region Top Front.
    const top = cells.find((c) => c.region[1] === 1 && c.region[0] === 0)!;
    expect(top.region).toEqual([0, 1, 1]);
    expect(Math.max(...top.points.map((p) => p[1]))).toBeLessThanOrEqual(-t + 1e-9);
    const iso = viewBasis(regionView([1, 1, 1]));
    const isoCells = cubeCells(iso.right, iso.up, iso.back);
    expect(isoCells.length).toBe(27);
    expect(new Set(isoCells.map((c) => c.face.join(','))).size).toBe(3);
    // Sorted far to near.
    for (let i = 1; i < isoCells.length; i++) expect(isoCells[i]!.depth).toBeGreaterThanOrEqual(isoCells[i - 1]!.depth);
  });

  it('places face labels upright in their own view', () => {
    expect(faceLabelAxes([0, 0, 1])).toEqual({ u: [1, 0, 0], v: [0, 1, 0] });
    expect(faceLabelAxes([0, 1, 0])).toEqual({ u: [1, 0, 0], v: [0, 0, -1] });
    expect(faceLabelAxes([1, 0, 0])).toEqual({ u: [0, 0, -1], v: [0, 1, 0] });
    expect(faceLabelAxes([0, 0, -1])).toEqual({ u: [-1, 0, 0], v: [0, 1, 0] });
  });
});

describe('handle drags', () => {
  it('projects a screen move on the screen direction of the axis', () => {
    // 1 m along the normal spans 50 px to the right.
    expect(axisDragMetres([25, 0], [50, 0])).toBeCloseTo(0.5, 12);
    expect(axisDragMetres([0, 40], [50, 0])).toBeCloseTo(0, 12);
    expect(axisDragMetres([-30, -40], [30, 40])).toBeCloseTo(-1, 12);
    expect(axisDragMetres([10, 10], [0, 0])).toBeNull();
  });

  it('measures ring angles about the axis', () => {
    // Ring square to +Z through the origin, angle measured from +X; ray straight down -Z through (0, 2, 5).
    expect(ringAngle([0, 2, 5], [0, 0, -1], [0, 0, 0], [0, 0, 1], [1, 0, 0])).toBeCloseTo(Math.PI / 2, 12);
    expect(ringAngle([-1, 0, 5], [0, 0, -1], [0, 0, 0], [0, 0, 1], [1, 0, 0])).toBeCloseTo(Math.PI, 12);
    expect(ringAngle([0, 0, 5], [1, 0, 0], [0, 0, 0], [0, 0, 1], [1, 0, 0])).toBeNull();
    expect(wrapAngle(3 * Math.PI / 2)).toBeCloseTo(-Math.PI / 2, 12);
  });

  it('snaps rotations to 15 degrees unless free', () => {
    expect(snapAngle(7 * D)).toBe(0);
    expect(snapAngle(8 * D)).toBeCloseTo(15 * D, 12);
    expect(snapAngle(-52 * D)).toBeCloseTo(-45 * D, 12);
    expect(snapAngle(52 * D, 15, true)).toBeCloseTo(52 * D, 12);
    expect(snapAngle(52 * D, 0)).toBeCloseTo(52 * D, 12);
  });

  it('turns the plane axis and keeps the plane through the pivot', () => {
    const n = rotatePlaneAxis([0, 1, 0], [1, 0, 0], 45 * D);
    close(n, [0, Math.SQRT1_2, Math.SQRT1_2]);
    expect(rotatePlaneAxis([0, 1, 0], [1, 0, 0], 90 * D)).toEqual([0, 0, 1]);
    const centre: V3 = [1, 2, 3];
    const pivot: V3 = [1, 4, 3];
    const off = offsetThrough(centre, pivot, n);
    const p = sectionPlane('custom', centre, off, false, [0, 0, -1], n);
    // The pivot lies on the new plane.
    const d = p.normal[0] * (pivot[0] - p.point[0]) + p.normal[1] * (pivot[1] - p.point[1]) + p.normal[2] * (pivot[2] - p.point[2]);
    expect(d).toBeCloseTo(0, 12);
  });

  it('gives in-plane ring axes, horizontal first for a wall-like plane', () => {
    const a = planeAxes([1, 0, 0]);
    expect(Math.abs(a.u[1])).toBeLessThan(1e-12);
    close([a.u[0] * 1 + a.u[1] * 0 + a.u[2] * 0], [0]);
    const t = planeAxes([0, 1, 0]);
    for (const v of [t.u, t.v]) expect(Math.abs(v[1])).toBeLessThan(1e-12);
  });

  it('turns a world axis direction back into axis settings with the same cut', () => {
    expect(planeSettingsFor([0, 1, 0], 2, false)).toEqual({ axis: 'y', normal: [0, 1, 0], offset: 2, flip: false });
    const neg = planeSettingsFor([0, 0, -1], 2, false);
    expect(neg).toEqual({ axis: 'z', normal: [0, 0, 1], offset: -2, flip: true });
    const a = sectionPlane('z', [0, 0, 0], neg.offset, neg.flip, [0, 0, -1]);
    const b = sectionPlane('custom', [0, 0, 0], 2, false, [0, 0, -1], [0, 0, -1]);
    close(a.normal, b.normal);
    close(a.point, b.point);
    expect(planeSettingsFor([1, 1, 0], 1, true).axis).toBe('custom');
  });
});

describe('section config: tilted plane', () => {
  it('accepts a unit normal for axis custom and clones it', () => {
    const c = defaultSection();
    const r = mergeSection(c, { plane: { axis: 'custom', normal: [0, 3, 4] } });
    expect(r.bad).toEqual([]);
    expect(c.plane.axis).toBe('custom');
    close(c.plane.normal!, [0, 0.6, 0.8]);
    const k = cloneSection(c);
    expect(k.plane.normal).not.toBe(c.plane.normal);
    expect(mergeSection(c, { plane: { normal: [0, 0, 0] } }).bad).toEqual(['section.plane.normal']);
  });
});
