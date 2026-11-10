import { describe, expect, it } from 'vitest';
import { shapePointWorld, snapshotProjector } from '../src/bcf/annotate';
import type { BcfSnapshotView } from '../src/bcf/model';
import { boxCorners, ellipseInQuad, rebaseShape } from '../src/markup/layout';
import { PAGE_SIZES, pictureBox, pictureWidthFor } from '../src/markup/report';

const shift: [number, number, number] = [0, 0, 0];
const camA: BcfSnapshotView = { position: [10, -12, 6], direction: [-0.5, 0.8, -0.3], up: [0, 0, 1], fov: 45, aspect: 1.6 };
const camB: BcfSnapshotView = { position: [14, -4, 8], direction: [-0.8, 0.45, -0.4], up: [0, 0, 1], fov: 40, aspect: 1.3 };
const shape = { points: [[0.3, 0.3], [0.6, 0.55], [0.4, 0.7]] as Array<[number, number]>, depth: 14 };

describe('Update view: rebasing shapes', () => {
  it('keeps a shape on the same model points as seen from the new camera', () => {
    const r = rebaseShape(shape, camA, camB, shift)!;
    expect(r).not.toBeNull();
    const projB = snapshotProjector(camB, shift, 1000, 1000 / camB.aspect);
    shape.points.forEach(([u, v], i) => {
      const w = shapePointWorld(camA, shift, u, v, shape.depth);
      const q = projB(w);
      expect(r.points[i]![0] * 1000).toBeCloseTo(q.x, 1);
      expect(r.points[i]![1] * (1000 / camB.aspect)).toBeCloseTo(q.y, 1);
    });
    expect(r.depth).toBeGreaterThan(1);
  });

  it('is the identity for the same camera', () => {
    const r = rebaseShape(shape, camA, camA, shift)!;
    r.points.forEach((p, i) => {
      expect(p[0]).toBeCloseTo(shape.points[i]![0], 4);
      expect(p[1]).toBeCloseTo(shape.points[i]![1], 4);
    });
    expect(r.depth).toBeCloseTo(14, 1);
  });

  it('gives null when a point falls behind the new camera', () => {
    const behind: BcfSnapshotView = { ...camA, position: [10, -12, 6], direction: [0.5, -0.8, 0.3] };
    expect(rebaseShape(shape, camA, behind, shift)).toBeNull();
  });
});

describe('Update view: boxes become quads', () => {
  it('re-projects the 4 corners of a box so it keeps its place from the new camera', () => {
    const box = { points: [[0.3, 0.3], [0.6, 0.55]] as Array<[number, number]>, depth: 14 };
    const r = rebaseShape(box, camA, camB, shift, true)!;
    expect(r.points.length).toBe(4);
    const projB = snapshotProjector(camB, shift, 1000, 1000 / camB.aspect);
    boxCorners(box.points).forEach(([u, v], i) => {
      const q = projB(shapePointWorld(camA, shift, u, v, box.depth));
      expect(r.points[i]![0] * 1000).toBeCloseTo(q.x, 1);
      expect(r.points[i]![1] * (1000 / camB.aspect)).toBeCloseTo(q.y, 1);
    });
    // the same camera gives the same box back as 4 corners
    const same = rebaseShape(box, camA, camA, shift, true)!;
    expect(same.points.map((p) => p.map((x) => Math.round(x * 1e3) / 1e3))).toEqual([[0.3, 0.3], [0.6, 0.3], [0.6, 0.55], [0.3, 0.55]]);
  });
  it('maps an ellipse into a quad and keeps 2-point boxes as they are', () => {
    const c = boxCorners([[0, 0], [1, 1]]);
    const e = ellipseInQuad(c, 8);
    expect(e[0]).toEqual([1, 0.5]);
    expect(e[2]![0]).toBeCloseTo(0.5, 9);
    expect(e[2]![1]).toBeCloseTo(1, 9);
    expect(boxCorners([[1, 2], [3, 4], [5, 6], [7, 8]]).length).toBe(4);
  });
});

describe('PDF picture size', () => {
  it('derives the pixel width from dpi and the fitted picture on the page', () => {
    const box = pictureBox('A4');
    expect(box.w).toBeCloseTo(PAGE_SIZES.A4.w - 72, 6);
    // a wide picture fills the box width: 770 pt = 10.7 in
    expect(pictureWidthFor('A4', 3, 1, 200)).toBe(Math.round(((PAGE_SIZES.A4.w - 72) / 72) * 200));
    // a tall picture is limited by the box height
    const tall = pictureWidthFor('A4', 1, 1, 300);
    expect(tall).toBe(Math.round((box.h / 72) * 300));
    expect(pictureWidthFor('A4', 1.6, 1, 300)).toBeGreaterThan(pictureWidthFor('A4', 1.6, 1, 200));
    expect(pictureWidthFor('Letter', 1.6, 1, 200)).not.toBe(pictureWidthFor('A4', 1.6, 1, 200));
  });
});
