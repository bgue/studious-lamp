// Taking a snapshot of the model on screen (design 3.1, 4.1) and the matching ghost source. The only revision module that knows the
// viewer's loaded model; the signature work is sliced so the page stays responsive.

import type { LoadedModel } from '../model/loader';
import type { ClassifyResult } from '../classify/types';
import type { SceneModel } from '../types';
import { computeSignaturesSliced, rangesOfPairs } from './geomSig';
import { snapshotOf } from './snapshot';
import { boxEdges, meshOfElement } from './ghost';
import type { GhostMesh, GhostSource } from './ghost';
import type { ModelSnapshot } from './types';

const sigCache = new WeakMap<LoadedModel, Promise<Float32Array | null>>();

/** The geometry signatures of a loaded model (11 floats per element), computed once per model, sliced. Null when aborted. */
export function signaturesOf(loaded: LoadedModel, o: { onProgress?: (done: number, total: number) => void; signal?: { aborted: boolean } } = {}): Promise<Float32Array | null> {
  const hit = sigCache.get(loaded);
  if (hit) return hit;
  const g = loaded.geometry;
  const position = g.geometry.getAttribute('position').array as ArrayLike<number>;
  const index = (g.geometry.getIndex()?.array ?? new Uint32Array(0)) as ArrayLike<number>;
  const ranges = g.ranges;
  const p = computeSignaturesSliced({ position, index, ranges }, o).then((r) => { if (!r) sigCache.delete(loaded); return r; });
  sigCache.set(loaded, p);
  return p;
}

export interface CaptureInput {
  name: string;
  loaded: LoadedModel;
  results?: (globalId: string) => ClassifyResult | null | undefined;
  schemaHash: string;
  reviewFingerprint: string;
  onProgress?: (done: number, total: number) => void;
  signal?: { aborted: boolean };
}

/** Snapshot a loaded model. Null when the signature work was aborted. */
export async function captureSnapshot(i: CaptureInput): Promise<ModelSnapshot | null> {
  const sig = await signaturesOf(i.loaded, { ...(i.onProgress ? { onProgress: i.onProgress } : {}), ...(i.signal ? { signal: i.signal } : {}) });
  if (!sig) return null;
  return snapshotOf({ name: i.name, model: i.loaded.model as SceneModel, sig, ...(i.results ? { results: i.results } : {}), schemaHash: i.schemaHash, reviewFingerprint: i.reviewFingerprint });
}

/** The base shapes of a model that is still loaded in this page (F7): a GhostSource over its merged geometry. */
export function liveGhostSource(loaded: LoadedModel, snap: ModelSnapshot): GhostSource {
  const g = loaded.geometry;
  const position = g.geometry.getAttribute('position').array as ArrayLike<number>;
  const index = (g.geometry.getIndex()?.array ?? new Uint32Array(0)) as ArrayLike<number>;
  const byGid = new Map<string, number>();
  loaded.model.elements.forEach((e, i) => { if (e.globalId) byGid.set(e.globalId, i); });
  const snapIx = new Map<string, number>();
  snap.globalId.forEach((gid, i) => snapIx.set(gid, i));
  return {
    mesh(gid) {
      const e = byGid.get(gid);
      if (e === undefined) return null;
      const vr = g.vertexRanges[e], r = g.ranges[e];
      if (!vr || !r || r.count === 0) return null;
      return meshOfElement(position, index, vr.start, vr.count, r.start, r.count, gid);
    },
    box: (gid) => boxOf(snap, snapIx.get(gid)),
  };
}

/** The ghosts stored with a session (a decoded blob) plus the snapshot's bounds as the fallback. */
export function storedGhostSource(meshes: readonly GhostMesh[], snap: ModelSnapshot | null): GhostSource {
  const by = new Map(meshes.map((m) => [m.gid, m]));
  const ix = new Map<string, number>();
  snap?.globalId.forEach((gid, i) => ix.set(gid, i));
  return { mesh: (gid) => by.get(gid) ?? null, box: (gid) => (snap ? boxOf(snap, ix.get(gid)) : null) };
}

function boxOf(snap: ModelSnapshot, i: number | undefined): readonly number[] | null {
  if (i === undefined) return null;
  const b = snap.bounds.subarray(i * 6, i * 6 + 6);
  if (b.every((v) => v === 0)) return null;
  return Array.from(b);
}

/** Meshes of every element the diff says changed shape or place, was rematched or deleted: what the session stores (4.3). */
export function ghostMeshesFor(src: GhostSource, baseGids: Iterable<string>): GhostMesh[] {
  const out: GhostMesh[] = [];
  for (const gid of baseGids) { const m = src.mesh(gid); if (m && m.index.length) out.push(m); }
  return out;
}

export { boxEdges };
