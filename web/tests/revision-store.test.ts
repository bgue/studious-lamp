// Snapshots (encode, decode, detection), the store (eviction, sessions, resume, memory and IndexedDB backends) and the leak rule:
// nothing of this reaches localStorage, params, share links, views, presets or packed pages.
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { resolve } from 'node:path';
import { beforeAll, describe, expect, it } from 'vitest';
import type { ClassifyResult } from '../src/classify/types';
import { diffModels } from '../src/revision/diff';
import { SessionState, newSession, parseSession, sessionKey } from '../src/revision/session';
import { decodeSnapshot, encodeSnapshot, guidSketch, histogramSimilarity, nameStemOfFile, recordOf, revisionCandidates, sameStem, sketchJaccard, snapshotKey, stripFederation } from '../src/revision/snapshot';
import { DB_NAME, MemoryBackend, RevisionStore, SessionSaver, openIdbBackend, openRevisionBackend } from '../src/revision/store';
import type { ModelSnapshot } from '../src/revision/types';
import { cloneSnapshot, fzk1, loadIfc, prng, randomGuid, refresh, synthSnapshot, WEB } from './revision-helpers';

let v1: ModelSnapshot;
const result = (gid: string): ClassifyResult => ({
  id: gid, discipline: { code: 'ARC', label: 'Architecture', confidence: 0.9, probabilities: { ARC: 0.9, STR: 0.05, MEP: 0.03, CIV: 0.02 } }, subDiscipline: null,
  masterformat: { division: '06', title: 'Wood', confidence: 0.9, probabilities: { '06': 0.5, '05': 0.3, '07': 0.15, '08': 0.05 } }, buildingElement: 1,
  source: gid.charCodeAt(0) % 2 ? 'confirmed' : 'rules', needsReview: false,
});

beforeAll(async () => { v1 = (await loadIfc(fzk1(), { results: result })).snap; }, 60000);

describe('snapshot', () => {
  it('encodes and decodes to the same snapshot, with the results trimmed to the top 3 probabilities', async () => {
    const blob = await encodeSnapshot(v1);
    expect(blob.size).toBeGreaterThan(0);
    const back = await decodeSnapshot(blob);
    const { bounds, sig, guidSketch: sk, ...cols } = v1;
    const { bounds: b2, sig: s2, guidSketch: k2, ...cols2 } = back;
    expect(cols2).toEqual(cols);
    expect(b2).toEqual(bounds);
    expect(s2).toEqual(sig);
    expect(k2).toEqual(sk);
    const r = back.results.find(Boolean)!;
    expect(Object.keys(r.discipline.probabilities)).toHaveLength(3);
    expect(Object.keys(r.discipline.probabilities)).toEqual(['ARC', 'STR', 'MEP']);
    expect(Object.keys(r.masterformat!.probabilities)).toEqual(['06', '05', '07']);
  });

  it('is gzip-compressed and rejects what is not a snapshot', async () => {
    const blob = await encodeSnapshot(v1);
    const head = new Uint8Array(await blob.slice(0, 2).arrayBuffer());
    expect([head[0], head[1]]).toEqual([0x1f, 0x8b]);
    await expect(decodeSnapshot(new Blob([new Uint8Array([1, 2, 3, 4, 5, 6, 7, 8, 9])]))).rejects.toThrow(/not a model snapshot/);
  });

  it('makes a small record for detection', async () => {
    const rec = await recordOf(v1);
    expect(rec.key).toBe(snapshotKey(v1));
    expect(rec.counts.elements).toBe(v1.globalId.length);
    expect(rec.counts.results).toBe(v1.globalId.length);
    expect(rec.counts.committed).toBe(v1.results.filter((r) => r?.source === 'confirmed').length);
    expect(rec.size).toBe(rec.body.size);
    expect(rec.guidSketch.length).toBeLessThanOrEqual(256);
    expect(rec.identity).toEqual(v1.identity);
  });

  it('estimates the overlap of two GUID sets from the sketches', () => {
    const r = prng(5);
    const all = Array.from({ length: 6000 }, () => randomGuid(r));
    const a = guidSketch(all.slice(0, 4000)), b = guidSketch(all.slice(2000, 6000)); // 2000 shared of 6000 in the union: 1/3
    expect(sketchJaccard(a, b)).toBeGreaterThan(0.25);
    expect(sketchJaccard(a, b)).toBeLessThan(0.42);
    expect(sketchJaccard(a, a)).toBe(1);
    expect(sketchJaccard(a, guidSketch(['x', 'y']))).toBe(0);
    expect(sketchJaccard(new Uint32Array(0), a)).toBe(0);
    // small sets are exact, and the federation suffix does not matter
    expect(sketchJaccard(guidSketch(['a', 'b', 'c']), guidSketch(['b~2', 'c', 'd']))).toBeCloseTo(2 / 4, 10);
    expect(stripFederation('abc~12')).toBe('abc');
    expect(stripFederation('abc')).toBe('abc');
  });

  it('reduces a file name to its stem', () => {
    expect(nameStemOfFile('Haus.ifc')).toBe('haus');
    expect(nameStemOfFile('Haus (2).ifc')).toBe('haus');
    expect(nameStemOfFile('C:\\x\\Haus rev B.ifc')).toBe('haus');
    expect(nameStemOfFile('Haus_v3.ifc')).toBe('haus');
    expect(nameStemOfFile('Haus_2026-03-04.ifc')).toBe('haus');
    expect(nameStemOfFile('Haus-20260304.ifczip')).toBe('haus');
    expect(sameStem('Tower-A_v1.ifc', 'tower-a_v2.IFC')).toBe(true);
    expect(sameStem('Tower-A.ifc', 'Tower-B.ifc')).toBe(false);
    expect(sameStem('.ifc', '.ifc')).toBe(false);
    expect(histogramSimilarity({ a: 3, b: 4 }, { a: 3, b: 4 })).toBeCloseTo(1, 10);
    expect(histogramSimilarity({ a: 1 }, { b: 1 })).toBe(0);
  });
});

