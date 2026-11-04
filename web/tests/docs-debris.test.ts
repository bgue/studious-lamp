// The debris-demo sample model (tools/synth_model.py --debris 24 -n 400): its sidecar, its "Debris" selection set and what the
// cleanup defaults find in it. Pure: reads public/models/debris-demo.json, no browser.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { analyse, defaultRules } from '../src/cleanup/analysis';
import type { CleanupElement } from '../src/cleanup/analysis';
import { DEFAULT_SETS, defaultSetsFor } from '../src/selectionSets';
import type { SceneModel } from '../src/types';

interface Side { schema: string; elements: Array<{ id: number; globalId: string; ifcClass: string; name: string; storey: number | null; bounds: [number, number, number, number, number, number] }>; storeys: unknown[] }
const side = JSON.parse(readFileSync(fileURLToPath(new URL('../public/models/debris-demo.json', import.meta.url)), 'utf8')) as Side;
const isDebris = (name: string): boolean => name.startsWith('Debris');
const elements: CleanupElement[] = side.elements.map((e) => ({ id: e.id, ifcClass: e.ifcClass, bounds: e.bounds }));
const nameOf = (id: number): string => side.elements[id]!.name;

describe('debris-demo model', () => {
  it('is registered as a sample model with a Debris selection set', () => {
    // app.ts runs the viewer on import, so read the source text instead
    const read = (p: string): string => readFileSync(fileURLToPath(new URL(p, import.meta.url)), 'utf8');
    expect(read('../src/app.ts')).toMatch(/MODEL_NAMES = \[[^\]]*'debris-demo'/);
    expect(read('../tools/build-single-file.mjs')).toMatch(/name: 'debris-demo'/);
    expect(DEFAULT_SETS['debris-demo']!.map((d) => d.name)).toEqual(['Debris']);
  });

  it('has the xray-model/1 schema and about 400 elements, 31 of them debris', () => {
    expect(side.schema).toBe('xray-model/1');
    expect(side.elements.length).toBe(400);
    expect(side.elements.filter((e) => isDebris(e.name)).length).toBe(24 + 7);
  });

  it('the Debris set lists exactly the elements named Debris', () => {
    const model = { elements: side.elements, storeys: side.storeys, byGlobalId: new Map() } as unknown as SceneModel;
    const sets = defaultSetsFor(model, 'debris-demo');
    expect(sets.map((s) => s.name)).toEqual(['Debris']);
    const want = side.elements.filter((e) => isDebris(e.name)).map((e) => e.globalId);
    expect(sets[0]!.globalIds).toEqual(want);
  });

  it('cleanup defaults find the floating items, the far stray, the duplicates and the degenerate wall, and no structure', () => {
    const res = analyse(elements, defaultRules());
    const matched = res.ids.map(nameOf);
    expect(matched.every(isDebris)).toBe(true);
    expect(matched.filter((n) => n.startsWith('Debris bolt')).length).toBe(14);
    expect(matched.filter((n) => n.startsWith('Debris offcut')).length).toBe(10);
    expect(matched).toContain('Debris far stray');
    expect(matched).toContain('Debris duplicate beam 1');
    expect(matched).toContain('Debris duplicate beam 2');
    expect(matched).toContain('Debris zero-thickness wall');
    expect(res.counts.strays).toBe(1);
    expect(res.counts.duplicates).toBe(2);
    expect(res.counts.degenerate).toBe(1);
    // the touching cluster has contacts, so only mode 'small clusters' matches it
    expect(matched.some((n) => n.startsWith('Debris cluster'))).toBe(false);
  });

  it("mode 'small clusters' also matches the three touching boxes", () => {
    const rules = defaultRules();
    rules.floating.mode = 'small clusters';
    const matched = analyse(elements, rules).ids.map(nameOf);
    expect(matched.filter((n) => n.startsWith('Debris cluster')).length).toBe(3);
    expect(matched.every(isDebris)).toBe(true);
  });
});
