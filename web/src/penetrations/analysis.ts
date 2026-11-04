// Penetration schedule analysis: where do MEP elements pass through structural hosts, and is there an opening?
// Pure over bounds plus callbacks (geometry.intersects, an optional axis estimator), so it is testable with boxes.
//
// Frame: viewer coordinates, Y up (the sidecar frame). Lengths in the inputs are metres; the outputs that people read
// (sizes, thickness, gap) are millimetres rounded to integers.

export type Box6 = readonly [number, number, number, number, number, number];
export type Vec3 = readonly [number, number, number];

export type PenStatus = 'opening' | 'none' | 'unknown';
export type PenOrientation = 'vertical' | 'horizontal' | 'inclined';

export interface PenElement {
  id: number;
  ifcClass: string;
  storey: number | null;
  bounds: Box6;
}

export interface OpeningRec {
  expressId: number;
  /** element id of the voided host */
  host: number;
  bounds: Box6;
}

export interface PenInput {
  mep: readonly PenElement[];
  hosts: readonly PenElement[];
  /** relations.openings; undefined or empty means the model has no opening data (status `unknown`). */
  openings?: readonly OpeningRec[];
  /** relations.hosts: [filler element, host element]; a filler listed for the host counts as having an opening. */
  hostedBy?: ReadonlyArray<readonly [number, number]>;
  /** Geometry confirmation of a bounds-overlapping pair (geometry.intersects). */
  intersects(mep: number, host: number): boolean;
  /** Unit direction of the element's long axis (viewer frame). Without it the longest bounds extent is used. */
  axisOf?(id: number): Vec3 | null;
}

export interface PenOptions {
  /** Containment tolerance for the opening test, metres. Default 0.005. */
  tolerance?: number;
  /** Axis elevation above the horizontal plane at or above which a run is vertical. Default 75. */
  verticalDeg?: number;
  /** ... at or below which it is horizontal. Default 15. */
  horizontalDeg?: number;
}

export interface Penetration {
  /** 1-based, in schedule order (MEP element id, then host id). */
  id: number;
  mep: number;
  host: number;
  storey: number | null;
  /** Centre of the bounds intersection, viewer frame, metres. */
  location: [number, number, number];
  orientation: PenOrientation;
  /** The two smaller extents of the MEP bounds, mm (approximate for inclined runs). */
  sizeMm: [number, number];
  /** Smallest extent of the host bounds, mm. */
  hostThicknessMm: number;
  status: PenStatus;
  /** Smallest clearance between the MEP cross-section and the opening, mm (negative: opening smaller). null when unknown. */
  gapMm: number | null;
  /** Express id of the opening that contains the location (null when hosted by relation only, or none). */
  openingExpressId: number | null;
}

export const OPENING_TOLERANCE = 0.005;
const EPS = 1e-9;

export const extents = (b: Box6): [number, number, number] => [b[3] - b[0], b[4] - b[1], b[5] - b[2]];

export function intersectBox(a: Box6, b: Box6): Box6 | null {
  const lo = [Math.max(a[0], b[0]), Math.max(a[1], b[1]), Math.max(a[2], b[2])];
  const hi = [Math.min(a[3], b[3]), Math.min(a[4], b[4]), Math.min(a[5], b[5])];
  if (lo[0]! > hi[0]! + EPS || lo[1]! > hi[1]! + EPS || lo[2]! > hi[2]! + EPS) return null;
  return [lo[0]!, lo[1]!, lo[2]!, hi[0]!, hi[1]!, hi[2]!];
}

