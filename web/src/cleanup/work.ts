// Staged simplification: the tools preview a change (nothing touches the model), the user applies it (the change is
// staged here) and the plan builder turns the staged edits into a CleanupPlan. Reset forgets everything staged.
// Pure: no DOM and no three.js, so it runs in node tests.

import type { ElementRecord } from '../types';
import { cleanMesh, creaseNormals, dropSmallPieces } from './simplify/mesh';
import { decimateMesh } from './simplify/decimate';
import type { DecimateOptions } from './simplify/decimate';
import { findSmallDetails } from './simplify/details';
import type { DetailOptions } from './simplify/details';
import { findHiddenInterior } from './simplify/interior';
import type { InteriorOptions, RayCaster } from './simplify/interior';
import { groupInstances } from './simplify/instances';
import type { InstanceGroup } from './simplify/instances';
import { INSTANCE_NODE_BYTES, MESH_OVERHEAD_BYTES, NODE_BYTES, meshBytes, meshOf, runChunked, sourceMesh, sourceTriangles } from './simplify/types';
import type { ChunkOptions, GeometrySource, MeshData } from './simplify/types';
import type { StagedReplacement } from './plan';

export type SimplifyTool = 'decimate' | 'details' | 'interior' | 'instances' | 'weld';

/** A computed but not yet applied change, with the numbers the panel shows. */
export interface PendingEdit {
  tool: SimplifyTool;
  /** Elements the change touches. */
  ids: number[];
  replacements: Map<number, StagedReplacement>;
  removals: Map<number, string>;
  groups: InstanceGroup[] | null;
  trianglesBefore: number;
  trianglesAfter: number;
  /** Estimated glb bytes of the touched elements before and after. */
  bytesBefore: number;
  bytesAfter: number;
  text: string;
}

export class SimplifyWork {
  /** Removed element id -> reason (rules that hid elements are added by the plugin at plan time). */
  readonly removals = new Map<number, string>();
  readonly replacements = new Map<number, StagedReplacement>();
  groups: InstanceGroup[] = [];

  get isEmpty(): boolean {
    return this.removals.size === 0 && this.replacements.size === 0 && this.groups.length === 0;
  }

  clear(): void {
    this.removals.clear();
    this.replacements.clear();
    this.groups = [];
  }

  /** The mesh the next tool works on: the staged replacement, else the original. */
  mesh(src: GeometrySource, id: number): MeshData | null {
    return this.replacements.get(id)?.mesh ?? sourceMesh(src, id, true);
  }

  triangles(src: GeometrySource, id: number): number {
    const r = this.replacements.get(id);
    return r ? Math.floor(r.mesh.indices.length / 3) : sourceTriangles(src, id);
  }

  commit(p: PendingEdit): void {
    for (const [id, r] of p.replacements) {
      this.replacements.set(id, r);
      // a changed mesh no longer matches its instance group: drop the group (run the duplicate tool again)
      this.groups = this.groups.filter((g) => !g.members.some((m) => m.id === id));
    }
    for (const [id, reason] of p.removals) this.removals.set(id, reason);
    if (p.groups) this.groups = p.groups;
  }
}

export interface ToolContext {
  src: GeometrySource;
  elements: ReadonlyArray<ElementRecord>;
  work: SimplifyWork;
  chunk?: ChunkOptions;
}

const candidates = (c: ToolContext): ElementRecord[] => c.elements.filter((e) => sourceTriangles(c.src, e.id) > 0 && !c.work.removals.has(e.id));
const fmtInt = (n: number): string => Math.round(n).toLocaleString('en-US');
export const fmtBytes = (n: number): string => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : n >= 1024 ? `${(n / 1024).toFixed(0)} kB` : `${Math.round(n)} B`);

function blank(tool: SimplifyTool): PendingEdit {
  return { tool, ids: [], replacements: new Map(), removals: new Map(), groups: null, trianglesBefore: 0, trianglesAfter: 0, bytesBefore: 0, bytesAfter: 0, text: '' };
}

