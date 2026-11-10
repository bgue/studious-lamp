import { describe, expect, it } from 'vitest';
import {
  INSTRUCTIONS, MARKUP_SCHEMA, addComment, addMarkup, buildMarkupDoc, compareModels, globalIdHash, markupDocJson, mergeSets,
  modelIdentity, newMarkup, parseMarkupDoc, referencedGuids, sanitizeMarkup, unknownGuids,
} from '../src/markup/model';
import type { MarkupSet } from '../src/markup/model';

function sample(): MarkupSet {
  const set: MarkupSet = {
    id: 'set1', title: 'Level 2 routing', author: 'Ana', created: '2026-01-01T10:00:00.000Z', updated: '2026-01-01T10:00:00.000Z',
    view: {
      id: 'v1', name: 'Level 2 routing', created: '2026-01-01T10:00:00.000Z', updated: '2026-01-01T10:00:00.000Z',
      camera: { position: [6, 5.5, 13], target: [-3.9, -1.8, -4.8], up: [0, 1, 0], fov: 45, ortho: false },
      selection: ['GUID-SEL'], hides: { mode: 'hide', ids: ['GUID-H1', 'GUID-H2'] }, params: { xray: true },
    },
    camera: { position: [6, -13, 5.5], direction: [-0.5, 0.8, -0.3], up: [0, 0, 1], fov: 45, aspect: 1.6 },
    markups: [], nextNumber: 1,
  };
  addMarkup(set, newMarkup('cloud', { author: 'Ana', shape: { points: [[0.2, 0.2], [0.5, 0.4]], depth: 12.3 }, text: 'Clash with duct' }));
  addMarkup(set, newMarkup('callout', { author: 'Ana', text: 'Move pipe', anchor: { kind: 'element', point: [1, 2, 3], elementGuid: 'GUID-A', local: [0.1, 0, 0] }, offset: [0.1, -0.09], colour: 'blue' }));
  const m = addMarkup(set, newMarkup('measure', { author: 'Ana', anchor: { kind: 'measurement', point: [0, 0, 0], measurement: { kind: 'element', a: [0, 0, 0], b: [1, 0, 0], distance: 1, label: '1.000 m', elementGuids: ['GUID-A', 'GUID-B'] } }, offset: [0, 0.1] }));
  m.status = 'resolved';
  m.assignee = 'Ben';
  m.due = '2026-02-03';
  addComment(m, 'Ben', 'Checked on site', '2026-01-02T08:00:00.000Z');
  return set;
}

describe('markup numbering', () => {
  it('numbers markups and never reuses a number after a delete', () => {
    const s = sample();
    expect(s.markups.map((m) => m.number)).toEqual([1, 2, 3]);
    s.markups = s.markups.filter((m) => m.number !== 3);
    const m = addMarkup(s, newMarkup('rect', { author: 'x', shape: { points: [[0, 0], [1, 1]], depth: 1 } }));
    expect(m.number).toBe(4);
  });
});

