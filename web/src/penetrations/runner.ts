// Penetration analysis over the loaded model: builds the PenInput (MEP set, hosts, openings, geometry callbacks)
// from the app and runs analysis.ts. Kept apart from the DOM so the plugin, the smoke test and scripts can call it.

import type { ViewerApp } from '../app';
import { analysePenetrations, principalAxis, summarise } from './analysis';
import type { Box6, PenElement, PenSummary, Penetration } from './analysis';

export const SCOPES = ['focus classes', 'focus only'] as const;
export type PenScope = (typeof SCOPES)[number];

/** Host classes: context classes that carry openings in practice. */
export const HOST_CLASS_RE = /slab|wall|beam|column|footing|roof/i;

export interface PenRun {
  rows: Penetration[];
  summary: PenSummary;
  ms: number;
  scope: PenScope;
  mepCount: number;
  hostCount: number;
  /** Whether the model carries opening bounds (otherwise every status is unknown unless hosted by relation). */
  hasOpeningData: boolean;
}

export function runPenetrations(app: ViewerApp, scope: PenScope): PenRun {
  const t0 = performance.now();
  const loaded = app.loaded;
  const geo = app.geometry;
  if (!loaded || !geo) return { rows: [], summary: summarise([]), ms: 0, scope, mepCount: 0, hostCount: 0, hasOpeningData: false };
  const model = loaded.model;
  const settings = app.controller.settings.classification;
  const focusClasses = new Set(settings.focusClasses);
  const hostClasses = new Set(settings.ctxClasses.filter((c) => HOST_CLASS_RE.test(c)));
  const focusNow = app.controller.classification.focus;

  const mep: PenElement[] = [];
  const hosts: PenElement[] = [];
  for (const e of model.elements) {
    if (!loaded.geometry.hasGeometry(e.id)) continue;
    const pe: PenElement = { id: e.id, ifcClass: e.ifcClass, storey: e.storey, bounds: e.bounds as Box6 };
    if (hostClasses.has(e.ifcClass)) hosts.push(pe);
    else if (scope === 'focus only' ? focusNow.has(e.id) : focusClasses.has(e.ifcClass)) mep.push(pe);
  }

  const axes = new Map<number, readonly [number, number, number] | null>();
  const axisOf = (id: number): readonly [number, number, number] | null => {
    if (axes.has(id)) return axes.get(id)!;
    const pts = geo.samplePoints(id, 48).map((p) => [p.x, p.y, p.z] as const);
    const a = principalAxis(pts);
    axes.set(id, a);
    return a;
  };

  const openings = model.relations.openings;
  const rows = analysePenetrations({
    mep,
    hosts,
    openings,
    hostedBy: model.relations.hosts,
    intersects: (a, b) => geo.intersects(a, b),
    axisOf,
  });
  return {
    rows,
    summary: summarise(rows),
    ms: performance.now() - t0,
    scope,
    mepCount: mep.length,
    hostCount: hosts.length,
    hasOpeningData: (openings?.length ?? 0) > 0,
  };
}