function summary(p: PendingEdit, what: string): string {
  return `${what}: ${fmtInt(p.ids.length)} elements, ${fmtInt(p.trianglesBefore)} to ${fmtInt(p.trianglesAfter)} triangles, ~${fmtBytes(p.bytesBefore)} to ~${fmtBytes(p.bytesAfter)}`;
}

function bytesOf(m: MeshData): number {
  const x = meshOf(m);
  return meshBytes(x.vertexCount, x.indexCount);
}

// ---------------------------------------------------------------- decimation

export interface DecimateToolOptions extends DecimateOptions {
  mode: 'ratio' | 'error';
}

export async function previewDecimation(c: ToolContext, o: DecimateToolOptions): Promise<PendingEdit | null> {
  const p = blank('decimate');
  const opts: DecimateOptions = {
    sharpAngle: o.sharpAngle,
    minTriangles: o.minTriangles,
    ...(o.mode === 'ratio' ? { ratio: o.ratio } : { maxError: o.maxError }),
  };
  const done = await runChunked(candidates(c), (e) => {
    const m = c.work.mesh(c.src, e.id);
    if (!m) return;
    const r = decimateMesh(m, opts);
    if (!r.changed) return;
    p.ids.push(e.id);
    p.replacements.set(e.id, { mesh: r.mesh, ops: [...(c.work.replacements.get(e.id)?.ops ?? []), 'decimate'] });
    p.trianglesBefore += r.trianglesBefore;
    p.trianglesAfter += r.trianglesAfter;
    p.bytesBefore += bytesOf(m);
    p.bytesAfter += bytesOf(r.mesh);
  }, c.chunk);
  if (!done) return null;
  p.text = summary(p, 'Decimation');
  return p;
}

// ---------------------------------------------------------------- weld and clean

export interface CleanToolOptions {
  weldTolerance: number;
  dropDegenerate: boolean;
  dropDuplicateFaces: boolean;
}

export async function previewClean(c: ToolContext, o: CleanToolOptions): Promise<PendingEdit | null> {
  const p = blank('weld');
  let degenerate = 0, dup = 0, welded = 0;
  const done = await runChunked(candidates(c), (e) => {
    const m = c.work.mesh(c.src, e.id);
    if (!m) return;
    const r = cleanMesh(m, { weldTolerance: o.weldTolerance, dropDegenerate: o.dropDegenerate, dropDuplicateFaces: o.dropDuplicateFaces });
    const out = creaseNormals(r.mesh);
    const before = bytesOf(m), after = bytesOf(out);
    const fewerTris = r.stats.trianglesAfter < r.stats.trianglesBefore;
    // keep an element only when the clean-up helps (fewer triangles or a smaller mesh), so a tidy mesh is left alone
    if (!fewerTris && after >= before) return;
    degenerate += r.stats.degenerate;
    dup += r.stats.duplicateFaces;
    welded += r.stats.welded;
    p.ids.push(e.id);
    p.replacements.set(e.id, { mesh: out, ops: [...(c.work.replacements.get(e.id)?.ops ?? []), 'weld'] });
    p.trianglesBefore += r.stats.trianglesBefore;
    p.trianglesAfter += r.stats.trianglesAfter;
    p.bytesBefore += before;
    p.bytesAfter += after;
  }, c.chunk);
  if (!done) return null;
  p.text = `${summary(p, 'Weld and clean')}; ${fmtInt(welded)} vertices welded, ${fmtInt(degenerate)} degenerate and ${fmtInt(dup)} duplicate triangles`;
  return p;
}

// ---------------------------------------------------------------- small details