describe('detection (3.1)', () => {
  const small = (name: string, seed: number, savedAt: string): ModelSnapshot => synthSnapshot({ n: 40, name, seed, savedAt });
  it('offers a stored model that shares at least 30 % of the GUIDs, with the reason', async () => {
    const store = new RevisionStore();
    await store.saveSnapshot(v1);
    const head = (await loadIfc(resolve(WEB, 'tests/fixtures/ifc/fzk-v2.ifc'))).snap;
    const c = await store.candidates(head);
    expect(c).toHaveLength(1);
    expect(c[0]).toMatchObject({ key: snapshotKey(v1), reason: 'shared-guids', strength: 'strong', reviewed: v1.results.filter((r) => r?.source === 'confirmed').length });
    expect(c[0]!.overlap).toBeGreaterThan(0.6);
    expect(c[0]!.message).toMatch(/revision of AC20-FZK-Haus\.ifc .*shares \d+ % of its elements/);
    expect(await store.candidates(v1)).toEqual([]); // the same model is no candidate
  });

  it('offers a same-named model with other content, and a similar name with regenerated GUIDs as weak', async () => {
    const store = new RevisionStore();
    await store.saveSnapshot(small('Haus.ifc', 1, '2026-01-01T00:00:00Z'));
    await store.saveSnapshot(small('Plan_v1.ifc', 2, '2026-01-02T00:00:00Z'));
    await store.saveSnapshot(small('Other.ifc', 3, '2026-01-03T00:00:00Z'));
    const sameName = small('haus.IFC', 11, '2026-02-01T00:00:00Z');
    sameName.globalId = sameName.globalId.slice(0, 30).concat(Array.from({ length: 10 }, (_, i) => `n${i}`));
    expect((await store.candidates(refresh(sameName)))[0]).toMatchObject({ reason: 'same-name', strength: 'strong' });
    const regen = small('Plan_v2.ifc', 12, '2026-02-02T00:00:00Z'); // other GUIDs, the same mix of classes
    const found = await store.candidates(regen);
    expect(found.map((c) => [c.name, c.reason, c.strength])).toEqual([['Plan_v1.ifc', 'regenerated-guids', 'weak']]);
    // nothing for an unrelated model
    const lone = refresh(small('Unrelated.ifc', 13, '2026-02-03T00:00:00Z'));
    lone.ifcClass = lone.ifcClass.map(() => 'IfcRoof');
    expect(await store.candidates(refresh(lone))).toEqual([]);
  });

  it('lists candidates newest first', async () => {
    const store = new RevisionStore();
    const a = small('Haus.ifc', 1, '2026-01-01T00:00:00Z');
    const b = cloneSnapshot(a); b.globalId = b.globalId.slice(); b.identity = { ...a.identity, name: 'Haus_v2.ifc' }; b.savedAt = '2026-01-05T00:00:00Z';
    await store.saveSnapshot(a); await store.saveSnapshot(refresh(b, 'Haus_v2.ifc'));
    const head = refresh(cloneSnapshot(a), 'Haus_v3.ifc'); head.globalId = a.globalId.slice(0, 35).concat(['z1', 'z2', 'z3', 'z4', 'z5']);
    expect((await store.candidates(refresh(head, 'Haus_v3.ifc'))).map((c) => c.name)).toEqual(['Haus_v2.ifc', 'Haus.ifc']);
  });
});

