import { describe, expect, it } from 'vitest';
import {
  AUTO_MIN_SAMPLES, AUTO_TARGET, BONE_DENSITY, CONTRAST_PIVOT, DEFAULT_DENSITY, K_TISSUE, PALETTE_TABLE, advanceScan, attenuate, autoExposureFor, nonZeroPercentile, smoothExposure, contrastCurve, densityForMaterial, extentAlong, mriGrey, paletteMap, phaseToPosition, positionToPhase, slabFor, windowLevel,
} from '../src/imaging/maths';
import type { Box6 } from '../src/imaging/maths';
import { cloneImaging, defaultImaging, mergeImaging } from '../src/imaging/config';
import { IMG_COMPOSITE_FRAG, IMG_SLAB_FRAG, IMG_THICK_FRAG } from '../src/render/imagingGlsl';

describe('density from the material name', () => {
  it('maps the keywords of the spec', () => {
    expect(densityForMaterial('Concrete C30/37')).toBe(1.0);
    expect(densityForMaterial('metal_steel-galvanized')).toBe(3.0);
    expect(densityForMaterial('Steel S355')).toBe(3.0);
    expect(densityForMaterial('wood_spruce_beam')).toBe(0.4);
    expect(densityForMaterial('Timber')).toBe(0.4);
    expect(densityForMaterial('Brick')).toBe(0.8);
    expect(densityForMaterial('masonry wall')).toBe(0.8);
    expect(densityForMaterial('gypsum_fiber-board_panel')).toBe(0.3);
    expect(densityForMaterial('Plaster')).toBe(0.3);
    expect(densityForMaterial('Glass 6mm')).toBe(0.6);
    expect(densityForMaterial('Mineral wool insulation')).toBe(0.05);
  });
  it('falls back to 0.7 for unknown or missing names', () => {
    expect(densityForMaterial('PVC')).toBe(DEFAULT_DENSITY);
    expect(densityForMaterial('')).toBe(0.7);
    expect(densityForMaterial(undefined)).toBe(0.7);
    expect(densityForMaterial(null)).toBe(0.7);
  });
  it('knows the German names of the fzk-haus model and reinforced concrete is concrete', () => {
    expect(densityForMaterial('Holz')).toBe(0.4);
    expect(densityForMaterial('Leichtbeton 102890359 0.3')).toBe(1.0);
    expect(densityForMaterial('Stahlbeton 65690 0.2')).toBe(1.0);
    expect(densityForMaterial('concrete_reinforced_in-situ')).toBe(1.0);
  });
  it('insulation wins over wood in "wood fibre insulation"', () => {
    expect(densityForMaterial('Wood fibre insulation')).toBe(0.05);
  });
});

describe('attenuation', () => {
  it('is 1 - exp(-exposure k T)', () => {
    expect(attenuate(0.2, 1)).toBeCloseTo(1 - Math.exp(-K_TISSUE * 0.2), 12);
    expect(attenuate(0.2, 2)).toBeCloseTo(1 - Math.exp(-2 * K_TISSUE * 0.2), 12);
    expect(attenuate(1, 1, 3)).toBeCloseTo(1 - Math.exp(-3), 12);
  });
  it('is 0 for no material, and clamps open-mesh (negative) thickness at zero', () => {
    expect(attenuate(0, 1)).toBe(0);
    expect(attenuate(-4.2, 1)).toBe(0);
    expect(attenuate(5, 0)).toBe(0);
  });
  it('is monotone in thickness and exposure and stays below 1', () => {
    let prev = 0;
    for (let t = 0.1; t < 20; t += 0.7) {
      const a = attenuate(t, 1);
      expect(a).toBeGreaterThan(prev);
      expect(a).toBeLessThanOrEqual(1);
      prev = a;
    }
    expect(attenuate(1, 2)).toBeGreaterThan(attenuate(1, 1));
  });
  it('density times thickness through closed solids: front faces subtract, back faces add', () => {
    // a wall 0.3 m thick seen at view depths 10 and 10.3, density 1.0 ; the shader sums -z d (front) and +z d (back)
    const d = 1.0;
    const sum = -10 * d + 10.3 * d;
    expect(sum).toBeCloseTo(0.3, 12);
    // an open mesh with only its front face: negative, clamped to nothing
    expect(attenuate(-10 * d, 1)).toBe(0);
  });
});

