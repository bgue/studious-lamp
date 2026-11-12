// The review walk: order generation, the pending/commit/revert log, committed results and re-runs, the exports and the leak rule for the
// reviewer's name. No browser: the service runs with the rules only on the sidecar of a shipped model.

import { describe, expect, it } from 'vitest';
import { ClassifyService, ReviewLog, SkipList, UNSURE_CONFIDENCE, buildWalk, chainOrder, createReviewPersistence, modelFingerprint, parseReviewLog, runnerUp, sweepOrder, walkElementsOf, walkProgress } from '../src/classify';
import type { KeyValueStorage, ReviewCommit, ReviewPersistence, WalkElement, WalkOrder } from '../src/classify';
import { confirmedTruths } from '../src/classify/calibrateRules';
import { makeManual, ResultStore } from '../src/classify/results';
import { defaultSchema, schemaHash } from '../src/classify/schema';
import { MemoryStorage } from '../src/selectionSets';
import type { ClassifyResult } from '../src/classify/types';
import { sidecarModel } from './classify-helpers';

import { overallConfidence as overallOf } from '../src/classify/review';

const kv = (m: MemoryStorage): KeyValueStorage => m as unknown as KeyValueStorage;

/** A persistence that keeps the logs in a map (what IndexedDB does in the browser). */
function memoryPersistence(): ReviewPersistence & { saved: Map<string, ReviewCommit[]> } {
  const saved = new Map<string, ReviewCommit[]>();
  return {
    saved,
    load: async (fp) => JSON.parse(JSON.stringify(saved.get(fp) ?? [])) as ReviewCommit[],
    save: async (fp, _info, commits) => { saved.set(fp, JSON.parse(JSON.stringify(commits)) as ReviewCommit[]); return { where: 'indexeddb' as const }; },
  };
}

function make(opts: { storage?: MemoryStorage; persistence?: ReviewPersistence; model?: string } = {}) {
  const storage = opts.storage ?? new MemoryStorage();
  const persistence = opts.persistence ?? memoryPersistence();
  const svc = new ClassifyService({ storage: kv(storage), keyStorages: { session: kv(new MemoryStorage()), local: kv(new MemoryStorage()) }, reviewPersistence: persistence });
  const name = opts.model ?? 'process-plant';
  const model = sidecarModel(name);
  svc.setModel(model, name);
  return { svc, storage, persistence, model, name };
}

const result = (id: string, disc: string, conf = 0.9, sub: string | null = null): ClassifyResult => ({
  id,
  discipline: { code: disc, label: disc, confidence: conf, probabilities: { [disc]: conf } },
  subDiscipline: sub ? { code: sub, label: sub, confidence: conf, probabilities: { [sub]: conf } } : null,
  masterformat: null,
  buildingElement: 1,
  source: 'rules',
  needsReview: false,
});