describe('retention', () => {
  const small = (name: string, day: number): ModelSnapshot => synthSnapshot({ n: 30, name, seed: day, savedAt: `2026-01-${String(day).padStart(2, '0')}T00:00:00Z` });

  it('keeps the 3 newest snapshots per name stem and leaves other stems alone', async () => {
    const store = new RevisionStore();
    for (let d = 1; d <= 5; d++) await store.saveSnapshot(small(`Haus_v${d}.ifc`, d));
    await store.saveSnapshot(small('Garage.ifc', 6));
    expect((await store.records()).map((r) => r.name).sort()).toEqual(['Garage.ifc', 'Haus_v3.ifc', 'Haus_v4.ifc', 'Haus_v5.ifc']);
  });

  it('does not evict a snapshot that an open session refers to', async () => {
    const store = new RevisionStore();
    const oldest = small('Haus_v1.ifc', 1);
    await store.saveSnapshot(oldest);
    const head = small('Haus_v2.ifc', 2);
    await store.saveSnapshot(head);
    await store.saveSession(newSession({ base: oldest.identity, head: head.identity, diff: diffModels(oldest, head) }));
    for (let d = 3; d <= 6; d++) await store.saveSnapshot(small(`Haus_v${d}.ifc`, d));
    const names = (await store.records()).map((r) => r.name).sort();
    expect(names).toContain('Haus_v1.ifc');
    expect(names).toContain('Haus_v2.ifc');
    expect(names).not.toContain('Haus_v3.ifc');
    // once the session is finished the protection ends
    const s = (await store.sessions())[0]!;
    s.status = 'finished';
    await store.saveSession(s);
    await store.evict();
    expect((await store.records()).map((r) => r.name).sort()).toEqual(['Haus_v4.ifc', 'Haus_v5.ifc', 'Haus_v6.ifc']);
  });

  it('evicts the oldest first when the total size is over the limit', async () => {
    const store = new RevisionStore(new MemoryBackend(), { maxBytes: 1 });
    await store.saveSnapshot(small('A.ifc', 1));
    await store.saveSnapshot(small('B.ifc', 2));
    expect(await store.records()).toHaveLength(0);
    const big = new RevisionStore(new MemoryBackend(), { maxBytes: 1e9 });
    await big.saveSnapshot(small('A.ifc', 1)); await big.saveSnapshot(small('B.ifc', 2));
    const sizes = (await big.records()).sort((a, b) => (a.savedAt < b.savedAt ? -1 : 1)).map((r) => r.size);
    const limited = new RevisionStore(new MemoryBackend(), { maxBytes: sizes[1]! + 10 });
    await limited.saveSnapshot(small('A.ifc', 1)); await limited.saveSnapshot(small('B.ifc', 2));
    expect((await limited.records()).map((r) => r.name)).toEqual(['B.ifc']);
  });

  it('loads a stored snapshot back', async () => {
    const store = new RevisionStore();
    const s = small('Haus_v1.ifc', 1);
    await store.saveSnapshot(s);
    const back = await store.loadSnapshot(snapshotKey(s));
    expect(back!.globalId).toEqual(s.globalId);
    expect(back!.sig).toEqual(s.sig);
    expect(await store.loadSnapshot('nope')).toBeNull();
  });
});

