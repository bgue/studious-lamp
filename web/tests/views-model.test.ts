// Saved views, pure parts: storage format and versioning, list operations, GlobalId remapping of hides / isolate,
// params diff and merge, share-link encoding.
import { describe, expect, it } from 'vitest';
import { MemoryStorage } from '../src/selectionSets';
import {
  VIEWS_SCHEMA,
  changedSections,
  compactHides,
  decodeViewShare,
  defaultName,
  diffParams,
  duplicateView,
  encodeViewShare,
  expandHides,
  filterParams,
  filterViews,
  findView,
  fromBase64Url,
  hashWithoutView,
  loadPackedSeen,
  loadViews,
  mergePackedViews,
  mergeParams,
  mergeViews,
  moveView,
  parseViewsDocument,
  resolveGlobalIds,
  sanitizeView,
  savePackedSeen,
  saveViews,
  shareView,
  stepIndex,
  packedSeenKey,
  storageKey,
  toBase64Url,
  uniqueName,
  viewShareFromHash,
  viewShareUrl,
  viewSummary,
  viewsDocument,
} from '../src/views/model';
import type { SavedView } from '../src/views/model';

function view(name: string, extra: Partial<SavedView> = {}): SavedView {
  return {
    id: `id-${name}`,
    name,
    created: '2026-01-01T00:00:00.000Z',
    updated: '2026-01-01T00:00:00.000Z',
    camera: { position: [10, 8, 10], target: [0, 1, 0], up: [0, 1, 0], fov: 50, ortho: false },
    selection: ['G1'],
    params: { schema: 'xray-params/1', xray: true, section: { box: { enabled: true } } },
    ...extra,
  };
}

describe('storage format', () => {
  it('round-trips through storage under xray.views.<model>', () => {
    const st = new MemoryStorage();
    const views = [view('A', { thumb: 'data:image/jpeg;base64,AAAA' }), view('B', { hides: { mode: 'show', ids: ['G2'] }, pins: ['G3'], exploded: true })];
    expect(saveViews(st, 'fzk-haus', views)).toBe(true);
    const raw = JSON.parse(st.getItem(storageKey('fzk-haus'))!);
    expect(raw.schema).toBe(VIEWS_SCHEMA);
    expect(raw.model).toBe('fzk-haus');
    expect(loadViews(st, 'fzk-haus').views).toEqual(views);
    expect(loadViews(st, 'other').views).toEqual([]);
  });

  it('removes the key when the list is empty, and tolerates a throwing storage', () => {
    const st = new MemoryStorage();
    saveViews(st, 'm', [view('A')]);
    saveViews(st, 'm', []);
    expect(st.getItem(storageKey('m'))).toBeNull();
    const bad = { getItem: () => { throw new Error('denied'); }, setItem: () => { throw new Error('quota'); } };
    expect(saveViews(bad, 'm', [view('A')])).toBe(false);
    expect(loadViews(bad, 'm').views).toEqual([]);
    expect(loadViews(null, 'm').views).toEqual([]);
  });

  it('accepts a bare list as version 1 and refuses a newer major version', () => {
    expect(parseViewsDocument([view('A')]).views.map((v) => v.name)).toEqual(['A']);
    const newer = parseViewsDocument({ schema: 'xray-views/2', views: [view('A')] });
    expect(newer.error).toMatch(/newer/);
    expect(newer.views).toEqual([]);
    expect(parseViewsDocument({ schema: 'xray-params/1' }).error).toMatch(/not a views document/);
    expect(parseViewsDocument('{oops').error).toMatch(/not JSON/);
  });

  it('sanitises entries: fills defaults, drops bad ones with a reason, makes ids unique', () => {
    const p = parseViewsDocument({
      schema: VIEWS_SCHEMA,
      model: 'm',
      views: [
        { name: 'Old', camera: { position: [1, 2, 3], target: [0, 0, 0] } },
        { name: 'NoCam' },
        { camera: { position: [1, 2, 3], target: [0, 0, 0] } },
        { ...view('Dup'), id: 'same', thumb: 'javascript:alert(1)', junk: 1 },
        { ...view('Dup2'), id: 'same' },
      ],
    });
    expect(p.model).toBe('m');
    expect(p.views.map((v) => v.name)).toEqual(['Old', 'Dup', 'Dup2']);
    expect(p.bad).toHaveLength(2);
    expect(p.views[0]!.camera).toEqual({ position: [1, 2, 3], target: [0, 0, 0], up: [0, 1, 0], fov: 50, ortho: false });
    expect(p.views[0]!.selection).toEqual([]);
    expect(p.views[1]!.thumb).toBeUndefined();
    expect('junk' in p.views[1]!).toBe(false);
    expect(new Set(p.views.map((v) => v.id)).size).toBe(3);
  });

  it('reads a shared single view document', () => {
    const p = parseViewsDocument({ schema: 'xray-view/1', model: 'm', view: view('S') });
    expect(p.views.map((v) => v.name)).toEqual(['S']);
  });

  it('exports with or without thumbnails', () => {
    const d = viewsDocument('m', [view('A', { thumb: 'data:image/jpeg;base64,AA' })], false);
    expect(d.views[0]!.thumb).toBeUndefined();
    expect(viewsDocument('m', [view('A', { thumb: 'data:image/jpeg;base64,AA' })]).views[0]!.thumb).toBeDefined();
  });
});

