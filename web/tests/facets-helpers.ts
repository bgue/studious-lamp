// Shared by the facet tests: synthetic meshes in the viewer frame (y up), boxes and rotations.

import type { OrientationMesh } from '../src/classify/facets/orientation';

export interface Mesh extends OrientationMesh {
  position: Float32Array;
  index: Uint32Array;
}

/** An axis-aligned box centred at (cx, cy, cz) with sizes (sx, sy, sz) along viewer x, y, z. 12 triangles. */
export function box(cx: number, cy: number, cz: number, sx: number, sy: number, sz: number): Mesh {
  const p: number[] = [];
  for (const dx of [-0.5, 0.5]) for (const dy of [-0.5, 0.5]) for (const dz of [-0.5, 0.5]) p.push(cx + dx * sx, cy + dy * sy, cz + dz * sz);
  // vertex index = (dx>0)*4 + (dy>0)*2 + (dz>0)
  const quads = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]];
  const idx: number[] = [];
  for (const [a, b, c, d] of quads) idx.push(a!, b!, c!, a!, c!, d!);
  return { position: new Float32Array(p), index: new Uint32Array(idx) };
}

/** Rotate a mesh about an axis through the origin (viewer axes) by `deg` degrees. */
export function rotate(m: Mesh, axis: 'x' | 'y' | 'z', deg: number): Mesh {
  const a = (deg * Math.PI) / 180, c = Math.cos(a), s = Math.sin(a);
  const out = new Float32Array(m.position);
  for (let i = 0; i < out.length; i += 3) {
    const x = out[i]!, y = out[i + 1]!, z = out[i + 2]!;
    if (axis === 'y') { out[i] = c * x + s * z; out[i + 2] = -s * x + c * z; }
    else if (axis === 'x') { out[i + 1] = c * y - s * z; out[i + 2] = s * y + c * z; }
    else { out[i] = c * x - s * y; out[i + 1] = s * x + c * y; }
  }
  return { position: out, index: m.index };
}

export function merge(...ms: Mesh[]): Mesh {
  const pos: number[] = [];
  const idx: number[] = [];
  for (const m of ms) {
    const base = pos.length / 3;
    pos.push(...m.position);
    for (const i of m.index) idx.push(i + base);
  }
  return { position: new Float32Array(pos), index: new Uint32Array(idx) };
}

export function boundsOf(m: Mesh): [number, number, number, number, number, number] {
  const b: [number, number, number, number, number, number] = [Infinity, Infinity, Infinity, -Infinity, -Infinity, -Infinity];
  for (let i = 0; i < m.position.length; i += 3) for (let k = 0; k < 3; k++) { b[k] = Math.min(b[k]!, m.position[i + k]!); b[k + 3] = Math.max(b[k + 3]!, m.position[i + k]!); }
  return b;
}
