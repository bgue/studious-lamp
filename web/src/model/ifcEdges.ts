// Crease edges of the merged geometry, computed with typed arrays (no three.js, so it runs in the import worker).
// A port of three's EdgesGeometry applied to every element's own triangles: an edge is drawn where two faces meet at more
// than `thresholdDeg` (30, MergedGeometry's EDGE_THRESHOLD_DEG) and where an edge has a single face (open boundary). The
// output is identical to what MergedGeometry's constructor builds element by element (tests/large-direct.test.ts).
// Differences are only in the data structures: vertices are matched by their position rounded to 1e-4 (as EdgesGeometry
// does) through an open-addressing table instead of strings, and the edge map is keyed by a number.

/** Crease angle (degrees) above which an edge between two faces is drawn. */
export const EDGE_THRESHOLD_DEG = 30;

export interface EdgeResult {
  /** xyz of segment end points, 2 vertices per segment, element after element. */
  position: Float32Array;
  /** Per element [start, count] in vertices (2 Uint32 per element). */
  ranges: Uint32Array;
}

export interface EdgeInput {
  position: Float32Array;
  index: Uint32Array;
  /** [start, count] per element, vertices (2 per element). */
  vertexRanges: Uint32Array;
  /** [start, count] per element, indices (2 per element). */
  ranges: Uint32Array;
  elementCount: number;
}

const PRECISION = 1e4;