export async function previewSmallDetails(c: ToolContext, o: DetailOptions): Promise<PendingEdit | null> {
  const p = blank('details');
  const cands = candidates(c);
  const items = cands.map((e) => ({ id: e.id, ifcClass: e.ifcClass, bounds: e.bounds, triangles: c.work.triangles(c.src, e.id) }));
  const small = new Set(findSmallDetails(items, o));
  for (const id of small) {
    p.ids.push(id);
    p.removals.set(id, 'small detail');
    const m = c.work.mesh(c.src, id);
    p.trianglesBefore += c.work.triangles(c.src, id);
    if (m) p.bytesBefore += bytesOf(m) + NODE_BYTES + MESH_OVERHEAD_BYTES;
  }
  let pieces = 0;
  if (o.subMeshes && o.maxSize > 0) {
    const rest = cands.filter((e) => !small.has(e.id) && (o.classes.length === 0 || o.classes.includes(e.ifcClass)));
    const done = await runChunked(rest, (e) => {
      const m = c.work.mesh(c.src, e.id);
      if (!m) return;
      const w = cleanMesh(m, { dropDuplicateFaces: false }).mesh;
      const r = dropSmallPieces(w, o.maxSize);
      if (!r) return;
      const out = creaseNormals(r.mesh);
      pieces += r.removedPieces;
      p.ids.push(e.id);
      p.replacements.set(e.id, { mesh: out, ops: [...(c.work.replacements.get(e.id)?.ops ?? []), 'small pieces'] });
      p.trianglesBefore += Math.floor(m.indices.length / 3);
      p.trianglesAfter += Math.floor(out.indices.length / 3);
      p.bytesBefore += bytesOf(m);
      p.bytesAfter += bytesOf(out);
    }, c.chunk);
    if (!done) return null;
  }
  p.text = `${summary(p, 'Small details')}; ${small.size} elements removed${o.subMeshes ? `, ${pieces} loose pieces cut` : ''}`;
  return p;
}

// ---------------------------------------------------------------- hidden interior

export async function previewInterior(c: ToolContext, cast: RayCaster, o: Partial<InteriorOptions>): Promise<PendingEdit | null> {
  const p = blank('interior');
  const items = candidates(c).map((e) => ({ id: e.id, ifcClass: e.ifcClass, mesh: () => sourceMesh(c.src, e.id, false) }));
  const hidden = await findHiddenInterior(items, cast, o, c.chunk);
  if (!hidden) return null;
  for (const id of hidden) {
    p.ids.push(id);
    p.removals.set(id, 'hidden interior');
    p.trianglesBefore += c.work.triangles(c.src, id);
    const m = c.work.mesh(c.src, id);
    if (m) p.bytesBefore += bytesOf(m) + NODE_BYTES + MESH_OVERHEAD_BYTES;
  }
  p.text = summary(p, 'Hidden interior');
  return p;
}

// ---------------------------------------------------------------- duplicates

export async function previewInstances(c: ToolContext): Promise<PendingEdit | null> {
  const p = blank('instances');
  const colourKey = new Map<number, string>(c.elements.map((e) => [e.id, e.color.join(',')]));
  const items: Array<{ id: number; mesh: MeshData; key: string }> = [];
  const done = await runChunked(candidates(c), (e) => {
    const m = c.work.mesh(c.src, e.id);
    if (m && m.indices.length >= 3) items.push({ id: e.id, mesh: m, key: colourKey.get(e.id) ?? '' });
  }, c.chunk);
  if (!done) return null;
  const groups = groupInstances(items);
  p.groups = groups;
  const byId = new Map(items.map((i) => [i.id, i.mesh]));
  let repeats = 0;
  for (const g of groups) {
    const master = byId.get(g.master)!;
    const tris = Math.floor(master.indices.length / 3);
    for (const m of g.members) {
      p.ids.push(m.id);
      if (m.id === g.master) continue;
      repeats++;
      p.trianglesBefore += tris;
      p.bytesBefore += bytesOf(master) + NODE_BYTES + MESH_OVERHEAD_BYTES;
      p.bytesAfter += INSTANCE_NODE_BYTES;
    }
  }
  // triangles drawn stay the same; the stored ones drop to the masters
  p.trianglesAfter = 0;
  p.text = `Duplicates: ${groups.length} groups, ${fmtInt(repeats)} repeated elements become instances; stored triangles ${fmtInt(p.trianglesBefore)} to 0 for the repeats, ~${fmtBytes(p.bytesBefore)} to ~${fmtBytes(p.bytesAfter)}`;
  return p;
}

