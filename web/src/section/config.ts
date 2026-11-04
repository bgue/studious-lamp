// Settings of sectioning: types, defaults and validation (params section, window.__xraySection). Pure.

import type { Vec3 } from './maths';

export type RGB = [number, number, number];
export const FITS = ['selection', 'model'] as const;
export type Fit = (typeof FITS)[number];
export const PLANE_AXES = ['x', 'y', 'z', 'camera'] as const;
export type PlaneAxisName = (typeof PLANE_AXES)[number];

export interface BoxConfig {
  enabled: boolean;
  fit: Fit;
  /** Metres added around the fitted bounds. */
  margin: number;
  /** Explicit box (after a fit or a drag). Null until the first fit. */
  min: Vec3 | null;
  max: Vec3 | null;
}

export interface PlaneConfig {
  enabled: boolean;
  axis: PlaneAxisName;
  /** Metres from the fitted centre. */
  offset: number;
  flip: boolean;
}

export interface SectionConfig {
  box: BoxConfig;
  plane: PlaneConfig;
  caps: boolean;
  capColor: RGB;
  /** Draw the box outline and the drag handles. */
  showHandles: boolean;
}

export function defaultSection(): SectionConfig {
  return {
    box: { enabled: false, fit: 'selection', margin: 0.5, min: null, max: null },
    plane: { enabled: false, axis: 'y', offset: 0, flip: false },
    caps: true,
    capColor: [0.93, 0.78, 0.5],
    showHandles: true,
  };
}

export function cloneSection(c: SectionConfig): SectionConfig {
  return { box: { ...c.box, min: c.box.min ? [...c.box.min] : null, max: c.box.max ? [...c.box.max] : null }, plane: { ...c.plane }, caps: c.caps, capColor: [...c.capColor], showHandles: c.showHandles };
}

const num = (v: unknown, lo: number, hi: number): number | undefined => (typeof v === 'number' && Number.isFinite(v) ? Math.min(hi, Math.max(lo, v)) : undefined);
const oneOf = <T extends string>(v: unknown, list: readonly T[]): T | undefined => (typeof v === 'string' && (list as readonly string[]).includes(v) ? (v as T) : undefined);
const vec3 = (v: unknown): Vec3 | undefined => (Array.isArray(v) && v.length === 3 && v.every((x) => typeof x === 'number' && Number.isFinite(x)) ? [v[0] as number, v[1] as number, v[2] as number] : undefined);

export interface MergeResult {
  bad: string[];
  /** The box fit or margin changed without an explicit min / max in the same partial: the plugin should refit. */
  refit: boolean;
  /** Anything that affects the planes changed. */
  changed: boolean;
}

/** Merge `p` over `into`, ignoring invalid or unknown fields. */
export function mergeSection(into: SectionConfig, p: unknown, prefix = 'section'): MergeResult {
  const res: MergeResult = { bad: [], refit: false, changed: false };
  if (p === null || typeof p !== 'object') {
    if (p !== undefined) res.bad.push(prefix);
    return res;
  }
  const o = p as Record<string, unknown>;
  for (const k of Object.keys(o)) {
    const v = o[k];
    let ok = true;
    switch (k) {
      case 'caps':
      case 'showHandles':
        if (typeof v === 'boolean') into[k] = v;
        else ok = false;
        break;
      case 'capColor': {
        const c = vec3(v);
        if (c) into.capColor = [Math.min(1, Math.max(0, c[0])), Math.min(1, Math.max(0, c[1])), Math.min(1, Math.max(0, c[2]))];
        else ok = false;
        break;
      }
      case 'box':
        mergeBox(into.box, v, `${prefix}.box`, res);
        break;
      case 'plane':
        mergePlane(into.plane, v, `${prefix}.plane`, res);
        break;
      default:
        ok = false;
    }
    if (!ok) res.bad.push(`${prefix}.${k}`);
    else if (k !== 'box' && k !== 'plane') res.changed = true;
  }
  return res;
}

function mergeBox(into: BoxConfig, p: unknown, prefix: string, res: MergeResult): void {
  if (p === null || typeof p !== 'object') {
    if (p !== undefined) res.bad.push(prefix);
    return;
  }
  const o = p as Record<string, unknown>;
  let explicit = false;
  let refit = false;
  for (const k of Object.keys(o)) {
    const v = o[k];
    let ok = true;
    switch (k) {
      case 'enabled':
        if (typeof v === 'boolean') into.enabled = v;
        else ok = false;
        break;
      case 'fit': {
        const t = oneOf(v, FITS);
        if (t) {
          if (t !== into.fit) refit = true;
          into.fit = t;
        } else ok = false;
        break;
      }
      case 'margin': {
        const n = num(v, 0, 100);
        if (n !== undefined) {
          if (n !== into.margin) refit = true;
          into.margin = n;
        } else ok = false;
        break;
      }
      case 'min':
      case 'max': {
        if (v === null) into[k] = null;
        else {
          const c = vec3(v);
          if (c) {
            into[k] = c;
            explicit = true;
          } else ok = false;
        }
        break;
      }
      default:
        ok = false;
    }
    if (!ok) res.bad.push(`${prefix}.${k}`);
    else res.changed = true;
  }
  if (refit && !explicit) res.refit = true;
}

function mergePlane(into: PlaneConfig, p: unknown, prefix: string, res: MergeResult): void {
  if (p === null || typeof p !== 'object') {
    if (p !== undefined) res.bad.push(prefix);
    return;
  }
  const o = p as Record<string, unknown>;
  for (const k of Object.keys(o)) {
    const v = o[k];
    let ok = true;
    switch (k) {
      case 'enabled':
      case 'flip':
        if (typeof v === 'boolean') into[k] = v;
        else ok = false;
        break;
      case 'axis': {
        const t = oneOf(v, PLANE_AXES);
        if (t) into.axis = t;
        else ok = false;
        break;
      }
      case 'offset': {
        const n = num(v, -1000, 1000);
        if (n !== undefined) into.offset = n;
        else ok = false;
        break;
      }
      default:
        ok = false;
    }
    if (!ok) res.bad.push(`${prefix}.${k}`);
    else res.changed = true;
  }
}
