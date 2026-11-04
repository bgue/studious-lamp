// Algorithm 2: per-camera-move sightline sampling, target alpha, smoothing.

import { Vector3 } from 'three';
import {
  DEFAULT_SIGHTLINES,
  FLAG_FOCUS,
  FLAG_HIDDEN,
  FLAG_PINNED,
  FLAG_SELECTED,
  HIDDEN,
  type Classification,
  type ElementId,
  type FarMode,
  type GeometryProvider,
  type LayerWeighting,
  type OccluderScope,
  type OverrideSettings,
  type RenderState,
  type SightlineResult,
  type SightlineSettings,
} from '../types';

// ---------------------------------------------------------------- samples

export interface SampleSet {
  points: Vector3[];
  /** owners[i] is the element that points[i] was sampled from. */
  owners: ElementId[];
}

interface SampleCacheEntry {
  source: ReadonlySet<ElementId>;
  size: number;
  key: string;
  samples: SampleSet;
}

const sampleCache = new WeakMap<GeometryProvider, SampleCacheEntry>();

/**
 * L1: union of geometry.samplePoints(f, n_f) over the given elements, capped at
 * maxSamples by giving each element an even share of the budget
 * (n_f <= samplesPerObject). Cached per geometry provider by element set and
 * (samplesPerObject, maxSamples); the same Set instance with unchanged size is
 * treated as unchanged, otherwise the sorted id list is compared.
 */
export function collectSamples(
  geometry: GeometryProvider,
  ids: ReadonlySet<ElementId>,
  settings: Pick<SightlineSettings, 'samplesPerObject' | 'maxSamples'>,
): SampleSet {
  const prev = sampleCache.get(geometry);
  const tag = `${settings.samplesPerObject}|${settings.maxSamples}|`;
  if (prev && prev.source === ids && prev.size === ids.size && prev.key.startsWith(tag)) {
    return prev.samples;
  }
  const sorted = [...ids].sort((a, b) => a - b);
  const key = tag + sorted.join(',');
  if (prev && prev.key === key) {
    prev.source = ids;
    prev.size = ids.size;
    return prev.samples;
  }

  const samples: SampleSet = { points: [], owners: [] };
  const n = sorted.length;
  for (let i = 0; i < n; i++) {
    // Even share of the global budget: floor((i+1)M/n) - floor(iM/n).
    const share =
      Math.floor(((i + 1) * settings.maxSamples) / n) - Math.floor((i * settings.maxSamples) / n);
    const count = Math.min(settings.samplesPerObject, share);
    if (count <= 0) continue;
    const id = sorted[i]!;
    for (const p of geometry.samplePoints(id, count)) {
      samples.points.push(p);
      samples.owners.push(id);
    }
  }
  sampleCache.set(geometry, { source: ids, size: ids.size, key, samples });
  return samples;
}

/** Scope of a settings object; undefined means the default, 'all'. */
export function scopeOf(settings: Pick<Partial<SightlineSettings>, 'occluderScope'>): OccluderScope {
  return settings.occluderScope ?? 'all';
}

/** Layer weighting of a settings object; undefined means the default, 'front'. */
export function layerModeOf(settings: Pick<Partial<SightlineSettings>, 'layerWeighting'>): LayerWeighting {
  return settings.layerWeighting ?? DEFAULT_SIGHTLINES.layerWeighting;
}

/**
 * Hit credit of the k-th occluder on a ray, k = 0 for the one nearest the camera.
 * 'uniform': 1. 'front': layerFalloff^k. 'budget': 1 for k < layerBudget, else 0.
 */
export function layerCredit(
  settings: Partial<Pick<SightlineSettings, 'layerWeighting' | 'layerFalloff' | 'layerBudget'>>,
  k: number,
): number {
  switch (layerModeOf(settings)) {
    case 'uniform':
      return 1;
    case 'budget':
      return k < Math.max(0, Math.round(settings.layerBudget ?? DEFAULT_SIGHTLINES.layerBudget)) ? 1 : 0;
    default:
      return Math.pow(settings.layerFalloff ?? DEFAULT_SIGHTLINES.layerFalloff, k);
  }
}

/**
 * Ray candidates = Host + Near (scope 'near', the default here, as in the report) or Host + Near +
 * Far (scope 'all'), minus anything the render state already flags hidden.
 */
