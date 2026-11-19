// Shared shapes of the simplification tools. Everything under cleanup/simplify is pure TypeScript (no DOM, no three.js
// scene objects), so it runs in node tests and can move into a worker later.

export interface IndexRange {
  start: number;
  count: number;
}

/** One element's triangles: positions (x y z per vertex), optional normals, and a triangle index list (3 per triangle). */
export interface MeshData {
  positions: Float32Array;
  indices: Uint32Array;
  normals?: Float32Array;
}

/** Read access to the merged model buffers (structurally the same as MergedGeometry's attributes and range tables). */
export interface GeometrySource {
  position: Float32Array;
  normal: Float32Array;
  /** Global vertex indices. */
  index: Uint32Array;
  /** Per element: range in `index` (in indices). */
  ranges: ReadonlyArray<IndexRange>;
  /** Per element: range in the vertex buffers (in vertices). */
  vertexRanges: ReadonlyArray<IndexRange>;
}

export function triangleCountOf(m: Pick<MeshData, 'indices'>): number {
  return Math.floor(m.indices.length / 3);
}

/** Compact copy of one element's mesh (local vertex indices), or null when it has no triangles. */
export function sourceMesh(src: GeometrySource, id: number, withNormals = true): MeshData | null {
  const r = src.ranges[id];
  const vr = src.vertexRanges[id];
  if (!r || !vr || r.count < 3 || vr.count < 1) return null;
  const idx = new Uint32Array(r.count);
  for (let k = 0; k < r.count; k++) idx[k] = src.index[r.start + k]! - vr.start;
  const out: MeshData = { positions: src.position.slice(vr.start * 3, (vr.start + vr.count) * 3), indices: idx };
  if (withNormals) out.normals = src.normal.slice(vr.start * 3, (vr.start + vr.count) * 3);
  return out;
}

export function sourceTriangles(src: GeometrySource, id: number): number {
  return Math.floor((src.ranges[id]?.count ?? 0) / 3);
}

// ---------------------------------------------------------------- size estimate

/** Bytes a mesh takes in a glb: float32 positions and normals plus 16 or 32 bit indices. */
export function meshBytes(vertexCount: number, indexCount: number): number {
  return vertexCount * 24 + indexCount * (vertexCount < 65536 ? 2 : 4);
}

/** JSON and accessor overhead of one node that owns its own mesh, and of one extra node that only instances a mesh. */
export const NODE_BYTES = 120;
export const MESH_OVERHEAD_BYTES = 420;
export const INSTANCE_NODE_BYTES = 150;

export function meshOf(m: MeshData): { vertexCount: number; indexCount: number } {
  return { vertexCount: Math.floor(m.positions.length / 3), indexCount: m.indices.length };
}

// ---------------------------------------------------------------- chunked running

export interface ChunkOptions {
  /** Milliseconds of work between yields to the event loop (default 12). */
  budgetMs?: number;
  onProgress?: (done: number, total: number) => void;
  /** Set `aborted` to stop at the next chunk boundary. */
  signal?: { aborted: boolean };
  /** Replace the default yield (a macrotask) in tests. */
  yieldFn?: () => Promise<void>;
}

const defaultYield = (): Promise<void> => new Promise((r) => setTimeout(r, 0));

/**
 * Run `step` over `items`, yielding to the event loop every `budgetMs` so the page stays responsive and progress can paint.
 * Returns false when aborted, true when every item was processed.
 */
export async function runChunked<T>(items: readonly T[], step: (item: T, index: number) => void, o: ChunkOptions = {}): Promise<boolean> {
  const budget = o.budgetMs ?? 12;
  const yieldFn = o.yieldFn ?? defaultYield;
  const now = (): number => (typeof performance !== 'undefined' ? performance.now() : Date.now());
  let t0 = now();
  o.onProgress?.(0, items.length);
  for (let i = 0; i < items.length; i++) {
    if (o.signal?.aborted) return false;
    step(items[i]!, i);
    if (now() - t0 >= budget) {
      o.onProgress?.(i + 1, items.length);
      await yieldFn();
      t0 = now();
    }
  }
  o.onProgress?.(items.length, items.length);
  return !o.signal?.aborted;
}
