// Search bar: fuzzy matching, ranking of the label sources, section order, query detection and live query, recents.

import { describe, expect, it } from 'vitest';
import { fuzzyScore as paletteFuzzy } from '../src/ui/palette';
import { TIER, fuzzyScore, isBoundary, isSubsequence, quickPositions, quickScore, termsOf } from '../src/search/fuzzy';
import { ElementIndex } from '../src/search/elementIndex';
import { detectQuery, plainError, runLive } from '../src/search/queryMode';
import { EXPANDED_CAP, SECTION_CAP, normalizeFuzzy, orderGroups, rankByText } from '../src/search/rank';
import { QueryError } from '../src/query';
import { pushRecent, readRecent } from '../src/ui/awesomeBar';
import type { ElementRecord, SceneModel } from '../src/types';

function model(rows: Array<Partial<ElementRecord> & { storeyName?: string }>): SceneModel {
  const elements: ElementRecord[] = rows.map((r, id) => ({
    id,
    globalId: r.globalId ?? `0GID${String(id).padStart(6, '0')}`,
    ifcClass: r.ifcClass ?? 'IfcWall',
    name: r.name,
    storey: r.storey === undefined ? 0 : r.storey,
    material: r.material,
    color: [0.7, 0.7, 0.7, 1],
    bounds: [id, 0, 0, id + 1, 1, 1],
    props: r.props,
  }));
  return {
    schema: 'xray-model/1',
    units: 'm',
    originShift: [0, 0, 0],
    storeys: [
      { id: 0, name: 'Level 1', elevation: 0 },
      { id: 1, name: 'Level 2', elevation: 3 },
    ],
    elements,
    relations: { voids: [], fills: [], hosts: [], ports: [], systems: [] },
    byGlobalId: new Map(elements.map((e) => [e.globalId, e.id])),
  };
}

describe('shared fuzzy matching', () => {
  it('is the same function the palette uses', () => {
    expect(paletteFuzzy).toBe(fuzzyScore);
  });
  it('splits terms and finds word boundaries and subsequences', () => {
    expect(termsOf('  Duct   RUN ')).toEqual(['duct', 'run']);
    expect(isBoundary('basic wall', 6)).toBe(true);
    expect(isBoundary('basic wall', 7)).toBe(false);
    expect(isSubsequence('bwl', 'basic wall')).toBe(true);
    expect(isSubsequence('lwb', 'basic wall')).toBe(false);
  });
  it('ranks the tiers: equal, prefix, word start, substring, subsequence', () => {
    const s = (t: string, text: string) => quickScore(t, text);
    expect(s('wall', 'wall')).toBeGreaterThan(s('wall', 'wall 12'));
    expect(s('wall', 'wall 12')).toBeGreaterThan(s('wall', 'basic wall'));
    expect(s('wall', 'basic wall')).toBeGreaterThan(s('wall', 'firewalls'));
    expect(s('wall', 'firewalls')).toBeGreaterThan(s('wl', 'wall'));
    expect(s('wal', 'wxlxa')).toBe(-1);
    expect(s('wl', 'wall')).toBeGreaterThan(0);
    expect(s('wl', 'wall')).toBeLessThan(TIER.substring);
    expect(quickScore('wl', 'wall', false)).toBe(-1);
    expect(s('q', 'wall')).toBe(-1);
    expect(s('', 'wall')).toBe(-1);
  });
  it('prefers shorter text inside a tier', () => {
    expect(quickScore('duct', 'duct')).toBeGreaterThan(quickScore('duct', 'duct segment long name'));
    expect(quickScore('duct', 'ductwork')).toBeGreaterThan(quickScore('duct', 'ductwork with long tail'));
  });
  it('gives highlight positions: the substring, else a subsequence, else none', () => {
    expect(quickPositions('all', 'Wall 1')).toEqual([1, 2, 3]);
    expect(quickPositions('wl', 'Wall')).toEqual([0, 2]);
    expect(quickPositions('zz', 'Wall')).toEqual([]);
  });
});

describe('ranking of label sources', () => {
  const presets = [{ name: 'Presentation' }, { name: 'Coordination' }, { name: 'Peelback view' }, { name: 'Hide blockers' }];
  const text = (p: { name: string }) => ({ label: p.name });
  it('ranks prefix above subsequence and drops non-matches', () => {
    const r = rankByText(presets, 'pre', text);
    expect(r[0]!.item.name).toBe('Presentation');
    expect(r.map((x) => x.item.name)).not.toContain('Hide blockers');
  });
  it('returns the matched positions of the label', () => {
    const r = rankByText(presets, 'hb', text);
    expect(r[0]!.item.name).toBe('Hide blockers');
    expect(r[0]!.positions).toEqual([0, 5]);
  });
  it('uses the extra text at a discount', () => {
    const items = [{ label: 'Alpha', extra: 'shows the foundation' }, { label: 'Foundation tour' }];
    const r = rankByText(items, 'foundation', (i) => i);
    expect(r[0]!.item.label).toBe('Foundation tour');
    expect(r).toHaveLength(2);
  });
  it('lists everything in label order for an empty query', () => {
    const r = rankByText(presets, '', text);
    expect(r.map((x) => x.item.name)).toEqual(['Coordination', 'Hide blockers', 'Peelback view', 'Presentation']);
  });
  it('keeps scores in 0..100', () => {
    expect(normalizeFuzzy(500)).toBe(100);
    expect(normalizeFuzzy(-5)).toBe(1);
    const best = rankByText(presets, 'presentation', text)[0]!;
    expect(best.score).toBeGreaterThan(50);
    expect(best.score).toBeLessThanOrEqual(100);
  });
});

