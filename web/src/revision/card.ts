// What the revision card says about one diff entry (design 3.6): the "what changed" rows, the move in words, the geometry change in
// percent. Pure: it reads the two snapshots and the entry, and returns text. The panel only lays it out.

import { SIG_STRIDE } from './types';
import type { ChangeFlag, DiffEntry, ModelSnapshot, PropValue, Vec3 } from './types';

export const MAX_PROP_ROWS = 8;

export interface ChangeRow {
  flag: ChangeFlag;
  /** A key row (a property) names its key here. */
  label?: string;
  before?: string;
  after?: string;
  /** A row that is one sentence ("moved 8 mm north-east"). */
  text?: string;
}

const mmText = (m: number): string => {
  const mm = m * 1000;
  if (mm >= 1000) return `${(mm / 1000).toFixed(2)} m`;
  return `${mm >= 100 ? Math.round(mm) : Math.round(mm * 10) / 10} mm`;
};

/**
 * "moved 8 mm north-east". IFC axes: x east, y north, z up. A direction counts when its part is at least 38 % of the move (so a 22
 * degree slant still reads as one direction); the vertical part is named after the horizontal one.
 */
export function moveText(delta: Vec3 | undefined, move: number | undefined, rotated?: boolean): string {
  if (delta === undefined || move === undefined) return rotated ? 'turned' : 'moved';
  const len = Math.hypot(delta[0], delta[1], delta[2]) || 1;
  const names: string[] = [];
  const ns = Math.abs(delta[1]) / len >= 0.38 ? (delta[1] > 0 ? 'north' : 'south') : '';
  const ew = Math.abs(delta[0]) / len >= 0.38 ? (delta[0] > 0 ? 'east' : 'west') : '';
  const ud = Math.abs(delta[2]) / len >= 0.38 ? (delta[2] > 0 ? 'up' : 'down') : '';
  if (ns && ew) names.push(`${ns}-${ew}`); else if (ns || ew) names.push(ns || ew);
  if (ud) names.push(ud);
  if (names.length === 0) names.push(Math.abs(delta[2]) > Math.abs(delta[0]) && Math.abs(delta[2]) > Math.abs(delta[1]) ? (delta[2] > 0 ? 'up' : 'down') : Math.abs(delta[0]) >= Math.abs(delta[1]) ? (delta[0] > 0 ? 'east' : 'west') : (delta[1] > 0 ? 'north' : 'south'));
  return `${rotated ? 'turned and ' : ''}moved ${mmText(move)} ${names.join(' and ')}`;
}

const pct = (a: number, b: number): string => {
  if (a <= 0) return b > 0 ? 'new' : '0 %';
  const p = Math.round(((b - a) / a) * 100);
  return `${p > 0 ? '+' : p < 0 ? '−' : ''}${Math.abs(p)} %`;
};

/** "area −12 %, volume −9 %" from the signatures (the base's and the head's index). */
export function geometryText(base: ModelSnapshot, i: number, head: ModelSnapshot, j: number): string {
  const a = base.sig[i * SIG_STRIDE]!, b = head.sig[j * SIG_STRIDE]!;
  const va = base.sig[i * SIG_STRIDE + 1]!, vb = head.sig[j * SIG_STRIDE + 1]!;
  const parts = [`area ${pct(a, b)}`];
  if (va > 0 || vb > 0) parts.push(`volume ${pct(va, vb)}`);
  const ea = base.sig.subarray(i * SIG_STRIDE + 8, i * SIG_STRIDE + 11), eb = head.sig.subarray(j * SIG_STRIDE + 8, j * SIG_STRIDE + 11);
  const grown = ['x', 'y', 'z'].map((ax, k) => ({ ax, d: eb[k]! - ea[k]! })).filter((x) => Math.abs(x.d) >= 0.01).sort((p, q) => Math.abs(q.d) - Math.abs(p.d))[0];
  if (grown) parts.push(`${grown.d > 0 ? 'longer' : 'shorter'} by ${mmText(Math.abs(grown.d))} along ${grown.ax}`);
  return parts.join(', ');
}

const val = (v: PropValue | undefined): string => (v === undefined ? '(none)' : String(v));
const dash = (s: string): string => (s === '' ? '(none)' : s);

/** The rows of the "what changed" table. Properties come last, at most `MAX_PROP_ROWS`, then one row "n more". */
export function changeRows(e: DiffEntry, base: ModelSnapshot | null, head: ModelSnapshot | null, bi: number | undefined, hi: number | undefined): ChangeRow[] {
  const rows: ChangeRow[] = [];
  const both = base !== null && head !== null && bi !== undefined && hi !== undefined;
  for (const f of e.flags) {
    switch (f) {
      case 'placement': rows.push({ flag: f, text: moveText(e.delta, e.move, e.rotated) }); break;
      case 'geometry': if (both) rows.push({ flag: f, text: geometryText(base, bi, head, hi) }); else rows.push({ flag: f, text: 'shape changed' }); break;
      case 'class': if (both) rows.push({ flag: f, before: base.ifcClass[bi]!, after: head.ifcClass[hi]! }); break;
      case 'type': if (both) rows.push({ flag: f, before: dash(base.typeName[bi]!), after: dash(head.typeName[hi]!) }); break;
      case 'attributes': if (both) {
        if (base.name[bi] !== head.name[hi]) rows.push({ flag: f, label: 'Name', before: dash(base.name[bi]!), after: dash(head.name[hi]!) });
        if (base.tag[bi] !== head.tag[hi]) rows.push({ flag: f, label: 'Tag', before: dash(base.tag[bi]!), after: dash(head.tag[hi]!) });
        if (!rows.some((r) => r.flag === 'attributes')) rows.push({ flag: f, text: 'attributes changed' });
      } break;
      case 'storey': if (both) rows.push({ flag: f, before: dash(base.storey[bi]?.name ?? ''), after: dash(head.storey[hi]?.name ?? '') }); break;
      case 'material': if (both) rows.push({ flag: f, before: dash(base.material[bi]!), after: dash(head.material[hi]!) }); break;
      case 'systems': if (both) rows.push({ flag: f, before: dash(base.systems[bi]!.join(', ')), after: dash(head.systems[hi]!.join(', ')) }); break;
      case 'properties': break;
    }
  }
  if (e.flags.includes('properties')) {
    const props = e.props ?? [];
    for (const p of props.slice(0, MAX_PROP_ROWS)) rows.push({ flag: 'properties', label: p.key, before: val(p.before), after: val(p.after) });
    if (props.length > MAX_PROP_ROWS) rows.push({ flag: 'properties', text: `${props.length - MAX_PROP_ROWS} more` });
  }
  return rows;
}

/** One line for a category badge or a table row: "Moved", "New", "Deleted"... */
export const CATEGORY_LABEL: Record<DiffEntry['category'], string> = { new: 'New', deleted: 'Deleted', changed: 'Changed', rematched: 'Rematched', unchanged: 'Unchanged' };
export const FLAG_LABEL: Record<ChangeFlag, string> = {
  geometry: 'Shape', placement: 'Moved', class: 'Class', type: 'Type', attributes: 'Attributes', storey: 'Storey', material: 'Material', properties: 'Properties', systems: 'Systems',
};
