// Settings of the imaging styles: types, defaults and the validation used by the params section and by
// window.__xrayImaging. Pure (no DOM, no GPU).

import { MRI_AXES, PALETTES, STYLES } from './maths';
import type { ImagingPalette, ImagingStyle, MriAxis } from './maths';

export interface MriConfig {
  axis: MriAxis;
  /** Slab thickness, metres. */
  thickness: number;
  /** 0..1 across the focus bounds along the axis. */
  position: number;
  scan: boolean;
  /** Fraction of the sweep per second. */
  scanSpeed: number;
}

export interface ImagingConfig {
  style: ImagingStyle;
  palette: ImagingPalette;
  exposure: number;
  /** Scale the tissue exposure so the 90th percentile of the context thickness maps to about 0.8; `exposure` then multiplies it. */
  autoExposure: boolean;
  contrast: number;
  boneGlow: number;
  tissueEdges: boolean;
  mri: MriConfig;
}

export function defaultImaging(): ImagingConfig {
  return {
    style: 'standard',
    palette: 'classic',
    exposure: 1,
    autoExposure: true,
    contrast: 1,
    boneGlow: 1,
    tissueEdges: true,
    mri: { axis: 'camera', thickness: 0.3, position: 0.5, scan: false, scanSpeed: 0.25 },
  };
}

export function cloneImaging(c: ImagingConfig): ImagingConfig {
  return { ...c, mri: { ...c.mri } };
}

const num = (v: unknown, lo: number, hi: number): number | undefined => (typeof v === 'number' && Number.isFinite(v) ? Math.min(hi, Math.max(lo, v)) : undefined);
const oneOf = <T extends string>(v: unknown, list: readonly T[]): T | undefined => (typeof v === 'string' && (list as readonly string[]).includes(v) ? (v as T) : undefined);

/** Merge `p` over `into`, ignoring invalid or unknown fields. Returns the dotted names it could not use. */
export function mergeImaging(into: ImagingConfig, p: unknown, prefix = 'imaging'): string[] {
  const bad: string[] = [];
  if (p === null || typeof p !== 'object') return p === undefined ? bad : [prefix];
  const o = p as Record<string, unknown>;
  for (const k of Object.keys(o)) {
    const v = o[k];
    let ok = true;
    switch (k) {
      case 'style': {
        const t = oneOf(v, STYLES);
        if (t) into.style = t;
        else ok = false;
        break;
      }
      case 'palette': {
        const t = oneOf(v, PALETTES);
        if (t) into.palette = t;
        else ok = false;
        break;
      }
      case 'exposure':
      case 'contrast':
      case 'boneGlow': {
        const n = num(v, 0, k === 'boneGlow' ? 5 : 10);
        if (n !== undefined) into[k] = n;
        else ok = false;
        break;
      }
      case 'tissueEdges':
      case 'autoExposure':
        if (typeof v === 'boolean') into[k] = v;
        else ok = false;
        break;
      case 'mri':
        bad.push(...mergeMri(into.mri, v, `${prefix}.mri`));
        break;
      default:
        ok = false;
    }
    if (!ok) bad.push(`${prefix}.${k}`);
  }
  return bad;
}

export function mergeMri(into: MriConfig, p: unknown, prefix = 'mri'): string[] {
  const bad: string[] = [];
  if (p === null || typeof p !== 'object') return p === undefined ? bad : [prefix];
  const o = p as Record<string, unknown>;
  for (const k of Object.keys(o)) {
    const v = o[k];
    let ok = true;
    switch (k) {
      case 'axis': {
        const t = oneOf(v, MRI_AXES);
        if (t) into.axis = t;
        else ok = false;
        break;
      }
      case 'thickness': {
        const n = num(v, 0.01, 50);
        if (n !== undefined) into.thickness = n;
        else ok = false;
        break;
      }
      case 'position': {
        const n = num(v, 0, 1);
        if (n !== undefined) into.position = n;
        else ok = false;
        break;
      }
      case 'scanSpeed': {
        const n = num(v, 0, 5);
        if (n !== undefined) into.scanSpeed = n;
        else ok = false;
        break;
      }
      case 'scan':
        if (typeof v === 'boolean') into.scan = v;
        else ok = false;
        break;
      default:
        ok = false;
    }
    if (!ok) bad.push(`${prefix}.${k}`);
  }
  return bad;
}
