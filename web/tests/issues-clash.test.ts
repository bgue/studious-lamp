import { describe, expect, it } from 'vitest';
import { MAX_BATCH, clashKey, clashRef, closestPoints, countsOf, countsText, isClashCheck, pairRegion, planClashRaise, resultKey, topBySeverity } from '../src/issues/clash';
import type { ClashResult, ExistingClash } from '../src/issues/clash';
import { penetrationResult, penetrationResults, penetrationSeverity } from '../src/penetrations/clash';
import type { Penetration } from '../src/penetrations/analysis';
import { clearanceResult, clearanceResults, clearanceSeverity } from '../src/measure/clearanceClash';
import { applySidecar, parseSidecar, sidecarJson } from '../src/bcf/sidecar';
import type { BcfTopic } from '../src/bcf/model';

const r = (check: 'penetration' | 'clearance', a: string, b: string, severity = 1): ClashResult => ({
  check, a, b, severity, title: `${check} ${a}/${b}`, description: '', priority: 'Normal', location: [0, 0, 0], region: [0, 0, 0, 1, 1, 1], attach: { kind: 'penetration' },
});
const ex = (check: 'penetration' | 'clearance', a: string, b: string, o: { open?: boolean; missing?: boolean } = {}): ExistingClash => ({
  topic: `t-${check}-${a}-${b}`, ref: { ...clashRef(check, a, b), ...(o.missing ? { missing: '2026-02-01T00:00:00.000Z' } : {}) }, open: o.open ?? true,
});

describe('clash key', () => {
  it('is the check type plus the sorted GlobalId pair, so either order is one result', () => {
    expect(clashKey('penetration', 'B', 'A')).toBe('penetration|A|B');
    expect(clashKey('penetration', 'A', 'B')).toBe(clashKey('penetration', 'B', 'A'));
  });
  it('differs by check type, and by pair', () => {
    expect(clashKey('clearance', 'A', 'B')).not.toBe(clashKey('penetration', 'A', 'B'));
    expect(clashKey('penetration', 'A', 'B')).not.toBe(clashKey('penetration', 'A', 'C'));
  });
  it('is not confused by GlobalIds that contain the separator-free characters of base 64', () => {
    expect(clashKey('penetration', '2O2Fr$t4X7Zf8NOew3FLOH', '3cUkl32yn9qRSPvBJVyWYp')).toBe('penetration|2O2Fr$t4X7Zf8NOew3FLOH|3cUkl32yn9qRSPvBJVyWYp');
  });
  it('makes the ref the topic stores, with the sorted pair', () => {
    expect(clashRef('clearance', 'Z', 'A')).toEqual({ check: 'clearance', key: 'clearance|A|Z', a: 'A', b: 'Z' });
    expect(resultKey(r('clearance', 'Z', 'A'))).toBe('clearance|A|Z');
    expect(isClashCheck('penetration')).toBe(true);
    expect(isClashCheck('x')).toBe(false);
  });
  it('has a batch limit of 200', () => expect(MAX_BATCH).toBe(200));
});

