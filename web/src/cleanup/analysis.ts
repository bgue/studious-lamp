// Model cleanup analysis: pure TypeScript over element bounds plus an optional geometry callback.
//
// Rules (all combinable, the result is a set of ids with per-id reasons):
//   floating    contact graph (bounds gap <= tolerance) -> connected components; a component is floating when it is not
//               the main component and its size is below the threshold
//   tiny        largest bounds dimension below a threshold, regardless of contact
//   strays      bounds centre further than k times the robust radius of the model from the median centre, and (optional)
//               at least `minGap` metres outside the box of the main model and no larger than `maxSize` metres
//   duplicates  same class, same triangle count, bounds equal within 2 mm: keep the lowest id
//   degenerate  no triangles, non-finite bounds, a bounds dimension below 0.1 mm, or a non-physical class
//   classes     quick toggles: proxies, furniture, accessories and fasteners
//
// Nothing here touches the DOM or three.js. The geometry callback is optional; without it the triangle based
// checks (zero triangles, duplicate triangle count, triangle count metric) and the precise/mesh volume modes degrade
// gracefully (see CleanupGeometry).

export type Bounds6 = readonly [number, number, number, number, number, number];

export interface CleanupElement {
  id: number;
  ifcClass: string;
  bounds: Bounds6;
}

/** Optional mesh access. Every member is optional. */
export interface CleanupGeometry {
  /** Triangles of the element (0: no geometry). Without it: no zero-triangle check, duplicates ignore triangle count. */
  triangleCount?(id: number): number;
  /** Absolute enclosed volume in m3, or null when the mesh is open or unavailable (the bounds volume is used then). */
  meshVolume?(id: number): number | null;
  /** Shortest surface distance, any value > maxDistance when farther. Enables `precise` contacts. */
  surfaceDistance?(a: number, b: number, maxDistance: number): number;
}

export const SIZE_METRICS = ['largest dimension (m)', 'bounds volume (m³)', 'mesh volume (m³)', 'triangle count'] as const;
export type SizeMetric = (typeof SIZE_METRICS)[number];
export const FLOATING_MODES = ['single elements', 'small clusters'] as const;
export type FloatingMode = (typeof FLOATING_MODES)[number];

/** Default threshold for each size metric. */
export const METRIC_DEFAULT_THRESHOLD: Record<SizeMetric, number> = {
  'largest dimension (m)': 0.5,
  'bounds volume (m³)': 0.05,
  'mesh volume (m³)': 0.05,
  'triangle count': 100,
};

export interface CleanupRules {
  floating: {
    enabled: boolean;
    metric: SizeMetric;
    threshold: number;
    mode: FloatingMode;
    /** Metres. */
    contactTolerance: number;
    precise: boolean;
  };
  tiny: { enabled: boolean; maxSize: number };
  strays: {
    enabled: boolean;
    /** k: a stray's centre lies further than k times the robust radius from the median centre. No unit. */
    factor: number;
    /** Metres. The stray must also lie at least this far outside the box of the other (main) elements. 0: no limit. */
    minGap: number;
    /** Metres. Only elements whose largest dimension is at most this count as strays. 0: any size. */
    maxSize: number;
  };
  duplicates: { enabled: boolean };
  degenerate: { enabled: boolean };
  classes: { proxies: boolean; furniture: boolean; accessories: boolean };
}

export function defaultRules(): CleanupRules {
  return {
    floating: { enabled: true, metric: 'largest dimension (m)', threshold: 0.5, mode: 'single elements', contactTolerance: 0.01, precise: false },
    tiny: { enabled: true, maxSize: 0.05 },
    strays: { enabled: true, factor: 6, minGap: 0, maxSize: 0 },
    duplicates: { enabled: true },
    degenerate: { enabled: true },
    classes: { proxies: false, furniture: false, accessories: false },
  };
}

export type RuleName = 'floating' | 'tiny' | 'strays' | 'duplicates' | 'degenerate' | 'classes';
export const RULE_NAMES: RuleName[] = ['floating', 'tiny', 'strays', 'duplicates', 'degenerate', 'classes'];