describe('sessions', () => {
  const pair = (): { a: ModelSnapshot; b: ModelSnapshot } => {
    const a = synthSnapshot({ n: 60, name: 'Haus_v1.ifc', seed: 1 });
    const b = cloneSnapshot(a);
    b.globalId = a.globalId.slice(0, 50).concat(Array.from({ length: 10 }, (_, i) => `new${i}`));
    for (let i = 50; i < 60; i++) b.sig[i * 11 + 2]! += 500; // the last ten are new elements, far from the old ones
    return { a, b: refresh(b, 'Haus_v2.ifc') };
  };

  /** A clock that the test advances by hand. */
  function timers() {
    let now = 0, id = 0;
    const pending = new Map<number, { at: number; fn: () => void }>();
    return {
      setTimer: (fn: () => void, ms: number) => { pending.set(++id, { at: now + ms, fn }); return id; },
      clearTimer: (t: unknown) => { pending.delete(t as number); },
      advance(ms: number) { now += ms; for (const [k, t] of [...pending]) if (t.at <= now) { pending.delete(k); t.fn(); } },
      get count() { return pending.size; },
    };
  }

  it('saves 500 ms after the last change, and at once on flush', async () => {
    const { a, b } = pair();
    const store = new RevisionStore();
    const state = new SessionState(newSession({ base: a.identity, head: b.identity, diff: diffModels(a, b) }));
    const t = timers();
    const saver = new SessionSaver(store, () => state.session, { setTimer: t.setTimer, clearTimer: t.clearTimer });
    const key = state.key;
    state.decide({ key: state.session.diff.entries[0]!.key, verdict: 'accepted', classification: 'new', by: 'Ana' }); saver.schedule();
    t.advance(300);
    state.skip([state.session.diff.entries[1]!.key]); saver.schedule(); // restarts the wait
    t.advance(300);
    expect(await store.loadSession(key)).toBeNull();
    expect(t.count).toBe(1);
    t.advance(250);
    await saver.flush();
    expect((await store.loadSession(key))!.skipped).toHaveLength(1);
    state.setCursor({ itemKey: 'k', elementIndex: 3 }); saver.schedule();
    await saver.flush(); // visibilitychange / pagehide: no waiting
    expect(t.count).toBe(0);
    expect((await store.loadSession(key))!.cursor).toMatchObject({ itemKey: 'k', elementIndex: 3 });
    expect(saver.lastError).toBeNull();
  });

  it('resumes: finds the open session by the head, restores decisions, skips and cursor, and lists what to redo', async () => {
    const { a, b } = pair();
    const store = new RevisionStore();
    const diff = diffModels(a, b);
    const state = new SessionState(newSession({ base: a.identity, head: b.identity, diff, carried: { commits: ['c1~x'], results: 40 } }));
    const [e1, e2, e3, e4] = diff.entries;
    state.decide({ key: e1!.key, verdict: 'accepted', classification: 'new', by: 'Ana' });
    state.decide({ key: e2!.key, verdict: 'accepted', classification: 'kept', by: 'Ana', commitId: 'c7' });
    state.decide({ key: e3!.key, verdict: 'rejected', classification: 'none', by: 'Ana', note: 'wrong', unsure: true });
    state.skip([e4!.key]);
    state.setCursor({ order: 'storey', filters: { flag: 'placement' }, itemKey: 'x', elementIndex: 2 });
    await store.saveSession(state.session);

    const found = await store.openSessionFor(b.identity); // after a reload the user opens the head file again
    expect(found).not.toBeNull();
    const again = new SessionState(found!);
    expect(again.key).toBe(sessionKey(a.identity, b.identity));
    expect(again.resumeLabel()).toBe(`Resume revision review (3 of ${diff.entries.length} decided)`);
    expect(again.session.cursor).toEqual({ order: 'storey', filters: { flag: 'placement' }, itemKey: 'x', elementIndex: 2 });
    expect(again.isSkipped(e4!.key)).toBe(true);
    expect(again.session.diff.entries).toHaveLength(diff.entries.length); // the diff is in the session: nothing is recomputed
    expect(again.pendingProposals().map((d) => d.key)).toEqual([e1!.key]); // e2 has its commit
    expect(again.needsClassify(() => false).length).toBeGreaterThan(0);
    expect(again.session.carried).toEqual({ commits: ['c1~x'], results: 40 });
    // a different head model is not offered this session; neither is a finished one
    expect(await store.openSessionFor(a.identity)).toBeNull();
    found!.status = 'finished';
    await store.saveSession(found!);
    expect(await store.openSessionFor(b.identity)).toBeNull();
    await store.deleteSession(found!.key);
    expect(await store.sessions()).toEqual([]);
  });

  it('survives the loss of its base snapshot (ghosts fall back to boxes)', async () => {
    const { a, b } = pair();
    const store = new RevisionStore();
    await store.saveSnapshot(a);
    await store.saveSession(newSession({ base: a.identity, head: b.identity, diff: diffModels(a, b) }));
    await store.backend.deleteSnapshot(snapshotKey(a));
    expect(await store.openSessionFor(b.identity)).not.toBeNull();
    expect(await store.backend.getGhosts('none')).toBeNull();
  });

  it('reads a stored session defensively', () => {
    expect(parseSession(null).session).toBeNull();
    expect(parseSession({ schema: 'other' }).errors[0]).toMatch(/Not a revision session/);
    const { a, b } = pair();
    const s = newSession({ base: a.identity, head: b.identity, diff: diffModels(a, b) });
    const messy = JSON.parse(JSON.stringify(s)) as Record<string, unknown>;
    messy['decisions'] = { ok: { verdict: 'accepted', classification: 'weird', at: 't', by: 'x' }, bad: { verdict: 'maybe' }, junk: 5 };
    messy['skipped'] = ['a', 3, 'b'];
    messy['cursor'] = { order: 'nonsense', elementIndex: -4 };
    messy['options'] = { moveTol: 0.5 };
    const p = parseSession(messy).session!;
    expect(Object.keys(p.decisions)).toEqual(['ok']);
    expect(p.decisions['ok']!.classification).toBe('none');
    expect(p.skipped).toEqual(['a', 'b']);
    expect(p.cursor).toEqual({ order: 'category', filters: {}, itemKey: null, elementIndex: 0 });
    expect(p.options.moveTol).toBe(0.5);
    expect(p.options.areaTol).toBe(0.005);
    expect(parseSession({ ...messy, diff: {} }).errors[0]).toMatch(/diff\.entries/);
  });
});

