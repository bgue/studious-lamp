// Point picking on the cloud: the shown point nearest to the cursor on screen, preferring the frontmost surface.
//
// The cloud has no BVH, so picking works in screen space. buildScreenIndex projects every shown point once for the
// current view (two passes, a counting sort into square cells of `cell` px) and pickNearest looks only at the cells
// around the cursor. On 2 million points a build takes some tens of ms; a query takes microseconds, so the index is
// rebuilt only when the view or the transform changes and hover stays cheap.
//
// Choice: first the points whose drawn square covers the cursor (within `innerPx`, about half the point size): what
// the user sees under the cursor. Only when there is none, the whole radius (8 px, for sparse clouds). Among the
// candidates: find the smallest view depth d0, keep those within a depth band of d0 (max(bandMin, bandRel * d0)),
// then take the one closest to the cursor. A plain "nearest on screen" would pick points of the far wall through
// gaps; a plain "frontmost" over the whole radius would jump to the top edge of a wall a few pixels away (in
// perspective, a wall top projects over the floor beside it) or to a stray noise point at the edge of the radius.
// Occlusion: the cloud is depth tested against opaque model surfaces when drawn, so a point hidden behind a wall is
// not what the user sees under the cursor. The caller passes the view depth of the first opaque model surface under
// the cursor (`maxDepth`, see PointCloudController.pickCloudAt); points behind it, by more than the depth band, are
// left out.
// Pure: no DOM, no three.js.

export interface ScreenIndex {
  width: number;
  height: number;
  cell: number;
  cols: number;
  rows: number;
  /** cellStart[c] .. cellStart[c + 1] index into `items` (point indices), `sx`, `sy`, `depth` (parallel to items). */
  cellStart: Uint32Array;
  items: Uint32Array;
  sx: Float32Array;
  sy: Float32Array;
  depth: Float32Array;
}

export interface ProjectionInput {
  /** 3 floats per point (the drawn positions, before the object matrix). */
  positions: Float32Array;
  /** Column-major clip matrix: projection * view * object (doubles). */
  clip: ArrayLike<number>;
  /** Column-major view * object matrix: its z row gives the view depth. */
  view: ArrayLike<number>;
  /** CSS pixels. */
  width: number;
  height: number;
  cell?: number;
  /** Indices to consider (the drawn subset); all points when absent. */
  indices?: Uint32Array | null;
  /** Return false to skip a point (clipped by a section plane). Called with the object-space position. */
  keep?: (x: number, y: number, z: number) => boolean;
}

export function buildScreenIndex(inp: ProjectionInput): ScreenIndex {
  const { positions: P, clip: m, view: v, width, height } = inp;
  const cell = inp.cell ?? 8;
  const cols = Math.max(1, Math.ceil(width / cell));
  const rows = Math.max(1, Math.ceil(height / cell));
  const total = inp.indices ? inp.indices.length : Math.floor(P.length / 3);
  const cellOf = new Int32Array(total);
  const counts = new Uint32Array(cols * rows + 1);
  const m0 = m[0]!, m1 = m[1]!, m3 = m[3]!, m4 = m[4]!, m5 = m[5]!, m7 = m[7]!, m8 = m[8]!, m9 = m[9]!, m11 = m[11]!, m12 = m[12]!, m13 = m[13]!, m15 = m[15]!;
  let visible = 0;
  for (let k = 0; k < total; k++) {
    const i = inp.indices ? inp.indices[k]! : k;
    const x = P[i * 3]!, y = P[i * 3 + 1]!, z = P[i * 3 + 2]!;
    const cw = m3 * x + m7 * y + m11 * z + m15;
    if (cw <= 1e-9) { cellOf[k] = -1; continue; }
    const nx = (m0 * x + m4 * y + m8 * z + m12) / cw;
    const ny = (m1 * x + m5 * y + m9 * z + m13) / cw;
    if (nx < -1 || nx > 1 || ny < -1 || ny > 1) { cellOf[k] = -1; continue; }
    if (inp.keep && !inp.keep(x, y, z)) { cellOf[k] = -1; continue; }
    const px = (nx * 0.5 + 0.5) * width, py = (0.5 - ny * 0.5) * height;
    const c = Math.min(rows - 1, Math.floor(py / cell)) * cols + Math.min(cols - 1, Math.floor(px / cell));
    cellOf[k] = c;
    counts[c + 1]!++;
    visible++;
  }
  const cellStart = new Uint32Array(cols * rows + 1);
  for (let c = 0; c < cols * rows; c++) cellStart[c + 1] = cellStart[c]! + counts[c + 1]!;
  const fill = cellStart.slice(0, cols * rows);
  const items = new Uint32Array(visible);
  const sx = new Float32Array(visible), sy = new Float32Array(visible), depth = new Float32Array(visible);
  const v2 = v[2]!, v6 = v[6]!, v10 = v[10]!, v14 = v[14]!;
  for (let k = 0; k < total; k++) {
    const c = cellOf[k]!;
    if (c < 0) continue;
    const i = inp.indices ? inp.indices[k]! : k;
    const x = P[i * 3]!, y = P[i * 3 + 1]!, z = P[i * 3 + 2]!;
    const cw = m3 * x + m7 * y + m11 * z + m15;
    const at = fill[c]!++;
    items[at] = i;
    sx[at] = ((m0 * x + m4 * y + m8 * z + m12) / cw * 0.5 + 0.5) * width;
    sy[at] = (0.5 - (m1 * x + m5 * y + m9 * z + m13) / cw * 0.5) * height;
    depth[at] = -(v2 * x + v6 * y + v10 * z + v14);
  }
  return { width, height, cell, cols, rows, cellStart, items, sx, sy, depth };
}