describe('walk orders', () => {
  const ORDERS: WalkOrder[] = ['type', 'systems', 'location', 'review'];

  it('are deterministic for every order, cover every classified element once, and ignore the input order', async () => {
    const { svc, model } = make();
    await svc.classify('all');
    expect(svc.results().length).toBeGreaterThan(50);
    const els = walkElementsOf(model);
    const input = { resultOf: (g: string) => svc.store.get(g), isCommitted: () => false, disciplineOrder: svc.schema.disciplines.map((d) => d.code) };
    for (const order of ORDERS) {
      const a = buildWalk({ ...input, elements: els, order });
      const b = buildWalk({ ...input, elements: [...els].reverse(), order });
      expect(a.map((i) => i.key), order).toEqual(b.map((i) => i.key));
      expect(a.flatMap((i) => i.elements.map((e) => e.globalId)), order).toEqual(b.flatMap((i) => i.elements.map((e) => e.globalId)));
      const seen = a.flatMap((i) => i.elements.map((e) => e.globalId));
      expect(new Set(seen).size, order).toBe(seen.length);
      expect(seen.length, order).toBe(svc.results().length);
    }
  });

  it('by type groups elements of one signature and one set of codes into one item, ordered by storey, system, discipline, position', () => {
    const mk = (id: string, cls: string, sig: string, x: number, o: Partial<WalkElement> = {}): WalkElement => ({ id: Number(id.slice(1)), globalId: id, ifcClass: cls, name: id, tag: '', storey: 0, storeyName: 'L0', elevation: 0, system: '', signature: sig, bounds: [x, 0, 0, x + 1, 1, 1], ...o });
    const els = [
      mk('e0', 'IfcPipeSegment', 'pipe', 5), mk('e1', 'IfcPipeSegment', 'pipe', 1), mk('e2', 'IfcBeam', 'beam', 3),
      mk('e3', 'IfcDuctSegment', 'duct', 0, { storey: 1, storeyName: 'L1', elevation: 4 }), mk('e4', 'IfcPump', 'pump', 9, { system: 'CW' }), mk('e5', 'IfcPump', 'pump', 8, { system: 'CW' }),
    ];
    const res: Record<string, ClassifyResult> = { e0: result('e0', 'PLB'), e1: result('e1', 'PLB'), e2: result('e2', 'STR'), e3: result('e3', 'MEC'), e4: result('e4', 'MEC'), e5: result('e5', 'MEC') };
    const items = buildWalk({ elements: els, resultOf: (g) => res[g], isCommitted: () => false, disciplineOrder: ['STR', 'MEC', 'PLB'], order: 'type' });
    // L0 first; inside L0 the system CW comes before the elements in no system (then discipline order STR, PLB); pipes are one item of 2, in position order
    expect(items.map((i) => i.elements.map((e) => e.globalId))).toEqual([['e5', 'e4'], ['e2'], ['e1', 'e0'], ['e3']]);
    expect(items[2]!.title).toBe('IfcPipeSegment: e1 (2)');
    // same signature but different codes: two items
    res['e0'] = result('e0', 'UTL');
    const split = buildWalk({ elements: els, resultOf: (g) => res[g], isCommitted: () => false, disciplineOrder: ['STR', 'MEC', 'PLB', 'UTL'], order: 'type' });
    expect(split.filter((i) => i.ifcClass === 'IfcPipeSegment').map((i) => i.elements.length)).toEqual([1, 1]);
  });

  it('along systems walks a run end to end, system by system', () => {
    const pipe = (id: string, x: number, system: string): WalkElement => ({ id: Number(id.slice(1)), globalId: id, ifcClass: 'IfcPipeSegment', name: id, tag: '', storey: 0, storeyName: 'L0', elevation: 0, system, signature: 'p', bounds: [x, 0, 0, x + 1, 0.2, 0.2] });
    const els = [pipe('p3', 6, 'A'), pipe('p1', 2, 'A'), pipe('p0', 0, 'A'), pipe('p2', 4, 'A'), pipe('p4', 8, 'A'), pipe('q0', 20, 'B'), pipe('q1', 22, 'B'), pipe('n0', 40, '')];
    const items = buildWalk({ elements: els, resultOf: (g) => result(g, 'PLB'), isCommitted: () => false, disciplineOrder: ['PLB'], order: 'systems' });
    const ids = items.map((i) => i.elements[0]!.globalId);
    expect(ids.slice(0, 5)).toSatisfy((a: string[]) => a.join() === 'p0,p1,p2,p3,p4' || a.join() === 'p4,p3,p2,p1,p0'); // one end to the other
    expect(ids.slice(5, 7).sort()).toEqual(['q0', 'q1']); // then the next system
    expect(ids[7]).toBe('n0'); // elements in no system last
    expect(items.every((i) => i.elements.length === 1)).toBe(true);
    expect(chainOrder([...els].reverse().filter((e) => e.system === 'A')).map((e) => e.globalId)).toEqual(chainOrder(els.filter((e) => e.system === 'A')).map((e) => e.globalId));
  });

  it('by location goes storey by storey and sweeps in a serpentine; needs review first puts the least confident first', () => {
    const at = (id: string, x: number, z: number, storey: number): WalkElement => ({ id: Number(id.slice(1)), globalId: id, ifcClass: 'IfcWall', name: id, tag: '', storey, storeyName: `S${storey}`, elevation: storey * 3, system: '', signature: id, bounds: [x, 0, z, x + 1, 1, z + 1] });
    const els = [at('a', 0, 0, 1), at('b', 2, 0, 1), at('c', 2, 4, 1), at('d', 0, 4, 1), at('e', 5, 5, 0)];
    expect(sweepOrder(els).map((e) => e.globalId)).toEqual(['e', 'a', 'b', 'c', 'd']);
    const loc = buildWalk({ elements: els, resultOf: (g) => result(g, 'ARC'), isCommitted: () => false, disciplineOrder: ['ARC'], order: 'location' });
    expect(loc.map((i) => i.elements[0]!.globalId)).toEqual(['e', 'a', 'b', 'c', 'd']);
    const conf: Record<string, number> = { a: 0.9, b: 0.4, c: 0.7, d: 0.55, e: 0.95 };
    const rev = buildWalk({ elements: els, resultOf: (g) => result(g, 'ARC', conf[g]), isCommitted: () => false, disciplineOrder: ['ARC'], order: 'review' });
    expect(rev.map((i) => i.elements[0]!.globalId)).toEqual(['b', 'd', 'c', 'a', 'e']);
  });

  it('filters by review flag, discipline and confirmation, and counts progress', () => {
    const el = (id: string): WalkElement => ({ id: Number(id.slice(1)), globalId: id, ifcClass: 'IfcWall', name: id, tag: '', storey: 0, storeyName: 'L0', elevation: 0, system: '', signature: id, bounds: [Number(id.slice(1)), 0, 0, Number(id.slice(1)) + 1, 1, 1] });
    const els = ['w0', 'w1', 'w2', 'w3'].map(el);
    const res: Record<string, ClassifyResult> = { w0: result('w0', 'ARC'), w1: { ...result('w1', 'ARC'), needsReview: true }, w2: { ...result('w2', 'STR'), needsReview: true }, w3: result('w3', 'ARC') };
    const base = { elements: els, resultOf: (g: string) => res[g], disciplineOrder: ['ARC', 'STR'], order: 'location' as const };
    const ids = (f: object, committed: string[] = []): string[] => buildWalk({ ...base, isCommitted: (g) => committed.includes(g), filters: f }).map((i) => i.elements[0]!.globalId);
    expect(ids({ needsReview: true })).toEqual(['w1', 'w2']);
    expect(ids({ discipline: 'ARC' })).toEqual(['w0', 'w1', 'w3']);
    expect(ids({ unconfirmed: true }, ['w0', 'w3'])).toEqual(['w1', 'w2']);
    expect(ids({ needsReview: true, discipline: 'STR', unconfirmed: true })).toEqual(['w2']);
    const p = walkProgress(els, (g) => (g === 'w0' ? 'confirmed' : g === 'w1' ? 'corrected' : null));
    expect(p).toEqual({ confirmed: 1, corrected: 1, remaining: 2, total: 4 });
  });

  it('finds the runner-up of the weakest part and skips codes the schema does not have', () => {
    const r: ClassifyResult = {
      ...result('x', 'PLB'),
      discipline: { code: 'PLB', label: 'Plumbing', confidence: 0.5, probabilities: { PLB: 0.5, MEC: 0.4, GEN: 0.1 } },
    };
    expect(runnerUp(r, () => true)).toMatchObject({ part: 'discipline', code: 'MEC', proposed: 'PLB' });
    expect(runnerUp(r, (_p, c) => c !== 'MEC')).toMatchObject({ code: 'GEN' });
    expect(runnerUp(result('y', 'PLB'), () => true)).toBeNull(); // a rule has no second choice
  });
});

