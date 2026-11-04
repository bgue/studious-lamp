// glb (+ optional model.json sidecar) -> SceneModel + MergedGeometry.

import { Box3, Color, Matrix4, SRGBColorSpace, Vector3 } from 'three';
import type { BufferGeometry, Material, Mesh, Object3D } from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import type { ClassStyles, ElementRecord, Relations, SceneModel, StoreyRecord } from '../types';
import { MergedGeometry } from './merged';
import { sanitizeProps } from './ifcProps';
import type { MeshPart } from './merged';

export { MergedGeometry, EDGE_THRESHOLD_DEG } from './merged';
export type { IndexRange, MeshPart } from './merged';

export interface LoadedModel {
  model: SceneModel;
  geometry: MergedGeometry;
}

/** Subset of the sidecar format that the loader reads; everything is optional/validated. */
interface SidecarJson {
  schema?: string;
  originShift?: [number, number, number];
  storeys?: StoreyRecord[];
  elements?: Array<Partial<ElementRecord> & { id?: number }>;
  relations?: Partial<Relations>;
  /** Class styles baked in by `ifc2glb.py --config` (passed through untouched; see src/styles.ts). */
  styles?: ClassStyles;
  materialAliases?: Record<string, string[]>;
}

const GREY: [number, number, number, number] = [0.7, 0.7, 0.7, 1];

const NAME_GUESSES: Array<[string, string]> = [
  ['slab', 'IfcSlab'],
  ['wall', 'IfcWall'],
  ['beam', 'IfcBeam'],
  ['column', 'IfcColumn'],
  ['duct', 'IfcDuctSegment'],
  ['pipe', 'IfcPipeSegment'],
  ['tray', 'IfcCableCarrierSegment'],
];

export function guessClassFromName(name: string): string {
  const n = name.toLowerCase();
  for (const [key, cls] of NAME_GUESSES) if (n.includes(key)) return cls;
  return 'Unknown';
}

export async function loadModel(glbUrl: string, jsonUrl?: string): Promise<LoadedModel> {
  const glbRes = await fetch(glbUrl);
  if (!glbRes.ok) throw new Error(`Failed to fetch ${glbUrl}: ${glbRes.status}`);
  const glb = await glbRes.arrayBuffer();
  let sidecar: unknown;
  if (jsonUrl) {
    const jr = await fetch(jsonUrl);
    if (!jr.ok) throw new Error(`Failed to fetch ${jsonUrl}: ${jr.status}`);
    sidecar = await jr.json();
  }
  return parseModel(glb, sidecar);
}

