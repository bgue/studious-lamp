// Algorithms 8/9 (stretch): category tiers.
//
// tiers[0] is the most important tier (what the selection belongs to: drawn
// opaque), tiers[1] ghosts less than tiers[2], and so on. Each entry is a list
// of IFC classes.
//
// Rank r elements are:
//   r = 0     the selection's connected run, restricted to classes in tiers[0], plus every
//             selected element whatever its class (explicit selection is intent)
//   r >= 1    Host + Near of Algorithm 1 run with Focus = every element of rank < r
//             and Context = classes in tiers[r]

import type { Vector3 } from 'three';
import {
  DEFAULT_CLASSIFICATION,
  DEFAULT_SIGHTLINES,
  type Classification,
  type ClassificationSettings,
  type ElementId,
  type GeometryProvider,
  type RenderState,
  type SceneModel,
  type SightlineResult,
  type SightlineSettings,
} from '../types';
import { addSelected, classifyFromFocus, connectedRun } from './classify';
import { castSamples, collectSamples, farTarget, layerCredit, occluderSet, scopeOf } from './sightlines';

export interface TierSettings extends SightlineSettings {
  /** Weight of a sample by the sample's own rank; index 0 is the top tier. */
  tierWeight: number[];
  /** alphaMin per occluder rank (index 0 is never an occluder). */
  tierAlphaMin: number[];
}

/** Defaults for the three-tier example. */
export const DEFAULT_TIER_SETTINGS: TierSettings = {
  ...DEFAULT_SIGHTLINES,
  tierWeight: [1.0, 0.6],
  tierAlphaMin: [1.0, 0.35, 0.15],
};

export interface TieredClassification {
  tierCount: number;
  /** Per-tier Algorithm 1 result. tiers[0] only has a focus set. */
  tiers: Classification[];
  /** Rank of every Focus/Host/Near element. Far and out-of-scope elements have no rank. */
  rank: Map<ElementId, number>;
  /**
   * Tier of each Far element: the first tier t >= 1 whose Context (its own classes) has it as Far.
   * Used by scope 'all': a Far element is occluded by samples of rank < t and uses tierAlphaMin[t].
   */
  farRank: Map<ElementId, number>;
  /** Single-bucket view for smoothAlpha/applyRenderState: focus = tier 0, host/near/far = unions. */
  flat: Classification;
}

/** Algorithm 8: run Algorithm 1 for each tier t >= 1 with Focus = all elements ranked above t. */
export function classifyTiers(
  model: SceneModel,
  geometry: GeometryProvider,
  selection: Iterable<ElementId>,
  tiers: string[][],
  settings: ClassificationSettings = DEFAULT_CLASSIFICATION,
): TieredClassification {
  const rank = new Map<ElementId, number>();
  const perTier: Classification[] = [];
  const above = new Set<ElementId>();

  if (tiers.length > 0) {
    const sel = [...selection];
    const focus = connectedRun(model, sel, new Set(tiers[0]));
    addSelected(model, sel, focus);
    perTier.push(classifyFromFocus(model, geometry, focus, { ...settings, ctxClasses: [] }));
    for (const id of focus) {
      rank.set(id, 0);
      above.add(id);
    }
  }

  const flat: Classification = {
    focus: new Set(perTier[0]?.focus),
    host: new Set(),
    near: new Set(),
    far: new Set(),
    proximityWeight: new Map(),
    bufferRadius: new Map(perTier[0]?.bufferRadius),
  };

  for (let t = 1; t < tiers.length; t++) {
    const cls = classifyFromFocus(model, geometry, above, { ...settings, ctxClasses: tiers[t] ?? [] });
    perTier.push(cls);
    const members: ElementId[] = [];
    for (const id of cls.host) {
      flat.host.add(id);
      members.push(id);
    }
    for (const id of cls.near) {
      flat.near.add(id);
      members.push(id);
    }
    for (const id of members) {
      rank.set(id, t);
      flat.proximityWeight.set(id, cls.proximityWeight.get(id) ?? 0);
    }
    for (const id of cls.far) flat.far.add(id);
    for (const id of members) above.add(id);
  }
  for (const id of [...flat.far]) if (rank.has(id)) flat.far.delete(id);

  const farRank = new Map<ElementId, number>();
  for (let t = 1; t < perTier.length; t++) {
    for (const id of perTier[t]!.far) if (!rank.has(id) && !farRank.has(id)) farRank.set(id, t);
  }

  return { tierCount: tiers.length, tiers: perTier, rank, farRank, flat };
}