describe('contrast curve', () => {
  it('is the identity at contrast 1', () => {
    for (const x of [0, 0.2, 0.5, 1]) expect(contrastCurve(x, 1)).toBeCloseTo(x, 12);
  });
  it('pivots at CONTRAST_PIVOT and clamps', () => {
    expect(contrastCurve(CONTRAST_PIVOT, 3)).toBeCloseTo(CONTRAST_PIVOT, 12);
    expect(contrastCurve(1, 5)).toBe(1);
    expect(contrastCurve(0, 5)).toBe(0);
    expect(contrastCurve(0.6, 2)).toBeGreaterThan(0.6);
    expect(contrastCurve(0.2, 2)).toBeLessThan(0.2);
  });
});

describe('palettes', () => {
  it('classic is black on empty, negative is white, fluoro is dark blue-green', () => {
    expect(paletteMap('classic', 0, 0)).toEqual([0, 0, 0]);
    expect(paletteMap('negative', 0, 0)).toEqual([1, 1, 1]);
    const f = paletteMap('fluoro', 0, 0);
    expect(f[2]).toBeGreaterThan(f[0]);
    expect(f[1]).toBeGreaterThan(f[0]);
    expect(Math.max(...f)).toBeLessThan(0.1);
  });
  it('more tissue is brighter in classic and fluoro, darker in negative', () => {
    const lum = (c: number[]): number => c[0]! * 0.3 + c[1]! * 0.6 + c[2]! * 0.1;
    expect(lum(paletteMap('classic', 0.8, 0))).toBeGreaterThan(lum(paletteMap('classic', 0.2, 0)));
    expect(lum(paletteMap('fluoro', 0.8, 0))).toBeGreaterThan(lum(paletteMap('fluoro', 0.2, 0)));
    expect(lum(paletteMap('negative', 0.8, 0))).toBeLessThan(lum(paletteMap('negative', 0.2, 0)));
  });
  it('bone reaches the bone colour, and is brighter than any tissue in classic', () => {
    expect(paletteMap('classic', 1, 1)).toEqual(PALETTE_TABLE.classic.bone);
    const lum = (c: number[]): number => c[0]! * 0.3 + c[1]! * 0.6 + c[2]! * 0.1;
    expect(lum(paletteMap('classic', 0.5, 1))).toBeGreaterThan(lum(paletteMap('classic', 1, 0)));
  });
  it('glow adds toward the glow colour and the result is clamped', () => {
    const a = paletteMap('classic', 0.3, 0, 0);
    const b = paletteMap('classic', 0.3, 0, 0.5);
    expect(b[2]).toBeGreaterThan(a[2]);
    for (const c of paletteMap('classic', 1, 1, 10)) expect(c).toBeLessThanOrEqual(1);
    for (const c of paletteMap('negative', 1, 1, 10)) expect(c).toBeGreaterThanOrEqual(0);
  });
  it('the GLSL composite uses the same shared constants', () => {
    expect(IMG_COMPOSITE_FRAG).toContain(String(K_TISSUE));
    expect(IMG_COMPOSITE_FRAG).toContain(String(CONTRAST_PIVOT));
    expect(IMG_THICK_FRAG).toContain(BONE_DENSITY.toFixed(1));
    expect(IMG_SLAB_FRAG).toContain('mriGrey');
  });
});

describe('MRI grey levels and window / level', () => {
  it('rises with density, between 0.16 and 0.86', () => {
    expect(mriGrey(0)).toBeCloseTo(0.16, 12);
    expect(mriGrey(0.05)).toBeLessThan(mriGrey(1.0));
    expect(mriGrey(1.0)).toBeLessThan(mriGrey(3.0));
    expect(mriGrey(1000)).toBeLessThanOrEqual(0.86 + 1e-9);
  });
  it('windowLevel: contrast 1 exposure 1 is the identity, exposure is a gain, contrast stretches about 0.5', () => {
    expect(windowLevel(0.4, 1, 1)).toBeCloseTo(0.4, 12);
    expect(windowLevel(0.4, 1.5, 1)).toBeCloseTo(0.6, 12);
    expect(windowLevel(0.5, 1, 3)).toBeCloseTo(0.5, 12);
    expect(windowLevel(0.7, 1, 2)).toBeCloseTo(0.9, 12);
    expect(windowLevel(0.9, 3, 3)).toBe(1);
  });
});

const BOXES: Box6[] = [[0, 0, 0, 2, 10, 1], [0, 2, 0, 1, 4, 3]];

