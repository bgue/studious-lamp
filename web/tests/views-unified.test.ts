// The unified list of views: saved views and markup sets as one list, the filters, issue membership, legacy sketches,
// the link between a saved view and its drawings, and the plans of the two entry points.
import { describe, expect, it } from 'vitest';
import { buildEntries, drawPlan, filterCounts, filterEntries, findEntry, isViewFilter, issueOfSet, issuePlan } from '../src/views/unified';
import type { SetLike, TopicLike } from '../src/views/unified';
import { duplicateView, mergeViews, parseViewsDocument, sanitizeView, shareView, stripView, viewsDocument } from '../src/views/model';
import type { SavedView } from '../src/views/model';

function view(id: string, name: string, o: Partial<SavedView> = {}): SavedView {
  return { id, name, created: '2026-01-01T00:00:00Z', updated: '2026-01-01T00:00:00Z', camera: { position: [0, 0, 5], target: [0, 0, 0], up: [0, 1, 0], fov: 50, ortho: false }, selection: [], params: {}, ...o };
}
function set(id: string, title: string, o: Partial<SetLike> = {}): SetLike {
  return { id, title, markups: [], view: view(`sv-${id}`, title), ...o };
}
const drawn = (n: number): unknown[] => Array.from({ length: n }, (_, i) => ({ id: `m${i}` }));
const topic = (guid: string, title: string, sketches: string[]): TopicLike => ({ guid, title, viewpoints: sketches.map((s, i) => ({ guid: `${guid}-vp${i}`, sketchId: s })) });

describe('buildEntries', () => {
  it('lists the saved views in order, then the loose sets', () => {
    const e = buildEntries({
      views: [view('a', 'Lobby'), view('b', 'Roof')],
      sets: [set('s1', 'Stair detail', { markups: drawn(2) })],
      topics: [],
    });
    expect(e.map((x) => x.key)).toEqual(['v:a', 'v:b', 's:s1']);
    expect(e[2]).toMatchObject({ loose: true, name: 'Stair detail', drawings: 2, hasDrawings: true, sheet: false });
    expect(e[0]).toMatchObject({ loose: false, drawings: 0, hasDrawings: false });
  });

  it('folds the drawing layer of a saved view into its entry', () => {
    const e = buildEntries({
      views: [view('a', 'Lobby', { drawings: 's1', thumb: 'data:image/jpeg;base64,AAAA' })],
      sets: [set('s1', 'Lobby', { markups: drawn(3), note: 'check the door' })],
      topics: [],
    });
    expect(e).toHaveLength(1);
    expect(e[0]).toMatchObject({ key: 'v:a', viewId: 'a', setId: 's1', drawings: 3, hasDrawings: true, note: 'check the door', loose: false });
    expect(e[0]!.thumb).toBe('data:image/jpeg;base64,AAAA');
  });

  it('takes the picture of the layer when the saved view has none', () => {
    const e = buildEntries({ views: [view('a', 'x', { drawings: 's1' })], sets: [set('s1', 'x', { thumb: 'data:image/jpeg;base64,BBBB' })], topics: [] });
    expect(e[0]!.thumb).toBe('data:image/jpeg;base64,BBBB');
  });

  it('shows a link to a set that is gone as a plain view', () => {
    const e = buildEntries({ views: [view('a', 'Lobby', { drawings: 'nope' })], sets: [], topics: [] });
    expect(e[0]).toMatchObject({ viewId: 'a', hasDrawings: false });
    expect(e[0]!.setId).toBeUndefined();
  });

  it('lets one saved view claim a set (the first wins)', () => {
    const e = buildEntries({ views: [view('a', 'A', { drawings: 's1' }), view('b', 'B', { drawings: 's1' })], sets: [set('s1', 'S', { markups: drawn(1) })], topics: [] });
    expect(e.map((x) => [x.key, x.setId ?? null])).toEqual([['v:a', 's1'], ['v:b', null]]);
  });

  it('builds a view from a legacy sketch: its own capture, name and picture', () => {
    const legacy = set('old', 'Old sketch', { markups: drawn(1), thumb: 'data:image/jpeg;base64,CCCC', view: view('sv-old', 'Old sketch', { exploded: true, selection: ['g1'] }) });
    const e = buildEntries({ views: [], sets: [legacy], topics: [] });
    expect(e).toHaveLength(1);
    expect(e[0]).toMatchObject({ key: 's:old', id: 'old', setId: 'old', name: 'Old sketch', loose: true, hasDrawings: true });
    expect(e[0]!.viewId).toBeUndefined();
    expect(e[0]!.summary).toContain('exploded');
    expect(e[0]!.summary).toContain('1 selected');
    expect(e[0]!.thumb).toBe('data:image/jpeg;base64,CCCC');
  });

  it('flags the pages of a PDF sheet', () => {
    const e = buildEntries({ views: [], sets: [set('p1', 'Plan page 1', { frame: { kind: 'sheet', sheet: 'sh1' }, markups: drawn(2) })], topics: [] });
    expect(e[0]).toMatchObject({ sheet: true, loose: true, summary: 'sheet page' });
  });

  it('knows the issue of a view (the viewpoint link is the truth), for both kinds of entry', () => {
    const topics = [topic('t1', 'Duct clash', ['s1']), topic('t2', 'Door', ['s2'])];
    const e = buildEntries({
      views: [view('a', 'Lobby', { drawings: 's1' })],
      sets: [set('s1', 'Lobby'), set('s2', 'Door view', { markups: drawn(1) }), set('s3', 'Free')],
      topics,
    });
    expect(e.map((x) => x.issue?.title ?? null)).toEqual(['Duct clash', 'Door', null]);
    expect(e[0]!.issue).toEqual({ topic: 't1', title: 'Duct clash', viewpoint: 't1-vp0' });
    expect(issueOfSet(topics, 'nope')).toBeUndefined();
  });

  it('ignores derived viewpoints (a Plan or Section of a view is not a view of its own)', () => {
    const t: TopicLike = { guid: 't', title: 'T', viewpoints: [{ guid: 'v1', sketchId: 's1' }, { guid: 'v2', sketchId: 's9', derived: { kind: 'plan' } }] };
    expect(issueOfSet([t], 's9')).toBeUndefined();
    expect(issueOfSet([t], 's1')?.viewpoint).toBe('v1');
  });
});

