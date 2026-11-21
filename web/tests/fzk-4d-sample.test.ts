// The sample 4D schedule for FZK-Haus (public/samples/fzk-haus.xer, made by tools/make_fzk_xer.py) and its configuration
// (public/samples/fzk-haus.4d.json) must link every element of the house to exactly one building activity, by the
// activity's Level code (-> storey) and Trade code (-> element query).
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { parseXer } from '../src/schedule/xer';
import { runQuery } from '../src/query';
import type { SceneModel } from '../src/types';
import type { FourDConfig } from '../src/schedule/types';

const file = (p: string): string => fileURLToPath(new URL(p, import.meta.url));
const xer = parseXer(readFileSync(file('../public/samples/fzk-haus.xer')));
const config = JSON.parse(readFileSync(file('../public/samples/fzk-haus.4d.json'), 'utf8')) as FourDConfig;
const raw = JSON.parse(readFileSync(file('../public/models/fzk-haus.json'), 'utf8')) as SceneModel & { elements: Array<{ globalId: string; storey: number; name: string; ifcClass: string }> };
const model = { ...raw, byGlobalId: new Map(raw.elements.map((e, i) => [e.globalId, i])) } as unknown as SceneModel;
const storeyName = (i: number): string => raw.storeys.find((s) => s.id === raw.elements[i]!.storey)?.name ?? '';

describe('FZK-Haus sample schedule', () => {
  it('parses without warnings, with a data date, codes and a critical path', () => {
    expect(xer.warnings).toEqual([]);
    expect(xer.project.shortName).toBe('FZK-HAUS');
    expect(xer.project.dataDate).toBe('2027-05-19T08:00');
    expect(Object.keys(xer.codeTypes).sort()).toEqual(['Level', 'Phase', 'Trade']);
    expect(xer.tasks.filter((t) => t.driving).length).toBeGreaterThan(10);
    expect(xer.tasks.some((t) => t.status === 'active')).toBe(true);
  });

  it('links every element to exactly one building activity by level and trade', () => {
    const owner = new Map<number, string[]>();
    for (const t of xer.tasks) {
      const q = config.tradeQueries?.[t.codes.Trade ?? ''];
      if (!q || t.type === 'milestone' || t.type === 'finishMilestone') continue;
      const r = runQuery(model, q);
      expect(r.error, `${t.code}: ${q}`).toBeNull();
      const level = config.values?.location?.[t.codes.Level ?? ''];
      const ids = r.ids.filter((i) => !level || storeyName(i) === level);
      expect(ids.length, `${t.code} ${t.name} builds something`).toBeGreaterThan(0);
      for (const i of ids) owner.set(i, [...(owner.get(i) ?? []), t.code]);
    }
    const unowned = raw.elements.map((e, i) => (owner.has(i) ? null : `${e.ifcClass} ${e.name}`)).filter(Boolean);
    const twice = [...owner].filter(([, c]) => c.length > 1).map(([i, c]) => `${raw.elements[i]!.name}: ${c.join(', ')}`);
    expect(twice).toEqual([]);
    expect(unowned).toEqual([]);
  });
});