/**
 * Algorithm 9: sightlines with tiers. A hit of occluder o by a sample from rank s only counts
 * when s < rank(o). Samples are weighted by tierWeight[s]; the occlusion of an occluder is the
 * weighted hit mass divided by the weighted mass of samples that could be occluded by it
 * (those with rank < rank(o)). Target alpha uses tierAlphaMin[rank(o)].
 *
 * With occluderScope 'all' (default) the Far elements of each tier's own Context join the ray
 * candidates: a Far element of tier t is treated like a rank-t occluder, with weight farWeight in
 * place of the proximity weight and ceiling 1 (target = 1 + (tierAlphaMin[t] - 1) * importance).
 */
export function sightlinesTiered(
  tc: TieredClassification,
  geometry: GeometryProvider,
  cameraPosition: Vector3,
  settings: TierSettings = DEFAULT_TIER_SETTINGS,
  state?: Pick<RenderState, 'flags'>,
): SightlineResult {
  const result: SightlineResult = { occlusion: new Map(), importance: new Map(), targetAlpha: new Map() };
  const rank = tc.rank;
  const weightOf = (r: number): number => settings.tierWeight[r] ?? 1;

  // Samples come from every ranked element except the last tier (nothing can hide those from below).
  const sampled = new Set<ElementId>();
  const occluderAll = new Set<ElementId>();
  for (const [id, r] of rank) {
    if (r < tc.tierCount - 1) sampled.add(id);
    if (r >= 1) occluderAll.add(id);
  }
  const farAll = scopeOf(settings) === 'all' ? tc.farRank : new Map<ElementId, number>();
  const rankOf = (id: ElementId): number => rank.get(id) ?? farAll.get(id) ?? 0;
  const candidates = new Set<ElementId>(occluderAll);
  for (const id of farAll.keys()) candidates.add(id);
  const active = state ? occluderSet({ host: candidates, near: new Set() }, state) : candidates;

  const samples = collectSamples(geometry, sampled, settings);
  const sampleRank = samples.owners.map((o) => rank.get(o) ?? 0);

  // eligibleMass[r] = total weight of samples with rank < r.
  const massByRank: number[] = new Array(tc.tierCount + 1).fill(0);
  for (const r of sampleRank) massByRank[r] = (massByRank[r] ?? 0) + weightOf(r);
  const eligible: number[] = new Array(tc.tierCount + 1).fill(0);
  for (let r = 1; r <= tc.tierCount; r++) eligible[r] = (eligible[r - 1] ?? 0) + (massByRank[r - 1] ?? 0);

  const hitMass = new Map<ElementId, number>();
  // Layer order k counts only the occluders that can hide the sample (rank above the sample's own),
  // k = 0 being the one nearest the camera.
  castSamples(
    geometry,
    samples,
    cameraPosition,
    active,
    (s, id, k) => {
      const credit = layerCredit(settings, k);
      if (credit > 0) hitMass.set(id, (hitMass.get(id) ?? 0) + weightOf(sampleRank[s]!) * credit);
    },
    (s, id) => sampleRank[s]! < rankOf(id),
  );

  for (const id of occluderAll) {
    const r = rank.get(id)!;
    const denom = eligible[r] ?? 0;
    const occlusion = denom > 0 ? Math.min(1, (hitMass.get(id) ?? 0) / denom) : 0;
    const w = tc.flat.proximityWeight.get(id) ?? 0;
    const importance = Math.pow(occlusion, settings.gamma) * w;
    const alphaMin = settings.tierAlphaMin[r] ?? settings.alphaMin;
    result.occlusion.set(id, occlusion);
    result.importance.set(id, importance);
    result.targetAlpha.set(id, settings.alphaMax + (alphaMin - settings.alphaMax) * importance);
  }
  for (const [id, r] of farAll) {
    const denom = eligible[r] ?? 0;
    const occlusion = denom > 0 ? Math.min(1, (hitMass.get(id) ?? 0) / denom) : 0;
    const importance = Math.pow(occlusion, settings.gamma) * settings.farWeight;
    result.occlusion.set(id, occlusion);
    result.importance.set(id, importance);
    result.targetAlpha.set(id, farTarget(settings.tierAlphaMin[r] ?? settings.alphaMin, importance));
  }
  return result;
}
