// The pure metric functions of bench/real-classify-truth.mjs.
import { describe, expect, it } from 'vitest';
// @ts-expect-error plain .mjs without types
import * as M from '../bench/truth-metrics.mjs';

const item = (pred: string | null, truth: string, conf = 1, alt: string[] = [], extra: Record<string, unknown> = {}) => M.makeItem({ key: `${truth}${pred}${conf}${Math.random()}`, pred, truth, conf, alt, ...extra });

describe('truth metrics', () => {
  it('strict and lenient accuracy, abstain counts as wrong', () => {
    const items = [item('A', 'A'), item('B', 'A', 1, ['B']), item('C', 'A'), item(null, 'A')];
    expect(M.accuracy(items)).toBeCloseTo(0.25);
    expect(M.lenientAccuracy(items)).toBeCloseTo(0.5);
    expect(M.fallbackRate(items)).toBeCloseTo(0.25);
    expect(M.judge('x', 'y', ['x'])).toEqual({ ok: false, okLenient: true });
  });

  it('coverage and precision at the threshold (inclusive), abstains never clear it', () => {
    const items = [item('A', 'A', 0.9), item('B', 'A', 0.6), item('A', 'A', 0.59), item(null, 'A'), item('B', 'B', 0.2)];
    expect(M.coverage(items, 0.6)).toBeCloseTo(2 / 5);
    expect(M.precisionAtMin(items, 0.6)).toBeCloseTo(0.5);
    expect(M.precisionAtMin(items, 0.95)).toBeNaN();
    expect(M.precisionAtMin([item('B', 'A', 0.9, ['B'])], 0.6, true)).toBe(1);
  });

  it('ECE with 10 bins', () => {
    // confidence 1, always right: 0. Confidence 0.95, half right: |0.5 - 0.95|.
    expect(M.ece([item('A', 'A'), item('A', 'A')])).toBeCloseTo(0);
    expect(M.ece([item('A', 'A', 0.95), item('B', 'A', 0.95)])).toBeCloseTo(0.45);
    // two bins: 0.15 (1 of 2 right -> 0.35 gap, weight 0.5) and 0.85 (1 of 2 right -> 0.35 gap, weight 0.5)
    expect(M.ece([item('A', 'A', 0.15), item('B', 'A', 0.15), item('A', 'A', 0.85), item('B', 'A', 0.85)])).toBeCloseTo(0.35);
    expect(M.ece([item(null, 'A')])).toBeNaN();
  });

  it('top confusions are sorted and capped', () => {
    const items = [item('B', 'A'), item('B', 'A'), item('C', 'A'), item(null, 'D'), item('A', 'A')];
    const c = M.topConfusions(items, 2);
    expect(c).toEqual([{ pair: 'A -> B', count: 2 }, { pair: 'A -> C', count: 1 }]);
  });

  it('chained versus oracle bookkeeping', () => {
    const k = (key: string, chOk: boolean, discOk: boolean, orOk: boolean) => [
      M.makeItem({ key, pred: chOk ? 'S' : 'X', truth: 'S', discOk }),
      M.makeItem({ key, pred: orOk ? 'S' : 'X', truth: 'S' }),
    ];
    const rows = [k('a', true, true, true), k('b', false, false, true), k('c', false, true, true), k('d', false, true, false), k('e', true, true, false)];
    const r = M.compareChainedOracle(rows.map((x) => x[0]), rows.map((x) => x[1]));
    expect(r).toMatchObject({ n: 5, bothRight: 1, chainedOnly: 1, oracleOnly: 2, bothWrong: 1, chainedWrongDiscipline: 1, lostToDiscipline: 1 });
    expect(r.chainedAccuracy).toBeCloseTo(2 / 5);
    expect(r.oracleAccuracy).toBeCloseTo(3 / 5);
    expect(r.gap).toBeCloseTo(0.2);
    expect(r.chainedAccuracyGivenDisciplineRight).toBeCloseTo(2 / 4);
  });

  it('majority, group truth and summarise', () => {
    expect(M.mostFrequent(['a', 'b', 'b', null]).value).toBe('b');
    expect(M.groupTruth([{ v: 'x' }, { v: 'y', a: ['x'] }, { v: 'y', a: ['z'] }], (m: { v: string; a?: string[] }) => ({ value: m.v, alt: m.a })).alt).toEqual(['x']);
    const s = M.summarise([item('A', 'A', 0.9), item('B', 'A', 0.7)], 0.6);
    expect(s).toMatchObject({ n: 2, accuracy: 0.5, coverage: 1, precision: 0.5 });
    expect(M.fnv('abc')).toHaveLength(8);
  });
});
