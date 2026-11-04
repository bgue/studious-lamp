import { describe, expect, it } from 'vitest';
import { PEEL_OUTSIDE, cloneViewModes, defaultViewModes, mergeBehind, mergePeel } from '../src/viewModes/config';
import { occluderMask } from '../src/viewModes/occluders';
import type { Classification } from '../src/types';
import { VIEWMODE_GLSL, PEEL_STEP_FRAG } from '../src/render/viewModeGlsl';
import { MESH_FRAG, MESH_VERT, EDGE_FRAG } from '../src/render/shaders';
import { JFA_START, PEEL_CAP_SLACK, PEEL_MAX_ELLIPSES } from '../src/viewModes/maths';

describe('view mode settings', () => {
  it('defaults follow the spec', () => {
    const c = defaultViewModes();
    expect(c.behind).toMatchObject({ enabled: false, frontTreatment: 'cut', offset: 0.2, frontAlpha: 0.12, orientation: 'camera', applyTo: 'all context', keepXrayBehind: false });
    expect(c.peel).toMatchObject({ enabled: false, radius: 0.4, slope: 0.6, feather: 0.08, rimBand: true, outside: 'x-ray', applyTo: 'all context', animate: true });
    expect(PEEL_OUTSIDE).toEqual(['x-ray', 'solid']);
  });

  it('merges valid fields, clamps numbers and reports the rest', () => {
    const c = defaultViewModes();
    const bad = mergeBehind(c.behind, { enabled: true, frontTreatment: 'ghost', offset: -0.5, frontAlpha: 7, orientation: 'sideways', nope: 1, capColour: [2, 0, 0.5] });
    expect(bad.sort()).toEqual(['behind.nope', 'behind.orientation']);
    expect(c.behind.enabled).toBe(true);
    expect(c.behind.frontTreatment).toBe('ghost');
    expect(c.behind.offset).toBe(-0.5);
    expect(c.behind.frontAlpha).toBe(1);
    expect(c.behind.orientation).toBe('camera');
    expect(c.behind.capColour).toEqual([1, 0, 0.5]);
    expect(mergePeel(c.peel, { radius: 'big', outside: 'solid', feather: 0.2 })).toEqual(['peel.radius']);
    expect(c.peel.outside).toBe('solid');
    expect(c.peel.feather).toBe(0.2);
    expect(mergePeel(c.peel, 5)).toEqual(['peel']);
    expect(mergePeel(c.peel, undefined)).toEqual([]);
  });

  it('clone is deep and JSON safe', () => {
    const a = defaultViewModes();
    const b = cloneViewModes(a);
    b.peel.rimColour[0] = 0;
    expect(a.peel.rimColour[0]).toBe(1);
    expect(JSON.parse(JSON.stringify(a))).toEqual(a);
  });
});

describe('occluder mask', () => {
  it('marks host, near and blocking far; not focus, not far without occlusion', () => {
    const c: Classification = { focus: new Set([0]), host: new Set([1]), near: new Set([2]), far: new Set([3, 4]), proximityWeight: new Map(), bufferRadius: new Map() };
    const m = occluderMask(6, c, new Map([[3, 0.4], [4, 0]]));
    expect(Array.from(m)).toEqual([0, 1, 1, 1, 0, 0]);
  });
});

describe('view mode shaders', () => {
  it('share the maths constants and are wired into every pass', () => {
    expect(VIEWMODE_GLSL).toContain(`PEEL_CAP_SLACK = ${PEEL_CAP_SLACK}`);
    expect(VIEWMODE_GLSL).toContain(`PEEL_MAX_ELLIPSES = ${PEEL_MAX_ELLIPSES}`);
    expect(MESH_FRAG).toContain('vmEval(');
    expect(EDGE_FRAG).toContain('vmEval(');
    expect(MESH_VERT).toContain('vmAny');
    expect(JFA_START).toBeGreaterThanOrEqual(64);
    expect(PEEL_STEP_FRAG).toContain('texelFetch');
  });

  it('the original passes are unchanged when no view mode is on: alpha test in the vertex shader keeps its first form', () => {
    expect(MESH_VERT).toContain('vAlpha < OPAQUE_ALPHA && !(sweepEnabled > 0.5 && vHold >= OPAQUE_ALPHA) && vmAny < 0.5');
  });
});
