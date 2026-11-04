import { describe, expect, it } from 'vitest';
import {
  GHOST_GLSL,
  INK_COLOUR,
  MIN_FILL_ALPHA,
  OPAQUE_ALPHA,
  RIM_OPACITY,
  desaturation,
  ghostFragmentAlpha,
  gradeStrengthFor,
  rimFactor,
  transparency,
} from '../src/render/ghostMath';
import { EDGE_FRAG, MESH_FRAG, MESH_VERT } from '../src/render/shaders';

describe('ghost effects scale with transparency', () => {
  it('t = 1 - alpha', () => {
    expect(transparency(1)).toBe(0);
    expect(transparency(0.15)).toBeCloseTo(0.85, 9);
    expect(transparency(1.2)).toBe(0);
    expect(transparency(-1)).toBe(1);
  });
  it('desaturation and depth grade vanish at alpha 1 and are nearly nothing at 0.99', () => {
    expect(desaturation(0.8, 1)).toBe(0);
    expect(gradeStrengthFor(0.5, 1)).toBe(0);
    expect(desaturation(0.8, 0.99)).toBeCloseTo(0.008, 9);
    expect(gradeStrengthFor(0.5, 0.99)).toBeCloseTo(0.005, 9);
    expect(desaturation(0.8, 0.15)).toBeCloseTo(0.68, 9);
    expect(gradeStrengthFor(0.5, 0.15)).toBeCloseTo(0.425, 9);
  });
  it('is continuous across the pass threshold', () => {
    const below = OPAQUE_ALPHA - 1e-4;
    expect(Math.abs(desaturation(0.8, below) - desaturation(0.8, OPAQUE_ALPHA))).toBeLessThan(1e-3);
    expect(Math.abs(ghostFragmentAlpha(below, 1) - 1)).toBeLessThan(2e-3);
    expect(ghostFragmentAlpha(1, 0.2)).toBe(1);
  });
});

describe('rim and minimum fill', () => {
  it('rim is 0 head-on and 1 edge-on, monotonic', () => {
    expect(rimFactor(1)).toBe(0);
    expect(rimFactor(0)).toBe(1);
    expect(rimFactor(0.3)).toBeGreaterThan(rimFactor(0.6));
  });
  it('head-on fragments keep their alpha, grazing ones become mostly opaque', () => {
    expect(ghostFragmentAlpha(0.15, 1)).toBeCloseTo(0.15, 9);
    expect(ghostFragmentAlpha(0.15, 0)).toBeCloseTo(0.15 + 0.85 * RIM_OPACITY, 9);
    expect(ghostFragmentAlpha(0.15, 0.2)).toBeGreaterThan(ghostFragmentAlpha(0.15, 0.8));
  });
  it('the rim reads at 45 degrees (alpha clearly above the base), unlike the old pow 3 / 0.6 boost', () => {
    const ndv = Math.cos(Math.PI / 4);
    const old = 0.15 + 0.85 * 0.6 * Math.pow(1 - ndv, 3);
    expect(old - 0.15).toBeLessThan(0.02);
    expect(ghostFragmentAlpha(0.15, ndv) - 0.15).toBeGreaterThan(0.05);
  });
  it('never more transparent than the minimum fill', () => {
    expect(ghostFragmentAlpha(0, 1)).toBeCloseTo(MIN_FILL_ALPHA, 9);
    expect(ghostFragmentAlpha(0.02, 1)).toBeCloseTo(MIN_FILL_ALPHA, 9);
  });
});

describe('shader sources', () => {
  it('both mesh passes use the one surfaceColour function; the opaque pass calls it with t = 0', () => {
    expect(MESH_FRAG).toContain('vec3 surfaceColour(');
    const calls = MESH_FRAG.match(/surfaceColour\(vColor/g) ?? [];
    expect(calls.length).toBe(2);
    expect(MESH_FRAG).toMatch(/surfaceColour\(vColor, n, vFlags, vWorldPos, 0\.0, 0\.0\)/);
    expect(MESH_FRAG).toMatch(/surfaceColour\(vColor, n, vFlags, vWorldPos, t, rim\)/);
  });
  it('desaturation and grade are scaled by t inside surfaceColour', () => {
    expect(MESH_FRAG).toContain('ghostDesaturate * t');
    expect(MESH_FRAG).toContain('gradeStrength * t');
  });
  it('the pass threshold is one shared constant, in the vertex and fragment shaders', () => {
    expect(GHOST_GLSL).toContain(`#define OPAQUE_ALPHA ${OPAQUE_ALPHA}`);
    expect(MESH_VERT).toContain(GHOST_GLSL);
    expect(MESH_FRAG).toContain(GHOST_GLSL);
    expect(MESH_FRAG.replace(GHOST_GLSL, '')).not.toContain('0.999');
  });
  it('the edge pass draws at max(edgeAlpha, alpha) in dark slate, not black', () => {
    expect(EDGE_FRAG).toContain('max(edgeAlpha, vAlpha)');
    expect(EDGE_FRAG).toContain('INK_COLOUR');
    const [r, g, b] = INK_COLOUR;
    expect(Math.min(r, g, b)).toBeGreaterThan(0.1);
    expect(Math.max(r, g, b)).toBeLessThan(0.45);
  });
});