describe('xray-markup-set/1 document', () => {
  const ids = ['GUID-A', 'GUID-B', 'GUID-SEL', 'GUID-H1', 'GUID-H2', 'GUID-X'];
  const identity = modelIdentity('fzk-haus.ifc', 6, ids);

  it('round-trips the sets through JSON text', () => {
    const doc = buildMarkupDoc(identity, [sample()], { link: 'https://example.org/?model=x#view=abc', now: new Date('2026-03-01T00:00:00Z') });
    expect(doc.schema).toBe(MARKUP_SCHEMA);
    expect(doc.instructions).toBe(INSTRUCTIONS);
    const back = parseMarkupDoc(markupDocJson(doc));
    expect(back.error).toBeUndefined();
    expect(back.bad).toEqual([]);
    expect(back.model).toEqual(identity);
    expect(back.link).toBe('https://example.org/?model=x#view=abc');
    expect(back.sets.length).toBe(1);
    expect(back.sets[0]).toEqual(doc.sets[0]);
    // and a second trip changes nothing
    expect(parseMarkupDoc(markupDocJson(buildMarkupDoc(identity, back.sets))).sets[0]).toEqual(back.sets[0]);
  });

  it('keeps the 3D anchors in the IFC frame with element ids, the shapes as fractions, comments and statuses', () => {
    const back = parseMarkupDoc(buildMarkupDoc(identity, [sample()])).sets[0]!;
    const [cloud, callout, measure] = back.markups;
    expect(cloud!.shape).toEqual({ points: [[0.2, 0.2], [0.5, 0.4]], depth: 12.3 });
    expect(callout!.anchor).toEqual({ kind: 'element', point: [1, 2, 3], elementGuid: 'GUID-A', local: [0.1, 0, 0] });
    expect(measure!.anchor!.measurement!.elementGuids).toEqual(['GUID-A', 'GUID-B']);
    expect(measure!.status).toBe('resolved');
    expect(measure!.assignee).toBe('Ben');
    expect(measure!.due).toBe('2026-02-03');
    expect(measure!.comments).toEqual([{ id: expect.any(String), author: 'Ben', date: '2026-01-02T08:00:00.000Z', text: 'Checked on site' }]);
    expect(back.nextNumber).toBe(4);
  });

  it('leaves thumbnails out unless asked and strips the view thumbnail', () => {
    const s = sample();
    s.thumb = 'data:image/jpeg;base64,AAAA';
    s.view.thumb = 'data:image/jpeg;base64,BBBB';
    expect(buildMarkupDoc(identity, [s]).sets[0]!.thumb).toBeUndefined();
    const withT = buildMarkupDoc(identity, [s], { withThumbs: true }).sets[0]!;
    expect(withT.thumb).toBe('data:image/jpeg;base64,AAAA');
    expect(withT.view.thumb).toBeUndefined();
    expect(parseMarkupDoc(withT.thumb ? buildMarkupDoc(identity, [s], { withThumbs: true }) : null).sets[0]!.thumb).toBe(s.thumb);
  });

  it('refuses other schemas, newer versions and bad JSON with a message', () => {
    expect(parseMarkupDoc('{nope').error).toMatch(/not JSON/);
    expect(parseMarkupDoc({ schema: 'xray-views/1', views: [] }).error).toMatch(/not an X-ray markup document/);
    expect(parseMarkupDoc({ schema: 'xray-markup-set/2', sets: [] }).error).toMatch(/version 2/);
    expect(parseMarkupDoc({ schema: 'xray-markup-set/1' }).error).toMatch(/no sets/);
    expect(parseMarkupDoc({ schema: 'xray-markup-set/1', sets: [{ title: 'x' }] }).error).toMatch(/no usable set/);
  });

  it('drops bad markups one by one and says why; fills ids, numbers and times', () => {
    const doc = JSON.parse(markupDocJson(buildMarkupDoc(identity, [sample()])));
    doc.sets[0].markups.push({ kind: 'spiral' }, { kind: 'cloud' }, { kind: 'callout', anchor: { kind: 'point' } }, { kind: 'rect', shape: { points: [[0, 0], [1, 1]], depth: 2 } });
    doc.sets[0].markups[0].number = 2; // duplicate of the second
    delete doc.sets[0].markups[1].id;
    doc.sets[0].extra = 'ignored';
    const r = parseMarkupDoc(doc);
    expect(r.error).toBeUndefined();
    expect(r.bad.length).toBe(3);
    expect(r.bad[0]).toMatch(/unknown kind "spiral"/);
    expect(r.bad[1]).toMatch(/cloud without a usable shape/);
    expect(r.bad[2]).toMatch(/callout without an anchor/);
    const s = r.sets[0]!;
    expect(s.markups.length).toBe(4);
    expect(new Set(s.markups.map((m) => m.number)).size).toBe(4);
    expect(new Set(s.markups.map((m) => m.id)).size).toBe(4);
    expect((s as unknown as Record<string, unknown>)['extra']).toBeUndefined();
  });

  it('sanitizes a markup: clamps unknown colours and weights, caps points', () => {
    const m = sanitizeMarkup({ kind: 'polyline', colour: 'pink', weight: 9, fill: 'yes', shape: { points: Array.from({ length: 3000 }, (_v, i) => [i / 3000, 0.5]), depth: 4 } });
    expect(typeof m).toBe('object');
    if (typeof m === 'string') return;
    expect(m.colour).toBe('red');
    expect(m.weight).toBe(2);
    expect(m.fill).toBe(false);
    expect(m.shape!.points.length).toBe(2000);
    expect(sanitizeMarkup({ kind: 'line', shape: { points: [[0, 0]], depth: 1 } })).toMatch(/usable shape/);
    expect(sanitizeMarkup({ kind: 'line', shape: { points: [[0, 0], ['a', 1]], depth: 1 } })).toMatch(/usable shape/);
  });

  it('keeps a box of 4 corners (after Update view) and cuts other counts to 2', () => {
    const quad = sanitizeMarkup({ kind: 'rect', shape: { points: [[0, 0], [1, 0], [1, 1], [0, 1]], depth: 3 } });
    expect(typeof quad === 'object' && quad.shape!.points.length).toBe(4);
    const three = sanitizeMarkup({ kind: 'ellipse', shape: { points: [[0, 0], [1, 0], [1, 1]], depth: 3 } });
    expect(typeof three === 'object' && three.shape!.points.length).toBe(2);
  });

  it('merges sets by id and keeps titles unique', () => {
    const a = sample();
    const b = { ...sample(), id: 'set2' };
    const r1 = mergeSets([a], [b]);
    expect(r1.added).toBe(1);
    expect(r1.sets[1]!.title).toBe('Level 2 routing (2)');
    const r2 = mergeSets(r1.sets, [{ ...a, title: 'Renamed' }]);
    expect(r2.replaced).toBe(1);
    expect(r2.sets[0]!.title).toBe('Renamed');
  });
});