describe('the review log', () => {
  const info = { modelName: 'm', modelFingerprint: 'fp1', schemaEdition: 'ed1' };
  const st = (d: string, source: ReviewCommit['changes'][number]['after']['source'] = 'rules', conf = 0.6) => ({ discipline: d, subDiscipline: null, division: null, source, confidence: conf });
  const ch = (g: string, from: string, to: string, action: 'confirm' | 'correct' = 'correct') => ({ globalId: g, before: st(from), after: st(to, action === 'confirm' ? 'confirmed' : 'corrected', 1), action });
  const t = (n: number): Date => new Date(Date.UTC(2026, 0, 1, 0, 0, n));

  it('appends immutable commits, refuses an empty commit or one without an author', () => {
    const log = new ReviewLog(info);
    expect(() => log.commit({ author: ' ', changes: [ch('a', 'MEC', 'PLB')] })).toThrow(/name or initials/);
    expect(() => log.commit({ author: 'ab', changes: [] })).toThrow(/nothing to commit/);
    const c = log.commit({ author: 'ab', note: 'first', changes: [ch('a', 'MEC', 'PLB')], now: t(1), id: 'c1' });
    expect(c).toMatchObject({ id: 'c1', author: 'ab', time: '2026-01-01T00:00:01.000Z', note: 'first', modelName: 'm', modelFingerprint: 'fp1', schemaEdition: 'ed1' });
    expect(Object.isFrozen(c)).toBe(true);
    expect(() => { (c as { note: string }).note = 'edited'; }).toThrow();
    expect(() => { (c.changes[0]!.after as { discipline: string }).discipline = 'X'; }).toThrow();
    expect(() => log.commit({ author: 'ab', changes: [ch('a', 'MEC', 'PLB')], id: 'c1' })).toThrow(/exists already/);
    expect(log.commits).toHaveLength(1);
  });

  it('reverts as a new commit and never edits the old one', () => {
    const log = new ReviewLog(info);
    const c1 = log.commit({ author: 'ab', changes: [ch('a', 'MEC', 'PLB'), ch('b', 'STR', 'STR', 'confirm')], now: t(1), id: 'c1' });
    expect(log.committedState('a')).toMatchObject({ discipline: 'PLB', source: 'corrected' });
    const before = JSON.stringify(c1);
    const { commit, skipped } = log.revert('c1', { author: 'cd', now: t(2), id: 'c2' });
    expect(skipped).toEqual([]);
    expect(log.commits.map((c) => c.id)).toEqual(['c1', 'c2']);
    expect(JSON.stringify(log.get('c1'))).toBe(before);
    expect(commit).toMatchObject({ id: 'c2', reverts: 'c1', author: 'cd' });
    expect(commit.changes[0]).toMatchObject({ globalId: 'a', before: { discipline: 'PLB', source: 'corrected' }, after: { discipline: 'MEC', source: 'rules' } });
    expect(log.effective().size).toBe(0); // both elements are back to their computed result
    expect(() => log.revert('c1', { author: 'cd' })).toThrow(/reverted already/);
    expect(() => log.revert('nope', { author: 'cd' })).toThrow(/no commit/);
  });

  it('leaves alone an element that a later commit changed again', () => {
    const log = new ReviewLog(info);
    log.commit({ author: 'ab', changes: [ch('a', 'MEC', 'PLB'), ch('b', 'STR', 'ARC')], now: t(1), id: 'c1' });
    log.commit({ author: 'ab', changes: [{ globalId: 'a', before: st('PLB', 'corrected', 1), after: st('GEN', 'corrected', 1), action: 'correct' }], now: t(2), id: 'c2' });
    const r = log.revert('c1', { author: 'ab', now: t(3), id: 'c3' });
    expect(r.skipped).toEqual(['a']);
    expect(r.commit.changes.map((c) => c.globalId)).toEqual(['b']);
    expect(log.committedState('a')).toMatchObject({ discipline: 'GEN' });
    expect(log.committedState('b')).toBeNull();
  });

  it('exports and imports, deduplicating by commit id and refusing another fingerprint', () => {
    const a = new ReviewLog(info);
    a.commit({ author: 'ab', changes: [ch('a', 'MEC', 'PLB')], now: t(1), id: 'c1' });
    a.commit({ author: 'cd', changes: [ch('b', 'STR', 'ARC')], now: t(2), id: 'c2' });
    const text = a.exportJson(t(9));
    expect(JSON.parse(text)).toMatchObject({ schema: 'xray-classification-review/1', modelFingerprint: 'fp1', modelName: 'm', schemaEdition: 'ed1', exportedAt: '2026-01-01T00:00:09.000Z' });
    const b = new ReviewLog(info);
    b.commit({ author: 'ef', changes: [ch('z', 'MEC', 'GEN')], now: t(5), id: 'c9' });
    expect(b.importDoc(text)).toEqual({ ok: true, added: ['c1', 'c2'], duplicates: [] });
    expect(b.importDoc(text)).toEqual({ ok: true, added: [], duplicates: ['c1', 'c2'] }); // the second import changes nothing
    expect(b.commits.map((c) => c.id)).toEqual(['c9', 'c1', 'c2']);
    expect(b.effective().size).toBe(3);
    const other = new ReviewLog({ ...info, modelFingerprint: 'fp2' });
    const refused = other.importDoc(text);
    expect(refused.ok).toBe(false);
    expect(refused.error).toMatch(/another model or schema.*fp1.*fp2/);
    expect(other.commits).toHaveLength(0);
    expect(b.importDoc('{"schema":"nope"}').ok).toBe(false);
    expect(b.importDoc('not json').error).toMatch(/not valid JSON/);
    expect(parseReviewLog({ schema: 'xray-classification-review/1', modelFingerprint: 'x', commits: [{ id: 'c' }] }).errors[0]).toMatch(/Commit 1 needs/);
  });

  it('replays commits in time order, whichever order they were appended in', () => {
    const log = new ReviewLog(info);
    log.commit({ author: 'ab', changes: [{ globalId: 'a', before: st('PLB', 'corrected', 1), after: st('GEN', 'corrected', 1), action: 'correct' }], now: t(5), id: 'late' });
    log.commit({ author: 'ab', changes: [ch('a', 'MEC', 'PLB')], now: t(1), id: 'early' }); // imported later, but older
    expect(log.committedState('a')).toMatchObject({ discipline: 'GEN' });
  });

  it('has a fingerprint of the GlobalIds and the schema hash, whatever their order', () => {
    const h = schemaHash(defaultSchema());
    expect(modelFingerprint(['b', 'a', 'c'], h)).toBe(modelFingerprint(['c', 'a', 'b'], h));
    expect(modelFingerprint(['a', 'b'], h)).not.toBe(modelFingerprint(['a', 'b', 'c'], h));
    expect(modelFingerprint(['a', 'b'], h)).not.toBe(modelFingerprint(['a', 'b'], `${h}x`));
    expect(modelFingerprint(['a', 'b'], h)).toMatch(/^[0-9a-f]{16}$/);
  });
});