describe('planClashRaise (the merge)', () => {
  const all = [r('penetration', 'A', 'B'), r('penetration', 'C', 'D'), r('penetration', 'E', 'F')];

  it('raises everything on a first run', () => {
    const p = planClashRaise('penetration', [], all, all);
    expect(p.fresh.length).toBe(3);
    expect(p.already.length).toBe(0);
    expect(countsOf(p)).toEqual({ fresh: 3, already: 0, resolved: 0 });
  });

  it('a re-run with the same results raises nothing: no doubles', () => {
    const existing = [ex('penetration', 'A', 'B'), ex('penetration', 'D', 'C'), ex('penetration', 'E', 'F')]; // D, C reversed
    const p = planClashRaise('penetration', existing, all, all);
    expect(p.fresh).toEqual([]);
    expect(p.already.map((x) => x.topic)).toEqual(['t-penetration-A-B', 't-penetration-D-C', 't-penetration-E-F']);
    expect(p.resolved).toEqual([]);
  });

  it('raises only the new results of a changed run', () => {
    const existing = [ex('penetration', 'A', 'B')];
    const p = planClashRaise('penetration', existing, all, all);
    expect(p.fresh.map(resultKey)).toEqual(['penetration|C|D', 'penetration|E|F']);
    expect(p.already.length).toBe(1);
  });

  it('counts a result twice in the input once', () => {
    const p = planClashRaise('penetration', [], all, [...all, r('penetration', 'B', 'A')]);
    expect(p.fresh.length).toBe(3);
  });

  it('finds results that no longer occur, flags them once, and offers to close the open ones', () => {
    const existing = [ex('penetration', 'A', 'B'), ex('penetration', 'X', 'Y'), ex('penetration', 'P', 'Q', { missing: true }), ex('penetration', 'M', 'N', { open: false })];
    const p = planClashRaise('penetration', existing, all, all);
    expect(p.resolved.map((e) => e.ref.key)).toEqual(['penetration|X|Y', 'penetration|P|Q', 'penetration|M|N']);
    expect(p.toFlag.map((e) => e.ref.key)).toEqual(['penetration|X|Y', 'penetration|M|N']); // P-Q has the note already
    expect(p.toClose.map((e) => e.ref.key)).toEqual(['penetration|X|Y', 'penetration|P|Q']); // M-N is closed already
    expect(countsOf(p)).toEqual({ fresh: 2, already: 1, resolved: 3 });
    expect(countsText(countsOf(p))).toBe('2 new, 1 already raised, 3 not found in the latest run');
  });

  it('a pair that comes back is reported, and is not resolved', () => {
    const p = planClashRaise('penetration', [ex('penetration', 'A', 'B', { missing: true })], all, all);
    expect(p.backAgain.map((e) => e.ref.key)).toEqual(['penetration|A|B']);
    expect(p.resolved).toEqual([]);
  });

  it('judges only the issues of the same check', () => {
    const p = planClashRaise('penetration', [ex('clearance', 'A', 'B'), ex('clearance', 'X', 'Y')], all, all);
    expect(p.already).toEqual([]);
    expect(p.fresh.length).toBe(3); // the same pair as a clearance issue is a different result
    expect(p.resolved).toEqual([]);
  });

  it('leaves out of the judgement what the run could not have found (another focus or scope)', () => {
    const existing = [ex('penetration', 'X', 'Y'), ex('penetration', 'U', 'V')];
    const p = planClashRaise('penetration', existing, all, all, (a) => a === 'X');
    expect(p.resolved.map((e) => e.ref.key)).toEqual(['penetration|X|Y']);
  });

  it('chosen is a subset: results outside it are not raised and do not make issues resolved', () => {
    const existing = [ex('penetration', 'C', 'D')];
    const p = planClashRaise('penetration', existing, all, [all[0]!]);
    expect(p.fresh.map(resultKey)).toEqual(['penetration|A|B']);
    expect(p.already).toEqual([]);
    expect(p.resolved).toEqual([]); // C-D is in the full run, only not chosen
  });

  it('the first of several issues with one key stands', () => {
    const a = ex('penetration', 'A', 'B');
    const b = { ...ex('penetration', 'B', 'A'), topic: 'other' };
    const p = planClashRaise('penetration', [a, b], all, all);
    expect(p.already.find((x) => resultKey(x.result) === 'penetration|A|B')!.topic).toBe(a.topic);
  });

  it('raising the same chosen set twice in a row makes no second issue (merge of the first result into the second plan)', () => {
    const first = planClashRaise('penetration', [], all, all);
    const made = first.fresh.map((x) => ex('penetration', x.a, x.b));
    const second = planClashRaise('penetration', made, all, all);
    expect(second.fresh.length).toBe(0);
    expect(second.already.length).toBe(all.length);
  });
});

