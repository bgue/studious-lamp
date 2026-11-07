// Search index on a synthetic model of 100,000 elements: build time and query times. The numbers go to the report
// (console) and the assertions keep a query well under the 20 ms of the task on a normal machine.

import { describe, expect, it } from 'vitest';
import { ElementIndex } from '../src/search/elementIndex';
import { termsOf } from '../src/search/fuzzy';
import { detectQuery, runLive } from '../src/search/queryMode';
import type { ElementRecord, SceneModel } from '../src/types';

const N = 100_000;
const CLASSES = ['IfcWall', 'IfcSlab', 'IfcDuctSegment', 'IfcPipeSegment', 'IfcBeam', 'IfcColumn', 'IfcDoor', 'IfcWindow', 'IfcCableCarrierSegment', 'IfcFlowTerminal'];
const MATERIALS = ['Concrete C30/37', 'Galvanised steel', 'Brick', 'Timber', 'Copper', 'PVC'];

function synthetic(n: number): SceneModel {
  const storeys = Array.from({ length: 20 }, (_, i) => ({ id: i, name: `Level ${i + 1}`, elevation: i * 3 }));
  const elements: ElementRecord[] = new Array(n);
  for (let i = 0; i < n; i++) {
    const cls = CLASSES[i % CLASSES.length]!;
    elements[i] = {
      id: i,
      globalId: `${(i * 2654435761 >>> 0).toString(36).padStart(7, '0')}${i.toString(36).padStart(5, '0')}$aB`,
      ifcClass: cls,
      name: `${cls.slice(3)} ${(i * 7919) % 100003}`,
      storey: i % 20,
      material: MATERIALS[i % MATERIALS.length],
      color: [0.7, 0.7, 0.7, 1],
      bounds: [i % 100, 0, Math.floor(i / 100) % 100, (i % 100) + 1, 1, (Math.floor(i / 100) % 100) + 1],
      props: {
        'Pset_Common.FireRating': `${(i % 4) + 1}h`,
        'Pset_Common.Reference': `REF-${i % 5000}`,
        'Pset_Common.IsExternal': i % 3 === 0,
        'Qto_Base.NetVolume': (i % 97) / 10,
        'Attr.Tag': `T${i}`,
        'Attr.ObjectType': `Type ${i % 40}`,
        'Pset_Mep.System': `System ${i % 25}`,
        'Pset_Mep.Flow': (i % 300) / 7,
      },
    };
  }
  return {
    schema: 'xray-model/1',
    units: 'm',
    originShift: [0, 0, 0],
    storeys,
    elements,
    relations: { voids: [], fills: [], hosts: [], ports: [], systems: [] },
    byGlobalId: new Map(),
  };
}

const median = (xs: number[]): number => [...xs].sort((a, b) => a - b)[Math.floor(xs.length / 2)]!;

function time<T>(fn: () => T, reps = 7): { ms: number; out: T } {
  const t: number[] = [];
  let out!: T;
  for (let i = 0; i < reps; i++) {
    const t0 = performance.now();
    out = fn();
    t.push(performance.now() - t0);
  }
  return { ms: median(t), out };
}

describe('search index at 100,000 elements', () => {
  const m = synthetic(N);

  it('builds once, then answers queries fast', () => {
    const t0 = performance.now();
    const idx = new ElementIndex(m).buildAll();
    const build = performance.now() - t0;
    expect(idx.ready).toBe(true);

    const queries = ['wall', 'duct 5', 'level 12 beam', 'galvanised', 'fire 2h', 'ifcdoor', 'zzzz', 'rdct', 'ref-4999', 'a'];
    const rows: string[] = [];
    let worst = 0;
    for (const q of queries) {
      const terms = termsOf(q);
      const { ms, out } = time(() => idx.search(terms, 200));
      worst = Math.max(worst, ms);
      rows.push(`${q.padEnd(14)} ${ms.toFixed(1).padStart(6)} ms  ${String(out.total).padStart(6)} matches`);
    }
    const wh = time(() => runLive(m, "class = 'IfcDuctSegment' and storey like '%1%'"), 5);
    console.log(`[search-index] ${N} elements: index build ${build.toFixed(0)} ms\n${rows.join('\n')}\nWHERE query (class and storey like) ${wh.ms.toFixed(1)} ms, ${wh.out.count} matches`);
    // The task asks for under about 20 ms. Leave a margin for a busy CI machine, and keep the typical case tight.
    expect(worst).toBeLessThan(60);
    const typical = median(queries.map((q) => time(() => idx.search(termsOf(q), 200), 5).ms));
    expect(typical).toBeLessThan(20);
    expect(build).toBeLessThan(4000);
    expect(wh.out.count).toBeGreaterThan(0);
  });

  it('ranks the exact name first at this size', () => {
    const idx = new ElementIndex(m).buildAll();
    const target = m.elements[54321]!;
    const r = idx.search(termsOf(target.name!), 5);
    expect(r.hits[0]!.id === 54321 || m.elements[r.hits[0]!.id]!.name === target.name).toBe(true);
  });

  it('detects the query forms quickly (it runs on every key)', () => {
    const { ms } = time(() => {
      for (let i = 0; i < 1000; i++) detectQuery("class = 'IfcDuctSegment' and storey like '%1%'");
    });
    expect(ms).toBeLessThan(50);
  });
});