describe('the review log in storage', () => {
  it('falls back to localStorage when IndexedDB is missing, and reports an error when both fail', async () => {
    const local = new MemoryStorage();
    const p = createReviewPersistence({ indexedDB: null, local: kv(local) });
    const log = new ReviewLog({ modelName: 'm', modelFingerprint: 'fpX', schemaEdition: 'e' });
    log.commit({ author: 'ab', changes: [{ globalId: 'a', before: { discipline: 'MEC', subDiscipline: null, division: null, source: 'rules', confidence: 0.5 }, after: { discipline: 'PLB', subDiscipline: null, division: null, source: 'corrected', confidence: 1 }, action: 'correct' }], id: 'c1' });
    expect(await p.save('fpX', log.info, log.commits)).toEqual({ where: 'localstorage' });
    expect((await p.load('fpX')).map((c) => c.id)).toEqual(['c1']);
    expect(await p.load('other')).toEqual([]);
    const blocked = { getItem: () => { throw new Error('blocked'); }, setItem: () => { throw new Error('blocked'); }, removeItem: () => { throw new Error('blocked'); } } as unknown as KeyValueStorage;
    const none = createReviewPersistence({ indexedDB: null, local: blocked });
    await expect(none.save('fpX', log.info, log.commits)).rejects.toThrow(/could not be stored/);
    expect(await none.load('fpX')).toEqual([]); // a load never throws
  });

  it('keeps working for the session when storage is blocked', async () => {
    const failing: ReviewPersistence = { load: async () => { throw new Error('blocked'); }, save: async () => { throw new Error('blocked'); } };
    const { svc } = make({ persistence: failing, model: 'fzk-haus' });
    await svc.review.ready;
    await svc.classify('all');
    svc.review.setReviewer('ab');
    const gid = svc.results()[0]!.id;
    svc.review.propose([gid], { action: 'confirm', item: 'i1' });
    const c = svc.review.commit('note');
    await new Promise((r) => setTimeout(r, 5));
    expect(svc.store.get(gid)).toMatchObject({ source: 'confirmed', commitId: c.id });
    expect(svc.review.storage.where).toBe('session');
    expect(svc.review.storage.error).toMatch(/blocked/);
    expect(svc.review.history()).toHaveLength(1);
  });
});

