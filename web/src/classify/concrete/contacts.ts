// Contacts between concrete elements, from their bounds: who bears on whom (Supports), who touches whom (joints) and the pour groups.
// Pure. Design sections 3.5 and 4. The geometry module refines the bounds contacts by face contact (a face's `touches`).

import type { Box6 } from './geometry';
import { storeyLabel } from './marks';

export interface ContactItem { id: string; bounds: Box6; storey: number | null }

export interface ContactGraph {
  /** Elements this one bears on (its bottom rests on their top). */
  restsOn: Map<string, string[]>;
  /** Elements that bear on this one. */
  carries: Map<string, string[]>;
  /** Elements whose bounds touch or overlap this one's (gap <= tolerance). */
  touching: Map<string, string[]>;
}

const push = (m: Map<string, string[]>, k: string, v: string): void => { (m.get(k) ?? m.set(k, []).get(k)!).push(v); };

/** Contact graph from bounds. `tol` (m): a gap up to this still counts as touching (default 1 cm). Sweep over X, so large models stay fast. */
export function contactGraph(items: readonly ContactItem[], tol = 0.01): ContactGraph {
  const g: ContactGraph = { restsOn: new Map(), carries: new Map(), touching: new Map() };
  const order = [...items].sort((a, b) => a.bounds[0] - b.bounds[0]);
  for (let i = 0; i < order.length; i++) {
    const A = order[i]!;
    for (let j = i + 1; j < order.length; j++) {
      const B = order[j]!;
      if (B.bounds[0] > A.bounds[3] + tol) break;
      const oy = Math.min(A.bounds[4], B.bounds[4]) - Math.max(A.bounds[1], B.bounds[1]);
      const oz = Math.min(A.bounds[5], B.bounds[5]) - Math.max(A.bounds[2], B.bounds[2]);
      const ox = Math.min(A.bounds[3], B.bounds[3]) - Math.max(A.bounds[0], B.bounds[0]);
      if (oy < -tol || oz < -tol || ox < -tol) continue;
      push(g.touching, A.id, B.id); push(g.touching, B.id, A.id);
      // bearing: one element's bottom on the other's top, with plan overlap
      if (ox > 0.01 && oy > 0.01 && ox * oy >= 0.005) {
        if (Math.abs(A.bounds[2] - B.bounds[5]) <= 0.05) { push(g.restsOn, A.id, B.id); push(g.carries, B.id, A.id); }
        else if (Math.abs(B.bounds[2] - A.bounds[5]) <= 0.05) { push(g.restsOn, B.id, A.id); push(g.carries, A.id, B.id); }
      }
    }
  }
  return g;
}

/** Roles that are cast together: slabs with their beams (deck), walls with columns (vertical), foundations with the slab on grade. A role in no class is cast alone. */
export function pourClassOf(role: string): string | null {
  switch (role) {
    case 'SUSPENDED_SLAB': case 'FLAT_SLAB': case 'RIBBED_SLAB': case 'WAFFLE_SLAB': case 'TRANSFER_SLAB': case 'TOPPING': case 'LANDING':
    case 'BEAM': case 'DOWNSTAND_BEAM': case 'UPSTAND_BEAM': case 'TRANSFER_BEAM': return 'DECK';
    case 'WALL': case 'SHEAR_WALL': case 'CORE_WALL': case 'RETAINING_WALL': case 'BASEMENT_WALL': case 'PARAPET': case 'COLUMN': case 'PIER': return 'VERTICAL';
    case 'PAD_FOOTING': case 'STRIP_FOOTING': case 'RAFT': case 'PILE_CAP': case 'GRADE_BEAM': case 'PLINTH': case 'SLAB_ON_GRADE': return 'FOUNDATION';
    default: return null;
  }
}

/** Methods that are poured on site. */
export const CAST_ON_SITE = new Set(['CAST_IN_PLACE', 'POST_TENSIONED', 'COMPOSITE_DECK']);

export interface PourItem { id: string; role: string; method: string; storey: number | null; x: number; y: number }

/**
 * Pour groups: elements that touch, are on the same storey, are cast on site and are in the same pour class (a slab and its
 * downstand beams are one group). Returns the stable id `PG-<storey>-<n>` of each element; precast and unclassed elements have none.
 * Groups are numbered per storey by their lowest x, then y, then first GlobalId.
 */
export function pourGroups(items: readonly PourItem[], touching: ReadonlyMap<string, readonly string[]>): Map<string, string> {
  const by = new Map(items.map((i) => [i.id, i]));
  const parent = new Map<string, string>();
  const find = (a: string): string => { let r = a; while (parent.get(r) !== r) r = parent.get(r)!; let c = a; while (parent.get(c) !== r) { const n = parent.get(c)!; parent.set(c, r); c = n; } return r; };
  const eligible = items.filter((i) => CAST_ON_SITE.has(i.method) && pourClassOf(i.role) !== null);
  for (const i of eligible) parent.set(i.id, i.id);
  for (const i of eligible) {
    for (const nb of touching.get(i.id) ?? []) {
      const j = by.get(nb);
      if (!j || !parent.has(j.id) || j.storey !== i.storey || pourClassOf(j.role) !== pourClassOf(i.role)) continue;
      const a = find(i.id), b = find(j.id);
      if (a !== b) parent.set(a < b ? b : a, a < b ? a : b);
    }
  }
  const groups = new Map<string, PourItem[]>();
  for (const i of eligible) (groups.get(find(i.id)) ?? groups.set(find(i.id), []).get(find(i.id))!).push(i);
  const q = (v: number): number => Math.round(v / 0.05);
  const list = [...groups.values()].map((m) => ({ m, x: Math.min(...m.map((i) => q(i.x))), y: Math.min(...m.map((i) => q(i.y))), id: m.map((i) => i.id).sort()[0]!, storey: m[0]!.storey }));
  list.sort((a, b) => storeyKey(a.storey) - storeyKey(b.storey) || a.x - b.x || a.y - b.y || (a.id < b.id ? -1 : 1));
  const n = new Map<string, number>();
  const out = new Map<string, string>();
  for (const gr of list) {
    const key = storeyLabel(gr.storey);
    const k = (n.get(key) ?? 0) + 1;
    n.set(key, k);
    for (const i of gr.m) out.set(i.id, `PG-${key}-${k}`);
  }
  return out;
}

const storeyKey = (s: number | null): number => (s === null ? Number.MAX_SAFE_INTEGER : s);
