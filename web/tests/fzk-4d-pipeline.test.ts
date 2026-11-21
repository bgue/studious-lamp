// End to end on the FZK-Haus sample: XER -> parser -> linker (attributes tier) -> report -> plan (planned, actual, lookahead).
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { parseXer } from '../src/schedule/xer';
import { fromSidecar } from '../src/schedule/model';
import { linkSchedule } from '../src/schedule/link';
import { buildReport, renderReportHtml } from '../src/schedule/report';
import { buildPlan } from '../src/schedule/plan';
import type { FourDConfig } from '../src/schedule/types';

const file = (p: string): string => fileURLToPath(new URL(p, import.meta.url));
const schedule = parseXer(readFileSync(file('../public/samples/fzk-haus.xer')));
const config = JSON.parse(readFileSync(file('../public/samples/fzk-haus.4d.json'), 'utf8')) as FourDConfig;
const model = fromSidecar(JSON.parse(readFileSync(file('../public/models/fzk-haus.json'), 'utf8')), { identityKey: 'fzk-sample' });
const links = linkSchedule(schedule, model, config, []);

describe('FZK-Haus 4D pipeline', () => {
  it('links every element by level and trade, with reasons, no ties and no unlinked elements', () => {
    const linked = new Set(links.links?.filter((l) => l.status === 'accepted' && l.role === 'build').flatMap((l) => l.elements));
    expect(linked.size).toBe(model.elements.length);
    expect(links.ties ?? []).toEqual([]);
    expect(links.unlinked_elements ?? []).toEqual([]);
    expect(links.links?.every((l) => (l.reasons ?? []).length > 0)).toBe(true);
  });

  it('reports full element coverage and lists the activities without geometry', () => {
    const r = buildReport(schedule, links, model);
    expect(r.coverage.elements.byCount).toBeCloseTo(1, 5);
    const html = renderReportHtml(r);
    expect(html).toContain('<table');
    expect(html).toContain('Screed drying');
  });

  it('plans a 90 s film in planned, actual and lookahead views', () => {
    for (const view of ['planned', 'actual'] as const) {
      const plan = buildPlan(schedule, links, model, { ...config.style, view });
      expect(plan.elements.length).toBe(model.elements.length);
      const last = plan.timeMap[plan.timeMap.length - 1]!;
      expect(last[1]).toBeCloseTo(90, 0);
      for (let i = 1; i < plan.timeMap.length; i++) expect(plan.timeMap[i]![1]).toBeGreaterThanOrEqual(plan.timeMap[i - 1]![1]);
      expect(plan.milestones.map((m) => m.name)).toContain('Building weathertight');
      expect(plan.tasks.some((t) => t.critical)).toBe(true);
    }
    const look = buildPlan(schedule, links, model, { ...config.style, window: { kind: 'lookahead', from: 'dataDate', weeks: 6 } });
    const dd = Date.UTC(2027, 4, 19, 8);
    expect(look.window.from).toBe(dd);
    expect(look.window.to - look.window.from).toBe(6 * 7 * 86400000);
    // the slab poured in March is already complete when a lookahead from May starts
    const slab = model.elements.find((e) => e.name === 'Bodenplatte')!;
    const tl = look.elements.find((e) => e.globalId === slab.globalId)!;
    expect(tl.intervals[0]!.state).toBe('complete');
  });
});
