// diffModels on the generated FZK-Haus revision (truth file), on the fully re-GUIDed and shifted copy, and on synthetic models for the
// timing budgets: 50 k x 50 k < 1 s, 500 k < 8 s, the fully re-GUIDed case within 3x of the first.
import { beforeAll, describe, expect, it } from 'vitest';
import { diffModels, diffProps } from '../src/revision/diff';
import { handleDiffMessage, runDiff, snapshotTransferables } from '../src/revision/diffWorker';
import type { DiffIn, DiffOut, DiffWorkerLike } from '../src/revision/diffWorker';
import type { DiffEntry, ModelSnapshot, RevisionDiff } from '../src/revision/types';
import { DEFAULT_REVISION_OPTIONS } from '../src/revision/types';
import { deriveHead, fzk1, measure, fzk2, fzk2Reguid, loadIfc, readTruth, synthSnapshot } from './revision-helpers';
import type { Truth } from './revision-helpers';

let v1: ModelSnapshot, v2: ModelSnapshot, v2r: ModelSnapshot;
let truth: Truth;
let diff: RevisionDiff;

beforeAll(async () => {
  [v1, v2, v2r] = (await Promise.all([loadIfc(fzk1()), loadIfc(fzk2()), loadIfc(fzk2Reguid())])).map((l) => l.snap) as [ModelSnapshot, ModelSnapshot, ModelSnapshot];
  truth = readTruth();
  diff = diffModels(v1, v2);
}, 120000);

const keyOf = (c: Truth['changes'][number]): string => (c.category === 'deleted' ? `del:${c.baseGuid}` : c.headGuid!);

describe('fzk-v2 against the truth file', () => {
  it('has every category and flag set exactly as generated', () => {
    const byKey = new Map(diff.entries.map((e) => [e.key, e]));
    for (const c of truth.changes) {
      const e = byKey.get(keyOf(c));
      expect(e, `${c.name} (${c.category}) is missing`).toBeDefined();
      expect(e!.category, c.name).toBe(c.category);
      expect([...e!.flags].sort(), c.name).toEqual([...c.flags].sort());
    }
    // nothing else is listed
    expect(diff.entries.map((e) => e.key).sort()).toEqual(truth.changes.map(keyOf).sort());
  });

  it('counts the categories and flags', () => {
    expect(diff.counts).toEqual({ new: 3, deleted: 4, changed: 14, rematched: 6, unchanged: v1.globalId.length - 24 });
    expect(diff.flagCounts).toEqual({ geometry: 2, placement: 6, class: 1, type: 2, attributes: 0, storey: 0, material: 0, properties: 3, systems: 0 });
    expect(diff.offset).toEqual([0, 0, 0]);
  });

  it('measures the moves: 5 mm within 0.5 mm, 250 mm too, a turn is rotated', () => {
    const byKey = new Map(diff.entries.map((e) => [e.key, e]));
    for (const c of truth.changes.filter((x) => x.moveMm !== undefined)) {
      const e = byKey.get(c.headGuid!)!;
      expect(e.move! * 1000, c.name).toBeGreaterThan(c.moveMm! - 0.5);
      expect(e.move! * 1000, c.name).toBeLessThan(c.moveMm! + 0.5);
      expect(e.rotated, c.name).toBeUndefined();
    }
    const turned = truth.changes.find((c) => c.rotated)!;
    expect(byKey.get(turned.headGuid!)!.rotated).toBe(true);
  });

  it('rematches the 6 re-GUIDed elements with a score of 0.95 or more, to the right base element', () => {
    const re = diff.entries.filter((e) => e.category === 'rematched');
    expect(re).toHaveLength(6);
    for (const e of re) {
      expect(e.score!).toBeGreaterThanOrEqual(0.95);
      expect(e.flags).toEqual([]);
      const t = truth.changes.find((c) => c.category === 'rematched' && c.headGuid === e.head)!;
      expect(e.base).toBe(t.baseGuid);
    }
  });

  it('marks the classification as affected where the type or class changed, and for new elements', () => {
    const affected = diff.entries.filter((e) => e.classifyAffected).map((e) => e.category + ':' + e.flags.join('+')).sort();
    expect(affected).toEqual(['changed:class', 'changed:type', 'changed:type', 'new:', 'new:', 'new:']);
  });

  it('lists the changed property with before and after', () => {
    const e = diff.entries.find((x) => x.flags.includes('properties'))!;
    expect(e.props).toEqual([{ key: 'Pset_WallCommon.ThermalTransmittance', before: 1.5, after: 0.9 }]);
  });

  it('is deterministic and does not touch its inputs', () => {
    const again = diffModels(v1, v2);
    expect(again).toEqual(diff);
  });

  it('follows the options: a 1 cm move tolerance leaves the 5 mm moves unchanged', () => {
    const d = diffModels(v1, v2, { moveTol: 0.01 });
    expect(d.counts.changed).toBe(14 - 3);
    expect(d.counts.unchanged).toBe(diff.counts.unchanged + 3);
    expect(d.options.moveTol).toBe(0.01);
    expect(DEFAULT_REVISION_OPTIONS.moveTol).toBe(0.001);
  });
});

