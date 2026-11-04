// Per-element "closed solid" flag: is the element's triangle soup an edge-manifold shell? Section caps, behind-only caps,
// peel caps and the MRI slab caps are painted for closed elements only. A single-sided element (a window pane, a
// surface sheet) shows its back faces shaded like any other face when a cut reveals them.
//
// Definition: vertices are welded by position (quantised to 10 micrometres, so the duplicated vertices of a crease or of
// a UV seam count as one), and every undirected edge must be used by an even number of triangles (2 for a plain shell).
// Degenerate edges (both ends welded to one vertex) are skipped. An element with fewer than 4 triangles is open.
// Tolerance: IFC triangulations of real solids often keep a few T-junctions (an edge matched by two shorter ones). An
// element with unmatched edges still counts as closed when they are at most 15 % of its edges and the vector area (the sum
// of the oriented triangle areas, which is zero for any watertight shell) is below 0.1 % of the total area. A pane, a
// sheet or a box with a missing face has a vector area of the order of its own area and stays open.
// Pure (typed arrays in, bytes out) and allocation-light: the scratch tables are reused across elements and cleared by
// stamps, so 100,000 elements cost tens of milliseconds (see tests/render-closed.test.ts for the measured time).

export interface Range {
  start: number;
  count: number;
}

const QUANT = 1e5;
const MIN_TRIANGLES = 4;
/** An element with a few unmatched edges still counts as closed when they are cracks or T-junctions of a watertight solid:
 *  at most this fraction of its edges is unmatched and its vector area (sum of the oriented triangle areas) vanishes. */
const MAX_UNMATCHED_FRACTION = 0.15;
const MAX_VECTOR_AREA_RATIO = 1e-3;

/**
 * `ranges[e]` is the element's index range (start, count in indices), `vertexRanges[e]` its vertex range (the indices are
 * global vertex numbers inside it). Returns 1 per closed element, 0 per open one (and per element without triangles).
 */
export function computeClosedFlags(
  position: ArrayLike<number>,
  index: ArrayLike<number>,
  ranges: ReadonlyArray<Range>,
  vertexRanges: ReadonlyArray<Range>,
  /** Optional diagnostics: per element `[unmatched edges, edges]` (2 ints each). */
  diag?: Int32Array,
): Uint8Array {
  const n = ranges.length;
  const out = new Uint8Array(n);
  let maxV = 0;
  let maxT = 0;
  for (let e = 0; e < n; e++) {
    maxV = Math.max(maxV, vertexRanges[e]?.count ?? 0);
    maxT = Math.max(maxT, Math.floor((ranges[e]?.count ?? 0) / 3));
  }
  if (maxT < MIN_TRIANGLES) return out;
  const wcap = pow2(maxV * 2 + 2);
  const ecap = pow2(maxT * 3 * 2 + 2);
  // Vertex weld: open addressing over the quantised position. wtab holds local vertex + 1 (valid when its stamp matches).
  const qx = new Int32Array(maxV);
  const qy = new Int32Array(maxV);
  const qz = new Int32Array(maxV);
  const wid = new Int32Array(maxV);
  const wtab = new Int32Array(wcap);
  const wstamp = new Int32Array(wcap);
  // Edge table: (a, b) weld ids with a < b, and the use count.
  const ea = new Int32Array(ecap);
  const eb = new Int32Array(ecap);
  const ecount = new Int32Array(ecap);
  const estamp = new Int32Array(ecap);
  let stamp = 0;

  for (let e = 0; e < n; e++) {
    const r = ranges[e]!;
    const vr = vertexRanges[e]!;
    const tris = Math.floor(r.count / 3);
    const nv = vr.count;
    if (tris < MIN_TRIANGLES || nv < 3) continue;
    stamp++;
    const wmask = pow2(nv * 2 + 2) - 1;
    const emask = pow2(tris * 3 * 2 + 2) - 1;
    for (let v = 0; v < nv; v++) {
      const g = (vr.start + v) * 3;
      const x = Math.round(position[g]! * QUANT) | 0;
      const y = Math.round(position[g + 1]! * QUANT) | 0;
      const z = Math.round(position[g + 2]! * QUANT) | 0;
      qx[v] = x;
      qy[v] = y;
      qz[v] = z;
      let h = (Math.imul(x, 73856093) ^ Math.imul(y, 19349663) ^ Math.imul(z, 83492791)) & wmask;
      for (;;) {
        if (wstamp[h] !== stamp) {
          wstamp[h] = stamp;
          wtab[h] = v + 1;
          wid[v] = v;
          break;
        }
        const u = wtab[h]! - 1;
        if (qx[u] === x && qy[u] === y && qz[u] === z) {
          wid[v] = u;
          break;
        }
        h = (h + 1) & wmask;
      }
    }
    let odd = 0;
    let edges = 0;
    let bad = false;
    let vax = 0;
    let vay = 0;
    let vaz = 0;
    let area = 0;
    const i0 = r.start;
    for (let t = 0; t < tris && !bad; t++) {
      const i = i0 + t * 3;
      const a = index[i]! - vr.start;
      const b = index[i + 1]! - vr.start;
      const c = index[i + 2]! - vr.start;
      if (a < 0 || b < 0 || c < 0 || a >= nv || b >= nv || c >= nv) {
        bad = true;
        break;
      }
      {
        const pa = (vr.start + a) * 3;
        const pb = (vr.start + b) * 3;
        const pc = (vr.start + c) * 3;
        const ux = position[pb]! - position[pa]!, uy = position[pb + 1]! - position[pa + 1]!, uz = position[pb + 2]! - position[pa + 2]!;
        const wx = position[pc]! - position[pa]!, wy = position[pc + 1]! - position[pa + 1]!, wz = position[pc + 2]! - position[pa + 2]!;
        const cx = uy * wz - uz * wy, cy = uz * wx - ux * wz, cz = ux * wy - uy * wx;
        vax += cx;
        vay += cy;
        vaz += cz;
        area += Math.sqrt(cx * cx + cy * cy + cz * cz);
      }
      const w0 = wid[a]!;
      const w1 = wid[b]!;
      const w2 = wid[c]!;
      for (let k = 0; k < 3; k++) {
        let p = k === 0 ? w0 : k === 1 ? w1 : w2;
        let q = k === 0 ? w1 : k === 1 ? w2 : w0;
        if (p === q) continue;
        if (p > q) {
          const s = p;
          p = q;
          q = s;
        }
        let h = (Math.imul(p, 0x9e3779b1) ^ Math.imul(q, 0x85ebca6b)) & emask;
        for (;;) {
          if (estamp[h] !== stamp) {
            estamp[h] = stamp;
            ea[h] = p;
            eb[h] = q;
            ecount[h] = 1;
            odd++;
            edges++;
            break;
          }
          if (ea[h] === p && eb[h] === q) {
            const cnt = ++ecount[h]!;
            if (cnt & 1) odd++;
            else odd--;
            break;
          }
          h = (h + 1) & emask;
        }
      }
    }
    if (diag) {
      diag[e * 2] = odd;
      diag[e * 2 + 1] = edges;
    }
    if (bad || edges === 0) continue;
    if (odd === 0) out[e] = 1;
    else if (odd <= MAX_UNMATCHED_FRACTION * edges && area > 0 && Math.sqrt(vax * vax + vay * vay + vaz * vaz) <= MAX_VECTOR_AREA_RATIO * area) out[e] = 1;
  }
  return out;
}

function pow2(v: number): number {
  let p = 16;
  while (p < v) p <<= 1;
  return p;
}
