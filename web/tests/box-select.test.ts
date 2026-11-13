import { describe, expect, it } from 'vitest';
import { Matrix4, PerspectiveCamera } from 'three';
import { boxModeOf, clipBounds, convexHull, pickInRect, rectOf, segmentTouchesRect } from '../src/input/boxSelect';
import type { BoxMode, PixelRect } from '../src/input/boxSelect';

// A camera at z = 10 looking down -z at a 200 x 100 pixel canvas. Boxes are given in world units; at distance 10 with a
// 90 degree field of view the view height is 20 units, so 1 unit is 5 pixels, and the centre of the canvas is (100, 50).
const W = 200;
const H = 100;
function viewProj(position: [number, number, number] = [0, 0, 10], fov = 90): { m: ArrayLike<number>; near: number } {
  const cam = new PerspectiveCamera(fov, W / H, 0.1, 100);
  cam.position.set(...position);
  cam.lookAt(0, 0, 0);
  cam.updateMatrixWorld();
  cam.updateProjectionMatrix();
  return { m: new Matrix4().multiplyMatrices(cam.projectionMatrix, cam.matrixWorldInverse).elements, near: cam.near };
}
type Box = [number, number, number, number, number, number];
function pick(boxes: Box[], rect: PixelRect, mode: BoxMode, opts: { eligible?: (i: number) => boolean; cam?: ReturnType<typeof viewProj> } = {}): number[] {
  const cam = opts.cam ?? viewProj();
  return pickInRect({ count: boxes.length, boundsOf: (i) => boxes[i], eligible: opts.eligible ?? (() => true), viewProj: cam.m, width: W, height: H, rect, mode, nearW: cam.near });
}
const cube = (x: number, y: number, z = 0, h = 1): Box => [x - h, y - h, z - h, x + h, y + h, z + h];

describe('box select: window and crossing', () => {
  // Rect from pixel (60,20) to (140,80): world x in [-8, 8] at the plane z = 0 (distance 10), y in [-6, 6].
  const rect: PixelRect = { x0: 60, y0: 20, x1: 140, y1: 80 };
  const boxes: Box[] = [
    cube(0, 0), // 0: inside
    cube(7.5, 0), // 1: straddles the right edge
    cube(-20, 0), // 2: outside, left
    cube(0, 0, 0, 30), // 3: huge, surrounds the whole rectangle
    cube(0, 5.5), // 4: straddles the top edge
    cube(5, -3), // 5: inside
  ];

  it('window picks only what lies fully inside', () => {
    expect(pick(boxes, rect, 'window')).toEqual([0, 5]);
  });

  it('crossing picks everything it touches, a surrounding element included', () => {
    expect(pick(boxes, rect, 'crossing')).toEqual([0, 1, 3, 4, 5]);
  });

  it('crossing always picks a superset of window', () => {
    const w = pick(boxes, rect, 'window');
    const c = pick(boxes, rect, 'crossing');
    for (const id of w) expect(c).toContain(id);
    expect(c.length).toBeGreaterThan(w.length);
  });

  it('a window that is too small for any element picks nothing, a crossing picks the one it hits', () => {
    const tiny: PixelRect = { x0: 99, y0: 49, x1: 101, y1: 51 };
    expect(pick(boxes, tiny, 'window')).toEqual([]);
    expect(pick(boxes, tiny, 'crossing')).toEqual([0, 3]);
  });

  it('skips elements that are not eligible (hidden, isolated away, click-through) and elements without bounds', () => {
    expect(pick(boxes, rect, 'crossing', { eligible: (i) => i !== 0 && i !== 3 })).toEqual([1, 4, 5]);
    const withHole: Array<Box | null> = [cube(0, 0), null];
    const ids = pickInRect({ count: 2, boundsOf: (i) => withHole[i], eligible: () => true, viewProj: viewProj().m, width: W, height: H, rect, mode: 'crossing', nearW: 0.1 });
    expect(ids).toEqual([0]);
  });

  it('picks nothing from behind the camera', () => {
    expect(pick([cube(0, 0, 20)], { x0: 0, y0: 0, x1: W, y1: H }, 'crossing')).toEqual([]);
    expect(pick([cube(0, 0, 20)], { x0: 0, y0: 0, x1: W, y1: H }, 'window')).toEqual([]);
  });

  it('an element that reaches behind the camera is a crossing hit, never a window hit', () => {
    const long: Box = [-1, -1, -5, 1, 1, 30]; // from in front of the camera to behind it
    const all: PixelRect = { x0: 0, y0: 0, x1: W, y1: H };
    expect(pick([long], all, 'window')).toEqual([]);
    expect(pick([long], { x0: 90, y0: 40, x1: 110, y1: 60 }, 'crossing')).toEqual([0]);
  });

  it('a diagonal element is a crossing hit only where its shape is, not in the empty corner of its bounding box', () => {
    // A box seen at 45 degrees (rotated about the view axis is not possible for an AABB), so use the hull test directly.
    const hull = convexHull([[0, 0], [100, 0], [0, 100]]);
    expect(hull.length).toBe(3);
    expect(segmentTouchesRect([0, 100], [100, 0], { x0: 80, y0: 80, x1: 100, y1: 100 })).toBe(false); // the empty corner
    expect(segmentTouchesRect([0, 100], [100, 0], { x0: 45, y0: 45, x1: 60, y1: 60 })).toBe(true);
  });

  it('an orthographic-like camera (tiny field of view) works the same', () => {
    const cam = viewProj([0, 0, 500], 2);
    const ids = pick([cube(0, 0)], { x0: 0, y0: 0, x1: W, y1: H }, 'window', { cam });
    expect(ids).toEqual([0]);
  });

  it('handles 5000 elements quickly', () => {
    const many: Box[] = [];
    for (let i = 0; i < 5000; i++) many.push(cube((i % 100) * 0.4 - 20, Math.floor(i / 100) * 0.4 - 10, (i % 7) - 3, 0.1));
    const t0 = performance.now();
    const w = pick(many, rect, 'window');
    const c = pick(many, rect, 'crossing');
    const ms = performance.now() - t0;
    expect(c.length).toBeGreaterThanOrEqual(w.length);
    expect(w.length).toBeGreaterThan(100);
    expect(ms).toBeLessThan(250);
  });
});