describe('section order and caps', () => {
  it('orders the sections by their best row, ties by the fixed order', () => {
    const g = [
      { section: 'settings' as const, rows: [{ score: 40 }] },
      { section: 'elements' as const, rows: [{ score: 40 }, { score: 20 }] },
      { section: 'commands' as const, rows: [{ score: 90 }] },
      { section: 'presets' as const, rows: [] },
    ];
    expect(orderGroups(g).map((x) => x.section)).toEqual(['commands', 'elements', 'settings']);
  });
  it('caps the element list at about 50 and an expanded list at 200', () => {
    expect(SECTION_CAP.elements).toBe(50);
    expect(EXPANDED_CAP).toBe(200);
  });
});

describe('element index ranking', () => {
  const m = model([
    { name: 'Basic Wall 1', ifcClass: 'IfcWall', props: { 'Pset_WallCommon.FireRating': '2h', 'Pset_WallCommon.IsExternal': true } },
    { name: 'Wall', ifcClass: 'IfcWall' },
    { name: 'Rectangular Duct 7', ifcClass: 'IfcDuctSegment', storey: 1, material: 'Galvanised steel' },
    { name: 'Door 3', ifcClass: 'IfcDoor', globalId: '3vB2YO9Mf0$u8_MzP1tmWk' },
    { name: undefined, ifcClass: 'IfcSlab', storey: 1, props: { 'Attr.Tag': 'S-100' } },
    { name: 'Firewalls', ifcClass: 'IfcWall' },
  ]);
  const idx = new ElementIndex(m).buildAll();
  const ids = (q: string) => idx.search(termsOf(q)).hits.map((h) => h.id);

  it('ranks an equal name over a prefix over a substring', () => {
    expect(ids('wall').slice(0, 3)).toEqual([1, 0, 5]);
  });
  it('finds by class, storey, material, GlobalId and property value', () => {
    expect(ids('ductsegment')).toEqual([2]);
    expect(ids('level 2')).toContain(2);
    expect(ids('galvan')).toEqual([2]);
    expect(ids('3vb2yo')).toEqual([3]);
    expect(ids('s-100')).toEqual([4]);
    expect(ids('2h')).toEqual([0]);
  });
  it('needs every term to match', () => {
    expect(ids('wall level')).toEqual(expect.arrayContaining([0, 1, 5]));
    expect(ids('wall level 2')).toEqual([]);
    expect(ids('duct level 2')).toEqual([2]);
  });
  it('matches by subsequence on the name and class', () => {
    expect(ids('bsc wl')).toEqual([0]);
    expect(ids('rdct')).toEqual([2]);
  });
  it('keeps at most `keep` hits and counts all matches', () => {
    const r = idx.search(['i'], 2);
    expect(r.hits).toHaveLength(2);
    expect(r.total).toBeGreaterThan(2);
  });
  it('explains a hit: highlight and where a hidden match came from', () => {
    const a = idx.explain(0, ['wall']);
    expect(a.label).toBe('Basic Wall 1');
    expect(a.labelPositions).toEqual([6, 7, 8, 9]);
    expect(a.sub).toBe('IfcWall · Level 1');
    expect(a.via).toBe('');
    const b = idx.explain(0, ['2h']);
    expect(b.via).toBe('Pset_WallCommon.FireRating = 2h');
    const c = idx.explain(3, ['3vb2']);
    expect(c.via).toBe('GlobalId 3vB2YO9Mf0$u8_MzP1tmWk');
    expect(idx.explain(4, ['slab']).label).toBe('IfcSlab');
  });
  it('searches a partial index and reports it', () => {
    const part = new ElementIndex(m);
    part.buildTo(2);
    expect(part.ready).toBe(false);
    expect(part.search(['wall']).scanned).toBe(2);
    part.buildAll();
    expect(part.ready).toBe(true);
  });
  it('builds in idle slices and can be cancelled', async () => {
    const big = model(Array.from({ length: 5000 }, (_, i) => ({ name: `Element ${i}` })));
    const i1 = new ElementIndex(big);
    let progress = 0;
    await i1.buildIdle({ budgetMs: 1, onProgress: () => progress++ });
    expect(i1.ready).toBe(true);
    expect(progress).toBeGreaterThan(0);
    const i2 = new ElementIndex(big);
    const p = i2.buildIdle({ budgetMs: 1 });
    i2.cancel();
    await p;
    expect(i2.built).toBeLessThanOrEqual(big.elements.length);
  });
});