describe('top N by severity', () => {
  it('keeps the worst N, worst first, and the input order among equals', () => {
    const list = [r('penetration', 'a', 'b', 1), r('penetration', 'c', 'd', 5), r('penetration', 'e', 'f', 3), r('penetration', 'g', 'h', 5), r('penetration', 'i', 'j', 3)];
    expect(topBySeverity(list, 3).map((x) => x.a)).toEqual(['c', 'g', 'e']);
    expect(topBySeverity(list, 0)).toEqual([]);
    expect(topBySeverity(list, 99).length).toBe(5);
    expect(list[0]!.a).toBe('a'); // the input is not reordered
  });
});

describe('pair geometry', () => {
  it('frames the region where two long elements are close, not their union', () => {
    const pipe: [number, number, number, number, number, number] = [0, 0, 0, 20, 0.2, 0.2];
    const beam: [number, number, number, number, number, number] = [15, 0.3, -0.1, 15.3, 0.5, 5];
    const reg = pairRegion(pipe, beam, 0.1);
    expect(reg[3] - reg[0]).toBeLessThan(3);
    expect(reg[0]).toBeGreaterThan(13);
  });
  it('falls back to the union when they are far apart', () => {
    const reg = pairRegion([0, 0, 0, 1, 1, 1], [10, 0, 0, 11, 1, 1], 0.1);
    expect(reg[0]).toBeLessThanOrEqual(0);
    expect(reg[3]).toBeGreaterThanOrEqual(11);
  });
  it('closest points of two boxes lie one on each, along the gap', () => {
    const [p, q] = closestPoints([0, 0, 0, 1, 1, 1], [3, 0, 0, 4, 1, 1]);
    expect(p[0]).toBe(1);
    expect(q[0]).toBe(3);
    expect(p[1]).toBeCloseTo(q[1]);
    const [m, n] = closestPoints([0, 0, 0, 2, 2, 2], [1, 1, 1, 3, 3, 3]); // overlapping: the same point
    expect(m).toEqual(n);
  });
});

describe('penetration results', () => {
  const pen = (o: Partial<Penetration> = {}): Penetration => ({ id: 1, mep: 10, host: 20, storey: 0, location: [1, 2, 3], orientation: 'vertical' as Penetration['orientation'], sizeMm: [200, 300], hostThicknessMm: 250, status: 'none', gapMm: null, openingExpressId: null, ...o });
  const ctx = { guid: (id: number) => (id === 99 ? undefined : `G${id}`), label: (id: number) => (id === 10 ? 'Duct-12' : id === 20 ? 'Wall-3' : `E${id}`), storeyName: (s: number | null) => (s === null ? '-' : `Level ${s}`) };

  it('titles "Penetration: Duct-12 through Wall-3" and carries both GlobalIds', () => {
    const x = penetrationResult(pen(), ctx)!;
    expect(x.title).toBe('Penetration: Duct-12 through Wall-3');
    expect([x.a, x.b]).toEqual(['G10', 'G20']);
    expect(x.check).toBe('penetration');
    expect(x.attach).toEqual({ kind: 'penetration' });
    expect(x.description).toContain('no opening');
    expect(x.description).toContain('Level 0');
    expect(x.priority).toBe('High');
    expect(x.region[0]).toBeLessThan(1);
    expect(x.region[3]).toBeGreaterThan(1);
  });
  it('ranks no opening above a too small opening above unknown above a fitting opening', () => {
    const s = (o: Partial<Penetration>): number => penetrationSeverity(pen(o));
    expect(s({ status: 'none' })).toBeGreaterThan(s({ status: 'opening', gapMm: -5 }));
    expect(s({ status: 'opening', gapMm: -5 })).toBeGreaterThan(s({ status: 'unknown' }));
    expect(s({ status: 'unknown' })).toBeGreaterThan(s({ status: 'opening', gapMm: 20 }));
    expect(s({ status: 'none', sizeMm: [500, 600] })).toBeGreaterThan(s({ status: 'none', sizeMm: [100, 100] }));
  });
  it('leaves out rows whose elements have no GlobalId', () => {
    expect(penetrationResults([pen(), pen({ id: 2, mep: 99 })], ctx).length).toBe(1);
  });
  it('the key does not depend on which element is named first', () => {
    const x = penetrationResult(pen(), ctx)!;
    const y = penetrationResult(pen({ mep: 20, host: 10 }), ctx)!;
    expect(resultKey(x)).toBe(resultKey(y));
  });
});