describe('model identity and mismatch', () => {
  const ids = ['b', 'a', 'c'];
  it('hashes the GlobalId list independent of order and duplicates', () => {
    expect(globalIdHash(['a', 'b', 'c'])).toBe(globalIdHash(['c', 'a', 'b', 'a']));
    expect(globalIdHash(['a', 'b', 'c'])).not.toBe(globalIdHash(['a', 'b', 'd']));
    expect(globalIdHash(['a', 'b', 'c'])).toMatch(/^[0-9a-f]{16}$/);
    expect(globalIdHash([])).toMatch(/^[0-9a-f]{16}$/);
  });
  it('reports same, revised, different and unknown', () => {
    const now = modelIdentity('house.ifc', 3, ids);
    expect(compareModels(modelIdentity('house.ifc', 3, ['a', 'b', 'c']), now).match).toBe('same');
    const rev = compareModels(modelIdentity('House.ifc', 4, ['a', 'b', 'c', 'd']), now);
    expect(rev.match).toBe('revised');
    expect(rev.message).toMatch(/changed/);
    const diff = compareModels(modelIdentity('office.ifc', 9, ['x']), now);
    expect(diff.match).toBe('different');
    expect(diff.message).toMatch(/office\.ifc/);
    expect(compareModels(undefined, now).match).toBe('unknown');
  });
  it('lists referenced and unknown GlobalIds once each', () => {
    const s = sample();
    expect(referencedGuids(s).sort()).toEqual(['GUID-A', 'GUID-B', 'GUID-H1', 'GUID-H2', 'GUID-SEL']);
    const have = new Set(['GUID-A', 'GUID-SEL']);
    expect(unknownGuids(s, (g) => have.has(g)).sort()).toEqual(['GUID-B', 'GUID-H1', 'GUID-H2']);
  });
});