describe('filters', () => {
  const entries = buildEntries({
    views: [view('a', 'Lobby'), view('b', 'Roof', { drawings: 's1' }), view('c', 'Stair', { drawings: 's2' })],
    sets: [set('s1', 'Roof', { markups: drawn(2), note: 'leak at the edge' }), set('s2', 'Stair'), set('p', 'Sheet A-101', { frame: { kind: 'sheet', sheet: 'x' }, markups: drawn(1) }), set('old', 'Legacy', { markups: drawn(1) })],
    topics: [topic('t1', 'Leaking roof', ['s1']), topic('t2', 'Stair width', ['s2'])],
  });

  it('All shows every entry', () => {
    expect(filterEntries(entries).map((e) => e.name)).toEqual(['Lobby', 'Roof', 'Stair', 'Sheet A-101', 'Legacy']);
  });
  it('With drawings keeps the views that have drawings (an empty layer in an issue does not count)', () => {
    expect(filterEntries(entries, { filter: 'drawings' }).map((e) => e.name)).toEqual(['Roof', 'Sheet A-101', 'Legacy']);
  });
  it('On sheets keeps the PDF pages', () => {
    expect(filterEntries(entries, { filter: 'sheets' }).map((e) => e.name)).toEqual(['Sheet A-101']);
  });
  it('In an issue keeps the views of issues, with or without drawings', () => {
    expect(filterEntries(entries, { filter: 'issue' }).map((e) => e.name)).toEqual(['Roof', 'Stair']);
  });
  it('the text matches name, note and issue title; every word must match', () => {
    expect(filterEntries(entries, { query: 'leak' }).map((e) => e.name)).toEqual(['Roof']);
    expect(filterEntries(entries, { query: 'stair width' }).map((e) => e.name)).toEqual(['Stair']);
    expect(filterEntries(entries, { query: 'roof nothing' })).toEqual([]);
    expect(filterEntries(entries, { filter: 'issue', query: 'lobby' })).toEqual([]);
  });
  it('counts what each chip shows', () => {
    expect(filterCounts(entries)).toEqual({ all: 5, drawings: 3, sheets: 1, issue: 2 });
  });
  it('knows its filter names', () => {
    expect(isViewFilter('drawings')).toBe(true);
    expect(isViewFilter('sketches')).toBe(false);
  });
  it('finds an entry by key, id, set id or name', () => {
    expect(findEntry(entries, 'v:b')?.name).toBe('Roof');
    expect(findEntry(entries, 'b')?.name).toBe('Roof');
    expect(findEntry(entries, 's1')?.name).toBe('Roof');
    expect(findEntry(entries, 'old')?.name).toBe('Legacy');
    expect(findEntry(entries, 'stair')?.name).toBe('Stair');
    expect(findEntry(entries, 'zzz')).toBeUndefined();
  });
});

describe('the entry points', () => {
  const entries = buildEntries({ views: [view('a', 'Plain'), view('b', 'Drawn', { drawings: 's1' })], sets: [set('s1', 'Drawn'), set('s2', 'Loose', { markups: drawn(1) })], topics: [topic('t', 'T', ['s2'])] });
  it('Draw on this view edits a layer that exists, makes one for a saved view, and saves the current state when nothing is picked', () => {
    expect(drawPlan(entries[1])).toBe('edit');
    expect(drawPlan(entries[2])).toBe('edit');
    expect(drawPlan(entries[0])).toBe('layer');
    expect(drawPlan(null)).toBe('current');
  });
  it('Make issue opens the issue of a view that is in one, else offers the chooser', () => {
    expect(issuePlan(entries[2]!)).toBe('open');
    expect(issuePlan(entries[0]!)).toBe('choose');
  });
});

describe('the link between a saved view and its drawings', () => {
  it('survives the stored document and the sanitizer', () => {
    const doc = viewsDocument('m', [view('a', 'Lobby', { drawings: 's1' })]);
    const back = parseViewsDocument(JSON.stringify(doc));
    expect(back.views[0]!.drawings).toBe('s1');
    expect(sanitizeView({ ...view('a', 'x'), drawings: 42 })).not.toHaveProperty('drawings');
  });
  it('is read from old documents that have none', () => {
    const old = { schema: 'xray-views/1', model: 'm', views: [view('a', 'Lobby')] };
    expect(parseViewsDocument(JSON.stringify(old)).views[0]).not.toHaveProperty('drawings');
  });
  it('is not in a share link or the params copy', () => {
    const v = view('a', 'Lobby', { drawings: 's1' });
    expect(shareView(v, null)).not.toHaveProperty('drawings');
    expect(stripView(v, false, false)).not.toHaveProperty('drawings');
    expect(stripView(v)).toHaveProperty('drawings', 's1');
  });
  it('stays with the view when an import replaces it, and does not pass to a copy', () => {
    const have = [view('a', 'Lobby', { drawings: 's1' })];
    const r = mergeViews(have, [view('a', 'Lobby', { updated: '2026-02-01T00:00:00Z' })]);
    expect(r.replaced).toBe(1);
    expect(r.views[0]!.drawings).toBe('s1');
    expect(duplicateView(have, 0)[1]).not.toHaveProperty('drawings');
  });
});