/** Same as loadModel but from memory (also used by tests and the procedural demo model). */
export async function parseModel(glb: ArrayBuffer, sidecar?: unknown): Promise<LoadedModel> {
  const loader = new GLTFLoader();
  const gltf = await loader.parseAsync(glb, '');
  const scene = gltf.scene;
  scene.updateMatrixWorld(true);
  const hasMaterials = ((gltf.parser.json as { materials?: unknown[] }).materials?.length ?? 0) > 0;

  const side = (sidecar ?? null) as SidecarJson | null;
  const records = side?.elements ?? null;

  // sidecar element id (as written) -> dense index
  const idToIndex = new Map<number, number>();
  const byGid = new Map<string, number>();
  if (records) {
    records.forEach((r, i) => {
      idToIndex.set(typeof r.id === 'number' ? r.id : i, i);
      if (r.globalId) byGid.set(r.globalId, i);
    });
  }

  // Collect meshes per element key.
  interface Group {
    key: string;
    sidecarIndex: number; // -1 when synthesised
    extrasId: number | null;
    node: Object3D;
    meshes: Mesh[];
  }
  const groups = new Map<string, Group>();
  const order: Group[] = [];

  const nodeName = (o: Object3D): string => {
    const orig = (o.userData as { name?: unknown }).name;
    return typeof orig === 'string' ? orig : o.name;
  };
  const extrasIdOf = (o: Object3D): number | null => {
    const id = (o.userData as { id?: unknown }).id;
    return typeof id === 'number' ? id : null;
  };

  const resolve = (mesh: Object3D): { key: string; node: Object3D; idx: number; extrasId: number | null } => {
    for (let o: Object3D | null = mesh; o && o !== scene; o = o.parent) {
      const eid = extrasIdOf(o);
      if (records) {
        if (eid !== null && idToIndex.has(eid)) return { key: `i${idToIndex.get(eid)}`, node: o, idx: idToIndex.get(eid)!, extrasId: eid };
        const gi = byGid.get(nodeName(o));
        if (gi !== undefined) return { key: `i${gi}`, node: o, idx: gi, extrasId: eid };
      } else if (eid !== null) {
        return { key: `x${eid}`, node: o, idx: -1, extrasId: eid };
      }
    }
    return { key: `u${mesh.uuid}`, node: mesh, idx: -1, extrasId: null };
  };

  scene.traverse((o) => {
    const mesh = o as Mesh;
    if (!mesh.isMesh) return;
    const geom = mesh.geometry as BufferGeometry;
    if (!geom.getAttribute('position')) return;
    const r = resolve(mesh);
    let g = groups.get(r.key);
    if (!g) {
      g = { key: r.key, sidecarIndex: r.idx, extrasId: r.extrasId, node: r.node, meshes: [] };
      groups.set(r.key, g);
      order.push(g);
    }
    g.meshes.push(mesh);
  });

  let elements: ElementRecord[];
  const parts: MeshPart[][] = [];
  let relations: Relations;
  let storeys: StoreyRecord[];
  let originShift: [number, number, number];

  const partsOf = (g: Group): MeshPart[] =>
    g.meshes.map((m) => ({ geometry: m.geometry as BufferGeometry, matrix: m.matrixWorld.clone() as Matrix4 }));

  if (records) {
    elements = records.map(normaliseRecord);
    for (let i = 0; i < elements.length; i++) parts.push([]);
    for (const g of order) {
      if (g.sidecarIndex >= 0) parts[g.sidecarIndex]!.push(...partsOf(g));
      // meshes in the glb that the sidecar does not know are ignored
    }
    storeys = side?.storeys ?? [];
    originShift = side?.originShift ?? [0, 0, 0];
    relations = normaliseRelations(side?.relations);
  } else {
    // Synthesised elements. If every node carries a unique numeric extras.id, honour that order.
    const allIds = order.length > 0 && order.every((g) => g.extrasId !== null);
    const sorted = allIds ? [...order].sort((a, b) => a.extrasId! - b.extrasId!) : order;
    elements = sorted.map((g, i) => {
      const name = nodeName(g.node) || `element-${i}`;
      const extras = g.node.userData as { ifcClass?: unknown };
      const cls = typeof extras.ifcClass === 'string' ? extras.ifcClass : guessClassFromName(name);
      parts.push(partsOf(g));
      return {
        id: i,
        globalId: name,
        ifcClass: cls,
        name,
        storey: null,
        color: materialColour(g.meshes[0]!, hasMaterials),
        bounds: [0, 0, 0, 0, 0, 0],
      };
    });
    storeys = [];
    originShift = [0, 0, 0];
    relations = { voids: [], fills: [], hosts: [], ports: [], systems: [] };
  }

  const geometry = new MergedGeometry(parts);

  reconcileBounds(elements, geometry, !!records);

  const byGlobalId = new Map<string, number>();
  for (const el of elements) byGlobalId.set(el.globalId, el.id);

  const model: SceneModel = {
    schema: 'xray-model/1',
    units: 'm',
    originShift,
    storeys,
    elements,
    relations,
    byGlobalId,
  };
  if (side?.styles) model.styles = side.styles;
  if (side?.materialAliases) model.materialAliases = side.materialAliases;
  return { model, geometry };
}