describe('list operations', () => {
  const list = [view('A'), view('B'), view('C')];

  it('moves, duplicates, filters, finds and steps', () => {
    expect(moveView(list, 0, 2).map((v) => v.name)).toEqual(['B', 'C', 'A']);
    expect(moveView(list, 2, 0).map((v) => v.name)).toEqual(['C', 'A', 'B']);
    const d = duplicateView(list, 1);
    expect(d.map((v) => v.name)).toEqual(['A', 'B', 'B copy', 'C']);
    expect(d[2]!.id).not.toBe('id-B');
    expect(filterViews(list, 'b')).toEqual([1]);
    expect(filterViews(list, '')).toEqual([0, 1, 2]);
    expect(findView(list, 'id-C')).toBe(2);
    expect(findView(list, 'c')).toBe(2);
    expect(findView(list, '2')).toBe(1);
    expect(findView(list, 'nope')).toBe(-1);
    expect(stepIndex(-1, 3, 1)).toBe(0);
    expect(stepIndex(-1, 3, -1)).toBe(2);
    expect(stepIndex(2, 3, 1)).toBe(0);
    expect(stepIndex(0, 3, -1)).toBe(2);
    expect(stepIndex(0, 0, 1)).toBe(-1);
  });

  it('names: unique and default', () => {
    expect(uniqueName('A', list)).toBe('A 2');
    expect(uniqueName('a', list, 'id-A')).toBe('a');
    expect(defaultName(list)).toBe('View 4');
  });

  it('merges imports: newer replaces, older is ignored, deleted ids are skipped, names made unique', () => {
    const newer = { ...view('B'), name: 'B new', updated: '2026-02-01T00:00:00.000Z' };
    const older = { ...view('C'), name: 'C old', updated: '2025-01-01T00:00:00.000Z' };
    const fresh = { ...view('A'), id: 'other' };
    const gone = { ...view('Z'), id: 'deleted' };
    const r = mergeViews(list, [newer, older, fresh, gone], new Set(['deleted']));
    expect(r.views.map((v) => v.name)).toEqual(['A', 'B new', 'C', 'A 2']);
    expect(r).toMatchObject({ added: 1, replaced: 1 });
  });

  it('summarises a view in one line', () => {
    const v = view('A', {
      params: { xray: true, section: { box: { enabled: true }, plane: { enabled: true } }, viewModes: { behind: { enabled: true }, peel: { enabled: false } }, imaging: { style: 'radiograph' } },
      hides: { mode: 'show', ids: ['G1', 'G2'] },
      camera: { position: [1, 1, 1], target: [0, 0, 0], up: [0, 1, 0], fov: 50, ortho: true },
    });
    expect(viewSummary(v)).toBe('x-ray · box · plane · behind · radiograph · ortho · isolate 2 · 1 selected');
  });
});