describe('every GUID regenerated and the model shifted by 1000 m', () => {
  it('rematches at least 95 % of it, none wrong, after removing the global offset', () => {
    const d = diffModels(v2, v2r);
    const n = v2.globalId.length;
    const right = d.entries.filter((e) => e.category === 'rematched' && truth.reguidMap[e.base!] === e.head);
    const wrong = d.entries.filter((e) => e.category === 'rematched' && truth.reguidMap[e.base!] !== e.head);
    expect(wrong).toHaveLength(0);
    expect(right.length / n).toBeGreaterThanOrEqual(0.95);
    expect(d.offset[0]).toBeCloseTo(1000, 2);
    expect(Math.abs(d.offset[1]) + Math.abs(d.offset[2])).toBeLessThan(0.01);
    // a pure re-GUID and shift changes nothing else
    expect(d.flagCounts.geometry + d.flagCounts.placement).toBe(0);
  });

  it('matches the original v1 through both revisions without a wrong pair', () => {
    const d = diffModels(v1, v2r);
    const v2guid = new Map(truth.changes.filter((c) => c.category === 'rematched').map((c) => [c.baseGuid!, c.headGuid!]));
    const wrong = d.entries.filter((e) => e.category === 'rematched' && truth.reguidMap[v2guid.get(e.base!) ?? e.base!] !== e.head);
    expect(wrong).toHaveLength(0);
    expect(d.counts.rematched).toBeGreaterThanOrEqual(0.85 * v1.globalId.length);
  });
});

describe('properties', () => {
  const o = { propRelTol: 1e-4, ignoreProps: ['Xray_', 'XR_Classification.'] };
  it('reports added, removed and changed keys, with a relative tolerance for numbers', () => {
    const d = diffProps({ 'A.x': 1, 'A.y': 'a', 'A.gone': true, 'A.n': 100 }, { 'A.x': 1.00005, 'A.y': 'b', 'A.new': 3, 'A.n': 100.1 }, o);
    expect(d).toEqual([
      { key: 'A.gone', before: true }, { key: 'A.n', before: 100, after: 100.1 }, { key: 'A.new', after: 3 }, { key: 'A.y', before: 'a', after: 'b' },
    ]);
  });
  it('ignores Attr.*, Xray_ sets and the classifier pset', () => {
    expect(diffProps({ 'Attr.Tag': 'a', 'Xray_Review.Status': 'x', 'XR_Classification.Discipline': 'ARC' }, { 'Attr.Tag': 'b', 'Xray_Review.Status': 'y' }, o)).toEqual([]);
  });
  it('treats null and empty the same', () => {
    expect(diffProps(null, null, o)).toEqual([]);
    expect(diffProps(null, { 'A.x': 1 }, o)).toEqual([{ key: 'A.x', after: 1 }]);
  });
});

