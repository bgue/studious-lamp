// The maths behind the pictures: the context box and which elements are in it, the clipping planes, the frame of each picture, the scale bar, the
// silhouette edges of the line drawing and the note that tells the model what the pictures are. The drawing itself uses WebGL and is covered by
// bench/smoke-classify-local.mjs. No picture ever enters params, links, views or packed pages (see classify-settings.test.ts).

import { describe, expect, it } from 'vitest';
import {
  FRAME_MARGIN, MAX_CONTEXT, MIN_MARGIN_M, boxPlanes, contextBox, contextIds, contextMargin, fitFrame, formatMetres, pictureKinds, pictureNote, scaleBarMetres, silhouetteSegments, thumbKey,
} from '../src/classify/thumbs';
import type { Bounds6, ThumbSettings } from '../src/classify/thumbs';

const box = (x: number, y: number, z: number, w = 1, h = 1, d = 1): Bounds6 => [x, y, z, x + w, y + h, z + d];
const src = (boxes: Array<Bounds6 | null>) => ({ bounds: (id: number) => boxes[id] ?? null, ids: () => boxes.map((_, i) => i) });
const S: ThumbSettings = { mode: 'both', style: 'render', plan: false, size: 384, margin: 25 };

describe('the context box', () => {
  it('grows the bounding box by 25 % of its largest side, at least 0.5 m, on every side', () => {
    expect(contextMargin(box(0, 0, 0, 4, 1, 2), 25)).toBeCloseTo(1, 9);
    expect(contextMargin(box(0, 0, 0, 1, 1, 1), 25)).toBe(MIN_MARGIN_M);
    expect(MIN_MARGIN_M).toBe(0.5);
    expect(contextBox(box(0, 0, 0, 4, 1, 2), 25)).toEqual([-1, -1, -1, 5, 2, 3]);
    expect(contextBox(box(0, 0, 0, 1, 1, 1), 0)).toEqual([-0.5, -0.5, -0.5, 1.5, 1.5, 1.5]); // 0 % still grows by the minimum
    expect(contextBox(box(0, 0, 0, 10, 1, 1), 100)).toEqual([-10, -10, -10, 20, 11, 11]);
  });
  it('has six clipping planes whose inside is exactly the box', () => {
    const b: Bounds6 = [-1, 0, 2, 3, 4, 6];
    const planes = boxPlanes(b);
    expect(planes).toHaveLength(6);
    const inside = (p: [number, number, number]): boolean => planes.every((n) => n[0] * p[0] + n[1] * p[1] + n[2] * p[2] + n[3] >= -1e-12);
    expect(inside([0, 1, 3])).toBe(true);
    expect(inside([-1, 0, 2])).toBe(true); // on the corner
    expect(inside([3, 4, 6])).toBe(true);
    for (const out of [[-1.01, 1, 3], [3.01, 1, 3], [0, -0.01, 3], [0, 4.01, 3], [0, 1, 1.99], [0, 1, 6.01]] as Array<[number, number, number]>) expect(inside(out)).toBe(false);
  });
});

describe('the elements in the box', () => {
  it('takes every element that intersects the box (touching counts), nearest to the element first, and leaves out the element, far ones and empty ones', () => {
    const el = box(0, 0, 0);
    const bx = contextBox(el, 25); // 0.5 m around
    const s = src([el, box(1.2, 0, 0), box(0, 0, 1.0), box(10, 0, 0), null, box(0.5, 0.5, 0.5), [1, 1, 1, 0, 0, 0], box(1.5, 0, 0)]);
    // 1: 0.2 m from the element, inside the box. 2: touches the element. 5 overlaps. 3 is far. 7 starts at the box wall (touching counts).
    expect(contextIds(s, 0, bx)).toEqual([5, 2, 1, 7]);
    expect(contextIds(s, 0, bx, 2)).toEqual([5, 2]);
    expect(contextIds(s, 3, contextBox(box(10, 0, 0), 25))).toEqual([]);
    expect(contextIds(s, 4, bx)).toEqual([]); // no geometry
  });
  it('is the same every time and caps at 120', () => {
    const boxes: Bounds6[] = [box(0, 0, 0)];
    for (let i = 0; i < 200; i++) boxes.push(box(0.1 + i * 0.001, 0, 0.1 + i * 0.001));
    const ids = contextIds(src(boxes), 0, contextBox(boxes[0]!, 25));
    expect(ids).toHaveLength(MAX_CONTEXT);
    expect(MAX_CONTEXT).toBe(120);
    expect(ids.slice(0, 3)).toEqual([1, 2, 3]);
    expect(contextIds(src(boxes), 0, contextBox(boxes[0]!, 25))).toEqual(ids);
  });
});

