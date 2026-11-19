// The ghost overlay of the revision walk (design 3.6 and 4.3): the base shape of a changed, rematched or deleted element drawn as a
// translucent tinted mesh over the revised model, a green frame around a new element, an amber frame around the head element of a
// change. Two parts: pure helpers (extract one element's triangles, quantise them for storage, convert frames) that node tests cover,
// and `GhostOverlay`, which owns the three.js objects.
//
// Frames. A snapshot is in IFC axes relative to its origin shift. The viewer's axes are (x, z, -y) of the IFC frame relative to the
// shift of the model on screen (the head). A base point goes to the head's viewer frame by adding the two shifts and the offset of the
// diff (`diff.offset`, head minus base: the global move of a model that was re-based).

import { BufferAttribute, BufferGeometry, Group, LineBasicMaterial, LineSegments, Mesh, MeshBasicMaterial, DoubleSide } from 'three';
import type { ViewerApp } from '../app';
import type { Vec3 } from './types';

export type GhostMode = 'both' | 'head' | 'base';
export const GHOST_MODES: readonly GhostMode[] = ['both', 'head', 'base'];
export const nextGhostMode = (m: GhostMode): GhostMode => GHOST_MODES[(GHOST_MODES.indexOf(m) + 1) % GHOST_MODES.length]!;
export const GHOST_MODE_LABEL: Record<GhostMode, string> = { both: 'Ghost: both', head: 'Ghost: head only', base: 'Ghost: base only' };

/** One element's triangles in IFC axes relative to its model's origin shift. */
export interface GhostMesh {
  gid: string;
  positions: Float32Array;
  index: Uint32Array;
}

/** Cap of the stored ghosts (4.3): the largest elements are dropped first and fall back to boxes. */
export const GHOST_CAP_BYTES = 64 * 1024 * 1024;
/** Quantisation of stored positions: 0.1 mm. */
export const GHOST_QUANT = 10000;

/**
 * The triangles of one element out of a merged geometry (viewer axes, absolute vertex indices): positions turned into IFC axes
 * (x, -z, y), the index made local. `vertexStart/Count` and `indexStart/Count` are the element's ranges.
 */
export function meshOfElement(position: ArrayLike<number>, index: ArrayLike<number>, vertexStart: number, vertexCount: number, indexStart: number, indexCount: number, gid: string): GhostMesh {
  const positions = new Float32Array(vertexCount * 3);
  for (let v = 0; v < vertexCount; v++) {
    const s = (vertexStart + v) * 3;
    positions[v * 3] = position[s]!;
    positions[v * 3 + 1] = -position[s + 2]!;
    positions[v * 3 + 2] = position[s + 1]!;
  }
  const idx = new Uint32Array(indexCount);
  for (let k = 0; k < indexCount; k++) idx[k] = index[indexStart + k]! - vertexStart;
  return { gid, positions, index: idx };
}

const MAGIC = 0x47485354; // "GHST"

/**
 * Pack meshes: JSON header, then per mesh Int32 positions (0.1 mm, relative to the mesh's minimum corner) and Uint32 indices. The
 * largest meshes are left out while the total is over `cap`. Returns the bytes and the gids that did not fit.
 */
export function encodeGhosts(meshes: readonly GhostMesh[], cap = GHOST_CAP_BYTES): { data: Uint8Array; dropped: string[] } {
  const size = (m: GhostMesh): number => m.positions.length * 4 + m.index.length * 4;
  const order = [...meshes].sort((a, b) => size(a) - size(b));
  const kept: GhostMesh[] = [];
  const dropped: string[] = [];
  let total = 0;
  for (const m of order) {
    if (total + size(m) > cap) dropped.push(m.gid);
    else { kept.push(m); total += size(m); }
  }
  const items = kept.map((m) => {
    let x = Infinity, y = Infinity, z = Infinity;
    for (let i = 0; i < m.positions.length; i += 3) { x = Math.min(x, m.positions[i]!); y = Math.min(y, m.positions[i + 1]!); z = Math.min(z, m.positions[i + 2]!); }
    if (!Number.isFinite(x)) { x = 0; y = 0; z = 0; }
    return { gid: m.gid, origin: [x, y, z] as Vec3, vertices: m.positions.length / 3, indices: m.index.length };
  });
  const head = new TextEncoder().encode(JSON.stringify({ v: 1, items }));
  const pad = (4 - ((8 + head.length) % 4)) % 4;
  const out = new Uint8Array(8 + head.length + pad + total);
  const dv = new DataView(out.buffer);
  dv.setUint32(0, MAGIC, true);
  dv.setUint32(4, head.length, true);
  out.set(head, 8);
  let o = 8 + head.length + pad;
  kept.forEach((m, k) => {
    const org = items[k]!.origin;
    for (let i = 0; i < m.positions.length; i++) { dv.setInt32(o, Math.round((m.positions[i]! - org[i % 3]!) * GHOST_QUANT), true); o += 4; }
    for (let i = 0; i < m.index.length; i++) { dv.setUint32(o, m.index[i]!, true); o += 4; }
  });
  return { data: out, dropped };
}

