// Settings of the view modes: types, defaults and the validation used by the params section and by
// window.__xrayViewModes. Pure (no DOM, no GPU).

import { APPLY_TO, FRONT_TREATMENTS, PEEL_EPS, PLANE_ORIENTATIONS } from './maths';
import type { ApplyTo, FrontTreatment, PlaneOrientation } from './maths';

export type RGB = [number, number, number];

export interface BehindConfig {
  enabled: boolean;
  frontTreatment: FrontTreatment;
  /** Metres: plane pushed toward the camera (negative: into the focus). For 'horizontal', above the focus top. */
  offset: number;
  /** Alpha of the front fragments under the 'ghost' treatment, independent of the sightline result. */
  frontAlpha: number;
  orientation: PlaneOrientation;
  applyTo: ApplyTo;
  /** Keep the sightline alpha of fragments behind the plane instead of drawing them solid. */
  keepXrayBehind: boolean;
  capColour: RGB;
}

export type PeelOutside = 'x-ray' | 'solid';
export const PEEL_OUTSIDE: readonly PeelOutside[] = ['x-ray', 'solid'];

export interface PeelConfig {
  enabled: boolean;
  /** Metres at the focus depth. */
  radius: number;
  slope: number;
  /** Metres. */
  feather: number;
  rimBand: boolean;
  rimColour: RGB;
  capColour: RGB;
  outside: PeelOutside;
  applyTo: ApplyTo;
  /** Grow the radius from 0 over 500 ms on enable and on selection change. */
  animate: boolean;
  /** Metres: context closer than this to the focus depth (a host wall around a window) is not cut. Not in the panel. */
  depthEps: number;
}

export interface ViewModesConfig {
  behind: BehindConfig;
  peel: PeelConfig;
}

export const DEFAULT_BEHIND: BehindConfig = {
  enabled: false,
  frontTreatment: 'cut',
  offset: 0.2,
  frontAlpha: 0.12,
  orientation: 'camera',
  applyTo: 'all context',
  keepXrayBehind: false,
  capColour: [0.93, 0.78, 0.5],
};

export const DEFAULT_PEEL: PeelConfig = {
  enabled: false,
  radius: 0.4,
  slope: 0.6,
  feather: 0.08,
  rimBand: true,
  rimColour: [1.0, 0.55, 0.12],
  capColour: [0.93, 0.78, 0.5],
  outside: 'x-ray',
  applyTo: 'all context',
  animate: true,
  depthEps: PEEL_EPS,
};

export function defaultViewModes(): ViewModesConfig {
  return { behind: { ...DEFAULT_BEHIND, capColour: [...DEFAULT_BEHIND.capColour] }, peel: { ...DEFAULT_PEEL, rimColour: [...DEFAULT_PEEL.rimColour], capColour: [...DEFAULT_PEEL.capColour] } };
}

const num = (v: unknown, lo: number, hi: number): number | undefined => (typeof v === 'number' && Number.isFinite(v) ? Math.min(hi, Math.max(lo, v)) : undefined);
const oneOf = <T extends string>(v: unknown, list: readonly T[]): T | undefined => (typeof v === 'string' && (list as readonly string[]).includes(v) ? (v as T) : undefined);
const rgb = (v: unknown): RGB | undefined =>
  Array.isArray(v) && v.length === 3 && v.every((x) => typeof x === 'number' && Number.isFinite(x)) ? (v.map((x) => Math.min(1, Math.max(0, x as number))) as RGB) : undefined;

/** Merge `p` over `into`, ignoring invalid or unknown fields. Returns the dotted names it could not use. */
export function mergeBehind(into: BehindConfig, p: unknown, prefix = 'behind'): string[] {
  const bad: string[] = [];
  if (p === null || typeof p !== 'object') return p === undefined ? bad : [prefix];
  const o = p as Record<string, unknown>;
  for (const k of Object.keys(o)) {
    const v = o[k];
    let ok = true;
    switch (k) {
      case 'enabled':
      case 'keepXrayBehind':
        if (typeof v === 'boolean') into[k] = v;
        else ok = false;
        break;
      case 'frontTreatment': {
        const t = oneOf(v, FRONT_TREATMENTS);
        if (t) into.frontTreatment = t;
        else ok = false;
        break;
      }
      case 'orientation': {
        const t = oneOf(v, PLANE_ORIENTATIONS);
        if (t) into.orientation = t;
        else ok = false;
        break;
      }
      case 'applyTo': {
        const t = oneOf(v, APPLY_TO);
        if (t) into.applyTo = t;
        else ok = false;
        break;
      }
      case 'offset': {
        const n = num(v, -20, 20);
        if (n !== undefined) into.offset = n;
        else ok = false;
        break;
      }
      case 'frontAlpha': {
        const n = num(v, 0, 1);
        if (n !== undefined) into.frontAlpha = n;
        else ok = false;
        break;
      }
      case 'capColour': {
        const c = rgb(v);
        if (c) into.capColour = c;
        else ok = false;
        break;
      }
      default:
        ok = false;
    }
    if (!ok) bad.push(`${prefix}.${k}`);
  }
  return bad;
}

export function mergePeel(into: PeelConfig, p: unknown, prefix = 'peel'): string[] {
  const bad: string[] = [];
  if (p === null || typeof p !== 'object') return p === undefined ? bad : [prefix];
  const o = p as Record<string, unknown>;
  for (const k of Object.keys(o)) {
    const v = o[k];
    let ok = true;
    switch (k) {
      case 'enabled':
      case 'rimBand':
      case 'animate':
        if (typeof v === 'boolean') into[k] = v;
        else ok = false;
        break;
      case 'radius':
      case 'slope':
      case 'feather':
      case 'depthEps': {
        const n = num(v, 0, k === 'radius' ? 10 : k === 'slope' ? 5 : 2);
        if (n !== undefined) into[k] = n;
        else ok = false;
        break;
      }
      case 'rimColour':
      case 'capColour': {
        const c = rgb(v);
        if (c) into[k] = c;
        else ok = false;
        break;
      }
      case 'outside': {
        const t = oneOf(v, PEEL_OUTSIDE);
        if (t) into.outside = t;
        else ok = false;
        break;
      }
      case 'applyTo': {
        const t = oneOf(v, APPLY_TO);
        if (t) into.applyTo = t;
        else ok = false;
        break;
      }
      default:
        ok = false;
    }
    if (!ok) bad.push(`${prefix}.${k}`);
  }
  return bad;
}

export function cloneViewModes(c: ViewModesConfig): ViewModesConfig {
  return JSON.parse(JSON.stringify(c)) as ViewModesConfig;
}