describe('clearance results', () => {
  const ctx = { guid: (id: number) => `G${id}`, label: (id: number) => (id === 1 ? 'Pipe-4' : 'Beam-9'), bounds: (id: number): [number, number, number, number, number, number] | null => (id === 1 ? [0, 0, 0, 2, 0.2, 0.2] : id === 2 ? [0, 0.32, 0, 6, 0.5, 0.4] : null), tight: 0.3 };

  it('titles "Clearance 120 mm < 300 mm: Pipe-4 / Beam-9" with a measurement attachment', () => {
    const x = clearanceResult({ focus: 1, context: 2, distance: 0.12 }, ctx)!;
    expect(x.title).toBe('Clearance 120 mm < 300 mm: Pipe-4 / Beam-9');
    expect([x.a, x.b]).toEqual(['G1', 'G2']);
    expect(x.attach.kind).toBe('measurement');
    if (x.attach.kind === 'measurement') {
      expect(x.attach.label).toBe('120 mm');
      expect(x.attach.distanceM).toBeCloseTo(0.12);
      expect(x.attach.pointB[1] - x.attach.pointA[1]).toBeCloseTo(0.12, 1);
    }
    expect(x.priority).toBe('Normal');
  });
  it('a touching pair is high priority and the most severe', () => {
    const t = clearanceResult({ focus: 1, context: 2, distance: 0 }, ctx)!;
    expect(t.priority).toBe('High');
    expect(t.severity).toBe(1);
    expect(clearanceSeverity(0.15, 0.3)).toBeCloseTo(0.5);
    expect(clearanceSeverity(0.3, 0.3)).toBe(0);
  });
  it('leaves out pairs without GlobalIds or bounds', () => {
    expect(clearanceResults([{ focus: 1, context: 2, distance: 0.1 }, { focus: 1, context: 7, distance: 0.1 }], ctx).length).toBe(1);
  });
});

describe('the side file keeps the clash ref of a topic', () => {
  const topic = (clash?: BcfTopic['clash']): BcfTopic => ({
    guid: '00000000-0000-4000-8000-000000000001', topicType: 'Clash', topicStatus: 'Open', title: 't', labels: ['clash', 'penetration'], referenceLinks: [], creationDate: '2026-01-01T00:00:00.000Z',
    creationAuthor: 'a', headerFiles: [], documentReferences: [], relatedTopics: [], comments: [], viewpoints: [], ...(clash ? { clash } : {}),
  });

  it('writes a side file for a topic with only a clash ref, and reads it back', () => {
    const t = topic({ ...clashRef('penetration', 'B', 'A'), missing: '2026-02-01T00:00:00.000Z' });
    const json = sidecarJson(t, '2.1')!;
    expect(json).toBeTruthy();
    const back = topic();
    applySidecar(back, parseSidecar(json));
    expect(back.clash).toEqual({ check: 'penetration', key: 'penetration|A|B', a: 'A', b: 'B', missing: '2026-02-01T00:00:00.000Z' });
  });
  it('writes nothing for a topic without markup, model or clash', () => {
    expect(sidecarJson(topic(), '2.1')).toBeNull();
  });
  it('ignores a clash entry that is not valid', () => {
    const read = parseSidecar(JSON.stringify({ format: 'xray-bcf-markup', version: 1, frame: 'ifc', units: 'm', topic: 'x', clash: { check: 'nope', a: 'A', b: 'B' }, viewpoints: {} }));
    expect(read.clash).toBeUndefined();
  });
});