export interface PickOptions {
  radiusPx?: number;
  /** Radius tried first, px (the drawn point's half size plus a little). 0 skips this step. */
  innerPx?: number;
  /** Depth band, metres: candidates within max(bandMin, bandRel * d0) of the frontmost depth d0 compete on screen distance. */
  bandMin?: number;
  bandRel?: number;
  /**
   * View depth of the first opaque model surface under the cursor, metres (Infinity or absent: none). Points deeper
   * than maxDepth + max(bandMin, bandRel * maxDepth) are hidden by it and cannot be picked.
   */
  maxDepth?: number;
}

/** Index of the picked point, or -1 when no point projects within the radius. */
export function pickNearest(idx: ScreenIndex, px: number, py: number, opt: PickOptions = {}): number {
  const inner = opt.innerPx ?? 2;
  if (inner > 0) {
    const k = pickWithin(idx, px, py, Math.min(inner, opt.radiusPx ?? 8), opt);
    if (k >= 0) return k;
  }
  return pickWithin(idx, px, py, opt.radiusPx ?? 8, opt);
}

function pickWithin(idx: ScreenIndex, px: number, py: number, r: number, opt: PickOptions): number {
  const r2 = r * r;
  const md = opt.maxDepth ?? Infinity;
  const limit = Number.isFinite(md) ? md + Math.max(opt.bandMin ?? 0.05, (opt.bandRel ?? 0.01) * Math.abs(md)) : Infinity;
  const c0 = Math.max(0, Math.floor((px - r) / idx.cell)), c1 = Math.min(idx.cols - 1, Math.floor((px + r) / idx.cell));
  const r0 = Math.max(0, Math.floor((py - r) / idx.cell)), r1 = Math.min(idx.rows - 1, Math.floor((py + r) / idx.cell));
  let d0 = Infinity;
  for (let row = r0; row <= r1; row++) {
    for (let col = c0; col <= c1; col++) {
      const c = row * idx.cols + col;
      for (let k = idx.cellStart[c]!; k < idx.cellStart[c + 1]!; k++) {
        const dx = idx.sx[k]! - px, dy = idx.sy[k]! - py;
        if (dx * dx + dy * dy <= r2 && idx.depth[k]! < d0 && idx.depth[k]! <= limit) d0 = idx.depth[k]!;
      }
    }
  }
  if (!Number.isFinite(d0)) return -1;
  const band = Math.max(opt.bandMin ?? 0.05, (opt.bandRel ?? 0.01) * Math.abs(d0));
  let best = -1, bestD = Infinity;
  for (let row = r0; row <= r1; row++) {
    for (let col = c0; col <= c1; col++) {
      const c = row * idx.cols + col;
      for (let k = idx.cellStart[c]!; k < idx.cellStart[c + 1]!; k++) {
        const dx = idx.sx[k]! - px, dy = idx.sy[k]! - py;
        const s = dx * dx + dy * dy;
        if (s <= r2 && idx.depth[k]! <= d0 + band && idx.depth[k]! <= limit && s < bestD) {
          bestD = s;
          best = idx.items[k]!;
        }
      }
    }
  }
  return best;
}