/** Read what `encodeGhosts` wrote. A damaged blob gives an empty list (the walk then draws boxes). */
export function decodeGhosts(buf: ArrayBuffer | Uint8Array): GhostMesh[] {
  try {
    const u = buf instanceof Uint8Array ? buf : new Uint8Array(buf);
    const dv = new DataView(u.buffer, u.byteOffset, u.byteLength);
    if (u.byteLength < 8 || dv.getUint32(0, true) !== MAGIC) return [];
    const hl = dv.getUint32(4, true);
    const head = JSON.parse(new TextDecoder().decode(u.subarray(8, 8 + hl))) as { items: Array<{ gid: string; origin: Vec3; vertices: number; indices: number }> };
    let o = 8 + hl + ((4 - ((8 + hl) % 4)) % 4);
    const out: GhostMesh[] = [];
    for (const it of head.items) {
      const positions = new Float32Array(it.vertices * 3);
      for (let i = 0; i < positions.length; i++) { positions[i] = dv.getInt32(o, true) / GHOST_QUANT + it.origin[i % 3]!; o += 4; }
      const index = new Uint32Array(it.indices);
      for (let i = 0; i < index.length; i++) { index[i] = dv.getUint32(o, true); o += 4; }
      out.push({ gid: it.gid, positions, index });
    }
    return out;
  } catch {
    return [];
  }
}

/** A point in IFC axes relative to the base's shift, in the head's viewer frame. */
export function baseToViewer(p: readonly [number, number, number], baseShift: Vec3, headShift: Vec3, offset: Vec3): Vec3 {
  const hx = p[0] + baseShift[0] + offset[0] - headShift[0];
  const hy = p[1] + baseShift[1] + offset[1] - headShift[1];
  const hz = p[2] + baseShift[2] + offset[2] - headShift[2];
  return [hx, hz, -hy];
}

/** The 12 edges of a box [x0,y0,z0,x1,y1,z1] as line-segment positions. */
export function boxEdges(b: readonly number[]): Float32Array {
  const [x0, y0, z0, x1, y1, z1] = b as [number, number, number, number, number, number];
  const c = [[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0], [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]] as const;
  const e = [[0, 1], [1, 2], [2, 3], [3, 0], [4, 5], [5, 6], [6, 7], [7, 4], [0, 4], [1, 5], [2, 6], [3, 7]] as const;
  const out = new Float32Array(e.length * 6);
  e.forEach(([a, b2], i) => { out.set(c[a]!, i * 6); out.set(c[b2]!, i * 6 + 3); });
  return out;
}

/** Where the base shape of an element comes from. */
export interface GhostSource {
  /** The base's triangles in IFC axes relative to its shift, or null (then the box is drawn). */
  mesh(gid: string): GhostMesh | null;
  /** The base's bounds [x0,y0,z0,x1,y1,z1] in IFC axes relative to its shift. */
  box(gid: string): readonly number[] | null;
}

export interface GhostTarget {
  kind: 'new' | 'deleted' | 'changed' | 'rematched';
  base?: string;
  /** Head bounds in the viewer frame (the head element's frame), when the element exists in the head. */
  headBox?: readonly number[];
}

const RED = 0xff5a5a, GREEN = 0x4fd18b, AMBER = 0xe0b252;

export interface GhostFrames {
  baseShift: Vec3;
  headShift: Vec3;
  offset: Vec3;
}

/** The three.js side. Owns one Group in the scene; `show` rebuilds it for the current targets. */
export class GhostOverlay {
  readonly group = new Group();
  mode: GhostMode = 'both';
  /** What the last `show` drew: for tests and scripts. */
  lastDrawn: { meshes: number; boxes: number; frames: number } = { meshes: 0, boxes: 0, frames: 0 };
  private source: GhostSource | null = null;
  private frames: GhostFrames = { baseShift: [0, 0, 0], headShift: [0, 0, 0], offset: [0, 0, 0] };
  private targets: GhostTarget[] = [];
  private readonly meshCache = new Map<string, BufferGeometry>();
  private attached = false;

  constructor(private readonly app: Pick<ViewerApp, 'renderer'>) {
    this.group.name = 'revision-ghost';
  }

  setSource(source: GhostSource | null, frames: GhostFrames): void {
    this.source = source;
    this.frames = frames;
    this.clearCache();
  }