/** One sidecar element record -> the SceneModel element (defaults, colour and props normalised). `i` is its dense index. */
export function normaliseRecord(r: Partial<ElementRecord> & { id?: number }, i: number): ElementRecord {
  return {
    id: i,
    globalId: r.globalId ?? `element-${i}`,
    expressId: r.expressId,
    ifcClass: r.ifcClass ?? 'Unknown',
    name: r.name,
    storey: r.storey ?? null,
    material: r.material,
    color: normaliseColor(r.color),
    bounds: (r.bounds ?? [0, 0, 0, 0, 0, 0]) as ElementRecord['bounds'],
    file: r.file,
    props: sanitizeProps(r.props),
  } as ElementRecord;
}

export function normaliseRelations(rel: Partial<Relations> | undefined): Relations {
  const r = rel ?? {};
  return {
    voids: r.voids ?? [],
    fills: r.fills ?? [],
    hosts: r.hosts ?? [],
    ports: r.ports ?? [],
    systems: r.systems ?? [],
    ...(Array.isArray(r.openings) && r.openings.length > 0 ? { openings: r.openings } : {}),
  };
}

/** Bounds: sidecar bounds stay as authored when present and sane; otherwise take them from geometry (and the other way for empty meshes). */
export function reconcileBounds(elements: ElementRecord[], geometry: MergedGeometry, hasRecords: boolean): void {
  elements.forEach((el, i) => {
    const gb = geometry.bounds[i]!;
    if (!gb.isEmpty()) {
      if (!hasRecords || !validBounds(el.bounds)) el.bounds = boxToArray(gb);
    } else if (validBounds(el.bounds)) {
      geometry.bounds[i]!.set(
        new Vector3(el.bounds[0], el.bounds[1], el.bounds[2]),
        new Vector3(el.bounds[3], el.bounds[4], el.bounds[5]),
      );
    }
  });
}

/** A LoadedModel from a sidecar head (everything but the elements), the normalised elements and the merged geometry. */
export function assembleLoaded(
  head: { originShift?: [number, number, number]; storeys?: StoreyRecord[]; relations?: Partial<Relations> },
  elements: ElementRecord[], geometry: MergedGeometry,
): LoadedModel {
  reconcileBounds(elements, geometry, true);
  const byGlobalId = new Map<string, number>();
  for (const el of elements) byGlobalId.set(el.globalId, el.id);
  const model: SceneModel = {
    schema: 'xray-model/1',
    units: 'm',
    originShift: head.originShift ?? [0, 0, 0],
    storeys: head.storeys ?? [],
    elements,
    relations: normaliseRelations(head.relations),
    byGlobalId,
  };
  return { model, geometry };
}

function validBounds(b: ElementRecord['bounds']): boolean {
  return b.length === 6 && b.every(Number.isFinite) && (b[3] >= b[0] && b[4] >= b[1] && b[5] >= b[2]) && b.some((v) => v !== 0);
}

function boxToArray(b: Box3): ElementRecord['bounds'] {
  return [b.min.x, b.min.y, b.min.z, b.max.x, b.max.y, b.max.z];
}

function normaliseColor(c: unknown): [number, number, number, number] {
  if (Array.isArray(c) && c.length >= 3 && c.every((x) => typeof x === 'number')) {
    return [c[0] as number, c[1] as number, c[2] as number, (c[3] as number | undefined) ?? 1];
  }
  return [...GREY];
}

/** Colour from the glTF material (converted to sRGB, the space RenderState colours use), else grey. */
function materialColour(mesh: Mesh, hasMaterials: boolean): [number, number, number, number] {
  if (!hasMaterials) return [...GREY];
  const mat = (Array.isArray(mesh.material) ? mesh.material[0] : mesh.material) as (Material & { color?: Color }) | undefined;
  if (!mat || !mat.color) return [...GREY];
  const out = { r: 0, g: 0, b: 0 };
  mat.color.getRGB(out, SRGBColorSpace);
  return [out.r, out.g, out.b, 1];
}