export function boxCentre(b: Box6): [number, number, number] {
  return [(b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2];
}

export function containsPoint(b: Box6, p: Vec3, tol: number): boolean {
  return p[0] >= b[0] - tol && p[0] <= b[3] + tol && p[1] >= b[1] - tol && p[1] <= b[4] + tol && p[2] >= b[2] - tol && p[2] <= b[5] + tol;
}

/** Index (0 x, 1 y, 2 z) of the largest |component| of a vector, or of the largest extent. */
function dominant(v: readonly number[]): number {
  let k = 0;
  for (let i = 1; i < 3; i++) if (Math.abs(v[i]!) > Math.abs(v[k]!)) k = i;
  return k;
}

/** Orientation of a run from its (unit) axis: elevation above the horizontal plane. Y is up. */
export function orientationOf(axis: Vec3, opts: PenOptions = {}): PenOrientation {
  const len = Math.hypot(axis[0], axis[1], axis[2]) || 1;
  const elev = (Math.asin(Math.min(1, Math.abs(axis[1]) / len)) * 180) / Math.PI;
  if (elev >= (opts.verticalDeg ?? 75)) return 'vertical';
  if (elev <= (opts.horizontalDeg ?? 15)) return 'horizontal';
  return 'inclined';
}

/**
 * Candidate (mep, host) pairs whose bounds overlap, by sort-and-sweep along x. Each pair is reported once.
 * Touching bounds count as overlapping; the geometry test decides.
 */
export function overlapPairs(mep: readonly PenElement[], hosts: readonly PenElement[]): Array<[PenElement, PenElement]> {
  interface Item { e: PenElement; host: boolean }
  const items: Item[] = [];
  for (const e of mep) items.push({ e, host: false });
  for (const e of hosts) items.push({ e, host: true });
  items.sort((a, b) => a.e.bounds[0] - b.e.bounds[0] || a.e.id - b.e.id);
  let activeM: PenElement[] = [];
  let activeH: PenElement[] = [];
  const out: Array<[PenElement, PenElement]> = [];
  const yzOverlap = (a: Box6, b: Box6): boolean =>
    a[1] <= b[4] + EPS && b[1] <= a[4] + EPS && a[2] <= b[5] + EPS && b[2] <= a[5] + EPS;
  for (const it of items) {
    const b = it.e.bounds;
    // an active element whose max x lies left of this min x can never overlap a later item either (sorted by min x)
    activeM = activeM.filter((m) => m.bounds[3] >= b[0] - EPS);
    activeH = activeH.filter((h) => h.bounds[3] >= b[0] - EPS);
    if (it.host) {
      for (const m of activeM) if (yzOverlap(m.bounds, b)) out.push([m, it.e]);
      activeH.push(it.e);
    } else {
      for (const h of activeH) if (yzOverlap(b, h.bounds)) out.push([it.e, h]);
      activeM.push(it.e);
    }
  }
  return out;
}

export interface PenSummary {
  total: number;
  opening: number;
  none: number;
  unknown: number;
}

export function summarise(rows: readonly Penetration[]): PenSummary {
  const s: PenSummary = { total: rows.length, opening: 0, none: 0, unknown: 0 };
  for (const r of rows) s[r.status]++;
  return s;
}

export function analysePenetrations(input: PenInput, opts: PenOptions = {}): Penetration[] {
  const tol = opts.tolerance ?? OPENING_TOLERANCE;
  const openingsByHost = new Map<number, OpeningRec[]>();
  for (const o of input.openings ?? []) {
    let l = openingsByHost.get(o.host);
    if (!l) openingsByHost.set(o.host, (l = []));
    l.push(o);
  }
  const haveOpeningData = (input.openings?.length ?? 0) > 0;
  const hostedSet = new Set<string>();
  for (const [f, h] of input.hostedBy ?? []) hostedSet.add(`${f}:${h}`);

  const pairs = overlapPairs(input.mep, input.hosts);
  pairs.sort((a, b) => a[0].id - b[0].id || a[1].id - b[1].id);

  const rows: Penetration[] = [];
  for (const [m, h] of pairs) {
    if (m.id === h.id || !input.intersects(m.id, h.id)) continue;
    const ov = intersectBox(m.bounds, h.bounds);
    if (!ov) continue;
    const location = boxCentre(ov);
    const me = extents(m.bounds);
    const he = extents(h.bounds);

    const axis = input.axisOf?.(m.id) ?? null;
    const longIdx = axis ? dominant(axis) : dominant(me);
    const orientation = axis ? orientationOf(axis, opts) : longIdx === 1 ? 'vertical' : 'horizontal';

    const sortedExt = [...me].sort((a, b) => a - b);
    const sizeMm: [number, number] = [Math.round(sortedExt[0]! * 1000), Math.round(sortedExt[1]! * 1000)];
    const hostThicknessMm = Math.round(Math.min(he[0], he[1], he[2]) * 1000);

    let status: PenStatus;
    let gapMm: number | null = null;
    let openingExpressId: number | null = null;

    // the smallest opening of this host that contains the location
    let best: OpeningRec | null = null;
    let bestVol = Infinity;
    for (const o of openingsByHost.get(h.id) ?? []) {
      if (!containsPoint(o.bounds, location, tol)) continue;
      const oe = extents(o.bounds);
      const vol = oe[0] * oe[1] * oe[2];
      if (vol < bestVol) {
        best = o;
        bestVol = vol;
      }
    }
    if (best) {
      status = 'opening';
      openingExpressId = best.expressId;
      const oe = extents(best.bounds);
      let g = Infinity;
      for (let k = 0; k < 3; k++) {
        if (k === longIdx) continue;
        g = Math.min(g, (oe[k]! - me[k]!) / 2);
      }
      gapMm = Number.isFinite(g) ? Math.round(g * 1000) : null;
    } else if (hostedSet.has(`${m.id}:${h.id}`)) {
      status = 'opening';
    } else {
      status = haveOpeningData ? 'none' : 'unknown';
    }

    rows.push({
      id: rows.length + 1,
      mep: m.id,
      host: h.id,
      storey: h.storey ?? m.storey,
      location,
      orientation,
      sizeMm,
      hostThicknessMm,
      status,
      gapMm,
      openingExpressId,
    });
  }
  return rows;
}

// ---------------------------------------------------------------- long-axis estimate (PCA of sample points)

/** Principal axis (unit vector, sign unspecified) of a point cloud, by power iteration on the covariance matrix. */
export function principalAxis(points: ReadonlyArray<Vec3>): Vec3 | null {
  const n = points.length;
  if (n < 3) return null;
  let cx = 0, cy = 0, cz = 0;
  for (const p of points) { cx += p[0]; cy += p[1]; cz += p[2]; }
  cx /= n; cy /= n; cz /= n;
  let xx = 0, xy = 0, xz = 0, yy = 0, yz = 0, zz = 0;
  for (const p of points) {
    const x = p[0] - cx, y = p[1] - cy, z = p[2] - cz;
    xx += x * x; xy += x * y; xz += x * z; yy += y * y; yz += y * z; zz += z * z;
  }
  let v: [number, number, number] = [1, 0.7, 0.3];
  for (let i = 0; i < 40; i++) {
    const nx = xx * v[0] + xy * v[1] + xz * v[2];
    const ny = xy * v[0] + yy * v[1] + yz * v[2];
    const nz = xz * v[0] + yz * v[1] + zz * v[2];
    const l = Math.hypot(nx, ny, nz);
    if (l < 1e-18) return null;
    v = [nx / l, ny / l, nz / l];
  }
  return v;
}

// ---------------------------------------------------------------- CSV

export interface PenCsvContext {
  mepName(id: number): string;
  mepGlobalId(id: number): string;
  mepClass(id: number): string;
  hostName(id: number): string;
  hostGlobalId(id: number): string;
  hostClass(id: number): string;
  storeyName(storey: number | null): string;
}

export const PEN_CSV_HEADER = [
  'id', 'mep_global_id', 'mep_class', 'mep_name', 'host_global_id', 'host_class', 'host_name', 'storey',
  'orientation', 'size_a_mm', 'size_b_mm', 'host_thickness_mm', 'status', 'gap_mm', 'x_m', 'y_m', 'z_m',
] as const;

/** Rows for toCsv. Location is in the viewer frame (Y up) as shown in the viewer, metres, 3 decimals. */
export function penetrationCsvRows(rows: readonly Penetration[], c: PenCsvContext): Array<Array<string | number | null>> {
  const r3 = (x: number): number => Math.round(x * 1000) / 1000;
  return rows.map((r) => [
    r.id, c.mepGlobalId(r.mep), c.mepClass(r.mep), c.mepName(r.mep), c.hostGlobalId(r.host), c.hostClass(r.host), c.hostName(r.host),
    c.storeyName(r.storey), r.orientation, r.sizeMm[0], r.sizeMm[1], r.hostThicknessMm, r.status, r.gapMm,
    r3(r.location[0]), r3(r.location[1]), r3(r.location[2]),
  ]);
}

// ---------------------------------------------------------------- filter and sort (drawer)

export interface PenFilter {
  status?: ReadonlySet<PenStatus>;
  storeys?: ReadonlySet<number | null>;
  hostClasses?: ReadonlySet<string>;
}

export function filterRows(rows: readonly Penetration[], f: PenFilter, hostClassOf: (id: number) => string): Penetration[] {
  return rows.filter(
    (r) =>
      (!f.status || f.status.size === 0 || f.status.has(r.status)) &&
      (!f.storeys || f.storeys.size === 0 || f.storeys.has(r.storey)) &&
      (!f.hostClasses || f.hostClasses.size === 0 || f.hostClasses.has(hostClassOf(r.host))),
  );
}
