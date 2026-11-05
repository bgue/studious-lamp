// The `pointcloud` section of the params document: display and alignment settings, not the data. Pure functions so
// the round trip is testable without a viewer.
//
// Alignment keys: coordinates, offset [x, y, z], rotationDeg (the manual nudge, unchanged since the first version),
// matrix (the registration, 16 numbers, column-major like three's Matrix4.elements; identity unless 3-point alignment
// or ICP found a tilt or a scale), keepVertical, allowScale. A document written before `matrix` existed has offset
// and rotationDeg only: it reads as the identity registration, which is what those numbers meant then.

import { COLOUR_MODES } from './colour';
import type { PointCloudSettings } from './controller';
import { identity, scaleOf } from './register';

export const COORD_MODE_LIST = ['project', 'viewer'] as const;
export const SCOPE_LIST = ['all elements', 'focus only'] as const;

export function collectPointCloudParams(s: PointCloudSettings): Record<string, unknown> {
  return {
    visible: s.visible, pointSize: s.pointSize, sizeAttenuation: s.sizeAttenuation,
    colourBy: s.colourBy === 'deviation' ? 'rgb' : s.colourBy, budget: s.budget, coordinates: s.coordinates,
    offset: [s.offsetX, s.offsetY, s.offsetZ], rotationDeg: s.rotationDeg, matrix: s.matrix.slice(), keepVertical: s.keepVertical,
    allowScale: s.allowScale, tolerance: s.tolerance, scope: s.scope,
  };
}

const obj = (v: unknown): Record<string, unknown> => (v && typeof v === 'object' ? (v as Record<string, unknown>) : {});

/** A usable registration: 16 finite numbers, last row 0 0 0 1, a rotation times a positive uniform scale. */
export function validRegistration(a: unknown): a is number[] {
  if (!Array.isArray(a) || a.length !== 16 || !a.every((x) => typeof x === 'number' && Number.isFinite(x))) return false;
  const m = a as number[];
  if (Math.abs(m[3]!) > 1e-9 || Math.abs(m[7]!) > 1e-9 || Math.abs(m[11]!) > 1e-9 || Math.abs(m[15]! - 1) > 1e-9) return false;
  const s = scaleOf(m);
  if (!(s > 0.001 && s < 1000)) return false;
  // columns orthogonal and of length s
  const col = (j: number): number[] => [m[j * 4]! / s, m[j * 4 + 1]! / s, m[j * 4 + 2]! / s];
  const dot = (u: number[], v: number[]): number => u[0]! * v[0]! + u[1]! * v[1]! + u[2]! * v[2]!;
  const c = [col(0), col(1), col(2)];
  for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) if (Math.abs(dot(c[i]!, c[j]!) - (i === j ? 1 : 0)) > 1e-6) return false;
  return true;
}

/** Apply a `pointcloud` value onto the settings. Bad keys go to `bad` as `${path}.key`; the rest still applies. */
export function applyPointCloudParams(s: PointCloudSettings, value: unknown, bad: string[], path: string): void {
  const o = obj(value);
  const num = (k: string, lo: number, hi: number, set: (v: number) => void): void => {
    if (o[k] === undefined) return;
    if (typeof o[k] === 'number' && Number.isFinite(o[k]) && (o[k] as number) >= lo && (o[k] as number) <= hi) set(o[k] as number);
    else bad.push(`${path}.${k}`);
  };
  const bool = (k: string, set: (v: boolean) => void): void => {
    if (o[k] === undefined) return;
    if (typeof o[k] === 'boolean') set(o[k] as boolean);
    else bad.push(`${path}.${k}`);
  };
  const pick = (k: string, list: readonly string[], set: (v: string) => void): void => {
    if (o[k] === undefined) return;
    if (typeof o[k] === 'string' && list.includes(o[k] as string)) set(o[k] as string);
    else bad.push(`${path}.${k}`);
  };
  bool('visible', (v) => (s.visible = v));
  bool('sizeAttenuation', (v) => (s.sizeAttenuation = v));
  bool('keepVertical', (v) => (s.keepVertical = v));
  bool('allowScale', (v) => (s.allowScale = v));
  num('pointSize', 1, 10, (v) => (s.pointSize = v));
  num('budget', 1000, 50_000_000, (v) => (s.budget = v));
  num('rotationDeg', -360, 360, (v) => (s.rotationDeg = v));
  num('tolerance', 0.0005, 5, (v) => (s.tolerance = v));
  pick('colourBy', COLOUR_MODES, (v) => (s.colourBy = v as typeof s.colourBy));
  pick('coordinates', COORD_MODE_LIST, (v) => (s.coordinates = v as typeof s.coordinates));
  pick('scope', SCOPE_LIST, (v) => (s.scope = v as typeof s.scope));
  if (o['offset'] !== undefined) {
    const a = o['offset'];
    if (Array.isArray(a) && a.length === 3 && a.every((x) => typeof x === 'number' && Number.isFinite(x))) {
      s.offsetX = a[0] as number;
      s.offsetY = a[1] as number;
      s.offsetZ = a[2] as number;
    } else bad.push(`${path}.offset`);
  }
  if (o['matrix'] !== undefined) {
    if (validRegistration(o['matrix'])) s.matrix = (o['matrix'] as number[]).slice();
    else bad.push(`${path}.matrix`);
  } else if (o['offset'] !== undefined || o['rotationDeg'] !== undefined) {
    // a document from before the registration matrix: its offset and rotation meant "no registration"
    s.matrix = identity();
  }
}