describe('committed results', () => {
  async function setup() {
    const ctx = make({ model: 'fzk-haus' });
    await ctx.svc.review.ready;
    await ctx.svc.classify('all');
    ctx.svc.review.setReviewer('Rita Reviewer');
    return ctx;
  }

  it('pend, undo item by item, commit once, and become the result with source confirmed or corrected', async () => {
    const { svc, model } = await setup();
    const walls = model.elements.filter((e) => e.ifcClass === 'IfcWallStandardCase').slice(0, 3).map((e) => e.globalId);
    const door = model.elements.find((e) => e.ifcClass === 'IfcDoor')!.globalId;
    const doorBefore = svc.store.get(door)!;
    svc.review.propose(walls, { action: 'confirm', item: 'walls' });
    svc.review.propose([door], { action: 'correct', codes: { discipline: 'STR', subDiscipline: 'BRC', masterformat: '05' }, item: 'door', comment: 'a steel door' });
    expect(svc.review.pending()).toHaveLength(4);
    expect(svc.store.get(door)!.source).toBe(doorBefore.source); // nothing is committed yet
    expect(svc.review.undoPending('walls')).toBe(3);
    expect(svc.review.pending().map((p) => p.globalId)).toEqual([door]);
    svc.review.propose(walls.slice(0, 2), { action: 'confirm', item: 'walls' });
    expect(svc.review.decision(walls[0]!)).toBe('confirmed');
    expect(svc.review.decision(door)).toBe('corrected');
    const c = svc.review.commit('first pass');
    expect(c).toMatchObject({ author: 'Rita Reviewer', note: 'first pass', modelName: 'fzk-haus', modelFingerprint: svc.review.fingerprint(), schemaEdition: svc.schema.edition ?? svc.schema.version ?? svc.schema.title });
    expect(c.changes).toHaveLength(3);
    const dc = c.changes.find((x) => x.globalId === door)!;
    expect(dc).toMatchObject({ action: 'correct', comment: 'a steel door', after: { discipline: 'STR', subDiscipline: 'BRC', division: '05', source: 'corrected', confidence: 1 } });
    expect(dc.before).toMatchObject({ discipline: doorBefore.discipline.code, source: doorBefore.source });
    expect(svc.review.pending()).toHaveLength(0);
    expect(svc.store.get(door)).toMatchObject({ source: 'corrected', needsReview: false, commitId: c.id, confirmedBy: 'Rita Reviewer', confirmedAt: c.time });
    expect(svc.store.get(door)!.discipline).toMatchObject({ code: 'STR', confidence: 1 });
    expect(svc.store.get(walls[0]!)).toMatchObject({ source: 'confirmed', needsReview: false });
    const props = model.elements[model.byGlobalId.get(door)!]!.props!;
    expect(props['XR_Classification.Source']).toBe('corrected');
    expect(props['XR_Classification.Discipline']).toBe('STR');
    expect(JSON.stringify(props)).not.toContain('Rita'); // the name is not written into the model
    expect(svc.stats().bySource).toMatchObject({ confirmed: 2, corrected: 1 });
    expect(() => svc.review.propose([door], { action: 'correct', codes: { discipline: 'ZZZ' }, item: 'x' })).toThrow(/not in the schema/);
  });

  it('asks for a reviewer before a commit and keeps the name on this device only', async () => {
    const { svc, storage, model } = await setup();
    svc.review.setReviewer('');
    svc.review.propose([model.elements[0]!.globalId], { action: 'confirm', item: 'i' });
    expect(() => svc.review.commit()).toThrow(/name or initials/);
    svc.review.setReviewer('  RR  ');
    expect(svc.review.reviewer()).toBe('RR');
    const again = new ClassifyService({ storage: kv(storage), keyStorages: { session: kv(new MemoryStorage()), local: kv(new MemoryStorage()) }, reviewPersistence: memoryPersistence() });
    expect(again.review.reviewer()).toBe('RR');
  });

  it('survive a re-run of the classifier, and the model disagreeing is flagged', async () => {
    const { svc, model } = await setup();
    const door = model.elements.find((e) => e.ifcClass === 'IfcDoor')!.globalId;
    const wall = model.elements.find((e) => e.ifcClass === 'IfcWallStandardCase')!.globalId;
    const wallBefore = svc.store.get(wall)!;
    svc.review.propose([door], { action: 'correct', codes: { discipline: 'STR', subDiscipline: 'BRC', masterformat: '05' }, item: 'a' });
    svc.review.propose([wall], { action: 'confirm', item: 'b' });
    svc.review.commit();
    expect(svc.review.disagreements().size).toBe(0);
    await svc.classify('all');
    await svc.classify('all', { rules: false });
    svc.clear();
    await svc.classify('all');
    expect(svc.store.get(door)).toMatchObject({ source: 'corrected', discipline: { code: 'STR' } });
    expect(svc.store.get(wall)).toMatchObject({ source: 'confirmed', discipline: { code: wallBefore.discipline.code } });
    expect([...svc.review.disagreements().keys()]).toEqual([door]); // the rules still say what they said, the person said STR
    expect(svc.review.disagreements().get(door)!.source).toBe('rules');
    expect(svc.needsReviewIds()).not.toContain(model.byGlobalId.get(door));
    expect(model.elements[model.byGlobalId.get(door)!]!.props!['XR_Classification.Source']).toBe('corrected'); // the written property too
  });

  it('come back after a reload from the stored log, and a revert returns the computed result', async () => {
    const storage = new MemoryStorage();
    const persistence = memoryPersistence();
    const a = make({ storage, persistence, model: 'fzk-haus' });
    await a.svc.review.ready;
    await a.svc.classify('all');
    a.svc.review.setReviewer('RR');
    const door = a.model.elements.find((e) => e.ifcClass === 'IfcDoor')!.globalId;
    const rule = a.svc.store.get(door)!;
    a.svc.review.propose([door], { action: 'correct', codes: { discipline: 'STR', subDiscipline: 'BRC', masterformat: '05' }, item: 'i' });
    const c = a.svc.review.commit('n');
    await new Promise((r) => setTimeout(r, 5));
    expect(persistence.saved.get(a.svc.review.fingerprint())).toHaveLength(1);

    const b = make({ storage, persistence, model: 'fzk-haus' });
    expect(b.svc.results()).toHaveLength(0); // before the log is read
    await b.svc.review.ready;
    expect(b.svc.results().map((r) => r.id)).toEqual([door]);
    expect(b.svc.store.get(door)).toMatchObject({ source: 'corrected', commitId: c.id, confirmedBy: 'RR' });
    expect(b.svc.review.history().map((x) => x.id)).toEqual([c.id]);
    await b.svc.classify('all');
    expect(b.svc.store.get(door)!.source).toBe('corrected');

    const rev = b.svc.review.revert(c.id, 'oops');
    expect(rev.commit).toMatchObject({ reverts: c.id });
    expect(b.svc.review.history().map((x) => x.id)).toEqual([rev.commit.id, c.id]); // newest first, nothing removed
    expect(b.svc.store.get(door)!.source).toBe(rule.source); // the computed result is the element's result again
    expect(b.svc.store.get(door)!.discipline.code).toBe(rule.discipline.code);
    expect(b.svc.review.disagreements().size).toBe(0);
  });

  it('keep a manual override under them and give it back on a revert', async () => {
    const { svc, model } = await setup();
    const door = model.elements.find((e) => e.ifcClass === 'IfcDoor')!.globalId;
    svc.override(door, { discipline: 'ARC' });
    svc.review.propose([door], { action: 'confirm', item: 'i' });
    const c = svc.review.commit();
    expect(svc.store.get(door)!.source).toBe('confirmed');
    svc.review.revert(c.id);
    expect(svc.store.get(door)!.source).toBe('manual');
  });

  it('are exported with who, when and the commit in JSON, CSV and Throughline', async () => {
    const { svc, model } = await setup();
    const door = model.elements.find((e) => e.ifcClass === 'IfcDoor')!.globalId;
    const other = model.elements.find((e) => e.ifcClass === 'IfcWallStandardCase')!.globalId;
    svc.review.propose([door], { action: 'confirm', item: 'i' });
    const c = svc.review.commit();
    const json = JSON.parse(svc.export('json')) as { results: ClassifyResult[] };
    expect(json.results.find((r) => r.id === door)).toMatchObject({ source: 'confirmed', confirmedBy: 'Rita Reviewer', confirmedAt: c.time, commitId: c.id });
    expect(json.results.find((r) => r.id === other)!.confirmedBy).toBeUndefined();
    const lines = svc.export('csv').trim().split(/\r\n/);
    const head = lines[0]!.split(',');
    expect(head.slice(-4)).toEqual(['ConfirmedBy', 'ConfirmedAt', 'CommitId', 'Unsure']);
    const row = lines.find((l) => l.startsWith(door))!;
    expect(row).toContain(',confirmed,');
    expect(row.endsWith(`Rita Reviewer,${c.time},${c.id},false`)).toBe(true);
    const tl = JSON.parse(svc.export('throughline')) as { elements: Array<{ global_id: string; attributes: Record<string, unknown> }> };
    expect(tl.elements.find((e) => e.global_id === door)!.attributes).toMatchObject({ source: 'confirmed', confirmed_by: 'Rita Reviewer', confirmed_at: c.time, commit_id: c.id });
    expect(Object.keys(tl.elements.find((e) => e.global_id === other)!.attributes)).not.toContain('confirmed_by');
  });

  it('round-trip through export and import of the review log on another page of the same model', async () => {
    const a = await setup();
    const ids = a.model.elements.slice(0, 4).map((e) => e.globalId);
    a.svc.review.propose(ids, { action: 'confirm', item: 'i' });
    a.svc.review.commit('one');
    const text = a.svc.review.exportLog();
    const b = make({ model: 'fzk-haus' });
    await b.svc.review.ready;
    await b.svc.classify('all');
    const r = b.svc.review.importLog(text);
    expect(r.ok && r.added.length).toBe(1);
    expect(b.svc.store.get(ids[0]!)!.source).toBe('confirmed');
    expect(b.svc.review.importLog(text)).toMatchObject({ ok: true, added: [], duplicates: r.added });
    expect(b.svc.review.history()).toHaveLength(1);
    const other = make({ model: 'process-plant' });
    await other.svc.review.ready;
    const bad = other.svc.review.importLog(text);
    expect(bad.ok).toBe(false);
    expect(bad.error).toMatch(/another model or schema/);
    expect(other.svc.review.history()).toHaveLength(0);
  });

  it('count as truth for the calibration, one label per signature by majority', async () => {
    const { svc, model } = await setup();
    const walls = model.elements.filter((e) => e.ifcClass === 'IfcWallStandardCase').slice(0, 3).map((e) => e.globalId);
    svc.review.propose(walls, { action: 'correct', codes: { discipline: 'STR' }, item: 'i' });
    svc.review.commit();
    const truths = confirmedTruths(svc.inputsFor(walls), svc.store.committed);
    expect(truths.length).toBeGreaterThan(0);
    expect(truths.every((t) => t.discipline === 'STR')).toBe(true);
    expect(confirmedTruths(svc.inputsFor('all'), new Map())).toEqual([]);
    await expect(svc.calibrateOnConfirmed()).rejects.toThrow(/decision model/); // no provider chosen in this test
  });
});

