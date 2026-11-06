// USDZ export of what the viewer shows, for AR Quick Look on iPhone and iPad (Safari has no WebXR AR). Every visible element
// keeps its current colour and its current x-ray alpha, baked into the material opacity, so focus elements are solid and
// ghosted context is see-through. Elements with the same colour and alpha (quantised) share one mesh and one material, which
// keeps the file small. The model is moved so the centre of its footprint is at the origin and its lowest point at height 0:
// Quick Look puts the origin on the surface the user taps. There is no site registration in Quick Look.
//
// three's USDZExporter (examples/jsm, with fflate) is loaded on demand, so it is not part of the main bundle chunk.

import { BufferAttribute, BufferGeometry, Color, Group, Mesh, MeshStandardMaterial } from 'three';
import { FLAG_HIDDEN } from '../types';
import type { RenderState } from '../types';

export interface UsdzSource {
  positions: ArrayLike<number>;
  normals: ArrayLike<number> | null;
  index: ArrayLike<number>;
  /** Per element: index range (3 per triangle) and vertex range into the merged buffers. */
  ranges: ReadonlyArray<{ start: number; count: number }>;
  vertexRanges: ReadonlyArray<{ start: number; count: number }>;
  state: RenderState;
}

export interface UsdzOptions {
  /** Alpha steps (10: 0.1, 0.2, ... 1). */
  alphaSteps?: number;
  /** Colour levels per channel. */
  colourLevels?: number;
  /** Elements below this alpha are left out (invisible). */
  minAlpha?: number;
  /** Move the footprint centre to the origin and the lowest point to 0. */
  centre?: boolean;
}

export interface UsdzBucket {
  colour: [number, number, number];
  alpha: number;
  elements: number[];
  vertices: number;
  triangles: number;
}

/** Group the visible elements by quantised colour and alpha (pure). */
export function bucketElements(src: Pick<UsdzSource, 'ranges' | 'state'>, opt: UsdzOptions = {}): UsdzBucket[] {
  const steps = opt.alphaSteps ?? 10;
  const levels = opt.colourLevels ?? 16;
  const minAlpha = opt.minAlpha ?? 0.02;
  const { alpha, color, flags } = src.state;
  const map = new Map<string, UsdzBucket>();
  const q = (v: number): number => Math.round(Math.min(1, Math.max(0, v)) * (levels - 1)) / (levels - 1);
  for (let id = 0; id < src.ranges.length; id++) {
    const r = src.ranges[id]!;
    if (r.count === 0) continue;
    const a = alpha[id] ?? 1;
    if ((flags[id]! & FLAG_HIDDEN) !== 0 || a < minAlpha) continue;
    const qa = Math.max(1 / steps, Math.round(Math.min(1, a) * steps) / steps);
    const c: [number, number, number] = [q(color[id * 3]!), q(color[id * 3 + 1]!), q(color[id * 3 + 2]!)];
    const key = `${c.join(',')}|${qa}`;
    let b = map.get(key);
    if (!b) map.set(key, (b = { colour: c, alpha: qa, elements: [], vertices: 0, triangles: 0 }));
    b.elements.push(id);
    b.triangles += r.count / 3;
  }
  // solid first, then by colour: a stable order for the file
  return [...map.values()].sort((x, y) => y.alpha - x.alpha || x.colour.join().localeCompare(y.colour.join()));
}

/** Footprint centre and lowest point of the visible buckets. */
function extents(src: UsdzSource, buckets: UsdzBucket[]): { cx: number; cz: number; minY: number } {
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, z0 = Infinity, z1 = -Infinity;
  const p = src.positions;
  for (const b of buckets)
    for (const id of b.elements) {
      const vr = src.vertexRanges[id]!;
      for (let v = vr.start; v < vr.start + vr.count; v++) {
        const x = p[v * 3]!, y = p[v * 3 + 1]!, z = p[v * 3 + 2]!;
        if (x < x0) x0 = x;
        if (x > x1) x1 = x;
        if (y < y0) y0 = y;
        if (z < z0) z0 = z;
        if (z > z1) z1 = z;
      }
    }
  return Number.isFinite(x0) ? { cx: (x0 + x1) / 2, cz: (z0 + z1) / 2, minY: y0 } : { cx: 0, cz: 0, minY: 0 };
}

export interface UsdzScene {
  group: Group;
  buckets: UsdzBucket[];
  elements: number;
  triangles: number;
  offset: [number, number, number];
}

