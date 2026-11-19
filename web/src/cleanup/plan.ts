// The result of cleanup in a form other writers can consume: which elements are gone, which have a replacement mesh,
// which repeat one master (instances) and the numbers. `buildCleanupPlan` is a pure function of the staged edits and the
// model buffers. The glb writer (cleanup/glbExport.ts) consumes it today; an IFC writer can consume the same plan later:
// removed GlobalIds become deletions, replacements become new representations, merged groups become mapped items.

import type { ElementRecord } from '../types';
import { creaseNormals } from './simplify/mesh';
import { pruneGroup } from './simplify/instances';
import type { InstanceGroup } from './simplify/instances';
import { INSTANCE_NODE_BYTES, MESH_OVERHEAD_BYTES, NODE_BYTES, meshBytes, meshOf, sourceMesh } from './simplify/types';
import type { GeometrySource, MeshData } from './simplify/types';

export interface ElementReplacement {
  globalId: string;
  /** Element index in the model the plan was made for. */
  id: number;
  /** Replacement mesh in model (world) coordinates, with normals. */
  mesh: Required<MeshData>;
  trianglesBefore: number;
  trianglesAfter: number;
  /** What was done, in order: 'decimate', 'weld', 'small pieces'. */
  ops: string[];
}

export interface MergedGroupMember {
  globalId: string;
  id: number;
  /** Column-major 4x4: takes the master's world-space mesh to this member's. Identity for the master. */
  matrix: number[];
}

export interface MergedGroup {
  masterGlobalId: string;
  masterId: number;
  /** The master first, then the repeats. */
  members: MergedGroupMember[];
  /** Triangles that are stored once instead of once per member. */
  trianglesSaved: number;
}

export interface PlanStats {
  elementsBefore: number;
  elementsAfter: number;
  removed: number;
  removedByReason: Record<string, number>;
  /** Elements with a replacement mesh. */
  simplified: number;
  /** Groups of repeated geometry, and the elements that became instances (members beyond each master). */
  instanceGroups: number;
  instancedElements: number;
  /** Triangles drawn: every remaining element counts, instances too. */
  trianglesBefore: number;
  trianglesAfter: number;
  /** Triangles stored in the file: each shared mesh counts once. */
  trianglesStoredBefore: number;
  trianglesStoredAfter: number;
  /** Estimated glb size in bytes (see simplify/types.ts for the formula). */
  bytesBefore: number;
  bytesAfter: number;
}

export interface CleanupPlan {
  schema: 'xray-cleanup-plan/1';
  removedGlobalIds: string[];
  /** Why each removed GlobalId went (rule names such as 'floating', 'small detail', 'hidden interior'). */
  removalReasons: Record<string, string[]>;
  replacements: ElementReplacement[];
  mergedGroups: MergedGroup[];
  stats: PlanStats;
}

export interface StagedReplacement {
  mesh: MeshData;
  ops: string[];
}

export interface PlanInput {
  elements: ReadonlyArray<Pick<ElementRecord, 'id' | 'globalId' | 'ifcClass' | 'name' | 'props'>>;
  source: GeometrySource;
  /** Removed element id -> reasons. Elements that a rule hid in the viewer belong here too. */
  removed: ReadonlyMap<number, readonly string[]>;
  replacements: ReadonlyMap<number, StagedReplacement>;
  groups: readonly InstanceGroup[];
  /** Props and name are not exported: leave them out of the size estimate. */
  stripProps?: boolean;
}

/** Bytes of the extras JSON of one node. */
export function extrasBytes(e: Pick<ElementRecord, 'id' | 'globalId' | 'ifcClass' | 'name' | 'props'>, stripProps: boolean): number {
  const extras: Record<string, unknown> = { id: e.id, ifcClass: e.ifcClass };
  if (!stripProps) {
    if (e.name) extras['ifcName'] = e.name;
    if (e.props && Object.keys(e.props).length > 0) extras['props'] = e.props;
  }
  return e.globalId.length + JSON.stringify(extras).length + 16;
}

export function withNormals(m: MeshData): Required<MeshData> {
  return m.normals ? (m as Required<MeshData>) : (creaseNormals(m) as Required<MeshData>);
}

