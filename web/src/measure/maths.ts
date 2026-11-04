// Measurement maths: pure functions (no DOM, no GPU) so they are unit tested.

export type V3 = readonly [number, number, number];
export const UNITS = ['m', 'mm'] as const;
export type Units = (typeof UNITS)[number];

export const distance = (a: V3, b: V3): number => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);

/** 3 decimals in metres ("1.234 m"), whole millimetres otherwise ("1234 mm"). */
export function formatLength(metres: number, units: Units): string {
  if (!Number.isFinite(metres)) return '-';
  return units === 'mm' ? `${Math.round(metres * 1000)} mm` : `${metres.toFixed(3)} m`;
}

export interface PxPoint {
  x: number;
  y: number;
  visible: boolean;
}

export interface SnapResult {
  point: V3;
  /** True when a vertex was within the radius. */
  snapped: boolean;
  /** Index into the candidate list, -1 when not snapped. */
  index: number;
  /** Screen distance to the chosen vertex, px (Infinity when no candidate was visible). */
  px: number;
}

/**
 * Snap to the vertex nearest to the cursor in screen space, when within `radiusPx`; otherwise return `hit` unchanged.
 * `project` maps a world point to CSS pixels (same frame as `cursor`).
 */
export function snapToVertex(hit: V3, vertices: readonly V3[], cursor: { x: number; y: number }, project: (p: V3) => PxPoint, radiusPx = 12): SnapResult {
  let best = -1;
  let bestPx = Infinity;
  for (let i = 0; i < vertices.length; i++) {
    const p = project(vertices[i]!);
    if (!p.visible) continue;
    const d = Math.hypot(p.x - cursor.x, p.y - cursor.y);
    if (d < bestPx) {
      bestPx = d;
      best = i;
    }
  }
  if (best >= 0 && bestPx <= radiusPx) return { point: vertices[best]!, snapped: true, index: best, px: bestPx };
  return { point: hit, snapped: false, index: -1, px: bestPx };
}

/** Viewer frame (Y up, origin shifted) -> IFC world frame (Z up), metres. */
export function toIfcWorld(p: V3, shift: V3): [number, number, number] {
  return [p[0] + shift[0], -p[2] + shift[1], p[1] + shift[2]];
}

export interface Measurement {
  id: number;
  kind: 'point' | 'element';
  a: [number, number, number];
  b: [number, number, number];
  /** metres */
  distance: number;
  /** element ids for kind 'element' */
  elementA?: number;
  elementB?: number;
}

export const MEASURE_CSV_HEADER = [
  'id', 'kind', 'distance_m', 'distance_mm', 'dx_m', 'dy_m', 'dz_m', 'ax', 'ay', 'az', 'bx', 'by', 'bz', 'element_a', 'element_b',
] as const;

/** CSV rows. Coordinates are IFC world (Z up, metres); dx, dy, dz are b - a in the same frame. */
export function measurementRows(list: readonly Measurement[], shift: V3, nameOf: (id: number) => string): Array<Array<string | number>> {
  const r3 = (x: number): number => Math.round(x * 1000) / 1000;
  return list.map((m) => {
    const a = toIfcWorld(m.a, shift);
    const b = toIfcWorld(m.b, shift);
    return [
      m.id, m.kind === 'point' ? 'point to point' : 'element to element', r3(m.distance), Math.round(m.distance * 1000),
      r3(b[0] - a[0]), r3(b[1] - a[1]), r3(b[2] - a[2]), r3(a[0]), r3(a[1]), r3(a[2]), r3(b[0]), r3(b[1]), r3(b[2]),
      m.elementA !== undefined ? nameOf(m.elementA) : '', m.elementB !== undefined ? nameOf(m.elementB) : '',
    ];
  });
}