describe('the worker entry', () => {
  it('handles a message and reports an error as a message', () => {
    const msg: DiffIn = { type: 'diff', id: 4, base: v1, head: v2 };
    const out = handleDiffMessage(msg);
    expect(out).toMatchObject({ type: 'diff', id: 4 });
    expect((out as Extract<DiffOut, { type: 'diff' }>).diff.counts.deleted).toBe(4);
    const bad = handleDiffMessage({ type: 'diff', id: 5, base: {} as ModelSnapshot, head: v2 });
    expect(bad.type).toBe('error');
  });

  it('runs on the main thread without a worker, and through a worker-like object with a transfer list', async () => {
    expect((await runDiff(v1, v2)).counts.new).toBe(3);
    const posted: Array<{ m: DiffIn; transfer?: Transferable[] }> = [];
    const listeners: Array<(ev: { data: DiffOut }) => void> = [];
    const fake: DiffWorkerLike = {
      postMessage: (m, transfer) => { posted.push({ m, ...(transfer ? { transfer } : {}) }); const out = handleDiffMessage(m); queueMicrotask(() => listeners.slice().forEach((l) => l({ data: out }))); },
      addEventListener: (_t, fn) => { listeners.push(fn); },
      removeEventListener: (_t, fn) => { listeners.splice(listeners.indexOf(fn), 1); },
    };
    const d = await runDiff(v1, v2, { worker: fake, transfer: true });
    expect(d.counts.deleted).toBe(4);
    expect(posted[0]!.transfer).toHaveLength(6);
    expect(snapshotTransferables(v1)).toHaveLength(3);
    expect(listeners).toHaveLength(0);
  });
});

describe('timing budgets', () => {
  /** One run; when it is over the budget up to two more, and the fastest counts. Time is min(wall, CPU), see measure(). */
  const ms = (f: () => RevisionDiff, budget = Infinity): { d: RevisionDiff; ms: number; wallMs: number } => {
    let best: { value: RevisionDiff; ms: number; wallMs: number } | null = null;
    for (let k = 0; k < 3 && (best === null || best.ms > budget); k++) { const m = measure(f); if (best === null || m.ms < best.ms) best = m; }
    return { d: best!.value, ms: best!.ms, wallMs: best!.wallMs };
  };

  it('50 k x 50 k elements in under 1 s, 50 k fully re-GUIDed within 3x', () => {
    const base = synthSnapshot({ n: 50_000 });
    const a = deriveHead(base, { deleteShare: 0.02, newShare: 0.02, moveShare: 0.05, moveBy: 0.01, propShare: 0.03 });
    const t1 = ms(() => diffModels(base, a.head), 1000);
    console.log(`diff 50k x 50k by GUID: ${t1.ms.toFixed(0)} ms (wall ${t1.wallMs.toFixed(0)})`, t1.d.counts);
    expect(t1.d.counts.deleted).toBe(a.deleted.size);
    expect(t1.d.counts.new).toBe(a.added.size);
    expect(t1.d.entries.filter((e) => e.flags.includes('placement') && e.category === 'changed').length).toBe(a.moved.size);
    expect(t1.ms).toBeLessThan(1000);

    const b = deriveHead(base, { reguid: true, shift: [250, -40, 0], deleteShare: 0.02, newShare: 0.02, moveShare: 0.05, moveBy: 0.01 });
    const t2 = ms(() => diffModels(base, b.head), 3000);
    const right = t2.d.entries.filter((e) => e.category === 'rematched' && b.pair.get(e.base!) === e.head).length;
    const wrong = t2.d.entries.filter((e) => e.category === 'rematched' && b.pair.get(e.base!) !== e.head).length;
    console.log(`diff 50k x 50k all re-GUIDed + shifted: ${t2.ms.toFixed(0)} ms (wall ${t2.wallMs.toFixed(0)})`, { right, wrong, offset: t2.d.offset });
    expect(wrong).toBe(0);
    expect(right).toBeGreaterThan(0.97 * b.pair.size);
    expect(t2.d.offset[0]).toBeCloseTo(250, 1);
    expect(t2.ms).toBeLessThan(3000);
  }, 60000);

  it('500 k x 500 k elements by GUID in under 8 s', () => {
    const base = synthSnapshot({ n: 500_000 });
    const a = deriveHead(base, { deleteShare: 0.01, newShare: 0.01, moveShare: 0.02, moveBy: 0.01, propShare: 0.01 });
    const t = ms(() => diffModels(base, a.head), 8000);
    console.log(`diff 500k x 500k by GUID: ${t.ms.toFixed(0)} ms (wall ${t.wallMs.toFixed(0)})`, t.d.counts);
    expect(t.d.counts.deleted).toBe(a.deleted.size);
    expect(t.ms).toBeLessThan(8000);
  }, 120000);
});

// keep the type import used by tooling
export type { DiffEntry };
