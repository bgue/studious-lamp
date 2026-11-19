// Saved 3D sketches and issues: the round trip through the store (snapshot bytes, links), one record per model, restore on model
// load, debounced saves, "clear all", and the guarantee that none of it goes into the places that travel.
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it, vi } from 'vitest';
import { BcfController } from '../src/bcf/controller';
import { emptyProject, newGuid } from '../src/bcf/model';
import type { BcfTopic } from '../src/bcf/model';
import { addMarkup, modelIdentity, newMarkup, SHEET_CAMERA, SHEET_VIEW } from '../src/markup/model';
import type { MarkupSet, ModelIdentity } from '../src/markup/model';
import { identityKey } from '../src/markup/scope';
import { sanitizeView, VIEW_EXCLUDED_SECTIONS } from '../src/views/model';
import { SAVE_DELAY_MS, WorkPersistence, groupByModel, recordOf, signature } from '../src/work/persist';
import { MemoryWorkBackend, WorkStore } from '../src/work/store';

const IDS: Record<string, string[]> = { 'A.ifc': ['g1', 'g2', 'g3'], 'B.ifc': ['h1', 'h2'] };
const A: ModelIdentity = modelIdentity('A.ifc', 3, IDS['A.ifc']!);
const B: ModelIdentity = modelIdentity('B.ifc', 2, IDS['B.ifc']!);
const CAMERA = { position: [20, -10, 8] as [number, number, number], direction: [-0.8, 0.5, -0.3] as [number, number, number], up: [0, 0, 1] as [number, number, number], fov: 38, aspect: 1.6 };
const PNG = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 1, 2, 3, 4]);

function sketch(id: string, model: ModelIdentity | null, title = id): MarkupSet {
  const set: MarkupSet = {
    id, title, author: 'Ana', created: '2026-01-01T10:00:00.000Z', updated: '2026-01-01T10:00:00.000Z',
    view: { id: 'v1', name: title, created: '2026-01-01T10:00:00.000Z', updated: '2026-01-01T10:00:00.000Z', camera: { position: [6, 5.5, 13], target: [0, 0, 0], up: [0, 1, 0], fov: 38, ortho: false }, selection: [], params: {} },
    camera: { ...CAMERA }, markups: [], nextNumber: 1, model,
  };
  addMarkup(set, newMarkup('rect', { author: 'Ana', shape: { points: [[0.2, 0.2], [0.5, 0.4]], depth: 12 } }));
  return set;
}

function topic(title: string, model: ModelIdentity | null, sketchId?: string): BcfTopic {
  const g = newGuid();
  const t: BcfTopic = {
    guid: newGuid(), topicType: 'Issue', topicStatus: 'Open', title, labels: [], referenceLinks: [], creationDate: '2026-01-02T10:00:00Z', creationAuthor: 'Ana',
    headerFiles: [], documentReferences: [], relatedTopics: [], comments: [],
    viewpoints: [{ guid: g, snapshot: PNG.slice(), snapshotMime: 'image/png', captureSeeThrough: new Set([1, 2]), ...(sketchId ? { sketchId } : {}), data: { guid: g, camera: { kind: 'perspective', ...CAMERA }, selection: [], visibility: null, coloring: [], clipping: [], lines: [] } }],
  };
  if (model) t.model = { ...model };
  return t;
}