  /** Draw for these targets with the current mode. */
  show(targets: readonly GhostTarget[], mode: GhostMode = this.mode): void {
    this.targets = [...targets];
    this.mode = mode;
    this.rebuild();
  }

  setMode(mode: GhostMode): void {
    this.mode = mode;
    this.rebuild();
  }

  hide(): void {
    this.targets = [];
    this.clearGroup();
    this.detach();
    this.app.renderer.markDirty();
  }

  dispose(): void {
    this.hide();
    this.clearCache();
  }

  private attach(): void {
    if (this.attached) return;
    this.app.renderer.scene.add(this.group);
    this.attached = true;
  }
  private detach(): void {
    if (!this.attached) return;
    this.app.renderer.scene.remove(this.group);
    this.attached = false;
  }

  private clearGroup(): void {
    for (const c of [...this.group.children]) {
      this.group.remove(c);
      const o = c as Mesh | LineSegments;
      if ('material' in o) (o.material as { dispose(): void }).dispose();
      if (o instanceof LineSegments) o.geometry.dispose(); // a mesh's geometry is cached
    }
  }
  private clearCache(): void {
    for (const g of this.meshCache.values()) g.dispose();
    this.meshCache.clear();
  }

  private geometryOf(gid: string): BufferGeometry | null {
    const hit = this.meshCache.get(gid);
    if (hit) return hit;
    const m = this.source?.mesh(gid);
    if (!m || m.index.length === 0) return null;
    const f = this.frames;
    const pos = new Float32Array(m.positions.length);
    for (let i = 0; i < m.positions.length; i += 3) {
      const v = baseToViewer([m.positions[i]!, m.positions[i + 1]!, m.positions[i + 2]!], f.baseShift, f.headShift, f.offset);
      pos[i] = v[0]; pos[i + 1] = v[1]; pos[i + 2] = v[2];
    }
    const g = new BufferGeometry();
    g.setAttribute('position', new BufferAttribute(pos, 3));
    g.setIndex(new BufferAttribute(m.index, 1));
    if (this.meshCache.size >= 64) { const k = this.meshCache.keys().next().value as string; this.meshCache.get(k)?.dispose(); this.meshCache.delete(k); }
    this.meshCache.set(gid, g);
    return g;
  }

  private rebuild(): void {
    this.clearGroup();
    const drawn = { meshes: 0, boxes: 0, frames: 0 };
    const showBase = this.mode !== 'head';
    const showHead = this.mode !== 'base';
    for (const t of this.targets) {
      if (showBase && t.base && t.kind !== 'new') {
        const g = this.geometryOf(t.base);
        if (g) {
          const mat = new MeshBasicMaterial({ color: RED, transparent: true, opacity: this.mode === 'base' ? 0.8 : 0.35, depthWrite: false, side: DoubleSide, toneMapped: false });
          const m = new Mesh(g, mat);
          m.renderOrder = 40;
          m.frustumCulled = false;
          m.raycast = () => {};
          m.userData['ghost'] = t.base;
          this.group.add(m);
          drawn.meshes++;
        } else {
          const b = this.source?.box(t.base);
          if (b) {
            const f = this.frames;
            const lo = baseToViewer([b[0]!, b[1]!, b[2]!], f.baseShift, f.headShift, f.offset);
            const hi = baseToViewer([b[3]!, b[4]!, b[5]!], f.baseShift, f.headShift, f.offset);
            this.group.add(this.lines(boxEdges([Math.min(lo[0], hi[0]), Math.min(lo[1], hi[1]), Math.min(lo[2], hi[2]), Math.max(lo[0], hi[0]), Math.max(lo[1], hi[1]), Math.max(lo[2], hi[2])]), RED, 'ghost-box'));
            drawn.boxes++;
          }
        }
      }
      if (showHead && t.headBox && t.kind !== 'deleted') {
        this.group.add(this.lines(boxEdges(t.headBox), t.kind === 'new' ? GREEN : AMBER, 'head-frame'));
        drawn.frames++;
      }
    }
    this.lastDrawn = drawn;
    if (this.group.children.length) this.attach(); else this.detach();
    this.app.renderer.markDirty();
  }

  private lines(pos: Float32Array, color: number, name: string): LineSegments {
    const g = new BufferGeometry();
    g.setAttribute('position', new BufferAttribute(pos, 3));
    const l = new LineSegments(g, new LineBasicMaterial({ color, transparent: true, opacity: 0.95, depthTest: false, depthWrite: false, toneMapped: false }));
    l.name = name;
    l.renderOrder = 41;
    l.frustumCulled = false;
    l.raycast = () => {};
    return l;
  }
}