describe('MRI slab', () => {
  it('axis y: position sweeps the focus bounds, thickness is the full width', () => {
    const lo = slabFor('y', [0, 0, -1], BOXES, 0, 0.3)!;
    const mid = slabFor('y', [0, 0, -1], BOXES, 0.5, 0.3)!;
    const hi = slabFor('y', [0, 0, -1], BOXES, 1, 0.3)!;
    expect(lo.normal).toEqual([0, 1, 0]);
    expect(lo.centre).toBeCloseTo(0, 12);
    expect(mid.centre).toBeCloseTo(5, 12);
    expect(hi.centre).toBeCloseTo(10, 12);
    expect(mid.half).toBeCloseTo(0.15, 12);
    expect(mid.min).toBe(0);
    expect(mid.max).toBe(10);
  });
  it('axis camera: normal is the view direction, extent is the projected corners', () => {
    const s = slabFor('camera', [0, 0, -2], BOXES, 0.5, 1)!;
    expect(s.normal).toEqual([0, 0, -1]);
    expect(s.min).toBeCloseTo(-3, 12);
    expect(s.max).toBeCloseTo(0, 12);
    expect(s.centre).toBeCloseTo(-1.5, 12);
    const d = slabFor('camera', [1, 1, 0], BOXES, 0, 1)!;
    expect(Math.hypot(...d.normal)).toBeCloseTo(1, 12);
    // the extent matches the 16 corners projected on that normal
    const [lo, hi] = extentAlong(d.normal, BOXES);
    expect(d.min).toBeCloseTo(lo, 12);
    expect(d.max).toBeCloseTo(hi, 12);
  });
  it('clamps position and rejects an empty list', () => {
    expect(slabFor('x', [0, 0, 1], BOXES, 3, 0.2)!.centre).toBeCloseTo(2, 12);
    expect(slabFor('x', [0, 0, 1], BOXES, -3, 0.2)!.centre).toBeCloseTo(0, 12);
    expect(slabFor('x', [0, 0, 1], [], 0.5, 0.2)).toBeNull();
  });
  it('a fragment is inside the slab when |n.p - c| <= half', () => {
    const s = slabFor('y', [0, 0, 1], BOXES, 0.5, 0.3)!;
    const inside = (y: number): boolean => Math.abs(y - s.centre) <= s.half;
    expect(inside(5.1)).toBe(true);
    expect(inside(5.2)).toBe(false);
  });
});

describe('MRI scan timing', () => {
  it('sweeps 0 to 1 and back at speed fraction per second', () => {
    let phase = 0;
    const pos: number[] = [];
    for (let i = 0; i < 9; i++) {
      pos.push(phaseToPosition(phase));
      phase = advanceScan(phase, 1, 0.25); // 4 s per sweep
    }
    expect(pos.map((p) => +p.toFixed(3))).toEqual([0, 0.25, 0.5, 0.75, 1, 0.75, 0.5, 0.25, 0]);
  });
  it('wraps after a full cycle and handles big or negative steps', () => {
    expect(advanceScan(1.9, 1, 0.2)).toBeCloseTo(0.1, 12);
    expect(advanceScan(0, 100, 0.25)).toBeCloseTo(1, 12);
    expect(advanceScan(0.1, -1, 0.25)).toBeGreaterThanOrEqual(0);
    expect(phaseToPosition(1.5)).toBeCloseTo(0.5, 12);
    expect(phaseToPosition(-0.25)).toBeCloseTo(0.25, 12);
  });
  it('zero speed holds the slice and a scan starts from the slider value', () => {
    expect(advanceScan(0.3, 5, 0)).toBe(0.3);
    expect(phaseToPosition(positionToPhase(0.62))).toBeCloseTo(0.62, 12);
  });
});

describe('imaging config', () => {
  it('has the documented defaults', () => {
    expect(defaultImaging()).toEqual({
      style: 'standard', palette: 'classic', exposure: 1, autoExposure: true, contrast: 1, boneGlow: 1, tissueEdges: true,
      mri: { axis: 'camera', thickness: 0.3, position: 0.5, scan: false, scanSpeed: 0.25 },
    });
  });
  it('merges valid fields, clamps numbers and reports the rest', () => {
    const c = defaultImaging();
    const bad = mergeImaging(c, { style: 'mri', palette: 'neon', exposure: 99, mri: { axis: 'y', position: 2, nonsense: 1 }, extra: true });
    expect(c.style).toBe('mri');
    expect(c.palette).toBe('classic');
    expect(c.exposure).toBe(10);
    expect(c.mri.axis).toBe('y');
    expect(c.mri.position).toBe(1);
    expect(bad.sort()).toEqual(['imaging.extra', 'imaging.mri.nonsense', 'imaging.palette']);
    const copy = cloneImaging(c);
    copy.mri.axis = 'z';
    expect(c.mri.axis).toBe('y');
  });
  it('accepts the partial documents presets write', () => {
    const c = defaultImaging();
    expect(mergeImaging(c, { style: 'radiograph', palette: 'classic' })).toEqual([]);
    expect(c.style).toBe('radiograph');
    expect(mergeImaging(c, 5)).toEqual(['imaging']);
    expect(mergeImaging(c, undefined)).toEqual([]);
  });
});