/** The two controllers as far as the persistence uses them. */
function fakes(initialModel: ModelIdentity) {
  const els = (m: ModelIdentity) => IDS[m.name]!.map((globalId) => ({ globalId }));
  const app = { loaded: {} as object | null, modelName: initialModel.name, controller: { model: { elements: els(initialModel) } } };
  const mkL = new Set<() => void>();
  const bcL = new Set<() => void>();
  const mk = {
    sets: [] as MarkupSet[],
    onChange: (cb: () => void) => { mkL.add(cb); },
    get: (id: string) => mk.sets.find((s) => s.id === id),
    adoptSet: (s: MarkupSet) => { mk.sets.push(s); mkL.forEach((l) => l()); return s; },
    deleteSet: (id: string) => { mk.sets = mk.sets.filter((s) => s.id !== id); mkL.forEach((l) => l()); },
    setStatus: () => undefined,
    fire: () => mkL.forEach((l) => l()),
  };
  const bcf = {
    project: emptyProject('2.1'),
    dirty: false,
    markupRev: 0,
    get topics() { return bcf.project.topics; },
    onChange: (cb: () => void) => { bcL.add(cb); },
    setStatus: () => undefined,
    deleteTopic: (g: string) => { bcf.project.topics = bcf.project.topics.filter((t) => t.guid !== g); bcL.forEach((l) => l()); return true; },
    adoptTopics: (t: readonly BcfTopic[], d: never[] = []) => BcfController.prototype.adoptTopics.call(bcf, t, d),
    fire: () => bcL.forEach((l) => l()),
  };
  return { app, mk, bcf };
}

function make(model: ModelIdentity, store: WorkStore) {
  const f = fakes(model);
  const p = new WorkPersistence(f.app as never, f.mk as never, f.bcf as never, store);
  return { ...f, p };
}

describe('the work store', () => {
  it('round-trips sketches, issues, links and snapshot bytes, and drops the session-only parts', async () => {
    const be = new MemoryWorkBackend();
    const store = new WorkStore(async () => be);
    const s = sketch('s1', A);
    const t = topic('Clash', A, 's1');
    const g = groupByModel([s], [t], A).get(identityKey(A))!;
    await store.put(recordOf(identityKey(A), g, []));
    const back = (await new WorkStore(async () => be).get(identityKey(A)))!;
    expect(back.sets[0]!.id).toBe('s1');
    expect(back.sets[0]!.markups).toHaveLength(1);
    expect(back.topics[0]!.title).toBe('Clash');
    expect(back.topics[0]!.viewpoints[0]!.sketchId).toBe('s1');
    expect(Array.from(back.topics[0]!.viewpoints[0]!.snapshot!)).toEqual(Array.from(PNG));
    expect(back.topics[0]!.viewpoints[0]!.captureSeeThrough).toBeUndefined();
  });

  it('keeps one record per model', async () => {
    const store = new WorkStore(async () => new MemoryWorkBackend());
    const groups = groupByModel([sketch('a', A), sketch('b', B)], [topic('ta', A), topic('tb', B)], A);
    for (const [k, g] of groups) await store.put(recordOf(k, g, []));
    expect((await store.keys()).sort()).toEqual([identityKey(A), identityKey(B)].sort());
    expect((await store.get(identityKey(A)))!.sets.map((s) => s.id)).toEqual(['a']);
    expect((await store.get(identityKey(B)))!.topics.map((t) => t.title)).toEqual(['tb']);
  });

  it('leaves sheet sketches and read-only imports to the sheets store, and puts model-less items with the loaded model', () => {
    const sheet: MarkupSet = { ...sketch('sh', null), frame: { kind: 'sheet', sheet: 'doc-p1' }, view: sanitizeView(SHEET_VIEW('x')) as never, camera: SHEET_CAMERA() };
    const ro: MarkupSet = { ...sketch('ro', A), readonly: true };
    const g = groupByModel([sheet, ro, sketch('free', null)], [topic('free', null)], A);
    expect([...g.values()]).toHaveLength(1);
    const only = g.get(identityKey(A))!;
    expect(only.sets.map((s) => s.id)).toEqual(['free']);
    expect(only.topics).toHaveLength(1);
    expect(groupByModel([sketch('free', null)], [], null).size).toBe(0);
  });

  it('the signature ignores snapshot content, so an unchanged state is not written again', () => {
    const g = groupByModel([sketch('s1', A)], [topic('T', A)], A).get(identityKey(A))!;
    const r1 = recordOf('k', g, [], 'x');
    const r2 = recordOf('k', g, [], 'y');
    expect(signature(r1)).toBe(signature(r2));
    g.sets[0]!.title = 'changed';
    expect(signature(recordOf('k', g, []))).not.toBe(signature(r1));
  });
});

