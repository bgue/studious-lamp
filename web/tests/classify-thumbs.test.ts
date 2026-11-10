// The maths behind the thumbnails: which neighbours are drawn, the frame of each view, the scale bar. The drawing itself uses WebGL and is
// covered by bench/smoke-classify-local.mjs. No picture ever enters params, links, views or packed pages (see classify-settings.test.ts).

import { describe, expect, it } from 'vitest';
import { FRAME_MARGIN, MAX_NEIGHBOURS, fitFrame, formatMetres, neighbourIds, neighbourMargin, scaleBarMetres, thumbKey, viewsOf } from '../src/classify/thumbs';
import type { Bounds6 } from '../src/classify/thumbs';

const box = (x: number, y: number, z: number, w = 1, h = 1, d = 1): Bounds6 => [x, y, z, x + w, y + h, z + d];
const src = (boxes: Array<Bounds6 | null>) => ({ bounds: (id: number) => boxes[id] ?? null, ids: () => boxes.map((_, i) => i) });

describe('neighbours', () => {
  it('takes the elements whose bounds lie within the margin, nearest first, and leaves out the element, far ones and empty ones', () => {
    const s = src([box(0, 0, 0), box(1.2, 0, 0), box(0, 0, 1.0), box(10, 0, 0), null, box(0.5, 0.5, 0.5), [1, 1, 1, 0, 0, 0]]);
    // margin: half the largest dimension, at least 0.5 m
    expect(neighbourMargin(box(0, 0, 0))).toBe(0.5);
    expect(neighbourIds(s, 0)).toEqual([5, 2, 1]); // 5 overlaps (gap 0), 2 touches (0), 1 is 0.2 away; then ordered by the distance of the centres
    expect(neighbourIds(s, 0, { margin: 0.1 })).toEqual([5, 2]);
    expect(neighbourIds(s, 3)).toEqual([]);
    expect(neighbourIds(s, 4)).toEqual([]); // no geometry
  });
  it('caps the neighbours at 40 and keeps the nearest', () => {
    const boxes: Bounds6[] = [box(0, 0, 0)];
    for (let i = 0; i < 100; i++) boxes.push(box(0.1 + i * 0.001, 0, 0.1 + i * 0.001));
    const ids = neighbourIds(src(boxes), 0, { margin: 5 });
    expect(ids).toHaveLength(MAX_NEIGHBOURS);
    expect(MAX_NEIGHBOURS).toBe(40);
    // all overlap the element (gap 0), so they are ordered by the distance of their centres
    expect(ids.slice(0, 3)).toEqual([1, 2, 3]);
  });
  it('is the same every time', () => {
    const s = src(Array.from({ length: 30 }, (_, i) => box(i * 0.3, 0, 0)));
    expect(neighbourIds(s, 10)).toEqual(neighbourIds(s, 10));
  });
});

describe('the frame and the scale bar', () => {
  it('fits the element plus a margin in each view, square', () => {
    const b = box(0, 0, 0, 4, 1, 2); // 4 wide (x), 1 high (y), 2 deep (z)
    const [plan, front, axo] = viewsOf(3);
    const p = fitFrame(b, plan!);
    expect(p.half).toBeCloseTo((4 / 2) * (1 + 2 * FRAME_MARGIN), 9); // plan: x by z, the larger is 4
    expect(p.cx).toBeCloseTo(Math.abs(p.cx) < 1e-9 ? 0 : p.cx, 9);
    const f = fitFrame(b, front!);
    expect(f.half).toBeCloseTo((4 / 2) * (1 + 2 * FRAME_MARGIN), 9); // front: x by y
    const a = fitFrame(b, axo!);
    expect(a.half).toBeGreaterThan(p.half * 0.9);
    expect(a.half).toBeLessThan((Math.hypot(4, 1, 2) / 2) * (1 + 2 * FRAME_MARGIN) + 1e-9);
  });
  it('does not collapse for a flat or tiny element', () => {
    expect(fitFrame(box(0, 0, 0, 0, 0, 0), viewsOf(1)[0]!).half).toBeGreaterThan(0.02);
  });
  it('offers 1 to 3 views: plan, front, axonometric', () => {
    expect(viewsOf(1).map((v) => v.name)).toEqual(['plan']);
    expect(viewsOf(2).map((v) => v.name)).toEqual(['plan', 'front']);
    expect(viewsOf(3).map((v) => v.name)).toEqual(['plan', 'front', 'axonometric']);
    expect(viewsOf(9)).toHaveLength(3);
    expect(viewsOf(0)).toHaveLength(1);
  });
  it('picks a round scale bar of at most a third of the width', () => {
    expect(scaleBarMetres(10)).toBe(2);
    expect(scaleBarMetres(3)).toBe(1);
    expect(scaleBarMetres(0.3)).toBe(0.1);
    expect(scaleBarMetres(60)).toBe(20);
    for (const w of [0.05, 0.4, 1, 2.5, 7, 12, 90, 300]) {
      const m = scaleBarMetres(w);
      expect(m).toBeLessThanOrEqual(w / 3 + 1e-12);
      expect(m * 3).toBeGreaterThan(w / 3);
    }
    expect(formatMetres(2)).toBe('2 m');
    expect(formatMetres(0.1)).toBe('10 cm');
    expect(formatMetres(0.005)).toBe('5 mm');
  });
  it('has a key that changes with every setting that changes a picture', () => {
    const k = (m: 'element' | 'element+neighbours', views: number, size: number) => thumbKey({ mode: m, views, size });
    expect(new Set([k('element', 1, 384), k('element+neighbours', 1, 384), k('element', 2, 384), k('element', 1, 512)]).size).toBe(4);
  });
});
