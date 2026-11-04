import { describe, expect, it } from 'vitest';
import { detectXr } from '../src/xr/session';

const nav = (modes: Record<string, boolean | Error>): { xr: { isSessionSupported(m: string): Promise<boolean> } } => ({
  xr: {
    isSessionSupported: async (m: string) => {
      const v = modes[m];
      if (v instanceof Error) throw v;
      return v ?? false;
    },
  },
});

describe('WebXR feature detection', () => {
  it('reports both modes when the device supports them', async () => {
    expect(await detectXr(nav({ 'immersive-vr': true, 'immersive-ar': true }))).toEqual({ vr: true, ar: true });
  });

  it('reports each mode on its own', async () => {
    expect(await detectXr(nav({ 'immersive-vr': true, 'immersive-ar': false }))).toEqual({ vr: true, ar: false });
    expect(await detectXr(nav({ 'immersive-ar': true }))).toEqual({ vr: false, ar: true });
  });

  it('hides everything without navigator.xr, with a broken one, or when the query throws', async () => {
    expect(await detectXr(undefined)).toEqual({ vr: false, ar: false });
    expect(await detectXr({})).toEqual({ vr: false, ar: false });
    expect(await detectXr({ xr: {} })).toEqual({ vr: false, ar: false });
    expect(await detectXr(nav({ 'immersive-vr': new Error('SecurityError'), 'immersive-ar': new Error('NotAllowed') }))).toEqual({ vr: false, ar: false });
  });

  it('treats a truthy but not true answer as unsupported', async () => {
    const odd = { xr: { isSessionSupported: async () => 'yes' as unknown as boolean } };
    expect(await detectXr(odd)).toEqual({ vr: false, ar: false });
  });
});
