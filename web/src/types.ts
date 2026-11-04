// Shared contracts for the X-ray reference implementation.
// Keep these stable: algorithms (src/algo), geometry/render (src/render),
// loader (src/model) and the app all compile against this file.

import type { Box3, Vector3 } from 'three';

export type ElementId = number;

export interface StoreyRecord {
  id: number;
  name: string;
  elevation: number;
}

export interface ElementRecord {
  id: ElementId;
  globalId: string;
  expressId?: number;
  ifcClass: string;
  name?: string;
  storey: number | null;
  material?: string;
  /** RGBA 0..1 */
  color: [number, number, number, number];
  /** [minx, miny, minz, maxx, maxy, maxz] in viewer coordinates */
  bounds: [number, number, number, number, number, number];
  file?: string;
}

export interface Relations {
  /** [hostElementId, openingExpressId] */
  voids: Array<[number, number]>;
  /** [openingExpressId, fillerElementId] */
  fills: Array<[number, number]>;
  /** derived: [fillerElementId, hostElementId] */
  hosts: Array<[ElementId, ElementId]>;
  /** element-level port connections */
  ports: Array<[ElementId, ElementId]>;
  systems: Array<{ name: string; elements: ElementId[] }>;
}

export interface SceneModel {
  schema: 'xray-model/1';
  units: 'm';
  originShift: [number, number, number];
  storeys: StoreyRecord[];
  elements: ElementRecord[];
  relations: Relations;
  byGlobalId: Map<string, ElementId>;
  /** Class styles baked into the sidecar by the converter (`--config`). Optional. */
  styles?: ClassStyles;
  /** Material-class aliases baked into the sidecar. Optional. */
  materialAliases?: Record<string, string[]>;
}

/**
 * Per-class base appearance. Keyed in `ClassStyles` by ifcClass or by a material-class alias.
 * See src/styles.ts for resolution and SPEC-style semantics:
 * - alphaMax caps opacity in every bucket (also Far and x-ray off): alpha = min(alpha, alphaMax)
 * - alphaMin replaces sightlines.alphaMin for this class (floor of ghosting)
 * - floor feeds Algorithm 7 (replaces the categoryFloors entry for the class)
 * - color replaces the element base colour (rgb 0..1)
 * - hidden hides the class
 */
export interface ClassStyle {
  alphaMax?: number;
  alphaMin?: number;
  floor?: number;
  color?: [number, number, number];
  hidden?: boolean;
}
/** key: ifcClass, or a material-class alias (see XrayConfig.materialAliases). */
export type ClassStyles = Record<string, ClassStyle>;
export interface XrayConfig {
  schema: 'xray-config/1';
  classStyles: ClassStyles;
  /** alias -> ["IfcMember", "IfcBeam:steel"]: a bare class matches the class, "Class:text" also needs the material name to contain text (case-insensitive). */
  materialAliases?: Record<string, string[]>;
}

/**
 * Everything the algorithms need from geometry. Implemented over the merged
 * geometry and BVH in src/render/geometry.ts; mocked with boxes in tests.
 */
export interface GeometryProvider {
  bounds(id: ElementId): Box3;
  /** Shortest surface-to-surface distance in metres. 0 when touching or overlapping. */
  surfaceDistance(a: ElementId, b: ElementId): number;
  /** True when the meshes overlap or one contains the other. */
  intersects(a: ElementId, b: ElementId): boolean;
  /** Area-weighted points on the surface of the element, in world space. */
  samplePoints(id: ElementId, count: number): Vector3[];
  /**
   * Every element in `candidates` whose surface the segment origin -> origin + dir * maxDistance
   * crosses, nearest to origin first. `dir` is unit length.
   */
  raycastAll(origin: Vector3, dir: Vector3, maxDistance: number, candidates: ReadonlySet<ElementId>): ElementId[];
}

export interface ClassificationSettings {
  focusClasses: string[];
  ctxClasses: string[];
  storeyBand: number;
  bufferBase: number;
  bufferScale: number;
  bufferLo: number;
  bufferHi: number;
}

