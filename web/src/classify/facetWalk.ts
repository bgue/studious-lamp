// Facet items of the review walk: a facet result that needs review (XR_Trade, XR_Placement, XR_Material, XR_Phase, XR_Orientation,
// XR_ClassRepair and the XR_Concrete* sets) is one walk item, one element and one facet. No DOM. The classification items come from
// reviewWalk.ts; the walk filter "Classification / Facets / Both" decides which of the two lists are shown.

import { sweepOrder } from './reviewWalk';
import type { FacetRef, WalkElement, WalkItem } from './reviewWalk';

export const WALK_KINDS = ['classification', 'facets', 'both'] as const;
export type WalkKind = (typeof WALK_KINDS)[number];
export const WALK_KIND_LABEL: Record<WalkKind, string> = { classification: 'Classification', facets: 'Facets', both: 'Both' };

/** What the walk needs of a facet result (a FacetResult or a ConcreteFacetResult). */
export interface FacetLike {
  facet: string;
  code: string;
  label: string;
  confidence: number;
  source: string;
  model?: string;
  needsReview: boolean;
  probabilities?: Record<string, number>;
  rationale?: string;
}

export interface FacetEntry {
  ref: FacetRef;
  result: FacetLike;
}

/** The facets and sets that the walk reviews, in the order of their items. */
export const REVIEWED_FACETS: readonly string[] = [
  'Trade', 'Placement', 'Material', 'Phase', 'Orientation', 'ClassRepair',
  'ConcreteGeometry', 'ConcreteElement', 'ConcreteMethod', 'ConcreteSpec', 'ConcreteReinforcement',
];

/** A result a person decided in the walk. */
export const isHumanFacet = (r: FacetLike): boolean => r.source === 'human';

/** Does a facet result belong in the walk: it needs review, or a person decided it (so it stays in view and can be stepped back to). */
export const inFacetWalk = (r: FacetLike): boolean => r.needsReview || isHumanFacet(r);

export interface FacetWalkInput {
  elements: readonly WalkElement[];
  entriesOf(globalId: string): readonly FacetEntry[];
  skipped?: { has(globalId: string): boolean };
  filters?: { unsure?: boolean; unconfirmed?: boolean; onlySkipped?: boolean };
}

export const facetItemKey = (ref: FacetRef, globalId: string): string => `facet:${ref.id}:${globalId}`;

/** The facet items, facet by facet in the order of REVIEWED_FACETS and, inside a facet, in the location sweep of the classification walk. */
export function buildFacetItems(input: FacetWalkInput): WalkItem[] {
  const f = input.filters ?? {};
  const byFacet = new Map<string, Array<{ e: WalkElement; entry: FacetEntry }>>();
  for (const e of input.elements) {
    for (const entry of input.entriesOf(e.globalId)) {
      const r = entry.result;
      if (!inFacetWalk(r)) continue;
      if (f.unconfirmed && isHumanFacet(r) && r.confidence >= 1) continue;
      if (f.unsure && !(isHumanFacet(r) && r.confidence < 1)) continue;
      if (f.onlySkipped && !(input.skipped?.has(e.globalId) ?? false)) continue;
      (byFacet.get(entry.ref.id) ?? byFacet.set(entry.ref.id, []).get(entry.ref.id)!).push({ e, entry });
    }
  }
  const out: WalkItem[] = [];
  const ids = [...REVIEWED_FACETS, ...[...byFacet.keys()].filter((k) => !REVIEWED_FACETS.includes(k))];
  for (const id of ids) {
    const list = byFacet.get(id);
    if (!list) continue;
    const entryOf = new Map(list.map((x) => [x.e.globalId, x.entry]));
    for (const e of sweepOrder(list.map((x) => x.e))) {
      const entry = entryOf.get(e.globalId)!;
      out.push({
        key: facetItemKey(entry.ref, e.globalId),
        facet: entry.ref,
        title: `${entry.ref.id.replace('Concrete', 'Concrete ')}: ${e.ifcClass}: ${e.name || e.tag || e.globalId}`,
        ifcClass: e.ifcClass,
        storeyName: e.storeyName,
        system: e.system,
        discipline: '',
        elements: [e],
      });
    }
  }
  return out;
}

export interface FacetCandidate {
  code: string;
  label: string;
  /** The model's probability, or null when the result has none for it. */
  probability: number | null;
}

/**
 * The numbered candidates of a facet result: the proposed code first (key 1), then the other codes of the list in the order of the
 * model's probabilities (key 2 is the runner-up). A result without probabilities has only the proposal. `codes` is the facet's code
 * list; codes that are not in it are left out. At most `max` (9, the number keys).
 */
export function facetCandidates(r: FacetLike, codes: readonly { code: string; label: string }[] | null, max = 9): FacetCandidate[] {
  const label = (c: string): string => codes?.find((x) => x.code === c)?.label ?? (c === r.code ? r.label : c);
  const out: FacetCandidate[] = [{ code: r.code, label: r.label, probability: r.probabilities?.[r.code] ?? null }];
  const ranked = Object.entries(r.probabilities ?? {}).filter(([c]) => c !== r.code && (!codes || codes.some((x) => x.code === c))).sort((a, b) => b[1] - a[1]);
  for (const [c, p] of ranked) if (out.length < max) out.push({ code: c, label: label(c), probability: p });
  return out;
}
