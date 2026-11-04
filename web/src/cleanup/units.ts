// Units of the cleanup thresholds. Rules store SI values (metres, m³); the panel and the drawer show lengths in the
// unit the user picks (mm, cm or m) and convert on the way in and out. Pure, no DOM.

import type { SizeMetric } from './analysis';

export const LENGTH_UNITS = ['mm', 'cm', 'm'] as const;
export type LengthUnit = (typeof LENGTH_UNITS)[number];
export const DEFAULT_LENGTH_UNIT: LengthUnit = 'm';

/** Metres per display unit. */
export const UNIT_SCALE: Record<LengthUnit, number> = { mm: 0.001, cm: 0.01, m: 1 };

export function isLengthUnit(v: unknown): v is LengthUnit {
  return typeof v === 'string' && (LENGTH_UNITS as readonly string[]).includes(v);
}

/** Strip float noise (0.1 * 3 and friends) without rounding real precision away. */
function clean(v: number): number {
  return Number.isFinite(v) ? Number(v.toPrecision(12)) : v;
}

/** Metres to the display unit. */
export function toDisplay(metres: number, unit: LengthUnit): number {
  return clean(metres / UNIT_SCALE[unit]);
}

/** Display unit to metres. */
export function fromDisplay(value: number, unit: LengthUnit): number {
  return clean(value * UNIT_SCALE[unit]);
}

/** Slider range of a length control in the display unit, from its range in metres. */
export function displayRange(minM: number, maxM: number, stepM: number, unit: LengthUnit): { min: number; max: number; step: number } {
  return { min: toDisplay(minM, unit), max: toDisplay(maxM, unit), step: toDisplay(stepM, unit) };
}

/** "max size (mm)". */
export function withUnit(label: string, unit: string): string {
  return `${label} (${unit})`;
}

/** Whether the floating threshold of a size metric is a length (and so follows the length unit). */
export function metricIsLength(metric: SizeMetric): boolean {
  return metric === 'largest dimension (m)';
}

/** Unit of the floating threshold for a size metric: the length unit, m³ or triangles. */
export function metricUnit(metric: SizeMetric, unit: LengthUnit): string {
  if (metricIsLength(metric)) return unit;
  if (metric === 'triangle count') return 'triangles';
  return 'm³';
}

/** The size metric without its unit, for the option labels: "largest dimension (m)" gives "largest dimension". */
export function metricLabel(metric: SizeMetric): string {
  return metric.replace(/\s*\(.*\)$/, '');
}

/** Threshold of a size metric in display units, and back. Only lengths convert. */
export function metricToDisplay(metric: SizeMetric, value: number, unit: LengthUnit): number {
  return metricIsLength(metric) ? toDisplay(value, unit) : value;
}
export function metricFromDisplay(metric: SizeMetric, value: number, unit: LengthUnit): number {
  return metricIsLength(metric) ? fromDisplay(value, unit) : value;
}