export function occluderSet(
  classification: Pick<Classification, 'host' | 'near'> & Partial<Pick<Classification, 'far'>>,
  state?: Pick<RenderState, 'flags'>,
  scope: OccluderScope = 'near',
): Set<ElementId> {
  const out = new Set<ElementId>();
  for (const id of classification.host) out.add(id);
  for (const id of classification.near) out.add(id);
  if (scope === 'all' && classification.far) for (const id of classification.far) out.add(id);
  if (state) {
    for (const id of out) if (((state.flags[id] ?? 0) & FLAG_HIDDEN) !== 0) out.delete(id);
  }
  return out;
}

/**
 * Cast a ray from every sample towards the camera and call `onHit(sampleIndex, occluderId, k)` for
 * each occluder crossed, where k is the layer order along that ray: 0 for the occluder nearest the
 * camera (the last hit raycastAll returns, since it orders hits from the sample outwards), 1 for
 * the next one behind it, and so on. `counts`, when given, filters which hits take part (and so
 * take a layer slot). Shared by the flat and tiered variants.
 */
export function castSamples(
  geometry: GeometryProvider,
  samples: SampleSet,
  cameraPosition: Vector3,
  occluders: ReadonlySet<ElementId>,
  onHit: (sample: number, occluder: ElementId, k: number) => void,
  counts?: (sample: number, occluder: ElementId) => boolean,
): void {
  if (occluders.size === 0) return;
  const dir = new Vector3();
  for (let i = 0; i < samples.points.length; i++) {
    const p = samples.points[i]!;
    dir.subVectors(cameraPosition, p);
    const dist = dir.length();
    if (dist < 1e-9) continue;
    dir.divideScalar(dist);
    let hits = geometry.raycastAll(p, dir, dist, occluders);
    if (counts) hits = hits.filter((id) => counts(i, id));
    const last = hits.length - 1;
    for (let j = 0; j <= last; j++) onHit(i, hits[j]!, last - j);
  }
}

// ------------------------------------------------------------- sightlines

/** Target alpha of a Far element: ceiling 1 (not alphaMax), importance already includes farWeight. */
export function farTarget(alphaMin: number, importance: number): number {
  return 1 + (alphaMin - 1) * importance;
}

/**
 * Algorithm 2, L1..L9. Steps 10 (floors) and 11 (smoothing) are `smoothAlpha`.
 *
 * `state` is optional: when given, occluders whose FLAG_HIDDEN is set are not
 * ray cast against (a hidden element cannot occlude). They still appear in the
 * result with occlusion 0.
 */
export function sightlines(
  classification: Classification,
  geometry: GeometryProvider,
  cameraPosition: Vector3,
  settings: SightlineSettings = DEFAULT_SIGHTLINES,
  state?: Pick<RenderState, 'flags'>,
): SightlineResult {
  const result: SightlineResult = {
    occlusion: new Map(),
    importance: new Map(),
    targetAlpha: new Map(),
  };
  const scope = scopeOf(settings);
  const all = new Set<ElementId>([...classification.host, ...classification.near]);
  const far = scope === 'all' ? classification.far : new Set<ElementId>();
  const active = state
    ? occluderSet(classification, state, scope)
    : scope === 'all'
      ? new Set<ElementId>([...all, ...far])
      : all;

  const samples = collectSamples(geometry, classification.focus, settings);
  const total = samples.points.length;
  const hits = new Map<ElementId, number>();
  castSamples(geometry, samples, cameraPosition, active, (_s, id, k) => {
    const credit = layerCredit(settings, k);
    if (credit > 0) hits.set(id, (hits.get(id) ?? 0) + credit); // L2-5, weighted by layer order
  });

  for (const id of all) {
    const occlusion = total > 0 ? Math.min(1, (hits.get(id) ?? 0) / total) : 0; // L7
    const w = classification.proximityWeight.get(id) ?? 0;
    const importance = Math.pow(occlusion, settings.gamma) * w; // L8
    const target = settings.alphaMax + (settings.alphaMin - settings.alphaMax) * importance; // L9
    result.occlusion.set(id, occlusion);
    result.importance.set(id, importance);
    result.targetAlpha.set(id, target);
  }
  // Far (scope 'all'): ceiling 1, weight farWeight instead of a proximity weight.
  for (const id of far) {
    const occlusion = total > 0 ? Math.min(1, (hits.get(id) ?? 0) / total) : 0;
    const importance = Math.pow(occlusion, settings.gamma) * settings.farWeight;
    result.occlusion.set(id, occlusion);
    result.importance.set(id, importance);
    result.targetAlpha.set(id, farTarget(settings.alphaMin, importance));
  }
  return result;
}

