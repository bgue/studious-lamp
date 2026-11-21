// What to write, per source file (design 1.7). Pure: a plan holds only classification output, review state, comments and cleanup marks;
// it has no field for keys, tokens or pictures.

import type { ClassificationSchema, ClassifyResult } from '../classify/types';
import type { SceneModel } from '../types';
import { familyOf } from './families';
import type { SchemaFamily } from './families';
import type { WorkScheduleSave } from './workSchedule';

export type { SchemaFamily };

/** Open questions of the design, each one constant. They may change later. */
export const XRAY_DEFAULTS = {
  /** Property set of the review state and provenance (1.6 B). Not `Pset_…`: that prefix is reserved for buildingSMART. */
  psetReview: 'Xray_Review',
  /** Property set of the cleanup marks (2.2). */
  psetCleanup: 'Xray_Cleanup',
  /** Property set of the 4D location, trade and zone (4D mapping tool; docs/design/4d-xer-animation.md section 10). */
  psetFourD: 'Xray_4D',
  /** Name of the MasterFormat division system. */
  divisionSystemName: 'MasterFormat',
  divisionSystemSource: 'CSI',
  /** Source text of the discipline system when the schema does not say. */
  disciplineSystemSource: 'project',
  /** Name of the relations that Xray writes. */
  relClassificationName: 'Xray classification',
  relPropertiesName: 'Xray properties',
} as const;

export interface SaveOptions {
  /** Write ReviewedBy and Comment (reviewer names and comments). Default false: no name leaves the viewer unless this is true. */
  includeReviewers: boolean;
  includeCleanupMarks: boolean;
  /** Write Xray_4D (Location, Trade, Zone) for the elements that have accepted 4D assignments. Default false. */
  includeFourD?: boolean;
  scope: 'all' | 'reviewed';
  /** Goes into the block comment. Default "dev". */
  toolVersion?: string;
}
export const DEFAULT_SAVE_OPTIONS: SaveOptions = { includeReviewers: false, includeCleanupMarks: true, scope: 'all' };

/** The facts about one source file that the writer needs. T2's `IfcSource` extends this with the blob. */
export interface IfcSourceInfo {
  /** Same string as ElementRecord.file. */
  fileName: string;
  /** FILE_SCHEMA as reported. */
  schema: string;
  /** Largest express id of the file as opened (includes our old block when there is one). */
  maxExpressId: number;
  /** OwnerHistory reference of the IfcProject, or null. */
  ownerHistoryId: number | null;
  classifications: Array<{ id: number; name: string; edition: string | null }>;
  /** `base=` of an existing XRAY-BEGIN marker: new ids start after it, replacing the old block. */
  blockBase?: number | null;
}

export type RevisionStatus = 'new' | 'changed' | 'rematched' | 'unchanged';

/** The accepted 4D values of one element. */
export interface FourDValues { location?: string; trade?: string; zone?: string }

export interface ElementSave {
  expressId: number;
  globalId: string;
  result?: ClassifyResult;
  comment?: string;
  revision?: { status: RevisionStatus; baseline: string };
  cleanup?: { rules: string[]; reasons: string[]; keptBecause?: string };
  /** Accepted 4D values (property names Location, Trade, Zone), only with `includeFourD`. */
  fourD?: FourDValues;
}

export interface FileSavePlan {
  fileName: string;
  family: SchemaFamily;
  /** Express ids are allocated from base + 1. */
  base: number;
  ownerHistoryId: number | null;
  existingClassifications: IfcSourceInfo['classifications'];
  elements: ElementSave[];
  /** 4D write-back (additive): the IfcWorkSchedule with its tasks, written as the last section of the block (IFC4 / IFC4X3; ignored for IFC2X3). */
  workSchedule?: WorkScheduleSave;
  /** Lines of an earlier block that stay (written first, ids up to `lastId`; `base` is then that block's base). Used by the 4D write-back to keep other sets. */
  preserved?: { lines: string[]; lastId: number };
}

export interface SaveExtra {
  comments?: ReadonlyMap<string, string>;
  revision?: ReadonlyMap<string, { status: RevisionStatus; baseline: string }>;
  cleanup?: ReadonlyMap<string, { rules: string[]; reasons: string[]; keptBecause?: string }>;
  /** Accepted 4D assignments by GlobalId (used only when `includeFourD` is on). */
  fourD?: ReadonlyMap<string, FourDValues>;
}

export class UnsupportedSchemaError extends Error {
  constructor(readonly schemaName: string, readonly fileName: string) {
    super(`${fileName}: the schema ${schemaName || '(none)'} is not supported for saving. Supported: IFC2X3, IFC4, IFC4X3.`);
    this.name = 'UnsupportedSchemaError';
  }
}

const REVIEWED = new Set(['confirmed', 'corrected', 'manual']);

/** One plan per source. Elements go to the file named by `record.file`; a model with one source and no file names uses that source. */
export function planSave(
  model: Pick<SceneModel, 'elements'>,
  results: ReadonlyMap<string, ClassifyResult>,
  _schema: ClassificationSchema,
  sources: readonly IfcSourceInfo[],
  o: SaveOptions,
  extra: SaveExtra = {},
): FileSavePlan[] {
  const plans = sources.map((s): FileSavePlan => {
    const family = familyOf(s.schema);
    if (!family) throw new UnsupportedSchemaError(s.schema, s.fileName);
    const base = s.blockBase ?? s.maxExpressId;
    return { fileName: s.fileName, family, base, ownerHistoryId: s.ownerHistoryId, existingClassifications: s.classifications.filter((c) => c.id <= base), elements: [] };
  });
  const byName = new Map(plans.map((p) => [p.fileName, p] as const));
  const seen = new Set<string>();
  for (const e of model.elements) {
    if (e.expressId === undefined) continue;
    const plan = e.file !== undefined ? byName.get(e.file) : plans.length === 1 ? plans[0] : undefined;
    if (!plan) continue;
    const key = `${plan.fileName}#${e.expressId}`;
    if (seen.has(key)) continue;
    const r = results.get(e.globalId);
    const result = r && (o.scope === 'all' || REVIEWED.has(r.source)) ? r : undefined;
    const cleanup = o.includeCleanupMarks ? extra.cleanup?.get(e.globalId) : undefined;
    const revision = extra.revision?.get(e.globalId);
    const fd = o.includeFourD ? extra.fourD?.get(e.globalId) : undefined;
    const fourD = fd && (fd.location || fd.trade || fd.zone) ? fd : undefined;
    // Revision state belongs to the review set, which exists only for an element with a result.
    if (!result && !cleanup && !fourD) continue;
    seen.add(key);
    const comment = extra.comments?.get(e.globalId);
    plan.elements.push({
      expressId: e.expressId,
      globalId: e.globalId,
      ...(result ? { result } : {}),
      ...(comment ? { comment } : {}),
      ...(revision && result ? { revision } : {}),
      ...(cleanup ? { cleanup } : {}),
      ...(fourD ? { fourD } : {}),
    });
  }
  for (const p of plans) p.elements.sort((a, b) => a.expressId - b.expressId);
  return plans;
}