/** A three.js group with one mesh per bucket (MeshStandardMaterial, opacity = the x-ray alpha). */
export function buildUsdzScene(src: UsdzSource, opt: UsdzOptions = {}): UsdzScene {
  const buckets = bucketElements(src, opt);
  const e = opt.centre === false ? { cx: 0, cz: 0, minY: 0 } : extents(src, buckets);
  const offset: [number, number, number] = [-e.cx, -e.minY, -e.cz];
  const group = new Group();
  group.name = 'xray-model';
  let elements = 0;
  let triangles = 0;
  buckets.forEach((b, bi) => {
    let nv = 0;
    let ni = 0;
    for (const id of b.elements) {
      nv += src.vertexRanges[id]!.count;
      ni += src.ranges[id]!.count;
    }
    const pos = new Float32Array(nv * 3);
    const nor = new Float32Array(nv * 3);
    const idx = new Uint32Array(ni);
    let vo = 0;
    let io = 0;
    for (const id of b.elements) {
      const vr = src.vertexRanges[id]!;
      const r = src.ranges[id]!;
      for (let k = 0; k < vr.count; k++) {
        const s = (vr.start + k) * 3;
        const d = (vo + k) * 3;
        pos[d] = src.positions[s]! + offset[0];
        pos[d + 1] = src.positions[s + 1]! + offset[1];
        pos[d + 2] = src.positions[s + 2]! + offset[2];
        if (src.normals) {
          nor[d] = src.normals[s]!;
          nor[d + 1] = src.normals[s + 1]!;
          nor[d + 2] = src.normals[s + 2]!;
        }
      }
      for (let k = 0; k < r.count; k++) idx[io + k] = src.index[r.start + k]! - vr.start + vo;
      vo += vr.count;
      io += r.count;
    }
    b.vertices = nv;
    const g = new BufferGeometry();
    g.setAttribute('position', new BufferAttribute(pos, 3));
    g.setAttribute('normal', new BufferAttribute(nor, 3));
    g.setIndex(new BufferAttribute(idx, 1));
    if (!src.normals) g.computeVertexNormals();
    const mat = new MeshStandardMaterial({
      color: new Color(b.colour[0], b.colour[1], b.colour[2]),
      roughness: 0.8,
      metalness: 0,
      transparent: b.alpha < 1,
      opacity: b.alpha,
    });
    mat.name = `xray_${b.alpha < 1 ? 'ghost' : 'solid'}_${bi}`;
    const mesh = new Mesh(g, mat);
    mesh.name = `bucket_${bi}`;
    group.add(mesh);
    elements += b.elements.length;
    triangles += ni / 3;
  });
  return { group, buckets, elements, triangles, offset };
}

/** Export a group to USDZ bytes (three's USDZExporter, loaded on demand; plane anchoring for Quick Look). */
export async function exportUsdz(group: Group): Promise<Uint8Array> {
  const { USDZExporter } = await import('three/examples/jsm/exporters/USDZExporter.js');
  const ex = new USDZExporter();
  return ex.parseAsync(group, {
    quickLookCompatible: true,
    includeAnchoringProperties: true,
    ar: { anchoring: { type: 'plane' }, planeAnchoring: { alignment: 'horizontal' } },
  });
}

/** Free the geometries and materials of a built scene. */
export function disposeUsdzScene(s: UsdzScene): void {
  s.group.traverse((o) => {
    const m = o as Mesh;
    m.geometry?.dispose();
    (m.material as MeshStandardMaterial | undefined)?.dispose?.();
  });
}

/** True where the browser opens AR Quick Look from <a rel="ar"> (Safari on iPhone and iPad, and on visionOS). */
export function quickLookSupported(doc: Document | undefined = typeof document === 'undefined' ? undefined : document): boolean {
  try {
    const a = doc?.createElement('a');
    return !!a?.relList?.supports?.('ar');
  } catch {
    return false;
  }
}

/**
 * Open the bytes in AR Quick Look: a link with rel="ar" and an <img> as its first child (Safari's rule). Where Quick Look is
 * missing the same click downloads the file (the download attribute), so the page is never navigated away.
 */
export function openUsdz(bytes: Uint8Array, name = 'xray-model.usdz', doc: Document = document): HTMLAnchorElement {
  const blob = new Blob([bytes as unknown as BlobPart], { type: 'model/vnd.usdz+zip' });
  const url = URL.createObjectURL(blob);
  const a = doc.createElement('a');
  a.rel = 'ar';
  a.href = url;
  a.download = name;
  a.style.display = 'none';
  a.appendChild(doc.createElement('img'));
  doc.body.appendChild(a);
  a.click();
  setTimeout(() => {
    a.remove();
    URL.revokeObjectURL(url);
  }, 60000);
  return a;
}
