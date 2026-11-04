import { describe, expect, it } from 'vitest';
import {
  LENGTH_UNITS, displayRange, fromDisplay, isLengthUnit, metricFromDisplay, metricLabel, metricToDisplay, metricUnit, toDisplay, withUnit,
} from '../src/cleanup/units';
import { SIZE_METRICS } from '../src/cleanup/analysis';
import { lookupHelp } from '../src/ui/help';
import { HELP } from '../src/ui/helpText';

describe('cleanup length units', () => {
  it('converts metres to mm, cm and m and back without float noise', () => {
    expect(toDisplay(0.05, 'mm')).toBe(50);
    expect(toDisplay(0.05, 'cm')).toBe(5);
    expect(toDisplay(0.05, 'm')).toBe(0.05);
    expect(toDisplay(0.3, 'mm')).toBe(300);
    expect(fromDisplay(50, 'mm')).toBe(0.05);
    expect(fromDisplay(3, 'cm')).toBe(0.03);
    for (const u of LENGTH_UNITS) for (const m of [0, 0.001, 0.01, 0.123, 1.5, 600]) expect(fromDisplay(toDisplay(m, u), u)).toBe(m);
  });

  it('scales slider ranges and labels with the unit', () => {
    expect(displayRange(0, 1, 0.001, 'mm')).toEqual({ min: 0, max: 1000, step: 1 });
    expect(displayRange(0, 0.5, 0.001, 'cm')).toEqual({ min: 0, max: 50, step: 0.1 });
    expect(withUnit('max size', 'mm')).toBe('max size (mm)');
    expect(isLengthUnit('cm')).toBe(true);
    expect(isLengthUnit('in')).toBe(false);
  });

  it('gives each size metric its unit: the length unit, m³ or triangles; only lengths convert', () => {
    const [dim, bvol, mvol, tri] = SIZE_METRICS;
    expect(metricUnit(dim, 'mm')).toBe('mm');
    expect(metricUnit(bvol, 'mm')).toBe('m³');
    expect(metricUnit(mvol, 'cm')).toBe('m³');
    expect(metricUnit(tri, 'm')).toBe('triangles');
    expect(metricLabel(dim)).toBe('largest dimension');
    expect(metricLabel(tri)).toBe('triangle count');
    expect(metricToDisplay(dim, 0.5, 'mm')).toBe(500);
    expect(metricFromDisplay(dim, 500, 'mm')).toBe(0.5);
    expect(metricToDisplay(bvol, 0.05, 'mm')).toBe(0.05);
    expect(metricFromDisplay(tri, 100, 'mm')).toBe(100);
  });
});

describe('help lookup of labels with a unit', () => {
  it('maps (mm) and (cm) to the (m) entry and drops a unit that follows another setting', () => {
    expect(lookupHelp('Tiny/max size (mm)')).toBe(HELP['Tiny/max size (m)']);
    expect(lookupHelp('Tiny/max size (cm)')).toBe(HELP['Tiny/max size (m)']);
    expect(lookupHelp('Floating/contact tolerance (mm)')).toBe(HELP['Floating/contact tolerance (m)']);
    expect(lookupHelp('Floating/threshold (m³)')).toBe(HELP['Floating/threshold']);
    expect(lookupHelp('Floating/threshold (triangles)')).toBe(HELP['Floating/threshold']);
    expect(lookupHelp('Distant strays/distance factor (× radius)')).toBe(HELP['Distant strays/distance factor']);
    expect(lookupHelp('Distant strays/min gap (mm)')).toBe(HELP['Distant strays/min gap (m)']);
    expect(lookupHelp('Nowhere/Nothing (mm)')).toBeUndefined();
  });

  it('has an entry for every cleanup control and every renamed control', () => {
    for (const k of ['Model cleanup/length unit', 'Distant strays/max size (m)', 'Classification (Alg 1)/bufferLo (m)', 'Classification (Alg 1)/bufferHi (m)',
      'Edge glow', 'Edge glow/glow scope', 'Edge glow/Edge glow']) expect(lookupHelp(k), k).toBeDefined();
  });
});