describe('GlobalId remapping', () => {
  // The same GlobalIds at other element ids, as after a reconversion of the IFC file.
  const reloaded = new Map([['G3', 0], ['G2', 1], ['G1', 2], ['G0', 3]]);

  it('resolves GlobalIds to the new ids and lists the missing ones', () => {
    expect(resolveGlobalIds(reloaded, ['G1', 'GX', 'G3'])).toEqual({ ids: [2, 0], missing: ['GX'] });
  });

  it('stores an isolate as the visible elements and expands it against the reloaded model', () => {
    const all = ['G0', 'G1', 'G2', 'G3'];
    expect(compactHides([], all)).toBeUndefined();
    expect(compactHides(['G0'], all)).toEqual({ mode: 'hide', ids: ['G0'] });
    const iso = compactHides(['G0', 'G2', 'G3'], all)!;
    expect(iso).toEqual({ mode: 'show', ids: ['G1'] });
    const e = expandHides(iso, reloaded, 4);
    expect(e.ids).toEqual([0, 1, 3]); // all but G1, which is element 2 now
    expect(expandHides({ mode: 'hide', ids: ['G0', 'GX'] }, reloaded, 4)).toEqual({ ids: [3], missing: ['GX'] });
  });
});

describe('params diff and merge', () => {
  const factory = { xray: true, sightlines: { alphaMin: 0.1, gamma: 1 }, section: { box: { enabled: false, min: null }, caps: true }, tiers: [['a'], ['b']] };

  it('diff keeps only differing leaves; merge restores the full document', () => {
    const full = { xray: false, sightlines: { alphaMin: 0.1, gamma: 2 }, section: { box: { enabled: true, min: [0, 0, 0] }, caps: true }, tiers: [['a'], ['b']], imaging: { style: 'mri' } };
    const d = diffParams(full, factory);
    expect(d).toEqual({ xray: false, sightlines: { gamma: 2 }, section: { box: { enabled: true, min: [0, 0, 0] } }, imaging: { style: 'mri' } });
    expect(mergeParams(factory, d)).toEqual(full);
    expect(diffParams(factory, factory)).toBeUndefined();
  });

  it('changed sections are only the ones that differ from the current state', () => {
    const target = mergeParams(factory, { sightlines: { gamma: 3 } }) as Record<string, unknown>;
    expect(Object.keys(changedSections(target, factory))).toEqual(['sightlines']);
  });

  it('filters the sections a view never stores', () => {
    const f = filterParams({ schema: 'x', camera: {}, overrides: {}, keymap: {}, views: [], classStyles: {}, xray: true, section: {} });
    expect(Object.keys(f)).toEqual(['xray', 'section']);
  });
});

describe('share link', () => {
  const factory = { schema: 'xray-params/1', xray: true, sightlines: { alphaMin: 0.1, gamma: 1 }, section: { box: { enabled: false } } };

  it('encodes one view compactly and decodes it back', () => {
    const v = view('Shared', {
      thumb: 'data:image/jpeg;base64,' + 'A'.repeat(4000),
      camera: { position: [10.123456789, 8, 10], target: [0, 1, 0], up: [0, 1, 0], fov: 50, ortho: false },
      params: { schema: 'xray-params/1', xray: true, sightlines: { alphaMin: 0.1, gamma: 2 }, section: { box: { enabled: true } } },
    });
    const enc = encodeViewShare('fzk-haus', v, factory);
    expect(enc).toMatch(/^[A-Za-z0-9_-]+$/);
    expect(enc.length).toBeLessThan(700);
    const back = decodeViewShare(enc)!;
    expect(back.model).toBe('fzk-haus');
    expect(back.view.thumb).toBeUndefined();
    expect(back.view.name).toBe('Shared');
    expect(back.view.camera.position[0]).toBeCloseTo(10.1235, 6);
    expect(back.view.params).toEqual({ sightlines: { gamma: 2 }, section: { box: { enabled: true } } });
    // The receiver merges the diff over its factory state and gets the full params back.
    expect(mergeParams(factory, back.view.params)).toEqual(v.params);
    expect(shareView(v, null).params).toEqual(v.params);
  });

  it('reads and removes the hash entry, keeps others, and builds the URL', () => {
    expect(viewShareFromHash('#view=abc_-1')).toBe('abc_-1');
    expect(viewShareFromHash('#p=xyz&view=abc')).toBe('abc');
    expect(viewShareFromHash('#preview=abc')).toBeNull();
    expect(hashWithoutView('#p=xyz&view=abc')).toBe('#p=xyz');
    expect(hashWithoutView('#view=abc')).toBe('');
    expect(viewShareUrl({ origin: 'http://h', pathname: '/x/', search: '?model=a&debug=1' }, 'fzk-haus', 'E')).toBe('http://h/x/?model=fzk-haus&debug=1#view=E');
    expect(decodeViewShare('!!!')).toBeNull();
    expect(decodeViewShare(toBase64Url(new TextEncoder().encode('{"schema":"other"}')))).toBeNull();
  });

  it('base64url round-trips binary data of any length', () => {
    for (const n of [0, 1, 2, 3, 100, 70000]) {
      const b = new Uint8Array(n).map((_, i) => (i * 37) & 255);
      expect(fromBase64Url(toBase64Url(b))).toEqual(b);
    }
  });

  it('sanitizeView rejects a view without a camera', () => {
    expect(typeof sanitizeView({ name: 'x' })).toBe('string');
  });
});