export function buildCleanupPlan(input: PlanInput): CleanupPlan {
  const { source, removed } = input;
  const strip = input.stripProps === true;
  const els = input.elements;
  const hasGeo = (id: number): boolean => (source.ranges[id]?.count ?? 0) >= 3;
  const srcTris = (id: number): number => Math.floor((source.ranges[id]?.count ?? 0) / 3);
  const srcBytes = (id: number): number => meshBytes(source.vertexRanges[id]?.count ?? 0, source.ranges[id]?.count ?? 0);

  const removedGlobalIds: string[] = [];
  const removalReasons: Record<string, string[]> = {};
  const byReason: Record<string, number> = {};
  const replacements: ElementReplacement[] = [];
  let simplified = 0;

  let elementsBefore = 0, trianglesBefore = 0, trianglesStoredBefore = 0, bytesBefore = 0;
  for (const e of els) {
    if (!hasGeo(e.id)) continue;
    elementsBefore++;
    trianglesBefore += srcTris(e.id);
    trianglesStoredBefore += srcTris(e.id);
    bytesBefore += srcBytes(e.id) + NODE_BYTES + MESH_OVERHEAD_BYTES + extrasBytes(e, strip);
  }

  // groups without removed members
  const groups: InstanceGroup[] = [];
  for (const g of input.groups) {
    const p = pruneGroup(g, (id) => removed.has(id) || !hasGeo(id));
    if (p) groups.push(p);
  }
  const memberOf = new Map<number, InstanceGroup>();
  for (const g of groups) for (const m of g.members) memberOf.set(m.id, g);

  let elementsAfter = 0, trianglesAfter = 0, trianglesStoredAfter = 0, bytesAfter = 0, instancedElements = 0;
  const effTris = (id: number): number => {
    const r = input.replacements.get(id);
    return r ? Math.floor(r.mesh.indices.length / 3) : srcTris(id);
  };
  const effBytes = (id: number): number => {
    const r = input.replacements.get(id);
    if (!r) return srcBytes(id);
    const m = meshOf(r.mesh);
    return meshBytes(m.vertexCount, m.indexCount);
  };
  for (const e of els) {
    if (!hasGeo(e.id)) continue;
    const reasons = removed.get(e.id);
    if (reasons) {
      removedGlobalIds.push(e.globalId);
      removalReasons[e.globalId] = [...reasons];
      for (const r of reasons) byReason[r] = (byReason[r] ?? 0) + 1;
      continue;
    }
    elementsAfter++;
    const g = memberOf.get(e.id);
    const master = g ? g.master : e.id;
    trianglesAfter += effTris(master);
    const ex = extrasBytes(e, strip);
    if (g && g.master !== e.id) {
      instancedElements++;
      bytesAfter += INSTANCE_NODE_BYTES + ex;
    } else {
      trianglesStoredAfter += effTris(e.id);
      bytesAfter += effBytes(e.id) + NODE_BYTES + MESH_OVERHEAD_BYTES + ex;
    }
    const r = input.replacements.get(e.id);
    if (r) {
      simplified++;
      replacements.push({
        globalId: e.globalId,
        id: e.id,
        mesh: withNormals(r.mesh),
        trianglesBefore: srcTris(e.id),
        trianglesAfter: Math.floor(r.mesh.indices.length / 3),
        ops: [...r.ops],
      });
    }
  }
  const idToGid = new Map<number, string>(els.map((e) => [e.id, e.globalId]));
  const mergedGroups: MergedGroup[] = groups.map((g) => ({
    masterGlobalId: idToGid.get(g.master) ?? '',
    masterId: g.master,
    members: g.members.map((m) => ({ id: m.id, globalId: idToGid.get(m.id) ?? '', matrix: m.matrix.slice() })),
    trianglesSaved: (g.members.length - 1) * effTris(g.master),
  }));
  return {
    schema: 'xray-cleanup-plan/1',
    removedGlobalIds,
    removalReasons,
    replacements,
    mergedGroups,
    stats: {
      elementsBefore,
      elementsAfter,
      removed: removedGlobalIds.length,
      removedByReason: byReason,
      simplified,
      instanceGroups: groups.length,
      instancedElements,
      trianglesBefore,
      trianglesAfter,
      trianglesStoredBefore,
      trianglesStoredAfter,
      bytesBefore,
      bytesAfter,
    },
  };
}

/** Original mesh of an element for export (normals included), or null without triangles. */
export function originalMesh(source: GeometrySource, id: number): Required<MeshData> | null {
  return sourceMesh(source, id, true) as Required<MeshData> | null;
}
