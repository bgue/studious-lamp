// XR_ConcreteElement.Mark: the IFC piece mark or Tag when it is present and unique, else a generated, stable mark
// `<role prefix><storey index>-<n>` (S1-03 = the third suspended slab on storey 1). Pure. Design section 4.

export const ROLE_PREFIX: Record<string, string> = {
  PAD_FOOTING: 'FP', STRIP_FOOTING: 'FS', RAFT: 'RF', PILE_CAP: 'PC', PILE: 'PL', GRADE_BEAM: 'GB', PLINTH: 'PT',
  SLAB_ON_GRADE: 'SG', SUSPENDED_SLAB: 'S', FLAT_SLAB: 'FL', RIBBED_SLAB: 'RS', WAFFLE_SLAB: 'WS', TRANSFER_SLAB: 'TS', TOPPING: 'TP', LANDING: 'LD',
  BEAM: 'B', DOWNSTAND_BEAM: 'B', UPSTAND_BEAM: 'UB', TRANSFER_BEAM: 'TB', COLUMN: 'C', PIER: 'PR',
  WALL: 'W', SHEAR_WALL: 'SW', CORE_WALL: 'CW', RETAINING_WALL: 'RW', BASEMENT_WALL: 'BW', PARAPET: 'PA',
  STAIR: 'ST', RAMP: 'RP', CORBEL: 'CB', CURB: 'CU', EQUIPMENT_PAD: 'EP', PRECAST_PANEL: 'PP', OTHER: 'X',
};

export interface MarkItem {
  id: string;
  role: string;
  /** Storey index (0 = lowest storey), or null when the element has none. */
  storey: number | null;
  /** The IFC piece mark or Tag, when there is one. */
  ifcMark?: string;
  /** Position of the frame origin, plan (m). */
  x: number;
  y: number;
}

export interface MarkResult { mark: string; source: 'ifc' | 'generated' }

export const storeyLabel = (s: number | null): string => (s === null ? 'X' : String(s));

/** The mark of every element. Same input, same marks: a series (prefix and storey) is numbered by x, then y (5 cm steps), then GlobalId. */
export function assignMarks(items: readonly MarkItem[]): Map<string, MarkResult> {
  const out = new Map<string, MarkResult>();
  const count = new Map<string, number>();
  for (const it of items) { const m = it.ifcMark?.trim(); if (m) count.set(m, (count.get(m) ?? 0) + 1); }
  const used = new Set<string>();
  const rest: MarkItem[] = [];
  for (const it of items) {
    const m = it.ifcMark?.trim();
    if (m && count.get(m) === 1) { out.set(it.id, { mark: m, source: 'ifc' }); used.add(m); } else rest.push(it);
  }
  const series = new Map<string, MarkItem[]>();
  for (const it of rest) {
    const key = `${ROLE_PREFIX[it.role] ?? 'X'}|${storeyLabel(it.storey)}`;
    (series.get(key) ?? series.set(key, []).get(key)!).push(it);
  }
  const q = (v: number): number => Math.round(v / 0.05);
  for (const [key, list] of series) {
    const [prefix, st] = key.split('|') as [string, string];
    list.sort((a, b) => q(a.x) - q(b.x) || q(a.y) - q(b.y) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
    let n = 0;
    for (const it of list) {
      let mark: string;
      do { n++; mark = `${prefix}${st}-${String(n).padStart(2, '0')}`; } while (used.has(mark));
      used.add(mark);
      out.set(it.id, { mark, source: 'generated' });
    }
  }
  return out;
}