/** Edge segments for every element. `progress` is called now and then with the number of elements done. */
export function computeEdges(input: EdgeInput, thresholdDeg = 30, progress?: (done: number) => void): EdgeResult {
  const { position, index, vertexRanges, ranges, elementCount: n } = input;
  const thresholdDot = Math.cos((thresholdDeg * Math.PI) / 180);
  const outRanges = new Uint32Array(n * 2);
  let out = new Float32Array(1 << 16);
  let outLen = 0;
  const reserve = (extra: number): void => {
    if (outLen + extra <= out.length) return;
    let cap = out.length;
    while (cap < outLen + extra) cap *= 2;
    const next = new Float32Array(cap);
    next.set(out.subarray(0, outLen));
    out = next;
  };

  // scratch, grown to the largest element
  let maxV = 0;
  let maxT = 0;
  for (let e = 0; e < n; e++) {
    if (vertexRanges[e * 2 + 1]! > maxV) maxV = vertexRanges[e * 2 + 1]!;
    if (ranges[e * 2 + 1]! / 3 > maxT) maxT = ranges[e * 2 + 1]! / 3;
  }
  let cap = 16;
  while (cap < maxV * 2) cap <<= 1;
  const mask = cap - 1;
  const table = new Int32Array(cap);
  const stamp = new Int32Array(cap); // table slot is valid when stamp === epoch (avoids clearing per element)
  const qx = new Float64Array(maxV);
  const qy = new Float64Array(maxV);
  const qz = new Float64Array(maxV);
  const canon = new Int32Array(maxV);
  const eI0 = new Int32Array(maxT * 3);
  const eI1 = new Int32Array(maxT * 3);
  const eNx = new Float64Array(maxT * 3);
  const eNy = new Float64Array(maxT * 3);
  const eNz = new Float64Array(maxT * 3);
  const edgeMap = new Map<number, number>(); // key -> entry index, or -1 once consumed (EdgesGeometry stores null)
  let epoch = 0;

  for (let e = 0; e < n; e++) {
    outRanges[e * 2] = outLen / 3;
    const tCount = ranges[e * 2 + 1]!;
    if (tCount === 0) {
      outRanges[e * 2 + 1] = 0;
      continue;
    }
    const v0 = vertexRanges[e * 2]!;
    const vN = vertexRanges[e * 2 + 1]!;
    const i0 = ranges[e * 2]!;
    epoch++;

    // canonical vertex per rounded position
    for (let i = 0; i < vN; i++) {
      const o = (v0 + i) * 3;
      const a = Math.round(position[o]! * PRECISION);
      const b = Math.round(position[o + 1]! * PRECISION);
      const c = Math.round(position[o + 2]! * PRECISION);
      qx[i] = a; qy[i] = b; qz[i] = c;
      let h = (Math.imul(a | 0, 73856093) ^ Math.imul(b | 0, 19349663) ^ Math.imul(c | 0, 83492791)) & mask;
      for (;;) {
        if (stamp[h] !== epoch) {
          stamp[h] = epoch;
          table[h] = i;
          canon[i] = i;
          break;
        }
        const t = table[h]!;
        if (qx[t] === a && qy[t] === b && qz[t] === c) {
          canon[i] = t;
          break;
        }
        h = (h + 1) & mask;
      }
    }

    edgeMap.clear();
    let entries = 0;
    const startLen = outLen;
    for (let t = 0; t < tCount; t += 3) {
      const ia = index[i0 + t]! - v0;
      const ib = index[i0 + t + 1]! - v0;
      const ic = index[i0 + t + 2]! - v0;
      const ca = canon[ia]!, cb = canon[ib]!, cc = canon[ic]!;
      if (ca === cb || cb === cc || cc === ca) continue; // degenerate once rounded
      const ao = (v0 + ia) * 3, bo = (v0 + ib) * 3, co = (v0 + ic) * 3;
      const ax = position[ao]!, ay = position[ao + 1]!, az = position[ao + 2]!;
      const bx = position[bo]!, by = position[bo + 1]!, bz = position[bo + 2]!;
      const cx = position[co]!, cy = position[co + 1]!, cz = position[co + 2]!;
      // Triangle.getNormal: (c - b) x (a - b), normalised (zero vector when degenerate)
      const tx = cx - bx, ty = cy - by, tz = cz - bz;
      const sx = ax - bx, sy = ay - by, sz = az - bz;
      let nx = ty * sz - tz * sy;
      let ny = tz * sx - tx * sz;
      let nz = tx * sy - ty * sx;
      const lenSq = nx * nx + ny * ny + nz * nz;
      if (lenSq > 0) {
        const k = 1 / Math.sqrt(lenSq);
        nx *= k; ny *= k; nz *= k;
      } else {
        nx = 0; ny = 0; nz = 0;
      }
      for (let j = 0; j < 3; j++) {
        const ja = j === 0 ? ia : j === 1 ? ib : ic;
        const jb = j === 0 ? ib : j === 1 ? ic : ia;
        const ka = j === 0 ? ca : j === 1 ? cb : cc;
        const kb = j === 0 ? cb : j === 1 ? cc : ca;
        const key = ka * vN + kb;
        const rkey = kb * vN + ka;
        const sib = edgeMap.get(rkey);
        if (sib !== undefined && sib >= 0) {
          if (nx * eNx[sib]! + ny * eNy[sib]! + nz * eNz[sib]! <= thresholdDot) {
            reserve(6);
            const po = (v0 + ja) * 3, qo = (v0 + jb) * 3;
            out[outLen++] = position[po]!; out[outLen++] = position[po + 1]!; out[outLen++] = position[po + 2]!;
            out[outLen++] = position[qo]!; out[outLen++] = position[qo + 1]!; out[outLen++] = position[qo + 2]!;
          }
          edgeMap.set(rkey, -1);
        } else if (!edgeMap.has(key)) {
          eI0[entries] = ja; eI1[entries] = jb;
          eNx[entries] = nx; eNy[entries] = ny; eNz[entries] = nz;
          edgeMap.set(key, entries++);
        }
      }
    }
    // unmatched edges, in the order they were first seen
    for (const idx of edgeMap.values()) {
      if (idx < 0) continue;
      reserve(6);
      const po = (v0 + eI0[idx]!) * 3, qo = (v0 + eI1[idx]!) * 3;
      out[outLen++] = position[po]!; out[outLen++] = position[po + 1]!; out[outLen++] = position[po + 2]!;
      out[outLen++] = position[qo]!; out[outLen++] = position[qo + 1]!; out[outLen++] = position[qo + 2]!;
    }
    outRanges[e * 2 + 1] = (outLen - startLen) / 3;
    if (progress && (e & 255) === 255) progress(e + 1);
  }
  progress?.(n);
  return { position: out.slice(0, outLen), ranges: outRanges };
}
