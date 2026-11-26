// What the app hands to the save plan: results, review comments, cleanup marks (design 1.6, 2.2). Pure (no DOM), so tests can call it.

import type { ClassificationSchema, ClassifyResult } from '../classify/types';
import type { ReviewCommit } from '../classify/reviewLog';
import type { SceneModel } from '../types';
import { planSave } from './plan';
import type { FileSavePlan, SaveExtra, SaveOptions } from './plan';
import type { IfcSource } from './source';

/** Newest comment of each element across the review log (commits are in order). Used only when `includeReviewers` is on. */
export function reviewComments(history: readonly ReviewCommit[]): Map<string, string> {
  const out = new Map<string, string>();
  for (const c of history) for (const ch of c.changes) if (ch.comment) out.set(ch.globalId, ch.comment);
  return out;
}

export interface CleanupMatchLike {
  id: number;
  globalId: string;
  rules: string[];
  reasons: string[];
}

/**
 * Marks for the elements cleanup hid and still hides: `owned` are element ids (`CleanupHides.owned`), the report supplies the rules
 * and reasons. An owned id the report no longer lists (the rules changed since) is marked with a generic rule and reason.
 */
export function cleanupMarks(owned: Iterable<number>, model: Pick<SceneModel, 'elements'>, matches: readonly CleanupMatchLike[] = []): Map<string, { rules: string[]; reasons: string[] }> {
  const byId = new Map(matches.map((m) => [m.id, m] as const));
  const out = new Map<string, { rules: string[]; reasons: string[] }>();
  for (const id of owned) {
    const el = model.elements[id];
    if (!el) continue;
    const m = byId.get(id);
    out.set(el.globalId, m ? { rules: [...m.rules], reasons: [...m.reasons] } : { rules: ['cleanup'], reasons: ['Hidden by model cleanup'] });
  }
  return out;
}

export interface PlanInputs {
  model: Pick<SceneModel, 'elements'>;
  sources: readonly IfcSource[];
  results: readonly ClassifyResult[];
  schema: ClassificationSchema;
  options: SaveOptions;
  history?: readonly ReviewCommit[];
  cleanup?: ReadonlyMap<string, { rules: string[]; reasons: string[] }>;
  /** `RevisionStatus` by GlobalId, from the revision walk (ticket T4). */
  revision?: SaveExtra['revision'];
  /** Accepted 4D assignments by GlobalId (the 4D mapping tool). Written only when `options.includeFourD` is on. */
  fourD?: SaveExtra['fourD'];
  /** Facet properties by GlobalId (flat XR_<Facet>.<Field>). Written only when `options.includeFacets` is on. */
  facets?: SaveExtra['facets'];
}

/** The plan of one save: one entry per source. Comments are read only when the reviewer box is ticked. */
export function planOf(i: PlanInputs): FileSavePlan[] {
  const results = new Map(i.results.map((r) => [r.id, r] as const));
  const extra: SaveExtra = {
    ...(i.options.includeReviewers && i.history ? { comments: reviewComments(i.history) } : {}),
    ...(i.options.includeCleanupMarks && i.cleanup ? { cleanup: i.cleanup } : {}),
    ...(i.revision ? { revision: i.revision } : {}),
    ...(i.options.includeFourD && i.fourD ? { fourD: i.fourD } : {}),
    ...(i.options.includeFacets && i.facets ? { facets: i.facets } : {}),
  };
  return planSave(i.model, results, i.schema, i.sources, i.options, extra);
}