describe('query detection', () => {
  it('detects where and ? prefixes as forced queries', () => {
    expect(detectQuery("where class = 'IfcWall'")).toEqual({ mode: 'query', expr: "class = 'IfcWall'", forced: true });
    expect(detectQuery('WHERE   a > 3')).toEqual({ mode: 'query', expr: 'a > 3', forced: true });
    expect(detectQuery('where')).toEqual({ mode: 'query', expr: '', forced: true });
    expect(detectQuery('?name like %x%')).toEqual({ mode: 'query', expr: 'name like %x%', forced: true });
    expect(detectQuery('? sizeY >= 2')).toEqual({ mode: 'query', expr: 'sizeY >= 2', forced: true });
  });
  it('detects a bare WHERE expression', () => {
    expect(detectQuery("class = 'IfcDuctSegment' and storey like '%1%'")).toMatchObject({ mode: 'query', forced: false });
    expect(detectQuery('volume > 0.5')).toMatchObject({ mode: 'query', forced: false });
    expect(detectQuery('"Pset_WallCommon.FireRating" = \'2h\'')).toMatchObject({ mode: 'query', forced: false });
    expect(detectQuery("name not like '%door%'")).toMatchObject({ mode: 'query' });
    expect(detectQuery("class in ('IfcWall','IfcSlab')")).toMatchObject({ mode: 'query' });
    expect(detectQuery('material is null')).toMatchObject({ mode: 'query' });
    expect(detectQuery('sizeY between 1 and 2')).toMatchObject({ mode: 'query' });
    expect(detectQuery('class =')).toMatchObject({ mode: 'query' });
  });
  it('leaves plain text alone', () => {
    for (const t of ['wall', 'basic wall 12', 'ifcwall level 2', 'where is the door', '2h', 'hide selected', 'S-100', 'a and b']) {
      const d = detectQuery(t);
      if (t === 'where is the door') expect(d.mode).toBe('query'); // starts with "where ": the person asked for a query
      else expect(d, t).toEqual({ mode: 'text' });
    }
  });
});

describe('live query', () => {
  const m = model([
    { name: 'A', ifcClass: 'IfcDuctSegment', storey: 0 },
    { name: 'B', ifcClass: 'IfcDuctSegment', storey: 1 },
    { name: 'C', ifcClass: 'IfcWall', storey: 1 },
  ]);
  it('counts the matches and returns the ids', () => {
    const r = runLive(m, "class = 'IfcDuctSegment' and storey like '%1%'");
    expect(r.error).toBeNull();
    expect(r.count).toBe(1);
    expect(r.ids).toEqual([0]);
    expect(runLive(m, "class = 'IfcDuctSegment'").count).toBe(2);
  });
  it('turns an engine error into plain text with the position', () => {
    const r = runLive(m, 'class =');
    expect(r.error).toMatch(/^Expected /);
    expect(r.error).toMatch(/character \d+/);
    expect(r.count).toBe(0);
    expect(plainError(new QueryError('Unterminated string: a closing \' is missing', 9))).toBe("Unterminated string: a closing ' is missing. Check the text around character 10.");
  });
  it('reports an unknown column and an empty expression without an error', () => {
    const r = runLive(m, 'nosuchcolumn = 1');
    expect(r.error).toBeNull();
    expect(r.unknown).toEqual(['nosuchcolumn']);
    expect(r.count).toBe(0);
    expect(runLive(m, '  ')).toMatchObject({ count: 0, error: null });
  });
});

describe('recent items', () => {
  it('puts the newest first, drops duplicates and caps the list', () => {
    expect(pushRecent(['a', 'b', 'c'], 'b')).toEqual(['b', 'a', 'c']);
    const long = Array.from({ length: 12 }, (_, i) => `k${i}`);
    expect(pushRecent(long, 'new')).toHaveLength(8);
    expect(pushRecent(long, 'new')[0]).toBe('new');
  });
  it('reads a stored list defensively', () => {
    const st = (v: string | null) => ({ getItem: () => v });
    expect(readRecent(st('["a","b"]'))).toEqual(['a', 'b']);
    expect(readRecent(st('{"a":1}'))).toEqual([]);
    expect(readRecent(st('not json'))).toEqual([]);
    expect(readRecent(st(null))).toEqual([]);
    expect(readRecent(null)).toEqual([]);
    expect(readRecent(st('["a",3,null,"b"]'))).toEqual(['a', 'b']);
  });
});