describe('automatic exposure', () => {
  const ramp = (n: number, hi: number): number[] => Array.from({ length: n }, (_, i) => ((i + 1) / n) * hi);

  it('maps the 90th percentile of the non-zero thickness to 0.8 intensity', () => {
    for (const hi of [0.3, 4, 60, 900]) {
      const t = ramp(1000, hi);
      const e = autoExposureFor(t)!;
      const p90 = nonZeroPercentile(t, 0.9)!.value;
      expect(attenuate(p90, e, K_TISSUE)).toBeCloseTo(AUTO_TARGET, 6);
    }
  });

  it('ignores empty pixels (zero or negative thickness) and gives the same factor with or without them', () => {
    const t = ramp(500, 12);
    const padded = [...t, ...new Array(3000).fill(0), ...new Array(200).fill(-0.5)];
    expect(autoExposureFor(padded)).toBeCloseTo(autoExposureFor(t)!, 9);
  });

  it('makes a tall and a flat model read alike: the exposure falls as the thickness grows', () => {
    const flat = autoExposureFor(ramp(1000, 1.5))!;
    const tall = autoExposureFor(ramp(1000, 150))!;
    expect(tall).toBeLessThan(flat / 50);
    // after the automatic factor the median pixel of both lands at about the same intensity
    const med = (hi: number, e: number): number => attenuate(hi / 2, e, K_TISSUE);
    expect(med(150, tall)).toBeCloseTo(med(1.5, flat), 1);
  });

  it('returns null for an empty or nearly empty frame and clamps absurd values', () => {
    expect(autoExposureFor([])).toBeNull();
    expect(autoExposureFor(new Array(AUTO_MIN_SAMPLES - 1).fill(2))).toBeNull();
    expect(autoExposureFor(new Array(100).fill(1e-9))).toBeNull();
    expect(autoExposureFor(new Array(100).fill(1e9))!).toBeGreaterThan(0);
    expect(autoExposureFor(new Array(100).fill(0.0011))!).toBeLessThanOrEqual(40);
  });

  it('smooths in the log domain, takes the first value as it is and ignores tiny changes', () => {
    expect(smoothExposure(null, 3)).toBe(3);
    expect(smoothExposure(1, 1.01)).toBe(1);
    const up = smoothExposure(1, 4, 0.5);
    expect(up).toBeCloseTo(2, 9); // halfway to 4 in the log domain
    let v: number | null = 1;
    for (let i = 0; i < 40; i++) v = smoothExposure(v, 0.1, 0.4);
    expect(v).toBeCloseTo(0.1, 1);
  });

  it('is on by default, validated and shared through the imaging params', () => {
    const c = defaultImaging();
    expect(c.autoExposure).toBe(true);
    expect(mergeImaging(c, { autoExposure: false })).toEqual([]);
    expect(c.autoExposure).toBe(false);
    expect(mergeImaging(c, { autoExposure: 'yes' })).toEqual(['imaging.autoExposure']);
    expect(c.autoExposure).toBe(false);
    expect(cloneImaging(c).autoExposure).toBe(false);
  });

  it('keeps the bone, the MRI level and the MRI context on the exposure slider and the radiograph tissue on its own uniform', () => {
    expect(IMG_COMPOSITE_FRAG).toContain('uniform float imgTissueExposure');
    expect(IMG_COMPOSITE_FRAG).toMatch(/imgAtt\(th\.r, [\d.]+, imgTissueExposure\)/);
    expect(IMG_COMPOSITE_FRAG).toMatch(/imgAtt\(th\.g, [\d.]+, imgExposure\)/);
    expect(IMG_COMPOSITE_FRAG).toMatch(/faint = [\d.]+ \* imgAtt\(th\.r, [\d.]+, imgExposure\)/);
  });
});

describe('caps only on closed solids (shader contract)', () => {
  it('paints caps and slab caps only where the element carries the closed flag (bit 4)', () => {
    expect(IMG_SLAB_FRAG).toContain('bool capBack = !gl_FrontFacing && flagClosed(vFlags)');
    expect(IMG_SLAB_FRAG).toContain('& 16');
  });
});