/**
 * L10-11: apply the floor, then move each occluder's alpha towards its target:
 * alpha += smoothingRate * (target - alpha). Mutates `alpha` in place.
 *
 * - occluder with floor HIDDEN: alpha left untouched (the HIDDEN flag does the work,
 *   see applyRenderState)
 * - Focus: 1. Everything that is not an occluder: 1.
 * - Far: under scope 'all' (the default) with farMode 'opaque' Far elements are stepped like
 *   occluders, with a default target of 1; otherwise 1 (hidden mode is a flag, not an alpha).
 *
 * Returns the alpha of every stepped element after the step.
 */
export function smoothAlpha(
  alpha: Float32Array,
  targetAlpha: ReadonlyMap<ElementId, number>,
  floors: ReadonlyMap<ElementId, number>,
  settings: Pick<SightlineSettings, 'alphaMax' | 'smoothingRate'> & Partial<Pick<SightlineSettings, 'occluderScope'>>,
  farMode: FarMode,
  classification: Pick<Classification, 'host' | 'near' | 'focus' | 'far'>,
): Map<ElementId, number> {
  const out = new Map<ElementId, number>();
  const k = settings.smoothingRate;
  const stepFar = scopeOf(settings) === 'all' && farMode !== 'hidden';
  const step = (id: ElementId, dflt: number): void => {
    if (id < 0 || id >= alpha.length) return;
    const floor = floors.get(id) ?? 0;
    if (floor === HIDDEN) {
      out.set(id, alpha[id]!);
      return;
    }
    const target = Math.max(targetAlpha.get(id) ?? dflt, floor);
    const next = alpha[id]! + k * (target - alpha[id]!);
    alpha[id] = next;
    out.set(id, alpha[id]!);
  };
  for (const id of classification.host) step(id, settings.alphaMax);
  for (const id of classification.near) step(id, settings.alphaMax);
  if (stepFar) for (const id of classification.far) step(id, 1);

  for (let i = 0; i < alpha.length; i++) {
    if (classification.host.has(i) || classification.near.has(i)) continue;
    if (stepFar && classification.far.has(i)) continue;
    alpha[i] = 1;
  }
  return out;
}

/**
 * Write alpha and flags into the render state.
 *
 * alpha: `alphas` (from smoothAlpha) for occluders and, when present there, Far; 1 for Focus and other Far.
 * flags: FLAG_FOCUS for Focus; FLAG_HIDDEN for user hides and, in 'hidden' far mode, Far;
 * FLAG_PINNED for user pins and project pins. FLAG_SELECTED is preserved.
 */
export function applyRenderState(
  state: RenderState,
  classification: Pick<Classification, 'focus' | 'far'>,
  alphas: ReadonlyMap<ElementId, number>,
  overrides: Pick<OverrideSettings, 'userHides' | 'userPins' | 'projectPins'>,
  farMode: FarMode,
): void {
  const n = state.alpha.length;
  for (let i = 0; i < n; i++) state.flags[i] = (state.flags[i] ?? 0) & FLAG_SELECTED;

  for (const [id, a] of alphas) if (id >= 0 && id < n) state.alpha[id] = a;
  for (const id of classification.far) {
    if (id < 0 || id >= n) continue;
    state.alpha[id] = farMode === 'hidden' ? 1 : (alphas.get(id) ?? 1);
    if (farMode === 'hidden') state.flags[id] = (state.flags[id] ?? 0) | FLAG_HIDDEN;
  }
  for (const id of classification.focus) {
    if (id < 0 || id >= n) continue;
    state.alpha[id] = 1;
    state.flags[id] = (state.flags[id] ?? 0) | FLAG_FOCUS;
  }
  for (const id of overrides.userHides) {
    if (id >= 0 && id < n) state.flags[id] = (state.flags[id] ?? 0) | FLAG_HIDDEN;
  }
  const pin = (id: number): void => {
    if (id >= 0 && id < n) state.flags[id] = (state.flags[id] ?? 0) | FLAG_PINNED;
  };
  for (const id of overrides.userPins) pin(id);
  for (const key of Object.keys(overrides.projectPins)) pin(Number(key));
}

/** A fresh RenderState for n elements: opaque, white, no flags. */
export function createRenderState(n: number): RenderState {
  return { alpha: new Float32Array(n).fill(1), color: new Float32Array(n * 3).fill(1), flags: new Uint8Array(n) };
}