export const PROXY_CLASSES = ['IfcBuildingElementProxy'];
export const FURNITURE_CLASSES = ['IfcFurnishingElement', 'IfcFurniture', 'IfcSystemFurnitureElement'];
export const ACCESSORY_CLASSES = ['IfcDiscreteAccessory', 'IfcFastener', 'IfcMechanicalFastener'];
/** Classes that are not physical building parts; matched by the degenerate rule if they slipped through the import. */
export const NON_PHYSICAL_CLASSES = [
  'IfcAnnotation', 'IfcVirtualElement', 'IfcGrid', 'IfcSpace', 'IfcSpatialZone', 'IfcExternalSpatialElement',
  'IfcOpeningElement', 'IfcSite', 'IfcBuilding', 'IfcBuildingStorey', 'IfcProject',
];

export const DEGENERATE_DIM = 1e-4;
export const DUPLICATE_TOL = 0.002;

export interface CleanupMatch {
  id: number;
  rules: RuleName[];
  reasons: string[];
}

export interface CleanupResult {
  /** Matched ids in ascending order. */
  ids: number[];
  matches: Map<number, CleanupMatch>;
  counts: Record<RuleName, number>;
  /** Contact components, for reporting. */
  components: { count: number; mainSize: number; mainElements: number };
  contactEdges: number;
  ms: number;
}

// ---------------------------------------------------------------- geometry helpers

export function isFiniteBounds(b: Bounds6): boolean {
  for (let i = 0; i < 6; i++) if (!Number.isFinite(b[i]!)) return false;
  return b[3]! >= b[0]! && b[4]! >= b[1]! && b[5]! >= b[2]!;
}

export function largestDimension(b: Bounds6): number {
  return Math.max(b[3] - b[0], b[4] - b[1], b[5] - b[2]);
}

export function boundsVolume(b: Bounds6): number {
  return Math.max(0, b[3] - b[0]) * Math.max(0, b[4] - b[1]) * Math.max(0, b[5] - b[2]);
}

/** Euclidean gap between a box and the box lo..hi (0 when they overlap); Infinity when lo..hi is empty. */
export function boxGap(b: Bounds6, lo: readonly number[], hi: readonly number[]): number {
  if (!(lo[0]! <= hi[0]!)) return Infinity;
  let s = 0;
  for (let a = 0; a < 3; a++) {
    const d = Math.max(0, lo[a]! - b[3 + a]!, b[a]! - hi[a]!);
    s += d * d;
  }
  return Math.sqrt(s);
}

function fmt(v: number): string {
  if (!Number.isFinite(v)) return String(v);
  const a = Math.abs(v);
  if (a === 0) return '0';
  if (a >= 100) return v.toFixed(0);
  if (a >= 1) return v.toFixed(2);
  if (a >= 0.01) return v.toFixed(3);
  return v.toPrecision(2);
}

/**
 * Absolute volume of a triangle soup by the signed tetrahedron sum (origin-based, so the origin is first moved to the
 * first vertex to keep float error low). `closed` is true when every directed edge has an opposite twin on welded vertices
 * (quantised to 1e-6 m), i.e. the mesh is a closed, consistently wound surface. Open meshes return closed = false.
 */
export function meshVolumeOf(
  positions: ArrayLike<number>,
  index: ArrayLike<number> | null,
  triStart: number,
  triCount: number,
): { volume: number; closed: boolean } {
  if (triCount <= 0) return { volume: 0, closed: false };
  const vi = (t: number, k: number): number => (index ? index[(triStart + t) * 3 + k]! : (triStart + t) * 3 + k);
  const ox = positions[vi(0, 0) * 3]!;
  const oy = positions[vi(0, 0) * 3 + 1]!;
  const oz = positions[vi(0, 0) * 3 + 2]!;
  let vol = 0;
  const weld = new Map<string, number>();
  const wid = (v: number): number => {
    const key = `${Math.round(positions[v * 3]! * 1e6)},${Math.round(positions[v * 3 + 1]! * 1e6)},${Math.round(positions[v * 3 + 2]! * 1e6)}`;
    let id = weld.get(key);
    if (id === undefined) {
      id = weld.size;
      weld.set(key, id);
    }
    return id;
  };
  const edges = new Map<string, number>();
  let closed = true;
  for (let t = 0; t < triCount; t++) {
    const a = vi(t, 0);
    const b = vi(t, 1);
    const c = vi(t, 2);
    const ax = positions[a * 3]! - ox, ay = positions[a * 3 + 1]! - oy, az = positions[a * 3 + 2]! - oz;
    const bx = positions[b * 3]! - ox, by = positions[b * 3 + 1]! - oy, bz = positions[b * 3 + 2]! - oz;
    const cx = positions[c * 3]! - ox, cy = positions[c * 3 + 1]! - oy, cz = positions[c * 3 + 2]! - oz;
    vol += (ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx)) / 6;
    const w = [wid(a), wid(b), wid(c)] as const;
    for (let k = 0; k < 3; k++) {
      const p = w[k]!;
      const q = w[(k + 1) % 3]!;
      if (p === q) continue;
      const fwd = `${p}>${q}`;
      const rev = `${q}>${p}`;
      const r = edges.get(rev);
      if (r) {
        if (r === 1) edges.delete(rev);
        else edges.set(rev, r - 1);
      } else edges.set(fwd, (edges.get(fwd) ?? 0) + 1);
    }
  }
  if (edges.size > 0) closed = false;
  return { volume: Math.abs(vol), closed };
}