describe('the persistence of a session', () => {
  it('saves after a quiet moment, and a new session on the same model gets the sketch, the issue and the link back', async () => {
    vi.useFakeTimers();
    try {
      const be = new MemoryWorkBackend();
      const one = make(A, new WorkStore(async () => be));
      await vi.advanceTimersByTimeAsync(0);
      await one.p.onModel();
      one.mk.sets.push(sketch('s1', A));
      one.bcf.project.topics.push(topic('Clash', A, 's1'));
      one.mk.fire();
      one.mk.fire();
      expect(await be.keys()).toEqual([]); // debounced: nothing yet
      await vi.advanceTimersByTimeAsync(SAVE_DELAY_MS + 50);
      expect(await be.keys()).toEqual([identityKey(A)]);
      const put = vi.spyOn(be, 'put');
      one.mk.fire();
      await vi.advanceTimersByTimeAsync(SAVE_DELAY_MS + 50);
      expect(put).not.toHaveBeenCalled(); // unchanged: no write

      const two = make(A, new WorkStore(async () => be));
      await two.p.onModel();
      expect(two.mk.sets.map((s) => s.id)).toEqual(['s1']);
      expect(two.bcf.project.topics.map((t) => t.title)).toEqual(['Clash']);
      expect(two.bcf.project.topics[0]!.viewpoints[0]!.sketchId).toBe('s1');
      expect(two.bcf.project.topics[0]!.viewpoints[0]!.snapshot!.length).toBe(PNG.length);
    } finally {
      vi.useRealTimers();
    }
  });

  it('keeps each model apart: another model gets nothing, and its work is saved under its own key', async () => {
    const be = new MemoryWorkBackend();
    const a = make(A, new WorkStore(async () => be));
    await a.p.onModel();
    a.mk.sets.push(sketch('sa', A));
    await a.p.save();
    const b = make(B, new WorkStore(async () => be));
    await b.p.onModel();
    expect(b.mk.sets).toHaveLength(0);
    expect(b.bcf.project.topics).toHaveLength(0);
    b.mk.sets.push(sketch('sb', B));
    b.bcf.project.topics.push(topic('tb', B));
    await b.p.save();
    expect((await be.get(identityKey(A)))!.sets.map((s) => s.id)).toEqual(['sa']);
    expect((await be.get(identityKey(B)))!.sets.map((s) => s.id)).toEqual(['sb']);
    // back on A: only A's work
    const a2 = make(A, new WorkStore(async () => be));
    await a2.p.onModel();
    expect(a2.mk.sets.map((s) => s.id)).toEqual(['sa']);
    expect(a2.bcf.project.topics).toHaveLength(0);
  });

  it('an item that names no model stays with the model it was first seen on when another model loads', async () => {
    const be = new MemoryWorkBackend();
    const a = make(A, new WorkStore(async () => be));
    await a.p.onModel();
    a.bcf.project.topics.push(topic('foreign', null));
    await a.p.save();
    expect((await be.get(identityKey(A)))!.topics).toHaveLength(1);
    // model B is loaded into the same session: the topic is still shown (unknown), but is saved with A
    (a.app as { loaded: object | null; modelName: string; controller: { model: { elements: Array<{ globalId: string }> } } }).loaded = {};
    (a.app as { modelName: string }).modelName = 'B.ifc';
    (a.app as { controller: { model: { elements: Array<{ globalId: string }> } } }).controller.model.elements = IDS['B.ifc']!.map((globalId) => ({ globalId }));
    await a.p.onModel();
    await a.p.save();
    expect((await be.get(identityKey(A)))!.topics).toHaveLength(1);
    expect(await be.get(identityKey(B))).toBeNull();
  });

  it('does not write (and so cannot wipe the saved copy) before the saved items are read back', async () => {
    const be = new MemoryWorkBackend();
    const a = make(A, new WorkStore(async () => be));
    await a.p.onModel();
    a.mk.sets.push(sketch('sa', A));
    await a.p.save();
    const b = make(A, new WorkStore(async () => be));
    await b.p.save(); // restore has not run yet
    expect((await be.get(identityKey(A)))!.sets).toHaveLength(1);
  });

  it('"Clear all" removes the sketches and issues of this model, here and in the saved copy, and leaves other models alone', async () => {
    const be = new MemoryWorkBackend();
    const a = make(A, new WorkStore(async () => be));
    await a.p.onModel();
    a.mk.sets.push(sketch('sa', A), sketch('sb', B));
    a.bcf.project.topics.push(topic('ta', A), topic('tb', B));
    await a.p.save();
    expect(a.p.counts()).toEqual({ sketches: 1, issues: 1 });
    expect(await a.p.clearModel()).toEqual({ sketches: 1, issues: 1 });
    expect(a.mk.sets.map((s) => s.id)).toEqual(['sb']);
    expect(a.bcf.project.topics.map((t) => t.title)).toEqual(['tb']);
    expect(await be.get(identityKey(A))).toBeNull();
    expect((await be.get(identityKey(B)))!.sets).toHaveLength(1);
    const again = make(A, new WorkStore(async () => be));
    await again.p.onModel();
    expect(again.mk.sets).toHaveLength(0);
  });

  it('works without IndexedDB: nothing persists, nothing throws', async () => {
    const s = new WorkStore(async () => null);
    const a = make(A, s);
    await a.p.onModel();
    a.mk.sets.push(sketch('sa', A));
    await a.p.save();
    expect(a.p.persistent).toBe(false);
  });
});