export interface Classification {
  focus: Set<ElementId>;
  host: Set<ElementId>;
  near: Set<ElementId>;
  far: Set<ElementId>;
  /** Defined for every element in host (1.0) and near (0..1). */
  proximityWeight: Map<ElementId, number>;
  /** Buffer radius used for each focus element, metres. */
  bufferRadius: Map<ElementId, number>;
}

export interface SightlineSettings {
  samplesPerObject: number;
  maxSamples: number;
  alphaMin: number;
  alphaMax: number;
  gamma: number;
  /** 0..1, fraction of the remaining change applied per update; 1 disables smoothing */
  smoothingRate: number;
  /**
   * Which Context elements are ray candidates. 'near': Host + Near only (the report's Algorithm 2).
   * 'all': Host, Near and Far; a Far element that blocks the focus ghosts with weight `farWeight`
   * (deviation from the report, see README). Treated as 'all' when undefined.
   */
  occluderScope: OccluderScope;
  /** 0..1, proximity weight of Far elements under scope 'all' (Host and Near use their Algorithm 1 weight). */
  farWeight: number;
  /**
   * How a hit counts when several occluders stack on one ray (deviation from the report, see README).
   * Order k = 0 for the occluder nearest the camera, 1 for the next one behind it, and so on.
   * 'uniform': credit 1 for every occluder. 'front': credit layerFalloff^k. 'budget': credit 1 for
   * k < layerBudget, else 0. Treated as 'front' when undefined.
   */
  layerWeighting: LayerWeighting;
  /** 0..1, per-layer decay of the credit under 'front' (0.5: front 1, next 0.5, then 0.25). */
  layerFalloff: number;
  /** Integer >= 1, number of layers per ray that ghost under 'budget'. */
  layerBudget: number;
}

export type OccluderScope = 'near' | 'all';

export type LayerWeighting = 'uniform' | 'front' | 'budget';

export interface SightlineResult {
  occlusion: Map<ElementId, number>;
  importance: Map<ElementId, number>;
  targetAlpha: Map<ElementId, number>;
}

export interface OverrideSettings {
  userPins: Set<ElementId>;
  userHides: Set<ElementId>;
  userPinFloor: number;
  /** ifcClass -> floor */
  categoryFloors: Record<string, number>;
  /** elementId -> floor */
  projectPins: Record<ElementId, number>;
}

export const HIDDEN = -1;

export type FarMode = 'opaque' | 'hidden';

export const FLAG_FOCUS = 1;
export const FLAG_HIDDEN = 2;
export const FLAG_PINNED = 4;
export const FLAG_SELECTED = 8;

/** Per-element state the renderer uploads. Arrays are indexed by element id. */
export interface RenderState {
  alpha: Float32Array;
  /** rgb interleaved, 0..1 */
  color: Float32Array;
  flags: Uint8Array;
}

export const DEFAULT_CLASSIFICATION: ClassificationSettings = {
  focusClasses: [
    'IfcDuctSegment', 'IfcDuctFitting', 'IfcPipeSegment', 'IfcPipeFitting',
    'IfcCableCarrierSegment', 'IfcCableCarrierFitting', 'IfcFlowSegment', 'IfcFlowFitting', 'IfcFlowTerminal',
  ],
  ctxClasses: [
    'IfcSlab', 'IfcWall', 'IfcWallStandardCase', 'IfcBeam', 'IfcColumn', 'IfcFooting', 'IfcStair', 'IfcRoof',
  ],
  storeyBand: 1,
  bufferBase: 0.30,
  bufferScale: 0.50,
  bufferLo: 0.30,
  bufferHi: 1.50,
};

export const DEFAULT_SIGHTLINES: SightlineSettings = {
  samplesPerObject: 64,
  maxSamples: 500,
  alphaMin: 0.15,
  alphaMax: 0.85,
  gamma: 0.5,
  smoothingRate: 0.20,
  occluderScope: 'all',
  farWeight: 0.7,
  layerWeighting: 'front',
  layerFalloff: 0.5,
  layerBudget: 2,
};

export const DEFAULT_OVERRIDES: OverrideSettings = {
  userPins: new Set(),
  userHides: new Set(),
  userPinFloor: 0.60,
  categoryFloors: { IfcColumn: 0.50 },
  projectPins: {},
};