describe('box select: the drag', () => {
  it('left to right is a window, right to left a crossing', () => {
    expect(boxModeOf(10, 50)).toBe('window');
    expect(boxModeOf(50, 10)).toBe('crossing');
    expect(boxModeOf(30, 30)).toBe('window');
  });

  it('builds the rectangle whichever way it is dragged', () => {
    expect(rectOf(50, 70, 10, 20)).toEqual({ x0: 10, y0: 20, x1: 50, y1: 70 });
    expect(rectOf(10, 20, 50, 70)).toEqual({ x0: 10, y0: 20, x1: 50, y1: 70 });
  });
});

describe('box select: section clipping', () => {
  const whole: PixelRect = { x0: 0, y0: 0, x1: W, y1: H };
  // A section box around x in [-3, 3]: planes keep the inside.
  const sbox = [
    { normal: [1, 0, 0], point: [-3, 0, 0] }, { normal: [-1, 0, 0], point: [3, 0, 0] },
    { normal: [0, 1, 0], point: [0, -9, 0] }, { normal: [0, -1, 0], point: [0, 9, 0] },
    { normal: [0, 0, 1], point: [0, 0, -9] }, { normal: [0, 0, -1], point: [0, 0, 9] },
  ];
  const boxes: Box[] = [cube(0, 0), cube(8, 0), cube(-8, 0), cube(3.5, 0)]; // inside, outside right, outside left, straddling the +x face
  const pickClip = (clip: Array<{ normal: number[]; point: number[] }> | null, rect: PixelRect, mode: BoxMode): number[] => {
    const cam = viewProj();
    return pickInRect({ count: boxes.length, boundsOf: (i) => boxes[i], eligible: () => true, viewProj: cam.m, width: W, height: H, rect, mode, nearW: cam.near, clip });
  };
  it('without a section every element is picked', () => {
    expect(pickClip(null, whole, 'crossing')).toEqual([0, 1, 2, 3]);
  });
  it('elements wholly outside the section box are not picked, in both modes', () => {
    expect(pickClip(sbox, whole, 'crossing')).toEqual([0, 3]);
    expect(pickClip(sbox, whole, 'window')).toEqual([0, 3]);
  });
  it('elements on the removed side of a single plane are not picked', () => {
    // Keeps x >= 1: the cube at -8 and the one at 0 (x from -1 to 1, touching only x = 1) go; 8 and 3.5 stay.
    expect(pickClip([{ normal: [1, 0, 0], point: [1, 0, 0] }], whole, 'crossing')).toEqual([0, 1, 3]);
  });
  it('an oblique plane culls what lies wholly behind it', () => {
    // Keeps x + y >= 6: the cube at 3.5 reaches 4.5 + 1 = 5.5 and goes, the one at 8 stays (the cube at 0 and -8 go too).
    const s = Math.SQRT1_2;
    expect(pickClip([{ normal: [s, s, 0], point: [6, 0, 0] }], whole, 'crossing')).toEqual([1]);
  });
  it('the bounds are trimmed to the visible part for a plane parallel to an axis', () => {
    const out: number[] = [];
    expect(clipBounds([2.5, -1, -1, 4.5, 1, 1], [{ n: [-1, 0, 0], w: 3, axis: 0 }], out)).toBe(true);
    expect(out).toEqual([2.5, -1, -1, 3, 1, 1]);
    expect(clipBounds([3.5, -1, -1, 4.5, 1, 1], [{ n: [-1, 0, 0], w: 3, axis: 0 }], out)).toBe(false);
  });
  it('a window around the visible part of a cut element picks it, one around the removed part does not', () => {
    // The cube at 3.5 spans x 2.5..4.5; the box keeps x <= 3, so the part drawn is x 2.5..3: pixels 100 + 5x = 112.5..115.
    expect(pickClip(sbox, { x0: 105, y0: 30, x1: 120, y1: 70 }, 'window')).toEqual([3]);
    expect(pickClip(null, { x0: 105, y0: 30, x1: 120, y1: 70 }, 'window')).toEqual([]);
  });
});
