// The viewer side of re-projection (src/bcf/reproject.ts): the element surfaces come from the per-element BVHs of the model, and
// the SurfaceResolver caches the answer per model load so that drawing does not redo it every frame. Shared by the markup tool and
// the BCF annotations through BcfController.resolveSurface.

import { Ray, Vector3, DoubleSide } from 'three';
import type { BufferGeometry } from 'three';
import type { MeshBVH } from 'three-mesh-bvh';
import type { ViewerApp } from '../app';
import { dirIfcToViewer, dirViewerToIfc, ifcToViewer, viewerToIfc } from '../bcf/model';
import type { Vec3 } from '../bcf/model';
import type { Box6, SurfaceData } from '../bcf/attach';
import { boundsToIfc } from '../bcf/surface';
import { reprojectSurface, targetsChanged } from '../bcf/reproject';
import type { ElementProbe, ProbeHit, ReprojectResult } from '../bcf/reproject';

function faceNormal(sub: BufferGeometry, face: number): Vec3 {
  const pos = sub.getAttribute('position');
  const idx = sub.getIndex();
  const i0 = idx ? idx.getX(face * 3) : face * 3;
  const i1 = idx ? idx.getX(face * 3 + 1) : face * 3 + 1;
  const i2 = idx ? idx.getX(face * 3 + 2) : face * 3 + 2;
  const a = new Vector3().fromBufferAttribute(pos, i0);
  const b = new Vector3().fromBufferAttribute(pos, i1).sub(a);
  const c = new Vector3().fromBufferAttribute(pos, i2).sub(a);
  const n = b.cross(c).normalize();
  return [n.x, n.y, n.z];
}

/** The per-element surfaces of the loaded model as an ElementProbe (IFC frame in and out). */
export function elementProbe(app: ViewerApp): ElementProbe {
  const shift = (): Vec3 => {
    const s = app.loaded?.model.originShift;
    return s ? [s[0], s[1], s[2]] : [0, 0, 0];
  };
  const idOf = (guid: string): number | undefined => app.controller.model.byGlobalId.get(guid);
  const tree = (id: number): { sub: BufferGeometry; bvh: MeshBVH } | null => {
    const sub = app.loaded?.geometry.subGeometry(id);
    const bvh = sub?.boundsTree as MeshBVH | undefined;
    return sub && bvh ? { sub, bvh } : null;
  };
  const toIfc = (v: Vector3): Vec3 => viewerToIfc([v.x, v.y, v.z], shift());
  return {
    bounds(guid): Box6 | null {
      const id = idOf(guid);
      return id === undefined ? null : boundsToIfc(app.controller.model.elements[id]?.bounds, shift());
    },
    cast(guid, origin, dir): ProbeHit | null {
      const id = idOf(guid);
      const t = id === undefined ? null : tree(id);
      if (!t) return null;
      const o = ifcToViewer(origin, shift());
      const d = dirIfcToViewer(dir);
      const hit = t.bvh.raycastFirst(new Ray(new Vector3(o[0], o[1], o[2]), new Vector3(d[0], d[1], d[2])), DoubleSide, 0, Infinity);
      if (!hit || hit.faceIndex == null) return null;
      let n = dirViewerToIfc(faceNormal(t.sub, hit.faceIndex));
      if (n[0] * dir[0] + n[1] * dir[1] + n[2] * dir[2] > 0) n = [-n[0], -n[1], -n[2]];
      return { point: toIfc(hit.point), normal: n, distance: hit.distance };
    },
    nearest(guid, p): ProbeHit | null {
      const id = idOf(guid);
      const t = id === undefined ? null : tree(id);
      if (!t) return null;
      const q = ifcToViewer(p, shift());
      const hit = t.bvh.closestPointToPoint(new Vector3(q[0], q[1], q[2]));
      if (!hit) return null;
      return { point: toIfc(hit.point), normal: dirViewerToIfc(faceNormal(t.sub, hit.faceIndex)), distance: hit.distance };
    },
  };
}

export interface ResolveOptions {
  /** The item was made on an earlier revision of this model: re-project whatever the fingerprint says. */
  revised: boolean;
  /** The authoring camera direction (IFC frame): the cast direction of points without a stored normal. */
  fallbackDir?: Vec3;
}

/**
 * Re-projection of the surface outlines of one model load, cached. `resolve` gives the data to draw: the stored data when its
 * targets are as they were, the points projected onto the current surface when they changed (or the model is a revision), or
 * null when the outline cannot land any more (detached). The cache lives until the model changes; `reset` drops it (an item was
 * moved to another model).
 */
export class SurfaceResolver {
  private loaded: object | null = null;
  private probe: ElementProbe | null = null;
  private plain = new WeakMap<SurfaceData, SurfaceData | null>();
  private revised = new WeakMap<SurfaceData, SurfaceData | null>();
  private readonly results = new WeakMap<SurfaceData, ReprojectResult>();

  constructor(private readonly app: ViewerApp, private readonly makeProbe: (app: ViewerApp) => ElementProbe = elementProbe) {}

  reset(): void {
    this.loaded = null;
  }

  private sync(): ElementProbe | null {
    const loaded = this.app.loaded ?? null;
    if (!loaded) return null;
    if (this.loaded !== loaded) {
      this.loaded = loaded;
      this.probe = this.makeProbe(this.app);
      this.plain = new WeakMap();
      this.revised = new WeakMap();
    }
    return this.probe;
  }

  resolve(s: SurfaceData, o: ResolveOptions): SurfaceData | null {
    const probe = this.sync();
    if (!probe) return s;
    const cache = o.revised ? this.revised : this.plain;
    const have = cache.get(s);
    if (have !== undefined) return have;
    let value: SurfaceData | null = s;
    if (o.revised || targetsChanged(s, probe)) {
      try {
        const r = reprojectSurface(s, probe, o.fallbackDir ? { fallbackDir: o.fallbackDir } : {});
        this.results.set(s, r);
        value = r.state === 'detached' ? null : (r.surface ?? s);
      } catch {
        value = s;
      }
    }
    cache.set(s, value);
    return value;
  }

  /** What the last re-projection of `s` found (absent when it was not re-projected). */
  result(s: SurfaceData): ReprojectResult | undefined {
    return this.results.get(s);
  }
}
