// Class styles: per-class base alpha cap, ghosting floor, colour and visibility.
//
// Resolution for an element e: every alias whose patterns match e contributes its style
// (aliases in key order, later keys win per field), then the style keyed by e.ifcClass is
// laid over it, so element-level entries win over alias entries field by field.

import type { ClassStyle, ClassStyles, ElementRecord, SceneModel, XrayConfig } from './types';

export type MaterialAliases = Record<string, string[]>;

/** The merged style of one element, plus where alphaMax came from. */
export interface ResolvedStyle {
  alphaMax?: number;
  alphaMin?: number;
  floor?: number;
  color?: [number, number, number];
  hidden?: boolean;
  /** alphaMax of the class-level (non-alias) entry only. Focus elements honour just this one. */
  alphaMaxOwn?: number;
}

const FIELDS = ['alphaMax', 'alphaMin', 'floor', 'color', 'hidden'] as const;

/** "IfcBeam" matches the class; "IfcBeam:steel" also needs the material name to contain "steel". */
export function patternMatches(pattern: string, el: Pick<ElementRecord, 'ifcClass' | 'material'>): boolean {
  const i = pattern.indexOf(':');
  if (i < 0) return pattern.trim() === el.ifcClass;
  const cls = pattern.slice(0, i).trim();
  const sub = pattern.slice(i + 1).trim().toLowerCase();
  if (cls !== el.ifcClass) return false;
  return sub === '' || (el.material ?? '').toLowerCase().includes(sub);
}

export function aliasMatches(patterns: readonly string[], el: Pick<ElementRecord, 'ifcClass' | 'material'>): boolean {
  return patterns.some((p) => patternMatches(p, el));
}

function overlay(into: ResolvedStyle, s: ClassStyle): void {
  for (const f of FIELDS) {
    const v = s[f];
    if (v !== undefined) (into as Record<string, unknown>)[f] = v;
  }
}

/** Per-element resolved style, null where no style applies. Index = element id. */
export function resolveStyleIndex(
  model: Pick<SceneModel, 'elements'>,
  styles: ClassStyles,
  aliases: MaterialAliases = {},
): Array<ResolvedStyle | null> {
  const aliasKeys = Object.keys(aliases).filter((k) => styles[k] !== undefined);
  return model.elements.map((el) => {
    let out: ResolvedStyle | null = null;
    for (const k of aliasKeys) {
      if (k === el.ifcClass) continue; // a key equal to the class is the class-level entry
      if (!aliasMatches(aliases[k]!, el)) continue;
      out ??= {};
      overlay(out, styles[k]!);
    }
    const own = styles[el.ifcClass];
    if (own) {
      out ??= {};
      overlay(out, own);
      if (own.alphaMax !== undefined) out.alphaMaxOwn = own.alphaMax;
    }
    return out;
  });
}

/**
 * Style keys that are meaningful for the model, with the number of elements each covers:
 * every ifcClass present, plus every alias that matches at least one element.
 * Classes first (alphabetical), then aliases.
 */
export function styleKeyCounts(
  model: Pick<SceneModel, 'elements'>,
  aliases: MaterialAliases = {},
): Array<{ key: string; count: number; kind: 'class' | 'alias' }> {
  const classes = new Map<string, number>();
  for (const el of model.elements) classes.set(el.ifcClass, (classes.get(el.ifcClass) ?? 0) + 1);
  const out: Array<{ key: string; count: number; kind: 'class' | 'alias' }> = [];
  for (const [key, count] of [...classes].sort((a, b) => a[0].localeCompare(b[0]))) out.push({ key, count, kind: 'class' });
  for (const [key, patterns] of Object.entries(aliases)) {
    if (classes.has(key)) continue;
    let count = 0;
    for (const el of model.elements) if (aliasMatches(patterns, el)) count++;
    if (count > 0) out.push({ key, count, kind: 'alias' });
  }
  return out;
}

function cleanStyle(s: unknown): ClassStyle | null {
  if (!s || typeof s !== 'object') return null;
  const o = s as Record<string, unknown>;
  const out: ClassStyle = {};
  const num = (v: unknown): number | undefined => (typeof v === 'number' && Number.isFinite(v) ? Math.min(1, Math.max(0, v)) : undefined);
  const aMax = num(o['alphaMax']);
  const aMin = num(o['alphaMin']);
  const fl = num(o['floor']);
  if (aMax !== undefined) out.alphaMax = aMax;
  if (aMin !== undefined) out.alphaMin = aMin;
  if (fl !== undefined) out.floor = fl;
  const c = o['color'];
  if (Array.isArray(c) && c.length >= 3 && c.slice(0, 3).every((x) => typeof x === 'number' && Number.isFinite(x))) {
    out.color = [0, 1, 2].map((i) => Math.min(1, Math.max(0, c[i] as number))) as [number, number, number];
  }
  if (typeof o['hidden'] === 'boolean') out.hidden = o['hidden'];
  return out;
}

/** Validate untrusted JSON (config file, sidecar, localStorage) into a clean ClassStyles. */
export function sanitizeStyles(raw: unknown): ClassStyles {
  const out: ClassStyles = {};
  if (!raw || typeof raw !== 'object') return out;
  for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
    const s = cleanStyle(v);
    if (s) out[k] = s;
  }
  return out;
}

export function sanitizeAliases(raw: unknown): MaterialAliases {
  const out: MaterialAliases = {};
  if (!raw || typeof raw !== 'object') return out;
  for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
    if (Array.isArray(v)) out[k] = v.filter((x): x is string => typeof x === 'string');
  }
  return out;
}

/**
 * Layer style sets, lowest precedence first. Per key, fields of later layers win; aliases of
 * later layers replace the alias of the same name.
 */
export function mergeStyles(...layers: Array<ClassStyles | undefined>): ClassStyles {
  const out: ClassStyles = {};
  for (const layer of layers) {
    if (!layer) continue;
    for (const [k, s] of Object.entries(layer)) out[k] = { ...(out[k] ?? {}), ...s };
  }
  return out;
}

export function mergeAliases(...layers: Array<MaterialAliases | undefined>): MaterialAliases {
  const out: MaterialAliases = {};
  for (const layer of layers) if (layer) for (const [k, v] of Object.entries(layer)) out[k] = [...v];
  return out;
}

export function parseConfig(raw: unknown): { classStyles: ClassStyles; materialAliases: MaterialAliases } {
  const o = (raw && typeof raw === 'object' ? raw : {}) as Partial<XrayConfig>;
  return { classStyles: sanitizeStyles(o.classStyles), materialAliases: sanitizeAliases(o.materialAliases) };
}

export function toConfig(classStyles: ClassStyles, materialAliases: MaterialAliases): XrayConfig {
  return { schema: 'xray-config/1', classStyles, materialAliases };
}
