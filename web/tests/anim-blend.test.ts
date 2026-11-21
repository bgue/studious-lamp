import { describe, expect, it } from 'vitest';
import { blendNumbers, blendValue, diffParams, easeValue, getAt, leaves, nest, pathKeys, switchPoint } from '../src/anim/blend';

describe('settings blending', () => {
  const from = { sightlines: { alphaMax: 1, style: 'lines' }, xray: true, cinematic: { glowStrength: 0.2, tiers: [1, 2] } };
  const to = { sightlines: { alphaMax: 0.2, style: 'dots' }, xray: true, cinematic: { glowStrength: 0.8, tiers: [1, 3] }, display: { edgeAlpha: 0.5 } };

  it('splits what differs into numbers (blended) and the rest (switched)', () => {
    const d = diffParams(from, to);
    expect(d.nums.map((n) => n.keys.join('.')).sort()).toEqual(['cinematic.glowStrength', 'sightlines.alphaMax']);
    expect(d.discrete.map((n) => n.keys.join('.')).sort()).toEqual(['cinematic.tiers', 'display.edgeAlpha', 'sightlines.style']);
    expect(diffParams(from, from)).toEqual({ nums: [], discrete: [] });
    // Leaves that the target does not name stay as they are.
    expect(diffParams(from, {})).toEqual({ nums: [], discrete: [] });
  });

  it('blends numbers by the eased progress and reaches the exact target at 1', () => {
    const d = diffParams(from, to);
    expect(blendNumbers(d.nums, 0.5)).toEqual({ sightlines: { alphaMax: 0.6 }, cinematic: { glowStrength: 0.5 } });
    expect(blendNumbers(d.nums, 1)).toEqual({ sightlines: { alphaMax: 0.2 }, cinematic: { glowStrength: 0.8 } });
  });

  it('eases and picks the switch point', () => {
    expect(easeValue('linear', 0.3)).toBe(0.3);
    expect(easeValue(undefined, 0.3)).toBe(0.3);
    expect(easeValue('inOut', 0.5)).toBeCloseTo(0.5, 9);
    expect(easeValue('in', 0.5)).toBeLessThan(0.5);
    expect(easeValue('out', 0.5)).toBeGreaterThan(0.5);
    expect(easeValue('inOut', 2)).toBe(1);
    expect(switchPoint('start')).toBe(0);
    expect(switchPoint('mid')).toBe(0.5);
    expect(switchPoint('end')).toBe(1);
    expect(switchPoint(undefined)).toBe(1);
    expect(switchPoint(undefined, 'start')).toBe(0);
  });

  it('blends numbers and switches the rest of a param cue (default at the end)', () => {
    expect(blendValue(0, 10, 0.25, 0.25, 1)).toBe(2.5);
    expect(blendValue(false, true, 0.9, 0.9, 1)).toBe(false);
    expect(blendValue(false, true, 1, 1, 1)).toBe(true);
    expect(blendValue('a', 'b', 0.1, 0.1, 0)).toBe('b');
    expect(blendValue('a', 'b', 0.4, 0.4, 0.5)).toBe('a');
  });

  it('reads, lists and nests setting paths', () => {
    expect(pathKeys('cinematic.glowStrength')).toEqual(['cinematic', 'glowStrength']);
    expect(getAt(from, ['sightlines', 'alphaMax'])).toBe(1);
    expect(getAt(from, ['nope', 'x'])).toBeUndefined();
    expect(leaves({ a: { b: 1, c: [1] }, d: 'x' }).map((l) => l.keys.join('.'))).toEqual(['a.b', 'a.c', 'd']);
    expect(nest([{ keys: ['a', 'b'], value: 1 }, { keys: ['a', 'c'], value: [1, 2] }])).toEqual({ a: { b: 1, c: [1, 2] } });
  });
});