describe('packed views (xray-pack --views)', () => {
  it('a deleted packed view stays deleted when the packed page is opened again', () => {
    const st = new MemoryStorage();
    const packed = [view('Roof'), view('Entrance')];
    // first open: both join the stored list, the marker records them
    let r = mergePackedViews(loadViews(st, 'fzk').views, packed, loadPackedSeen(st, 'fzk'));
    expect(r.added).toBe(2);
    saveViews(st, 'fzk', r.views);
    savePackedSeen(st, 'fzk', r.seen);
    expect(JSON.parse(st.getItem(packedSeenKey('fzk'))!)).toEqual({ 'id-Roof': packed[0]!.updated, 'id-Entrance': packed[1]!.updated });
    // the user deletes "Roof"
    saveViews(st, 'fzk', loadViews(st, 'fzk').views.filter((v) => v.name !== 'Roof'));
    // second open of the same page: "Roof" does not come back
    r = mergePackedViews(loadViews(st, 'fzk').views, packed, loadPackedSeen(st, 'fzk'));
    expect(r.views.map((v) => v.name)).toEqual(['Entrance']);
    expect(r.skipped).toBe(2);
    expect(r.added + r.replaced).toBe(0);
    // deleting all views (the key is removed) does not bring them back either
    saveViews(st, 'fzk', []);
    r = mergePackedViews(loadViews(st, 'fzk').views, packed, loadPackedSeen(st, 'fzk'));
    expect(r.views).toEqual([]);
    // another model is independent
    expect(mergePackedViews([], packed, loadPackedSeen(st, 'other')).added).toBe(2);
  });

  it('a packed view changed after the first open (newer updated) is offered again; a user edit is kept', () => {
    const st = new MemoryStorage();
    const packed = [view('Roof')];
    let r = mergePackedViews([], packed, {});
    savePackedSeen(st, 'm', r.seen);
    // the user edits the view: newer than the packed one, so a reopen keeps the edit
    const edited = { ...r.views[0]!, name: 'Roof (mine)', updated: '2026-02-01T00:00:00.000Z' };
    r = mergePackedViews([edited], packed, loadPackedSeen(st, 'm'));
    expect(r.views.map((v) => v.name)).toEqual(['Roof (mine)']);
    // the page is packed again with a newer version of the view after the user deleted it: it comes back
    const repacked = [{ ...packed[0]!, updated: '2026-03-01T00:00:00.000Z' }];
    r = mergePackedViews([], repacked, loadPackedSeen(st, 'm'));
    expect(r.added).toBe(1);
    expect(r.seen['id-Roof']).toBe('2026-03-01T00:00:00.000Z');
  });

  it('tolerates a missing, broken or throwing storage', () => {
    const st = new MemoryStorage();
    st.setItem(packedSeenKey('m'), '{oops');
    expect(loadPackedSeen(st, 'm')).toEqual({});
    expect(loadPackedSeen(null, 'm')).toEqual({});
    const bad = { getItem: () => { throw new Error('denied'); }, setItem: () => { throw new Error('quota'); } };
    expect(loadPackedSeen(bad, 'm')).toEqual({});
    expect(savePackedSeen(bad, 'm', { a: 'b' })).toBe(false);
    expect(packedSeenKey('m')).not.toBe(storageKey('m'));
  });
});
