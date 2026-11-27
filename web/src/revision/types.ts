// Shared contracts of the revision core (design: docs/design/ifc-save-and-revision.md, sections 3 and 4). No DOM, no three.js.

import type { ClassifyResult } from '../classify/types';
import type { ModelIdentity } from '../markup/model';
import type { PropValue } from '../model/ifcProps';

export type { ModelIdentity, PropValue };
export type Vec3 = [number, number, number];

export type Category = 'new' | 'deleted' | 'changed' | 'rematched' | 'unchanged';
export type ChangeFlag = 'geometry' | 'placement' | 'class' | 'type' | 'attributes' | 'storey' | 'material' | 'properties' | 'systems';

export const CATEGORIES: readonly Category[] = ['new', 'deleted', 'changed', 'rematched', 'unchanged'];
export const CHANGE_FLAGS: readonly ChangeFlag[] = ['geometry', 'placement', 'class', 'type', 'attributes', 'storey', 'material', 'properties', 'systems'];

/** Every tolerance and threshold of the diff, the match and the carry-over. Stored in the session so a resumed walk uses the same ones. */
export interface RevisionOptions {
  /** Relative area difference below which two shapes are the same (0.5 %). */
  areaTol: number;
  /** Relative difference of the largest of the three moment eigenvalues (1 %). */
  momentTol: number;
  /** Centroid shift in metres above which a placement change is flagged (1 mm). */
  moveTol: number;
  /** Extent difference: flagged when above max(extentTolAbs, extentTolRel x size). */
  extentTolAbs: number;
  extentTolRel: number;
  /** Storey elevations further apart than this (m) are different storeys. */
  elevationTol: number;
  /** Numbers compare equal below this relative difference. */
  propRelTol: number;
  /** Property keys that start with one of these are not compared (the classifier's own pset and our own sets). */
  ignoreProps: string[];
  /** When GUID pairs are fewer than this share of the smaller model, a global offset is estimated first. */
  guidPairFloor: number;
  /** Grid cell edge (m) of the candidate search. */
  gridCell: number;
  /** Shape agreement (relative) at which the geometry term g reaches 0. */
  matchShapeTol: number;
  /** Minimum score of a rematch, and the margin it needs over the next best candidate of either side. */
  matchMin: number;
  matchMargin: number;
  /** Score from which a rematch is "high" (eligible for bulk accept). */
  matchHigh: number;
  /** Detection (3.1): GUID overlap, class histogram similarity. */
  candidateOverlap: number;
  candidateStemSimilarity: number;
  /** Carry (3.4): when true a geometry or placement flag counts as "classification affected" (imageSettings()/geometrySettings() is on). */
  geometryAffectsClassification: boolean;
}

export const DEFAULT_REVISION_OPTIONS: RevisionOptions = {
  areaTol: 0.005,
  momentTol: 0.01,
  moveTol: 0.001,
  extentTolAbs: 0.002,
  extentTolRel: 0.001,
  elevationTol: 0.01,
  propRelTol: 1e-4,
  ignoreProps: ['Xray_', 'XR_'],
  guidPairFloor: 0.05,
  gridCell: 1,
  matchShapeTol: 0.05,
  matchMin: 0.8,
  matchMargin: 0.05,
  matchHigh: 0.95,
  candidateOverlap: 0.3,
  candidateStemSimilarity: 0.9,
  geometryAffectsClassification: false,
};

export const withOptions = (o?: Partial<RevisionOptions>): RevisionOptions => ({ ...DEFAULT_REVISION_OPTIONS, ...(o ?? {}) });

/** 11 floats per element. All are surface integrals, so they do not depend on how the surface is triangulated. */
export interface GeomSig {
  area: number;
  /** |signed volume| of a closed surface, 0 when the surface is open. */
  volume: number;
  /** Area-weighted centroid (IFC axes, relative to the model's origin shift in the snapshot). */
  centroid: Vec3;
  /** Eigenvalues of the area-weighted covariance, descending: rotation and translation free. */
  moments: Vec3;
  /** AABB size (IFC axes). */
  extent: Vec3;
}
export const SIG_STRIDE = 11;

export interface DiffEntry {
  /** Head GlobalId; "del:" + base GlobalId for deleted. */
  key: string;
  category: Category;
  base?: string;
  head?: string;
  flags: ChangeFlag[];
  /** Metres. */
  move?: number;
  /** The centroid shift (m, IFC axes), so a shifted grid line can be grouped by vector. */
  delta?: Vec3;
  rotated?: boolean;
  score?: number;
  props?: Array<{ key: string; before?: PropValue; after?: PropValue }>;
  /** signatureOf(buildInput) differs between base and head: the change can alter the classification. */
  classifyAffected: boolean;
}