describe('backends', () => {
  it('keeps data in memory when there is no IndexedDB, and says so', async () => {
    const be = await openRevisionBackend(null);
    expect(be.persistent).toBe(false);
    expect(new RevisionStore(be).persistent).toBe(false);
    expect(await openIdbBackend(undefined as unknown as IDBFactory | undefined)).toBeNull();
    const refusing = { open: () => { const r: Record<string, unknown> = {}; queueMicrotask(() => (r['onerror'] as () => void)()); return r; } } as unknown as IDBFactory;
    expect(await openIdbBackend(refusing)).toBeNull();
  });

  it('works against an IndexedDB (a small in-memory fake): stores, index names, round trip', async () => {
    const fake = fakeIdb();
    const be = await openIdbBackend(fake.factory);
    expect(be).not.toBeNull();
    expect(be!.persistent).toBe(true);
    expect(fake.dbName).toBe(DB_NAME);
    expect(fake.stores).toEqual({ snapshots: { keyPath: 'key', indexes: ['name'] }, sessions: { keyPath: 'key', indexes: ['headKey'] }, ghosts: { keyPath: undefined, indexes: [] } });
    const store = new RevisionStore(be!);
    const s = synthSnapshot({ n: 20, name: 'Haus_v1.ifc', seed: 4 });
    await store.saveSnapshot(s);
    expect((await store.loadSnapshot(snapshotKey(s)))!.globalId).toEqual(s.globalId);
    const t = synthSnapshot({ n: 20, name: 'Haus_v2.ifc', seed: 5 });
    const session = newSession({ base: s.identity, head: t.identity, diff: diffModels(s, t) });
    await store.saveSession(session);
    expect(fake.rows('sessions')[0]!['headKey']).toBe(`${t.identity.name.toLowerCase()}|${t.identity.elementCount}|${t.identity.guidHash}`);
    expect((await store.openSessionFor(t.identity))!.key).toBe(session.key);
    await be!.putGhosts(session.key, new Blob(['g']));
    expect(await be!.getGhosts(session.key)).not.toBeNull();
    await store.deleteSession(session.key);
    expect(await be!.getGhosts(session.key)).toBeNull();
  });
});

