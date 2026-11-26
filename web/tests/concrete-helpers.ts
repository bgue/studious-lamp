// Shared by the concrete tests: synthetic concrete elements as meshes in the viewer frame (y up). Dimensions are given in IFC axes
// (X east, Y north, Z up) and converted: viewer (x, y, z) = (X, Z, -Y).

import type { Mesh } from './facets-helpers';
import { merge } from './facets-helpers';

type P2 = [number, number];

/** Ear-clipping triangulation of a simple polygon (any winding). Returns index triples. */
export function earClip(poly: P2[]): Array<[number, number, number]> {
  const area = poly.reduce((s, p, i) => { const q = poly[(i + 1) % poly.length]!; return s + (p[0] * q[1] - q[0] * p[1]); }, 0);
  const ids = poly.map((_, i) => i);
  if (area < 0) ids.reverse();
  const out: Array<[number, number, number]> = [];
  const cr = (a: P2, b: P2, c: P2): number => (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
  let guard = 0;
  while (ids.length > 3 && guard++ < 1000) {
    let cut = false;
    for (let i = 0; i < ids.length; i++) {
      const a = ids[(i + ids.length - 1) % ids.length]!, b = ids[i]!, c = ids[(i + 1) % ids.length]!;
      if (cr(poly[a]!, poly[b]!, poly[c]!) <= 1e-12) continue;
      let inside = false;
      for (const d of ids) {
        if (d === a || d === b || d === c) continue;
        if (cr(poly[a]!, poly[b]!, poly[d]!) >= 0 && cr(poly[b]!, poly[c]!, poly[d]!) >= 0 && cr(poly[c]!, poly[a]!, poly[d]!) >= 0) { inside = true; break; }
      }
      if (inside) continue;
      out.push([a, b, c]);
      ids.splice(i, 1);
      cut = true;
      break;
    }
    if (!cut) break;
  }
  if (ids.length === 3) out.push([ids[0]!, ids[1]!, ids[2]!]);
  return out;
}

/** A closed prism: the polygon (in the plane of the two axes other than `axis`, IFC axes) extruded from `from` to `to` along `axis`. */
export function prism(poly: P2[], axis: 'X' | 'Y' | 'Z', from: number, to: number): Mesh {
  const ix = (a: number, b: number, c: number): [number, number, number] => (axis === 'Z' ? [a, b, c] : axis === 'X' ? [c, a, b] : [b, c, a]);
  const n = poly.length;
  const v: Array<[number, number, number]> = [];
  for (const [a, b] of poly) v.push(ix(a, b, from));
  for (const [a, b] of poly) v.push(ix(a, b, to));
  const pos: number[] = [];
  for (const [X, Y, Z] of v) pos.push(X, Z, -Y);
  const idx: number[] = [];
  for (const [a, b, c] of earClip(poly)) { idx.push(a, c, b); idx.push(n + a, n + b, n + c); }
  for (let i = 0; i < n; i++) { const j = (i + 1) % n; idx.push(i, j, n + j, i, n + j, n + i); }
  return { position: new Float32Array(pos), index: new Uint32Array(idx) };
}

/** An axis-aligned block in IFC axes from (x0, y0, z0) with sizes (dx, dy, dz): a closed mesh with 12 triangles. */
export function block(x0: number, y0: number, z0: number, dx: number, dy: number, dz: number): Mesh {
  return prism([[x0, y0], [x0 + dx, y0], [x0 + dx, y0 + dy], [x0, y0 + dy]], 'Z', z0, z0 + dz);
}

/** A regular polygon of n sides (a round column when n is large). */
export function circle(cx: number, cy: number, r: number, n = 24): P2[] {
  return Array.from({ length: n }, (_, i) => [cx + r * Math.cos((2 * Math.PI * i) / n), cy + r * Math.sin((2 * Math.PI * i) / n)] as P2);
}

export function rotateZ(m: Mesh, deg: number): Mesh {
  // IFC Z rotation = rotation about the viewer y axis, sense: viewer z = -Y
  const a = (deg * Math.PI) / 180, c = Math.cos(a), s = Math.sin(a);
  const out = new Float32Array(m.position);
  for (let i = 0; i < out.length; i += 3) { const X = out[i]!, Y = -out[i + 2]!; out[i] = c * X - s * Y; out[i + 2] = -(s * X + c * Y); }
  return { position: out, index: m.index };
}

export { merge };
export type { Mesh };
