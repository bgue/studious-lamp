import { describe, expect, it } from 'vitest';
import { bandOf, clearanceColour, CLASH_COLOUR, computeClearance, DEFAULT_CLEARANCE, TIGHT_COLOUR } from '../src/measure/clearance';
import type { ClearanceGeometry } from '../src/measure/clearance';

const S = { tight: 0.05, max: 0.5 };

describe('clearance bands', () => {
  it('clash for touching, overlapping and negative', () => {
    expect(bandOf(0, S)).toBe('clash');
    expect(bandOf(-0.1, S)).toBe('clash');
    expect(bandOf(1e-9, S)).toBe('clash');
  });
  it('tight below the threshold, ok up to and including max, far beyond', () => {
    expect(bandOf(0.01, S)).toBe('tight');
    expect(bandOf(0.0499, S)).toBe('tight');
    expect(bandOf(0.05, S)).toBe('ok');
    expect(bandOf(0.5, S)).toBe('ok');
    expect(bandOf(0.5001, S)).toBe('far');
  });
  it('colours: clash red, tight amber, ramp inside ok, none beyond', () => {
    expect(clearanceColour(0, S)).toEqual(CLASH_COLOUR);
    expect(clearanceColour(0.02, S)).toEqual(TIGHT_COLOUR);
    expect(clearanceColour(0.9, S)).toBeNull();
    const near = clearanceColour(0.05, S)!;
    const far = clearanceColour(0.5, S)!;
    const mid = clearanceColour(0.275, S)!;
    expect(near).not.toEqual(far);
    for (let i = 0; i < 3; i++) expect(mid[i]).toBeCloseTo((near[i]! + far[i]!) / 2, 6);
    expect(far[2]).toBeGreaterThan(far[0]); // cool: blue dominates
  });
  it('defaults are 5 cm and 50 cm', () => expect(DEFAULT_CLEARANCE).toEqual({ tight: 0.05, max: 0.5 }));
});

// 1-D boxes along x: element i occupies [lo, hi]
function line(boxes: Record<number, [number, number]>): ClearanceGeometry & { queries: number } {
  const g = {
    queries: 0,
    boundsDistance: (a: number, b: number) => Math.max(0, boxes[a]![0] - boxes[b]![1], boxes[b]![0] - boxes[a]![1]),
    surfaceDistance: (a: number, b: number, max: number) => {
      g.queries++;
      const d = Math.max(0, boxes[a]![0] - boxes[b]![1], boxes[b]![0] - boxes[a]![1]);
      return d > max ? d : d;
    },
  };
  return g;
}

describe('computeClearance', () => {
  const boxes: Record<number, [number, number]> = {
    1: [0, 1], // focus
    2: [1, 2], // touching -> clash
    3: [1.03, 2], // 0.03 -> tight
    4: [1.3, 2], // 0.3 -> ok
    5: [5, 6], // 4 -> far (no query: bounds prefilter)
    6: [0.5, 1.5], // overlapping -> clash
  };
  it('bands the context by minimum distance and skips far elements without mesh queries', () => {
    const g = line(boxes);
    const r = computeClearance([1], [2, 3, 4, 5, 6], g, S);
    expect(r.counts).toEqual({ clash: 2, tight: 1, ok: 1, far: 1 });
    expect(r.distances.get(3)).toBeCloseTo(0.03, 9);
    expect(r.distances.has(5)).toBe(false);
    expect(r.queried).toBe(4);
    expect(g.queries).toBe(4);
  });
  it('uses the nearest of several focus elements', () => {
    const b2: Record<number, [number, number]> = { 1: [0, 1], 2: [10, 11], 3: [1.4, 2], 4: [10.2, 12] };
    const r = computeClearance([1, 2], [3, 4], line(b2), S);
    expect(r.distances.get(3)).toBeCloseTo(0.4, 9);
    expect(r.distances.get(4)).toBeCloseTo(0, 9);
    expect(r.counts.clash).toBe(1);
  });
  it('never measures a focus element against itself', () => {
    const r = computeClearance([1], [1, 2], line(boxes), S);
    expect(r.counts.clash + r.counts.tight + r.counts.ok + r.counts.far).toBe(2);
    expect(r.distances.has(1)).toBe(false);
  });
  it('an empty focus leaves everything far', () => {
    const r = computeClearance([], [2, 3], line(boxes), S);
    expect(r.counts).toEqual({ clash: 0, tight: 0, ok: 0, far: 2 });
  });
  it('widening the range pulls in more elements', () => {
    const wide = computeClearance([1], [2, 3, 4, 5, 6], line(boxes), { tight: 0.05, max: 5 });
    expect(wide.counts.far).toBe(0);
    expect(wide.counts.ok).toBe(2);
  });
});
