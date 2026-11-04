import { describe, expect, it } from 'vitest';
import {
  OIT_GLSL,
  OIT_MAX_ALPHA,
  oitAccumulate,
  oitComposite,
  oitDepthTerm,
  oitWeight,
  overSorted,
} from '../src/render/oitMath';
import type { OitLayer } from '../src/render/oitMath';
import { MESH_FRAG, OIT_COMPOSITE_FRAG } from '../src/render/shaders';

const BG: [number, number, number] = [0.9, 0.92, 0.95];

describe('OIT weight function', () => {
  it('the paper depth term is non-increasing in depth and stays inside its clamps', () => {
    let prev = Infinity;
    for (let z = 0.01; z <= 2000; z *= 1.07) {
      const w = oitDepthTerm(z);
      expect(w).toBeLessThanOrEqual(prev + 1e-12);
      expect(w).toBeGreaterThanOrEqual(1e-2);
      expect(w).toBeLessThanOrEqual(3e3);
      prev = w;
    }
    expect(oitDepthTerm(0.001)).toBeCloseTo(3e3, 6);
    expect(oitDepthTerm(5000)).toBeCloseTo(1e-2, 9);
  });
  it('is strictly decreasing across building-scale depths (2 to 120 m)', () => {
    let prev = Infinity;
    for (let z = 2; z <= 120; z += 1) {
      const w = oitDepthTerm(z);
      expect(w).toBeLessThan(prev);
      prev = w;
    }
  });
  it('matches the formula in the middle of the range', () => {
    expect(oitDepthTerm(20)).toBeCloseTo(0.03 / (1e-5 + Math.pow(20 / 200, 4)), 9);
  });
  it('is proportional to alpha, and flat mode has no depth term', () => {
    expect(oitWeight(30, 0.5, 'paper')).toBeCloseTo(0.5 * oitDepthTerm(30), 12);
    expect(oitWeight(30, 0.5, 'flat')).toBe(0.5);
    expect(oitWeight(3, 0.5, 'flat')).toBe(oitWeight(300, 0.5, 'flat'));
  });
  it('a nearer layer outweighs a farther one of equal alpha (paper), not in flat mode', () => {
    expect(oitWeight(10, 0.4)).toBeGreaterThan(oitWeight(14, 0.4));
    expect(oitWeight(10, 0.4, 'flat')).toBe(oitWeight(14, 0.4, 'flat'));
  });
  it('the shader mirrors the TypeScript weight', () => {
    expect(OIT_GLSL).toContain('0.03 / (1e-5 + pow(z / 200.0, 4.0))');
    expect(OIT_GLSL).toContain('clamp(');
    expect(OIT_GLSL).toContain('1e-2, 3e3');
    expect(MESH_FRAG).toContain(OIT_GLSL);
  });
});

