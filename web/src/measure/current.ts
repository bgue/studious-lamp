// Read-only access to the measure tool's current measurements for other features (BCF annotations link to them).
// Goes through the tool's public scripting object (window.__xrayMeasure, set by plugins/measure.ts), so the tool itself
// needs no change. Points are in the viewer frame, like Measurement in maths.ts.

import { UNITS } from './maths';
import type { Measurement, Units } from './maths';

/** The current measurements (live array, do not modify); empty when the measure tool is not installed. */
export function currentMeasurements(): readonly Measurement[] {
  const m = (globalThis as { __xrayMeasure?: { list?: unknown } }).__xrayMeasure;
  return Array.isArray(m?.list) ? (m.list as Measurement[]) : [];
}

/** The measure tool's length unit ('m' or 'mm'); metres when the tool is not installed. */
export function currentMeasureUnits(): Units {
  const u = (globalThis as { __xrayMeasure?: { units?: unknown } }).__xrayMeasure?.units;
  return (UNITS as readonly unknown[]).includes(u) ? (u as Units) : 'm';
}