describe('the result store', () => {
  it('never lets a merge replace a committed result, and drops the committed overlay cleanly', () => {
    const store = new ResultStore();
    const schema = defaultSchema();
    store.merge([result('a', 'MEC')]);
    const c = { ...makeManual(schema, 'a', { discipline: 'PLB' }), source: 'confirmed' as const };
    store.setCommitted(new Map([['a', c]]));
    store.merge([result('a', 'MEC')]);
    expect(store.get('a')!.source).toBe('confirmed');
    expect([...store.disagreements.keys()]).toEqual(['a']);
    store.merge([result('a', 'PLB')]);
    expect(store.disagreements.size).toBe(0);
    store.rereview(0.99);
    expect(store.get('a')!.needsReview).toBe(false);
    store.setCommitted(new Map());
    expect(store.get('a')).toMatchObject({ source: 'rules', discipline: { code: 'PLB' } }); // the latest computed result is back
  });
});

describe('the unsure flag', () => {
  async function setup() {
    const ctx = make({ model: 'fzk-haus' });
    await ctx.svc.review.ready;
    await ctx.svc.classify('all');
    ctx.svc.review.setReviewer('Rita Reviewer');
    const ids = (cls: string, n = 1): string[] => ctx.model.elements.filter((e) => e.ifcClass === cls).slice(0, n).map((e) => e.globalId);
    return { ...ctx, ids };
  }
  const toMap = (gids: string[], svc: ClassifyService): Map<string, ClassifyResult> => new Map(gids.map((g) => [g, svc.store.get(g)!]));

  it('is off by default and applies only where it is set', async () => {
    const { svc, ids } = await setup();
    const [a, b] = [ids('IfcDoor')[0]!, ids('IfcWallStandardCase')[0]!];
    svc.review.propose([a], { action: 'confirm', item: 'a', unsure: true });
    svc.review.propose([b], { action: 'confirm', item: 'b' });
    expect(svc.review.pendingFor(a)).toMatchObject({ unsure: true, after: { source: 'confirmed', confidence: UNSURE_CONFIDENCE } });
    expect(svc.review.pendingFor(b)!.unsure).toBeUndefined();
    expect(svc.review.pendingFor(b)!.after.confidence).toBe(1);
  });

  it('round-trips through commit, JSON, CSV, Throughline, export and import, with the confidence below 1 and needsReview true', async () => {
    const a = await setup();
    const door = a.ids('IfcDoor')[0]!;
    const wall = a.ids('IfcWallStandardCase')[0]!;
    const sure = a.ids('IfcWindow')[0]!;
    a.svc.review.propose([door], { action: 'confirm', item: 'd', unsure: true });
    a.svc.review.propose([wall], { action: 'correct', codes: { discipline: 'STR', subDiscipline: 'BRC', masterformat: '05' }, item: 'w', unsure: true });
    a.svc.review.propose([sure], { action: 'confirm', item: 's' });
    const c = a.svc.review.commit('guesses');
    expect(c.changes.find((x) => x.globalId === door)).toMatchObject({ unsure: true, action: 'confirm' });
    expect(c.changes.find((x) => x.globalId === wall)).toMatchObject({ unsure: true, action: 'correct' });
    expect('unsure' in c.changes.find((x) => x.globalId === sure)!).toBe(false); // absent means false
    for (const g of [door, wall]) {
      const r = a.svc.store.get(g)!;
      expect(r.unsure).toBe(true);
      expect(['confirmed', 'corrected']).toContain(r.source);
      expect(overallOf(r)).toBe(UNSURE_CONFIDENCE);
      expect(r.needsReview).toBe(true);
    }
    expect(a.svc.store.get(wall)).toMatchObject({ source: 'corrected', discipline: { code: 'STR' }, subDiscipline: { code: 'BRC' }, masterformat: { division: '05' } });
    expect(a.svc.store.get(sure)).toMatchObject({ source: 'confirmed', needsReview: false });
    expect(a.svc.store.get(sure)!.unsure).toBeUndefined();
    // exports
    const json = JSON.parse(a.svc.export('json')) as { results: ClassifyResult[] };
    expect(json.results.find((r) => r.id === door)!.unsure).toBe(true);
    const lines = a.svc.export('csv').trim().split(/\r\n/);
    expect(lines.find((l) => l.startsWith(door))!.endsWith(',true')).toBe(true);
    expect(lines.find((l) => l.startsWith(sure))!.endsWith(',false')).toBe(true);
    const other = lines.find((l) => !l.startsWith('GlobalId') && l.includes(',rules,'))!;
    expect(other.endsWith(',false')).toBe(true);
    const tl = JSON.parse(a.svc.export('throughline')) as { elements: Array<{ global_id: string; attributes: Record<string, unknown> }> };
    expect(tl.elements.find((e) => e.global_id === door)!.attributes).toMatchObject({ unsure: true, needs_review: true });
    expect(tl.elements.find((e) => e.global_id === sure)!.attributes['unsure']).toBe(false);
    const uncommitted = tl.elements.find((e) => !e.attributes['confirmed_by'])!;
    expect(Object.keys(uncommitted.attributes)).not.toContain('unsure'); // only committed elements carry it
    // the log file and an import on another page
    const text = a.svc.review.exportLog();
    const doc = JSON.parse(text) as { schema: string; commits: Array<{ changes: Array<{ globalId: string; unsure?: boolean }> }> };
    expect(doc.schema).toBe('xray-classification-review/1');
    expect(doc.commits[0]!.changes.filter((x) => x.unsure === true).map((x) => x.globalId).sort()).toEqual([door, wall].sort());
    const b = make({ model: 'fzk-haus' });
    await b.svc.review.ready;
    await b.svc.classify('all');
    expect(b.svc.review.importLog(text)).toMatchObject({ ok: true });
    expect(b.svc.store.get(door)).toMatchObject({ unsure: true, needsReview: true, source: 'confirmed' });
    expect(overallOf(b.svc.store.get(wall)!)).toBe(UNSURE_CONFIDENCE);
    expect(b.svc.store.get(sure)!.unsure).toBeUndefined();
  });

  it('reads an old log without the field as sure, and checks the field when it is there', async () => {
    const a = await setup();
    const door = a.ids('IfcDoor')[0]!;
    a.svc.review.propose([door], { action: 'confirm', item: 'd' });
    a.svc.review.commit();
    const old = JSON.parse(a.svc.review.exportLog()) as { commits: Array<{ changes: Array<Record<string, unknown>> }> };
    expect(old.commits[0]!.changes.every((x) => !('unsure' in x))).toBe(true);
    const p = parseReviewLog(old);
    expect(p.errors).toEqual([]);
    expect(p.doc!.commits[0]!.changes[0]!.unsure).toBeUndefined();
    const b = make({ model: 'fzk-haus' });
    await b.svc.review.ready;
    await b.svc.classify('all');
    expect(b.svc.review.importLog(JSON.stringify(old)).ok).toBe(true);
    expect(b.svc.store.get(door)).toMatchObject({ source: 'confirmed', needsReview: false });
    expect(b.svc.store.get(door)!.unsure).toBeUndefined();
    expect(overallOf(b.svc.store.get(door)!)).toBe(1);
    // the validator: true is kept, false is dropped, anything else is refused
    const withFlag = (u: unknown): ReturnType<typeof parseReviewLog> => { const d = JSON.parse(JSON.stringify(old)) as typeof old; d.commits[0]!.changes[0]!['unsure'] = u; return parseReviewLog(d); };
    expect(withFlag(true).doc!.commits[0]!.changes[0]!.unsure).toBe(true);
    expect(withFlag(false).doc!.commits[0]!.changes[0]!.unsure).toBeUndefined();
    const bad = withFlag('yes');
    expect(bad.doc).toBeNull();
    expect(bad.errors.join(' ')).toMatch(/unsure/);
  });

  it('keeps unsure results in the review filters: Only needs review, Only unsure, and not settled for Only unconfirmed', async () => {
    const { svc, model, ids } = await setup();
    const door = ids('IfcDoor')[0]!;
    const sure = ids('IfcWindow')[0]!;
    svc.review.propose([door], { action: 'confirm', item: 'd', unsure: true });
    svc.review.propose([sure], { action: 'confirm', item: 's' });
    svc.review.commit();
    const input = { elements: walkElementsOf(model), resultOf: (g: string) => svc.store.get(g), isCommitted: (g: string) => { const c = svc.store.committed.get(g); return !!c && c.unsure !== true; }, disciplineOrder: svc.schema.disciplines.map((d) => d.code), order: 'location' as const };
    const gids = (f: object): string[] => buildWalk({ ...input, filters: f }).flatMap((i) => i.elements.map((e) => e.globalId));
    expect(gids({ needsReview: true })).toContain(door);
    expect(gids({ needsReview: true })).not.toContain(sure);
    expect(gids({ unsure: true })).toEqual([door]);
    expect(gids({ unconfirmed: true })).toContain(door);
    expect(gids({ unconfirmed: true })).not.toContain(sure);
    const rev = buildWalk({ ...input, order: 'review' });
    expect(rev.findIndex((i) => i.elements.some((e) => e.globalId === door))).toBeLessThan(rev.findIndex((i) => i.elements.some((e) => e.globalId === sure)));
  });

  it('is left out of the calibration labels, and a count says how many', async () => {
    const { svc, ids } = await setup();
    const walls = ids('IfcWallStandardCase', 3);
    const door = ids('IfcDoor')[0]!;
    svc.review.propose([walls[0]!, walls[1]!], { action: 'correct', codes: { discipline: 'STR' }, item: 'w' });
    svc.review.propose([walls[2]!, door], { action: 'correct', codes: { discipline: 'MEC' }, item: 'x', unsure: true });
    svc.review.commit();
    const all = toMap([...walls, door], svc);
    const truths = confirmedTruths(svc.inputsFor([...walls, door]), all);
    expect(truths.length).toBeGreaterThan(0);
    expect(truths.every((t) => t.discipline === 'STR')).toBe(true); // the unsure MEC guesses do not vote
    const onlyUnsure = confirmedTruths(svc.inputsFor([walls[2]!, door]), toMap([walls[2]!, door], svc));
    expect(onlyUnsure).toEqual([]);
    expect([...svc.store.committed.values()].filter((r) => r.unsure === true)).toHaveLength(2);
  });

  it('is superseded by a later sure confirmation of the same element, and the latest change always wins', async () => {
    const { svc, ids } = await setup();
    const door = ids('IfcDoor')[0]!;
    svc.review.propose([door], { action: 'confirm', item: 'd', unsure: true });
    const c1 = svc.review.commit();
    expect(svc.store.get(door)).toMatchObject({ unsure: true, needsReview: true });
    // the same codes again, now sure: not left out as "already committed"
    expect(svc.review.propose([door], { action: 'confirm', item: 'd2' })).toHaveLength(1);
    const c2 = svc.review.commit();
    expect(svc.store.get(door)!.unsure).toBeUndefined();
    expect(svc.store.get(door)).toMatchObject({ source: 'confirmed', needsReview: false, commitId: c2.id });
    expect(overallOf(svc.store.get(door)!)).toBe(1);
    // reverting the sure commit puts the unsure state of c1 back
    svc.review.revert(c2.id);
    expect(svc.store.get(door)).toMatchObject({ unsure: true, needsReview: true });
    expect(svc.review.log!.committedState(door)!.confidence).toBe(UNSURE_CONFIDENCE);
    // sure again; the same sure confirmation is left out, an unsure flag on a sure one is recorded and can be reverted
    svc.review.propose([door], { action: 'confirm', item: 'd3' });
    svc.review.commit();
    expect(svc.store.get(door)!.unsure).toBeUndefined();
    expect(svc.review.propose([door], { action: 'confirm', item: 'd4' })).toHaveLength(0);
    expect(svc.review.propose([door], { action: 'confirm', item: 'd5', unsure: true })).toHaveLength(1);
    const c5 = svc.review.commit();
    expect(svc.store.get(door)).toMatchObject({ unsure: true, needsReview: true });
    svc.review.revert(c5.id);
    expect(svc.store.get(door)!.unsure).toBeUndefined();
    expect(c1.changes[0]!.unsure).toBe(true);
  });
});

