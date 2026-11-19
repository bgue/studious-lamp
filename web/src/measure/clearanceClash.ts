// Clearance pairs (a context element too close to the focus) as clash results (src/issues/clash.ts). Pure: the plugin supplies how
// an element id reads. Tested in tests/issues-clash.test.ts.

import type { ClashResult } from '../issues/clash';
import { closestPoints, mmText, pairRegion } from '../issues/clash';
import type { Box6 } from '../bcf/plan';

export interface ClearanceClashContext {
  guid(id: number): string | undefined;
  label(id: number): string;
  /** Bounds of an element, viewer frame. */
  bounds(id: number): Box6 | null;
  /** The "tight" threshold of the run, metres. */
  tight: number;
}

/** Larger is worse: touching or overlapping is 1, the threshold itself 0. */
export function clearanceSeverity(d: number, tight: number): number {
  return tight > 0 ? 1 - Math.min(Math.max(d, 0), tight) / tight : 1;
}

export function clearanceResult(p: { focus: number; context: number; distance: number }, ctx: ClearanceClashContext): ClashResult | null {
  const a = ctx.guid(p.focus);
  const b = ctx.guid(p.context);
  const ba = ctx.bounds(p.focus);
  const bb = ctx.bounds(p.context);
  if (!a || !b || !ba || !bb) return null;
  const d = Math.max(0, p.distance);
  const [pa, pb] = closestPoints(ba, bb);
  const region = pairRegion(ba, bb, d);
  const touching = d <= 1e-6;
  const label = mmText(d);
  return {
    check: 'clearance', a, b, severity: clearanceSeverity(d, ctx.tight),
    title: `Clearance ${label} < ${mmText(ctx.tight)}: ${ctx.label(p.focus)} / ${ctx.label(p.context)}`,
    description: `${touching ? 'The elements touch or overlap' : `The surfaces are ${label} apart`}; the clearance asked for is ${mmText(ctx.tight)}.`,
    priority: touching ? 'High' : 'Normal',
    location: [(pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2, (pa[2] + pb[2]) / 2],
    region,
    attach: { kind: 'measurement', distanceM: d, label, pointA: pa, pointB: pb },
  };
}

export function clearanceResults(pairs: ReadonlyArray<{ focus: number; context: number; distance: number }>, ctx: ClearanceClashContext): ClashResult[] {
  const out: ClashResult[] = [];
  for (const p of pairs) {
    const x = clearanceResult(p, ctx);
    if (x) out.push(x);
  }
  return out;
}