describe('saved sketches and issues stay out of the places that travel', () => {
  const strip = (t: string): string => t.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '');

  it('the work code never touches localStorage, sessionStorage, the URL, history or share links', () => {
    const dir = fileURLToPath(new URL('../src/work/', import.meta.url));
    const files = (readdirSync(dir) as string[]).filter((f) => f.endsWith('.ts'));
    expect(files.length).toBeGreaterThanOrEqual(2);
    for (const f of files) {
      expect(strip(readFileSync(dir + f, 'utf8')), f).not.toMatch(/localStorage|sessionStorage|location\.(hash|search|href\s*=)|history\.(push|replace)State|URLSearchParams|registerParamSection|shareUrl/);
    }
    const plugin = strip(readFileSync(fileURLToPath(new URL('../src/plugins/work.ts', import.meta.url)), 'utf8'));
    expect(plugin).not.toMatch(/localStorage|sessionStorage|registerParamSection|shareUrl|URLSearchParams/);
  });

  it('only the work store opens IndexedDB in src/work, and the other places that travel never name the work database', () => {
    const dir = fileURLToPath(new URL('../src/work/', import.meta.url));
    for (const f of readdirSync(dir) as string[]) {
      if (!f.endsWith('.ts') || f === 'store.ts') continue;
      expect(readFileSync(dir + f, 'utf8'), f).not.toMatch(/indexedDB/);
    }
    const root = fileURLToPath(new URL('../src/', import.meta.url));
    for (const d of ['views', 'ui']) {
      for (const f of readdirSync(root + d) as string[]) {
        if (f.endsWith('.ts')) expect(readFileSync(`${root}${d}/${f}`, 'utf8'), `${d}/${f}`).not.toMatch(/xray-work|src\/work|\.\.\/work\//);
      }
    }
    for (const f of ['plugins/presets.ts', 'plugins/exportParams.ts', 'plugins/views.ts']) {
      expect(readFileSync(root + f, 'utf8'), f).not.toMatch(/xray-work|\.\.\/work\//);
    }
  });

  it('saved views never take the sketches or issues sections', () => {
    expect(VIEW_EXCLUDED_SECTIONS).toContain('sheets');
    expect(VIEW_EXCLUDED_SECTIONS.join(' ')).not.toMatch(/work/);
  });
});
