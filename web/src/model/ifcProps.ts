// Element properties for hover info: the pure rules shared by the browser reader (ifcRaw.ts) and mirrored by the
// converter (tools/glb_common.py: finalize_props and friends). No web-ifc and no three.js imports.
//
// Key format: `Attr.ObjectType | Attr.Tag | Attr.Description | Attr.PredefinedType`, `<PsetName>.<PropName>` for a
// single-value property, `<QtoName>.<QuantityName>` for a quantity. Groups, in output order:
//   0 attributes, 1 single-value properties of Pset_*Common, 2 base quantities with a whitelisted name, 3 everything else
// (`all` only). The cap is 24 entries, strings are cut to 80 characters, reals are rounded to 4 significant digits
// (integers are exact), measures are converted to SI (m, m2, m3, kg) with the file's project units. Keep in sync with
// glb_common.py.

export type PropValue = string | number | boolean;
export type PropsMode = 'none' | 'common' | 'all';

export const PROPS_CAP = 24;
export const PROPS_STR_MAX = 80;
export const PROPS_SIG_DIGITS = 4;

/** Quantity names kept in `common` mode (from a base quantity set). */
export const COMMON_QTY_NAMES: ReadonlySet<string> = new Set([
  'Length', 'Width', 'Height', 'Depth', 'Perimeter', 'NetArea', 'GrossArea', 'NetVolume', 'GrossVolume',
  'NetSideArea', 'GrossSideArea', 'CrossSectionArea', 'OuterSurfaceArea', 'NetWeight',
]);

export interface PropEntry { key: string; value: PropValue; group: number }

export const GROUP_ATTR = 0;
export const GROUP_COMMON = 1;
export const GROUP_QTY = 2;
export const GROUP_OTHER = 3;

/** `Pset_WallCommon`, `Pset_SlabCommon`, ... */
export const isCommonPset = (name: string): boolean => /^Pset_.*Common$/.test(name);
/** `Qto_WallBaseQuantities`, and the IFC2x3 name `BaseQuantities`. */
export const isBaseQtoSet = (name: string): boolean => /^Qto_.*BaseQuantities$/.test(name) || name === 'BaseQuantities';

/** Group of a single-value property, or null when the mode drops it. */
export function propertyGroup(setName: string, mode: PropsMode): number | null {
  if (mode === 'none') return null;
  if (isCommonPset(setName)) return GROUP_COMMON;
  return mode === 'all' ? GROUP_OTHER : null;
}

/** Group of a quantity, or null when the mode drops it. */
export function quantityGroup(setName: string, qtyName: string, mode: PropsMode): number | null {
  if (mode === 'none') return null;
  if (isBaseQtoSet(setName) && COMMON_QTY_NAMES.has(qtyName)) return GROUP_QTY;
  return mode === 'all' ? GROUP_OTHER : null;
}

/** Round to `digits` significant digits (4 by default). */
export function roundSig(x: number, digits = PROPS_SIG_DIGITS): number {
  if (!Number.isFinite(x) || x === 0) return x === 0 ? 0 : NaN;
  return Number(x.toPrecision(digits));
}

/** First 80 characters (code points). */
export function clipString(s: string): string {
  if (s.length <= PROPS_STR_MAX) return s;
  return Array.from(s).slice(0, PROPS_STR_MAX).join('');
}

/** SI factors of the project units: metres, square metres, cubic metres, kilograms per file unit. */
export interface UnitScales { length: number; area: number; volume: number; mass: number }
export const SI_SCALES: UnitScales = { length: 1, area: 1, volume: 1, mass: 1 };

const LENGTH_TYPES = new Set(['ifclengthmeasure', 'ifcpositivelengthmeasure', 'ifcnonnegativelengthmeasure']);
const INTEGER_TYPES = new Set(['ifcinteger', 'ifccountmeasure', 'ifctimestamp']);

/**
 * Number from an IFC value of type `typeName` (any case): measures converted to SI with `scales`, integers kept exact,
 * reals rounded to 4 significant digits. Returns null for NaN or infinity.
 */
export function normalizeNumber(typeName: string, x: number, scales: UnitScales): number | null {
  const t = typeName.toLowerCase();
  if (INTEGER_TYPES.has(t)) return Number.isFinite(x) ? x : null;
  let v = x;
  if (LENGTH_TYPES.has(t)) v = x * scales.length;
  else if (t === 'ifcareameasure') v = x * scales.area;
  else if (t === 'ifcvolumemeasure') v = x * scales.volume;
  else if (t === 'ifcmassmeasure') v = x * scales.mass;
  const r = roundSig(v);
  return Number.isFinite(r) ? r : null;
}

/** Entries -> ordered record: stable by group, first key wins, capped at 24. `undefined` when empty. */
export function finalizeProps(entries: PropEntry[], cap = PROPS_CAP): Record<string, PropValue> | undefined {
  if (entries.length === 0) return undefined;
  const sorted = entries.map((e, i) => ({ e, i })).sort((a, b) => a.e.group - b.e.group || a.i - b.i);
  const out: Record<string, PropValue> = {};
  let n = 0;
  for (const { e } of sorted) {
    if (n >= cap) break;
    if (Object.prototype.hasOwnProperty.call(out, e.key)) continue;
    out[e.key] = typeof e.value === 'string' ? clipString(e.value) : e.value;
    n++;
  }
  return n > 0 ? out : undefined;
}

/** The four attributes as entries (empty strings and NOTDEFINED are dropped). */
export function attributeEntries(a: { objectType?: string; tag?: string; description?: string; predefinedType?: string }): PropEntry[] {
  const out: PropEntry[] = [];
  const add = (k: string, v: string | undefined): void => {
    if (v === undefined || v === '' || v === 'NOTDEFINED') return;
    out.push({ key: `Attr.${k}`, value: v, group: GROUP_ATTR });
  };
  add('ObjectType', a.objectType);
  add('Tag', a.tag);
  add('Description', a.description);
  add('PredefinedType', a.predefinedType);
  return out;
}

/** Validate a sidecar `props` value: an object of string, finite number and boolean values, else undefined. */
export function sanitizeProps(p: unknown): Record<string, PropValue> | undefined {
  if (!p || typeof p !== 'object' || Array.isArray(p)) return undefined;
  const out: Record<string, PropValue> = {};
  let n = 0;
  for (const [k, v] of Object.entries(p as Record<string, unknown>)) {
    if (typeof v === 'string' || typeof v === 'boolean' || (typeof v === 'number' && Number.isFinite(v))) {
      out[k] = v;
      n++;
    }
  }
  return n > 0 ? out : undefined;
}