export interface RevisionDiff {
  base: ModelIdentity;
  head: ModelIdentity;
  options: RevisionOptions;
  counts: Record<Category, number>;
  flagCounts: Record<ChangeFlag, number>;
  /** Unchanged entries are counted, not listed. */
  entries: DiffEntry[];
  /** The global offset (m, IFC axes) that was removed before the signature match; [0,0,0] when GUIDs carried the match. */
  offset: Vec3;
}

export interface ModelSnapshot {
  schema: 'xray-model-snapshot/1';
  identity: ModelIdentity;
  savedAt: string;
  classificationSchemaHash: string;
  reviewFingerprint: string;
  /** IFC-frame shift: IFC world = viewer axes (x, -z, y) + originShift. */
  originShift: Vec3;
  /** The 256 smallest 32-bit hashes of the GlobalIds, ascending. */
  guidSketch: Uint32Array;
  classHistogram: Record<string, number>;
  // columnar, index = element order
  globalId: string[];
  ifcClass: string[];
  name: string[];
  tag: string[];
  typeName: string[];
  material: string[];
  storey: Array<{ name: string; elevation: number } | null>;
  systems: string[][];
  /** signatureOf(buildInput(model, id)). */
  classifySignature: string[];
  props: Array<Record<string, PropValue> | null>;
  /** 6 per element, IFC axes relative to originShift. An element without geometry has zeros and a zero area in `sig`. */
  bounds: Float32Array;
  /** 11 per element (GeomSig), IFC axes, centroid relative to originShift (the diff adds the shift in Float64). */
  sig: Float32Array;
  /** Probabilities trimmed to the top 3. */
  results: Array<ClassifyResult | null>;
}

export interface SnapshotRecord {
  key: string;
  /** The identity the key is made of (name, element count, GUID hash): detection uses compareModels on it. */
  identity: ModelIdentity;
  name: string;
  savedAt: string;
  counts: { elements: number; results: number; committed: number };
  guidSketch: Uint32Array;
  classHistogram: Record<string, number>;
  /** gzip(JSON header + Float32Arrays), see snapshot.ts. */
  body: Blob;
  /** Bytes of the body, for the retention limit. */
  size: number;
  classificationSchemaHash: string;
}

export interface RevisionDecision {
  key: string;
  verdict: 'accepted' | 'rejected';
  unsure?: true;
  classification: 'kept' | 'new' | 'edited' | 'none';
  /** The codes an edit (`E`) chose: `classification` is 'edited'. Kept so a resumed walk can propose the same correction again. */
  edited?: { discipline: string; subDiscipline: string | null; division: string | null };
  attachments?: 'keep' | 'reattach' | 'resolve';
  reattachTo?: string;
  note?: string;
  at: string;
  by: string;
  bulk?: string;
  commitId?: string;
}

export const REVISION_ORDERS = ['category', 'storey', 'class'] as const;
export type RevisionOrder = (typeof REVISION_ORDERS)[number];

export interface RevisionFilters {
  category?: Category;
  flag?: ChangeFlag;
  storey?: string;
  ifcClass?: string;
  undecided?: boolean;
  unsure?: boolean;
  onlySkipped?: boolean;
  hasAttachments?: boolean;
  /** Metres. */
  minMove?: number;
}

export interface RevisionSession {
  schema: 'xray-revision/1';
  key: string;
  base: ModelIdentity;
  head: ModelIdentity;
  baseName: string;
  createdAt: string;
  updatedAt: string;
  status: 'open' | 'finished';
  options: RevisionOptions;
  diff: RevisionDiff;
  carried: { commits: string[]; results: number } | null;
  decisions: Record<string, RevisionDecision>;
  skipped: string[];
  cursor: { order: RevisionOrder; filters: RevisionFilters; itemKey: string | null; elementIndex: number };
}

export interface BulkRule {
  id: string;
  label: string;
  category?: Category;
  /** All flags of the entry are in this set (and the entry has at least one flag). */
  flagsWithin?: ChangeFlag[];
  /** Metres. The entry must have a move at or below it. */
  maxMove?: number;
  /** Rotations are not moves: excluded when true. */
  excludeRotated?: boolean;
  minScore?: number;
  classifyAffected?: boolean;
  noAttachments?: boolean;
  needsReview?: boolean;
  /** Only results made by the rules (source 'rules'). */
  rulesOnly?: boolean;
  storey?: string;
  ifcClass?: string;
}
