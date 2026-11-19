// Penetration rows as clash results (src/issues/clash.ts): the title, the description, the severity and the region the camera
// frames. Pure: the plugin supplies how an element id reads. Tested in tests/issues-clash.test.ts.

import type { Penetration, PenStatus } from './analysis';
import type { ClashResult } from '../issues/clash';
import type { Box6 } from '../bcf/plan';

export interface PenClashContext {
  guid(id: number): string | undefined;
  label(id: number): string;
  storeyName(s: number | null): string;
}

export const STATUS_TEXT: Record<PenStatus, string> = { none: 'no opening', opening: 'opening', unknown: 'unknown' };

/** Larger is worse: no opening, then an opening too small for the element, then unknown, then a fitting opening. */
export function penetrationSeverity(r: Pick<Penetration, 'status' | 'gapMm' | 'sizeMm'>): number {
  const base = r.status === 'none' ? 4000 : r.status === 'opening' && r.gapMm !== null && r.gapMm < 0 ? 3000 : r.status === 'unknown' ? 2000 : 1000;
  return base + Math.min(999, Math.max(r.sizeMm[0], r.sizeMm[1])) / 1000;
}

export function penetrationResult(r: Penetration, ctx: PenClashContext): ClashResult | null {
  const a = ctx.guid(r.mep);
  const b = ctx.guid(r.host);
  if (!a || !b) return null;
  const sev = penetrationSeverity(r);
  const [x, y, z] = r.location;
  const half = Math.max(0.75, (2 * Math.max(r.sizeMm[1], r.hostThicknessMm)) / 1000);
  const region: Box6 = [x - half, y - half, z - half, x + half, y + half, z + half];
  return {
    check: 'penetration', a, b, severity: sev,
    title: `Penetration: ${ctx.label(r.mep)} through ${ctx.label(r.host)}`,
    description:
      `${STATUS_TEXT[r.status]}${r.gapMm !== null ? `, gap ${r.gapMm} mm` : ''}; ${r.orientation}; ${r.sizeMm[0]} x ${r.sizeMm[1]} mm; ` +
      `host thickness ${r.hostThicknessMm} mm; storey ${ctx.storeyName(r.storey)}`,
    priority: sev >= 3000 ? 'High' : sev >= 2000 ? 'Normal' : 'Low',
    location: [x, y, z],
    region,
    attach: { kind: 'penetration' },
  };
}

/** Every row that has GlobalIds on both elements, as results (rows without are left out). */
export function penetrationResults(rows: readonly Penetration[], ctx: PenClashContext): ClashResult[] {
  const out: ClashResult[] = [];
  for (const r of rows) {
    const x = penetrationResult(r, ctx);
    if (x) out.push(x);
  }
  return out;
}