describe('the pictures of a set', () => {
  it('sends the isolated picture first, the plan next and the context picture last', () => {
    const names = (mode: ThumbSettings['mode'], plan: boolean) => pictureKinds({ mode, plan }).map((v) => v.name);
    expect(names('isolated', false)).toEqual(['isolated']);
    expect(names('isolated', true)).toEqual(['isolated', 'plan']);
    expect(names('context', true)).toEqual(['context']);
    expect(names('both', false)).toEqual(['isolated', 'context']);
    expect(names('both', true)).toEqual(['isolated', 'plan', 'context']);
  });
  it('tells the model what each picture is, in the order they are sent', () => {
    expect(pictureNote(['isolated', 'context'], 'render')).toBe(
      'Picture 1: the element alone, a render, axonometric, with a scale bar. Picture 2: the element (orange) in its bounding box with nearby elements in grey.',
    );
    expect(pictureNote(['isolated', 'plan', 'context'], 'vector')).toBe(
      'Picture 1: the element alone, a line drawing, axonometric, with a scale bar. Picture 2: the element alone, a line drawing, seen from above. Picture 3: line drawing of the element (black) in its bounding box with nearby elements in grey.',
    );
    for (const n of [pictureNote(['isolated', 'plan', 'context'], 'vector'), pictureNote(['context'], 'render')]) for (const sentence of n.split('. ')) expect(sentence.split(' ').length).toBeLessThanOrEqual(25);
  });
});

describe('the frame and the scale bar', () => {
  it('fits the element plus a margin in each view, square', () => {
    const b = box(0, 0, 0, 4, 1, 2); // 4 wide (x), 1 high (y), 2 deep (z)
    const [axo, plan] = pictureKinds({ mode: 'isolated', plan: true });
    const p = fitFrame(b, plan!);
    expect(p.half).toBeCloseTo((4 / 2) * (1 + 2 * FRAME_MARGIN), 9); // plan: x by z, the larger is 4
    const a = fitFrame(b, axo!);
    expect(a.half).toBeGreaterThan(p.half * 0.9);
    expect(a.half).toBeLessThan((Math.hypot(4, 1, 2) / 2) * (1 + 2 * FRAME_MARGIN) + 1e-9);
  });
  it('fits the whole context box in the context picture', () => {
    const b = box(0, 0, 0, 4, 1, 2);
    const ctx = pictureKinds({ mode: 'context', plan: false })[0]!;
    const inBox = fitFrame(contextBox(b, 25), ctx);
    const alone = fitFrame(b, ctx);
    expect(inBox.half).toBeGreaterThan(alone.half);
  });
  it('does not collapse for a flat or tiny element', () => {
    expect(fitFrame(box(0, 0, 0, 0, 0, 0), pictureKinds({ mode: 'isolated', plan: false })[0]!).half).toBeGreaterThan(0.02);
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
    const keys = [
      thumbKey(S), thumbKey({ ...S, mode: 'isolated' }), thumbKey({ ...S, mode: 'context' }), thumbKey({ ...S, style: 'vector' }), thumbKey({ ...S, plan: true }),
      thumbKey({ ...S, size: 512 }), thumbKey({ ...S, margin: 50 }),
    ];
    expect(new Set(keys).size).toBe(keys.length);
  });
});

describe('silhouette edges of the line drawing', () => {
  // A cube from the front (the camera on +z): the 4 edges around the front face are silhouettes, nothing else is.
  const cube = (): { p: number[]; i: number[] } => {
    const p = [0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0, 0, 0, 1, 1, 0, 1, 1, 1, 1, 0, 1, 1];
    const i = [0, 2, 1, 0, 3, 2, 4, 5, 6, 4, 6, 7, 0, 1, 5, 0, 5, 4, 3, 7, 6, 3, 6, 2, 0, 4, 7, 0, 7, 3, 1, 2, 6, 1, 6, 5];
    return { p, i };
  };
  const count = (a: Float32Array): number => a.length / 6;
  it('finds the outline of a cube seen from the front', () => {
    const c = cube();
    const s = silhouetteSegments(c.p, c.i, [0, 0, 1]);
    expect(count(s)).toBe(4);
    for (let k = 0; k < count(s); k++) {
      const z = [s[k * 6 + 2], s[k * 6 + 5]];
      expect(z).toEqual([1, 1]); // all on the front face
    }
  });
  it('finds the sides of a round pipe (no crease edge on a smooth surface) and its end rings', () => {
    // A cylinder along x, 24 sides, seen along y: the silhouette is the two lines at z = +r and z = -r, plus the ring edges that face sideways.
    const n = 24, r = 0.1, L = 2;
    const p: number[] = [];
    for (let k = 0; k < n; k++) { const a = (k / n) * Math.PI * 2; p.push(0, Math.cos(a) * r, Math.sin(a) * r, L, Math.cos(a) * r, Math.sin(a) * r); }
    const i: number[] = [];
    for (let k = 0; k < n; k++) { const a = k * 2, b = ((k + 1) % n) * 2; i.push(a, b, a + 1, b, b + 1, a + 1); }
    const s = silhouetteSegments(p, i, [0, 1, 0]);
    // an open tube: the 2 side lines (front and back halves meet at z = +-r) and the boundary rings (every ring edge has one face)
    let sides = 0;
    for (let k = 0; k < count(s); k++) {
      const dx = Math.abs(s[k * 6]! - s[k * 6 + 3]!);
      if (dx > 1) sides++;
    }
    expect(sides).toBe(2);
    expect(count(s)).toBe(2 + 2 * n); // the 2 side lines and the 2 open rings of 24 edges
  });
  it('gives nothing for an empty or degenerate mesh', () => {
    expect(silhouetteSegments([], null, [0, 0, 1])).toHaveLength(0);
    expect(silhouetteSegments([0, 0, 0, 1, 0, 0, 2, 0, 0], null, [0, 0, 1])).toHaveLength(0);
  });
});