describe('skipping', () => {
  it('keeps a session list that is not a change: nothing pending, nothing in the log', async () => {
    const ctx = make({ model: 'fzk-haus' });
    await ctx.svc.review.ready;
    await ctx.svc.classify('all');
    ctx.svc.review.setReviewer('RR');
    const [a, b, c] = ctx.model.elements.slice(0, 3).map((e) => e.globalId) as [string, string, string];
    const skips = ctx.svc.review.skips;
    expect(skips.add([a, b])).toBe(2);
    expect(skips.add([b, c])).toBe(1); // b was on the list
    expect(skips.size).toBe(3);
    expect(ctx.svc.review.pending()).toHaveLength(0);
    expect(ctx.svc.review.history()).toHaveLength(0);
    expect(() => ctx.svc.review.commit()).toThrow(/no pending/); // a skip is nothing to commit
    // a decision settles the skip
    ctx.svc.review.propose([a], { action: 'confirm', item: 'i' });
    expect(skips.has(a)).toBe(false);
    expect(skips.ids().sort()).toEqual([b, c].sort());
    ctx.svc.review.commit();
    expect(ctx.svc.review.history()[0]!.changes.map((x) => x.globalId)).toEqual([a]);
    expect(JSON.stringify(ctx.svc.review.exportLog())).not.toContain(b); // skipped elements are in no log
    // a new model or schema starts an empty list
    ctx.svc.review.reload();
    expect(skips.size).toBe(0);
  });

  it('revisits only the skipped elements, as groups of the same type', () => {
    const el = (id: string, sig: string): WalkElement => ({ id: Number(id.slice(1)), globalId: id, ifcClass: 'IfcWall', name: id, tag: '', storey: 0, storeyName: 'L0', elevation: 0, system: '', signature: sig, bounds: [Number(id.slice(1)), 0, 0, Number(id.slice(1)) + 1, 1, 1] });
    const els = [el('w0', 'A'), el('w1', 'A'), el('w2', 'A'), el('w3', 'B')];
    const skips = new SkipList();
    skips.add(['w1', 'w3']);
    const base = { elements: els, resultOf: (g: string) => result(g, 'ARC'), isCommitted: () => false, disciplineOrder: ['ARC'], order: 'type' as const, skipped: skips };
    const all = buildWalk(base);
    expect(all.map((i) => i.elements.length).sort()).toEqual([1, 3]);
    const only = buildWalk({ ...base, filters: { onlySkipped: true } });
    expect(only.flatMap((i) => i.elements.map((e) => e.globalId)).sort()).toEqual(['w1', 'w3']);
    expect(only.map((i) => i.elements.length).sort()).toEqual([1, 1]); // w1 alone: the group is the skipped part of the type
    skips.remove(['w1', 'w3']);
    expect(buildWalk({ ...base, filters: { onlySkipped: true } })).toEqual([]);
    skips.add(['w0', 'w1', 'w2']);
    expect(buildWalk({ ...base, filters: { onlySkipped: true } }).map((i) => i.elements.length)).toEqual([3]); // the whole group
    skips.clear();
    expect(skips.size).toBe(0);
  });
});