describe('OIT composite', () => {
  const two = (z1: number, z2: number): OitLayer[] => [
    { color: [0.85, 0.2, 0.15], alpha: 0.3, z: z1 },
    { color: [0.15, 0.3, 0.85], alpha: 0.3, z: z2 },
  ];

  it('gives the same result whatever the order the layers arrive in', () => {
    const layers: OitLayer[] = [
      { color: [0.85, 0.2, 0.15], alpha: 0.3, z: 12 },
      { color: [0.15, 0.3, 0.85], alpha: 0.3, z: 15 },
      { color: [0.2, 0.8, 0.3], alpha: 0.55, z: 21 },
      { color: [0.5, 0.5, 0.5], alpha: 0.15, z: 30 },
    ];
    const ref = oitComposite(oitAccumulate(layers), BG);
    const perms: number[][] = [];
    const permute = (a: number[], k: number): void => {
      if (k === a.length) perms.push([...a]);
      for (let i = k; i < a.length; i++) {
        [a[k], a[i]] = [a[i]!, a[k]!];
        permute(a, k + 1);
        [a[k], a[i]] = [a[i]!, a[k]!];
      }
    };
    permute([0, 1, 2, 3], 0);
    expect(perms.length).toBe(24);
    for (const p of perms) {
      const out = oitComposite(oitAccumulate(p.map((i) => layers[i]!)), BG);
      for (let c = 0; c < 3; c++) expect(out[c]!).toBeCloseTo(ref[c]!, 12);
    }
  });

  it('two layers at alpha 0.3 match the sorted over operator within a tolerance', () => {
    // Worst case for the approximation: strongly different colours. Error is bounded by 0.045 * |C1 - C2|.
    for (const [z1, z2] of [[10, 13], [20, 23], [20.2, 20.45], [40, 44]] as const) {
      const layers = two(z1, z2);
      const wb = oitComposite(oitAccumulate(layers), BG);
      const over = overSorted(layers, BG);
      for (let c = 0; c < 3; c++) expect(Math.abs(wb[c]! - over[c]!)).toBeLessThan(0.04);
    }
  });

  it('the result does not depend on which layer is which when the layers are identical in colour', () => {
    const a: OitLayer = { color: [0.3, 0.4, 0.5], alpha: 0.3, z: 10 };
    const b: OitLayer = { color: [0.3, 0.4, 0.5], alpha: 0.3, z: 25 };
    const wb = oitComposite(oitAccumulate([a, b]), BG);
    const over = overSorted([a, b], BG);
    for (let c = 0; c < 3; c++) expect(wb[c]!).toBeCloseTo(over[c]!, 12);
  });

  it('coverage is exactly 1 - (1 - a1)(1 - a2): over a background equal to the layer colour nothing changes', () => {
    const col: [number, number, number] = [0.4, 0.5, 0.6];
    const layers: OitLayer[] = [
      { color: col, alpha: 0.3, z: 10 },
      { color: col, alpha: 0.3, z: 30 },
    ];
    const out = oitComposite(oitAccumulate(layers), col);
    for (let c = 0; c < 3; c++) expect(out[c]!).toBeCloseTo(col[c]!, 12);
    // and over a black background the colour is scaled by the coverage 0.51
    const dark = oitComposite(oitAccumulate(layers), [0, 0, 0]);
    expect(dark[0]!).toBeCloseTo(0.4 * 0.51, 12);
  });

  it('the depth weight moves the result toward the nearer layer, toward the sorted result', () => {
    const layers = two(20, 23); // one storey apart at typical viewing distance
    const near = layers[0]!.color;
    const flat = oitComposite(oitAccumulate(layers, 'flat'), BG);
    const paper = oitComposite(oitAccumulate(layers, 'paper'), BG);
    const over = overSorted(layers, BG);
    // red channel: near layer is the redder one
    expect(near[0]).toBeGreaterThan(layers[1]!.color[0]);
    expect(Math.abs(paper[0]! - over[0]!)).toBeLessThan(Math.abs(flat[0]! - over[0]!));
  });

  it('no layers leaves the background untouched; accum.a = 0 does not divide by zero', () => {
    const out = oitComposite(oitAccumulate([]), BG);
    expect(out).toEqual(BG);
  });

  it('a fully opaque rim fragment keeps a finite revealage sum', () => {
    const b = oitAccumulate([{ color: [1, 1, 1], alpha: 1, z: 10 }]);
    expect(Number.isFinite(b.logReveal)).toBe(true);
    expect(b.logReveal).toBeCloseTo(-Math.log(1 - OIT_MAX_ALPHA), 12);
    const out = oitComposite(b, [0, 0, 0]);
    expect(out[0]!).toBeGreaterThan(0.99);
  });

  it('the composite shader decodes revealage as exp(-sum) and guards a half-float overflow', () => {
    expect(OIT_COMPOSITE_FRAG).toContain('exp(-texelFetch(tReveal');
    expect(OIT_COMPOSITE_FRAG).toContain('isinf(');
    expect(OIT_COMPOSITE_FRAG).toContain('max(acc.a, 1e-5)');
  });
});