describe('leak rule', () => {
  it('never touches localStorage or sessionStorage', async () => {
    const calls: string[] = [];
    const trap = new Proxy({}, { get: (_t, k) => { calls.push(String(k)); return () => null; }, set: (_t, k) => { calls.push(`set ${String(k)}`); return true; } });
    const g = globalThis as unknown as Record<string, unknown>;
    const saved = { l: g['localStorage'], s: g['sessionStorage'] };
    g['localStorage'] = trap; g['sessionStorage'] = trap;
    try {
      const store = new RevisionStore();
      const a = synthSnapshot({ n: 30, name: 'Haus_v1.ifc', seed: 1 }), b = synthSnapshot({ n: 30, name: 'Haus_v2.ifc', seed: 2 });
      await store.saveSnapshot(a);
      await store.candidates(b);
      const st = new SessionState(newSession({ base: a.identity, head: b.identity, diff: diffModels(a, b) }));
      st.decide({ key: st.session.diff.entries[0]!.key, verdict: 'accepted', classification: 'new', by: 'Ana' });
      await store.saveSession(st.session);
      await store.openSessionFor(b.identity);
      await store.evict();
    } finally {
      g['localStorage'] = saved.l; g['sessionStorage'] = saved.s;
    }
    expect(calls).toEqual([]);
  });

  it('is referenced by no module that builds params, links, views, presets or packed pages, and uses no browser location', () => {
    const src = resolve(WEB, 'src');
    const walk = (dir: string): string[] => readdirSync(dir).flatMap((f) => { const p = resolve(dir, f); return statSync(p).isDirectory() ? walk(p) : p.endsWith('.ts') ? [p] : []; });
    const files = walk(src);
    const own = (p: string): boolean => /\/src\/revision\//.test(p) || /\/src\/plugins\/revision[A-Za-z]*\.ts$/.test(p);
    for (const f of files.filter((p) => !own(p))) {
      const text = readFileSync(f, 'utf8');
      expect(text.includes('xray-revisions'), `${f} names the revision database`).toBe(false);
      expect(/from '(\.\.?\/)+revision\//.test(text) && !/\/src\/plugins\//.test(f) && !/\/src\/classify\//.test(f), `${f} imports the revision core`).toBe(false);
    }
    for (const f of files.filter((p) => /\/src\/revision\//.test(p))) {
      const text = readFileSync(f, 'utf8').replace(/\/\/.*$/gm, '');
      expect(/localStorage|sessionStorage|URLSearchParams|location\.|history\.(push|replace)State/.test(text), `${f} uses browser storage or the URL`).toBe(false);
    }
  });
});

// ---------------------------------------------------------------- a small in-memory IndexedDB, enough for the backend

function fakeIdb() {
  const data = new Map<string, Map<string, Record<string, unknown>>>();
  const meta: Record<string, { keyPath: string | undefined; indexes: string[] }> = {};
  const out = { dbName: '', stores: meta, rows: (s: string) => [...(data.get(s)?.values() ?? [])], factory: null as unknown as IDBFactory };
  const request = <T>(fn: () => T): IDBRequest<T> => {
    const r: Record<string, unknown> = {};
    queueMicrotask(() => { try { r['result'] = fn(); (r['onsuccess'] as (() => void) | undefined)?.(); } catch (e) { r['error'] = e; (r['onerror'] as (() => void) | undefined)?.(); } });
    return r as unknown as IDBRequest<T>;
  };
  const objectStore = (name: string): IDBObjectStore => {
    const rows = data.get(name)!;
    const keyPath = meta[name]!.keyPath;
    return {
      put: (v: Record<string, unknown>, k?: string) => request(() => { rows.set(String(keyPath ? v[keyPath] : k), v); return undefined; }),
      get: (k: string) => request(() => rows.get(String(k))),
      getAll: () => request(() => [...rows.values()]),
      delete: (k: string) => request(() => { rows.delete(String(k)); return undefined; }),
    } as unknown as IDBObjectStore;
  };
  out.factory = {
    open: (name: string) => {
      out.dbName = name;
      const r: Record<string, unknown> = {};
      const db = {
        createObjectStore: (n: string, o?: { keyPath?: string }) => { data.set(n, new Map()); meta[n] = { keyPath: o?.keyPath, indexes: [] }; return { createIndex: (i: string) => { meta[n]!.indexes.push(i); } }; },
        transaction: (n: string) => ({ objectStore: () => objectStore(n) }),
      };
      queueMicrotask(() => { r['result'] = db; (r['onupgradeneeded'] as () => void)(); (r['onsuccess'] as () => void)(); });
      return r;
    },
  } as unknown as IDBFactory;
  return out;
}
