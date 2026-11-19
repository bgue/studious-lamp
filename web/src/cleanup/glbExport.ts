// Write the cleaned model as a .glb with three's GLTFExporter (loaded on demand, so it stays out of the main chunk).
//
// One node per element, named by GlobalId, with extras { id, ifcClass, ifcName?, props? } so the viewer's glb loader gets
// selection and hover properties back (see model/loader.ts). Removed elements are left out, replaced elements get their
// replacement mesh, and the elements of a merged group share one glTF mesh (instancing): the master's mesh is stored in a
// local frame and every member node carries the matrix that places it.

import { BufferAttribute, BufferGeometry, Color, Matrix4, Mesh, MeshStandardMaterial, Scene, SRGBColorSpace } from 'three';
import type { ElementRecord } from '../types';
import type { CleanupPlan } from './plan';
import { originalMesh } from './plan';
import type { GeometrySource, MeshData } from './simplify/types';

export interface GlbExportOptions {
  /** Leave the element name and properties out of the extras (class and id stay). */
  stripProps: boolean;
}

export type ExportElement = Pick<ElementRecord, 'id' | 'globalId' | 'ifcClass' | 'name' | 'color' | 'props'>;

function toGeometry(m: MeshData, centre?: [number, number, number]): BufferGeometry {
  const g = new BufferGeometry();
  let pos = m.positions;
  if (centre) {
    pos = new Float32Array(m.positions.length);
    for (let i = 0; i < pos.length; i += 3) {
      pos[i] = m.positions[i]! - centre[0];
      pos[i + 1] = m.positions[i + 1]! - centre[1];
      pos[i + 2] = m.positions[i + 2]! - centre[2];
    }
  }
  g.setAttribute('position', new BufferAttribute(pos, 3));
  if (m.normals) g.setAttribute('normal', new BufferAttribute(m.normals, 3));
  const nv = pos.length / 3;
  g.setIndex(new BufferAttribute(nv < 65536 ? Uint16Array.from(m.indices) : m.indices, 1));
  return g;
}

function centroidOf(p: ArrayLike<number>): [number, number, number] {
  let x = 0, y = 0, z = 0;
  const n = Math.floor(p.length / 3);
  for (let i = 0; i < n; i++) {
    x += p[i * 3]!;
    y += p[i * 3 + 1]!;
    z += p[i * 3 + 2]!;
  }
  return n > 0 ? [x / n, y / n, z / n] : [0, 0, 0];
}

/** The three.js scene that the exporter writes: one Mesh per element, instances share a geometry object. */
export function buildExportScene(elements: readonly ExportElement[], source: GeometrySource, plan: CleanupPlan, opts: GlbExportOptions): Scene {
  const scene = new Scene();
  scene.name = 'xray-cleaned';
  const removed = new Set(plan.removedGlobalIds);
  const repl = new Map(plan.replacements.map((r) => [r.id, r.mesh]));
  const byId = new Map(elements.map((e) => [e.id, e]));
  const memberMatrix = new Map<number, { master: number; matrix: number[] }>();
  for (const g of plan.mergedGroups) for (const m of g.members) memberMatrix.set(m.id, { master: g.masterId, matrix: m.matrix });

  const materials = new Map<string, MeshStandardMaterial>();
  const materialOf = (c: ExportElement['color']): MeshStandardMaterial => {
    const key = c.join(',');
    let m = materials.get(key);
    if (!m) {
      m = new MeshStandardMaterial({ color: new Color().setRGB(c[0], c[1], c[2], SRGBColorSpace), roughness: 0.85, metalness: 0 });
      if (c[3] < 1) {
        m.transparent = true;
        m.opacity = c[3];
      }
      materials.set(key, m);
    }
    return m;
  };
  const meshOfElement = (id: number): MeshData | null => repl.get(id) ?? originalMesh(source, id);
  const sharedGeometry = new Map<number, { geometry: BufferGeometry; centre: [number, number, number] }>();
  const masterGeometry = (id: number): { geometry: BufferGeometry; centre: [number, number, number] } | null => {
    let s = sharedGeometry.get(id);
    if (!s) {
      const m = meshOfElement(id);
      if (!m) return null;
      const centre = centroidOf(m.positions);
      s = { geometry: toGeometry(m, centre), centre };
      sharedGeometry.set(id, s);
    }
    return s;
  };

  const tmp = new Matrix4();
  for (const e of elements) {
    if (removed.has(e.globalId)) continue;
    let mesh: Mesh | null = null;
    const inst = memberMatrix.get(e.id);
    if (inst) {
      const s = masterGeometry(inst.master);
      if (s) {
        mesh = new Mesh(s.geometry, materialOf(e.color));
        // world = M * (local + centre)
        mesh.matrix.fromArray(inst.matrix).multiply(tmp.makeTranslation(s.centre[0], s.centre[1], s.centre[2]));
      }
    } else {
      const m = meshOfElement(e.id);
      if (m && m.indices.length >= 3) mesh = new Mesh(toGeometry(m), materialOf(e.color));
    }
    if (!mesh) continue;
    mesh.name = e.globalId;
    mesh.matrixAutoUpdate = false;
    const extras: Record<string, unknown> = { id: e.id, ifcClass: e.ifcClass };
    if (!opts.stripProps) {
      if (e.name) extras['ifcName'] = e.name;
      if (e.props && Object.keys(e.props).length > 0) extras['props'] = e.props;
    }
    mesh.userData = extras;
    scene.add(mesh);
  }
  return scene;
}

/** The glb bytes. Throws when the exporter fails. */
export async function exportCleanedGlb(elements: readonly ExportElement[], source: GeometrySource, plan: CleanupPlan, opts: GlbExportOptions): Promise<ArrayBuffer> {
  const { GLTFExporter } = await import('three/examples/jsm/exporters/GLTFExporter.js');
  const scene = buildExportScene(elements, source, plan, opts);
  const exporter = new GLTFExporter();
  const out = await exporter.parseAsync(scene, { binary: true, onlyVisible: false });
  scene.traverse((o) => {
    const m = o as Mesh;
    if (m.isMesh) m.geometry.dispose();
  });
  return out as ArrayBuffer;
}