// ---------------------------------------------------------------- contact graph

class UnionFind {
  readonly parent: Int32Array;
  constructor(n: number) {
    this.parent = new Int32Array(n);
    for (let i = 0; i < n; i++) this.parent[i] = i;
  }
  find(x: number): number {
    const p = this.parent;
    while (p[x]! !== x) {
      p[x] = p[p[x]!]!;
      x = p[x]!;
    }
    return x;
  }
  union(a: number, b: number): void {
    const ra = this.find(a);
    const rb = this.find(b);
    if (ra !== rb) this.parent[Math.max(ra, rb)] = Math.min(ra, rb);
  }
}

/**
 * Pairs of valid elements whose bounds are within `tol` metres of each other (Euclidean gap between the boxes).
 * Sort-and-sweep along the axis with the widest spread of box minima: O(n log n + candidate pairs). `visit` gets
 * indices into `els`; return false to drop the pair (precise refinement).
 */
function sweepPairs(els: readonly CleanupElement[], valid: readonly number[], tol: number, visit: (i: number, j: number) => void): void {
  const n = valid.length;
  if (n < 2) return;
  const B = new Float64Array(n * 6);
  for (let k = 0; k < n; k++) {
    const b = els[valid[k]!]!.bounds;
    for (let c = 0; c < 6; c++) B[k * 6 + c] = b[c]!;
  }
  // Axis with the widest spread of minima.
  let axis = 0;
  let best = -1;
  for (let a = 0; a < 3; a++) {
    let lo = Infinity;
    let hi = -Infinity;
    for (let k = 0; k < n; k++) {
      const v = B[k * 6 + a]!;
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
    if (hi - lo > best) {
      best = hi - lo;
      axis = a;
    }
  }
  const order = new Uint32Array(n);
  for (let k = 0; k < n; k++) order[k] = k;
  const keys = new Float64Array(n);
  for (let k = 0; k < n; k++) keys[k] = B[k * 6 + axis]!;
  order.sort((p, q) => keys[p]! - keys[q]!);
  const a1 = (axis + 1) % 3;
  const a2 = (axis + 2) % 3;
  const t2 = tol * tol;
  for (let s = 0; s < n; s++) {
    const i = order[s]!;
    const reach = B[i * 6 + 3 + axis]! + tol;
    const i1lo = B[i * 6 + a1]!, i1hi = B[i * 6 + 3 + a1]!, i2lo = B[i * 6 + a2]!, i2hi = B[i * 6 + 3 + a2]!;
    for (let u = s + 1; u < n; u++) {
      const j = order[u]!;
      if (keys[j]! > reach) break;
      const g1 = Math.max(0, B[j * 6 + a1]! - i1hi, i1lo - B[j * 6 + 3 + a1]!);
      if (g1 > tol) continue;
      const g2 = Math.max(0, B[j * 6 + a2]! - i2hi, i2lo - B[j * 6 + 3 + a2]!);
      if (g2 > tol) continue;
      const g0 = Math.max(0, keys[j]! - B[i * 6 + 3 + axis]!);
      if (g0 * g0 + g1 * g1 + g2 * g2 > t2) continue;
      visit(i, j);
    }
  }
}

// ---------------------------------------------------------------- the analysis

function median(a: number[]): number {
  if (a.length === 0) return 0;
  const s = Float64Array.from(a).sort();
  const m = s.length >> 1;
  return s.length % 2 ? s[m]! : (s[m - 1]! + s[m]!) / 2;
}

export function analyse(elements: readonly CleanupElement[], rulesIn?: Partial<CleanupRules> | CleanupRules, geometry?: CleanupGeometry): CleanupResult {
  const t0 = performance.now();
  const d = defaultRules();
  const rules: CleanupRules = {
    floating: { ...d.floating, ...rulesIn?.floating },
    tiny: { ...d.tiny, ...rulesIn?.tiny },
    strays: { ...d.strays, ...rulesIn?.strays },
    duplicates: { ...d.duplicates, ...rulesIn?.duplicates },
    degenerate: { ...d.degenerate, ...rulesIn?.degenerate },
    classes: { ...d.classes, ...rulesIn?.classes },
  };

  const matches = new Map<number, CleanupMatch>();
  const counts: Record<RuleName, number> = { floating: 0, tiny: 0, strays: 0, duplicates: 0, degenerate: 0, classes: 0 };
  const add = (id: number, rule: RuleName, reason: string): void => {
    let m = matches.get(id);
    if (!m) {
      m = { id, rules: [], reasons: [] };
      matches.set(id, m);
    }
    if (!m.rules.includes(rule)) {
      m.rules.push(rule);
      counts[rule]++;
    }
    m.reasons.push(reason);
  };

  const n = elements.length;
  const tri = (id: number): number | undefined => geometry?.triangleCount?.(id);

  // Degenerate (also decides which elements take part in the other rules).
  const bad = new Uint8Array(n); // 1: degenerate, excluded from the graph and statistics
  const nonPhysical = new Set(NON_PHYSICAL_CLASSES);
  for (let k = 0; k < n; k++) {
    const e = elements[k]!;
    let why: string | null = null;
    if (!isFiniteBounds(e.bounds)) why = 'non-finite or empty bounds';
    else if (tri(e.id) === 0) why = 'no triangles';
    else {
      const b = e.bounds;
      const dim = Math.min(b[3] - b[0], b[4] - b[1], b[5] - b[2]);
      if (dim < DEGENERATE_DIM) why = `zero-thickness bounds (${fmt(dim * 1000)} mm < ${DEGENERATE_DIM * 1000} mm)`;
    }
    if (why) bad[k] = 1;
    if (rules.degenerate.enabled) {
      if (why) add(e.id, 'degenerate', `degenerate: ${why}`);
      if (nonPhysical.has(e.ifcClass)) add(e.id, 'degenerate', `degenerate: non-physical class ${e.ifcClass}`);
    }
  }
  const valid: number[] = [];
  for (let k = 0; k < n; k++) if (!bad[k]) valid.push(k);

  // Class groups.
  const cls = rules.classes;
  if (cls.proxies || cls.furniture || cls.accessories) {
    const map = new Map<string, string>();
    if (cls.proxies) for (const c of PROXY_CLASSES) map.set(c, 'proxy');
    if (cls.furniture) for (const c of FURNITURE_CLASSES) map.set(c, 'furniture');
    if (cls.accessories) for (const c of ACCESSORY_CLASSES) map.set(c, 'accessory or fastener');
    for (const e of elements) {
      const g = map.get(e.ifcClass);
      if (g) add(e.id, 'classes', `class group ${g}: ${e.ifcClass}`);
    }
  }

  // Tiny.
  if (rules.tiny.enabled) {
    for (const k of valid) {
      const e = elements[k]!;
      const s = largestDimension(e.bounds);
      if (s < rules.tiny.maxSize) add(e.id, 'tiny', `tiny: largest dimension ${fmt(s)} m < ${fmt(rules.tiny.maxSize)} m`);
    }
  }

  // Distant strays.
  if (rules.strays.enabled && valid.length >= 3) {
    const cx: number[] = [];
    const cy: number[] = [];
    const cz: number[] = [];
    for (const k of valid) {
      const b = elements[k]!.bounds;
      cx.push((b[0] + b[3]) / 2);
      cy.push((b[1] + b[4]) / 2);
      cz.push((b[2] + b[5]) / 2);
    }
    const mx = median(cx), my = median(cy), mz = median(cz);
    const dist = cx.map((x, i) => Math.hypot(x - mx, cy[i]! - my, cz[i]! - mz));
    const radius = median(dist);
    if (radius > 1e-6) {
      const st = rules.strays;
      const limit = st.factor * radius;
      // Box of the main model: every element inside the limit. The gap of a candidate is measured to that box.
      const lo = [Infinity, Infinity, Infinity];
      const hi = [-Infinity, -Infinity, -Infinity];
      for (let i = 0; i < valid.length; i++) {
        if (dist[i]! > limit) continue;
        const b = elements[valid[i]!]!.bounds;
        for (let a = 0; a < 3; a++) {
          if (b[a]! < lo[a]!) lo[a] = b[a]!;
          if (b[3 + a]! > hi[a]!) hi[a] = b[3 + a]!;
        }
      }
      const minGap = Math.max(0, st.minGap ?? 0);
      const maxSize = Math.max(0, st.maxSize ?? 0);
      for (let i = 0; i < valid.length; i++) {
        if (!(dist[i]! > limit)) continue;
        const b = elements[valid[i]!]!.bounds;
        const size = largestDimension(b);
        if (maxSize > 0 && size > maxSize) continue;
        const gap = boxGap(b, lo, hi);
        if (minGap > 0 && !(gap >= minGap)) continue;
        let why = `distant stray: ${fmt(dist[i]!)} m from the model centre > ${fmt(st.factor)} x robust radius ${fmt(radius)} m`;
        if (minGap > 0) why += `, ${fmt(gap)} m outside the main model >= ${fmt(minGap)} m`;
        if (maxSize > 0) why += `, largest dimension ${fmt(size)} m <= ${fmt(maxSize)} m`;
        add(elements[valid[i]!]!.id, 'strays', why);
      }
    }
  }

  // Duplicates.
  if (rules.duplicates.enabled) {
    const groups = new Map<string, number[]>();
    for (const k of valid) {
      const e = elements[k]!;
      const key = `${e.ifcClass}|${tri(e.id) ?? -1}`;
      let g = groups.get(key);
      if (!g) groups.set(key, (g = []));
      g.push(k);
    }
    for (const g of groups.values()) {
      if (g.length < 2) continue;
      g.sort((p, q) => elements[p]!.bounds[0] - elements[q]!.bounds[0]);
      const uf = new UnionFind(g.length);
      for (let a = 0; a < g.length; a++) {
        const ba = elements[g[a]!]!.bounds;
        for (let b = a + 1; b < g.length; b++) {
          const bb = elements[g[b]!]!.bounds;
          if (bb[0] - ba[0] > DUPLICATE_TOL) break;
          let same = true;
          for (let c = 0; c < 6 && same; c++) if (Math.abs(ba[c]! - bb[c]!) > DUPLICATE_TOL) same = false;
          if (same) uf.union(a, b);
        }
      }
      const byRoot = new Map<number, number[]>();
      for (let a = 0; a < g.length; a++) {
        const r = uf.find(a);
        let l = byRoot.get(r);
        if (!l) byRoot.set(r, (l = []));
        l.push(elements[g[a]!]!.id);
      }
      for (const l of byRoot.values()) {
        if (l.length < 2) continue;
        const keep = Math.min(...l);
        for (const id of l) if (id !== keep) add(id, 'duplicates', `duplicate of #${keep} (same class, bounds within ${DUPLICATE_TOL * 1000} mm)`);
      }
    }
  }

  // Floating: contact graph and components.
  let contactEdges = 0;
  let compCount = 0;
  let mainSize = 0;
  let mainElements = 0;
  if (rules.floating.enabled && valid.length > 0) {
    const fl = rules.floating;
    const tol = Math.max(0, fl.contactTolerance);
    const uf = new UnionFind(valid.length);
    const precise = fl.precise && geometry?.surfaceDistance;
    // Own size proxy that decides whether an edge needs mesh refinement: edges between two elements that are
    // both at or above the threshold are kept as contacts without a mesh test.
    const cheapSize = (k: number): number => {
      const b = elements[valid[k]!]!.bounds;
      if (fl.metric === 'largest dimension (m)') return largestDimension(b);
      if (fl.metric === 'triangle count') return tri(elements[valid[k]!]!.id) ?? Infinity;
      return boundsVolume(b);
    };
    const large = precise ? valid.map((_, k) => cheapSize(k) >= fl.threshold) : [];
    sweepPairs(elements, valid, tol, (i, j) => {
      if (precise && !(large[i] && large[j])) {
        const dist = geometry!.surfaceDistance!(elements[valid[i]!]!.id, elements[valid[j]!]!.id, tol);
        if (!(dist <= tol)) return;
      }
      contactEdges++;
      uf.union(i, j);
    });

    // Component aggregates.
    interface Comp { members: number[]; lo: number[]; hi: number[]; volSum: number }
    const comps = new Map<number, Comp>();
    for (let k = 0; k < valid.length; k++) {
      const r = uf.find(k);
      let c = comps.get(r);
      if (!c) comps.set(r, (c = { members: [], lo: [Infinity, Infinity, Infinity], hi: [-Infinity, -Infinity, -Infinity], volSum: 0 }));
      c.members.push(k);
      const b = elements[valid[k]!]!.bounds;
      for (let a = 0; a < 3; a++) {
        if (b[a]! < c.lo[a]!) c.lo[a] = b[a]!;
        if (b[3 + a]! > c.hi[a]!) c.hi[a] = b[3 + a]!;
      }
      c.volSum += boundsVolume(b);
    }
    compCount = comps.size;
    // Main structure: largest total bounds volume (ties and all-zero volumes: element count). Volume rather than
    // count so that a few thousand pipe fragments never outrank the slabs and walls; only non-main components can match.
    let main: Comp | null = null;
    for (const c of comps.values()) {
      if (!main || c.volSum > main.volSum || (c.volSum === main.volSum && c.members.length > main.members.length)) main = c;
    }
    mainSize = main?.volSum ?? 0;
    mainElements = main?.members.length ?? 0;

    const meshVol = (k: number): number => {
      const e = elements[valid[k]!]!;
      const v = geometry?.meshVolume?.(e.id);
      return v === null || v === undefined ? boundsVolume(e.bounds) : v;
    };
    const unit = fl.metric === 'largest dimension (m)' ? ' m' : fl.metric === 'triangle count' ? ' triangles' : ' m³';
    const label = fl.metric === 'largest dimension (m)' ? 'largest dimension' : fl.metric === 'triangle count' ? 'triangle count' : fl.metric.replace(/ \(.*$/, '');
    for (const c of comps.values()) {
      if (c === main) continue;
      if (fl.mode === 'single elements' && c.members.length !== 1) continue;
      let size: number;
      switch (fl.metric) {
        case 'largest dimension (m)':
          size = Math.max(c.hi[0]! - c.lo[0]!, c.hi[1]! - c.lo[1]!, c.hi[2]! - c.lo[2]!);
          break;
        case 'bounds volume (m³)':
          size = c.members.length === 1 ? c.volSum : (c.hi[0]! - c.lo[0]!) * (c.hi[1]! - c.lo[1]!) * (c.hi[2]! - c.lo[2]!);
          break;
        case 'mesh volume (m³)':
          size = 0;
          for (const k of c.members) size += meshVol(k);
          break;
        default:
          size = 0;
          for (const k of c.members) size += tri(elements[valid[k]!]!.id) ?? 0;
      }
      if (!(size < fl.threshold)) continue;
      const what = c.members.length === 1 ? 'lone element, no contacts' : `cluster of ${c.members.length} touching elements`;
      const reason = `floating ${what}: ${label} ${fmt(size)}${unit} < ${fmt(fl.threshold)}${unit}`;
      for (const k of c.members) add(elements[valid[k]!]!.id, 'floating', reason);
    }
  }

  const ids = [...matches.keys()].sort((a, b) => a - b);
  return {
    ids,
    matches,
    counts,
    components: { count: compCount, mainSize, mainElements },
    contactEdges,
    ms: performance.now() - t0,
  };
}

/** "Floating 12, Tiny 3, Strays 1, Duplicates 0, Degenerate 0, Classes 0" */
export function summarise(counts: Record<RuleName, number>): string {
  return `Floating ${counts.floating}, Tiny ${counts.tiny}, Strays ${counts.strays}, Duplicates ${counts.duplicates}, Degenerate ${counts.degenerate}, Classes ${counts.classes}`;
}
