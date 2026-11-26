import { describe, expect, it } from 'vitest';
import { MAX_SLICE_MS, nextSliceMs } from './sliceBudget';

describe('nextSliceMs', () => {
  it('keeps the base slice when the gap was short', () => {
    expect(nextSliceMs(8, 0)).toBe(8);
    expect(nextSliceMs(8, 10)).toBe(8);
  });
  it('grows with half the gap but never beyond the cap', () => {
    expect(nextSliceMs(8, 40)).toBe(20);
    expect(nextSliceMs(8, 5000)).toBe(MAX_SLICE_MS);
    expect(nextSliceMs(8, 5000, 50)).toBe(50);
  });
  it('ignores bad gaps and clamps a base above the cap', () => {
    expect(nextSliceMs(8, NaN)).toBe(8);
    expect(nextSliceMs(8, -3)).toBe(8);
    expect(nextSliceMs(100, 0)).toBe(MAX_SLICE_MS);
  });
});
