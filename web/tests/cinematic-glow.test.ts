import { describe, expect, it } from 'vitest';
import { DEFAULT_GLOW_SCOPE, GLOW_SCOPES, glowIds, glowScopeFromLegacy, isGlowScope } from '../src/cinematic/glow';
import type { Classification } from '../src/types';
import { defaultConfig } from '../src/plugins/cinematic';

const cls: Classification = {
  focus: new Set([0, 1]),
  host: new Set([2]),
  near: new Set([3, 4]),
  far: new Set([5, 6, 7]),
  proximityWeight: new Map(),
  bufferRadius: new Map(),
};
const sorted = (s: Set<number>): number[] => [...s].sort((a, b) => a - b);

describe('edge glow scope', () => {
  it('focus glows the focus set only', () => {
    expect(sorted(glowIds('focus', cls, 8))).toEqual([0, 1]);
  });

  it('near glows focus, host and near', () => {
    expect(sorted(glowIds('near', cls, 8))).toEqual([0, 1, 2, 3, 4]);
  });

  it('all glows every element, less the hidden ones when given', () => {
    expect(sorted(glowIds('all', cls, 8))).toEqual([0, 1, 2, 3, 4, 5, 6, 7]);
    expect(sorted(glowIds('all', cls, 8, new Set([6, 1])))).toEqual([0, 2, 3, 4, 5, 7]);
  });

  it('defaults to focus and maps the old glowNear switch', () => {
    expect(DEFAULT_GLOW_SCOPE).toBe('focus');
    expect(defaultConfig().glowScope).toBe('focus');
    expect('glowNear' in defaultConfig()).toBe(false);
    expect(glowScopeFromLegacy(true)).toBe('near');
    expect(glowScopeFromLegacy(false)).toBe('focus');
    expect(GLOW_SCOPES).toEqual(['focus', 'near', 'all']);
    expect(isGlowScope('near')).toBe(true);
    expect(isGlowScope('host')).toBe(false);
  });
});
