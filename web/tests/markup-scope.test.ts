// Which model an item belongs to (src/markup/scope.ts): the scoping decision per compareModels result, the "Other models"
// grouping, the model identity of markup sets and BCF topics in their files, and the controllers' behaviour on a model change.

import { describe, expect, it } from 'vitest';
import { identityKey, loadedIdentity, modelLabel, scopeOf, splitByScope } from '../src/markup/scope';
import { buildMarkupDoc, markupDocJson, modelIdentity, parseMarkupDoc } from '../src/markup/model';
import type { MarkupSet, ModelIdentity } from '../src/markup/model';
import { MarkupController } from '../src/markup/controller';
import { BcfController } from '../src/bcf/controller';
import { emptyProject } from '../src/bcf/model';
import type { BcfAnnotation, BcfTopic } from '../src/bcf/model';
import { applySidecar, parseSidecar, sidecarJson } from '../src/bcf/sidecar';
import { parseBcf } from '../src/bcf/parse';
import { writeBcf } from '../src/bcf/write';

const ids = (n: number, p = 'g'): string[] => Array.from({ length: n }, (_v, i) => `${p}${i}`);
const A = modelIdentity('FZK-Haus', 100, ids(100));
const A2 = modelIdentity('FZK-Haus', 104, ids(104)); // same name, other content: a revision
const B = modelIdentity('Building', 50, ids(50, 'b'));
const C = modelIdentity('Process plant', 30, ids(30, 'c'));

describe('scopeOf: the decision per compareModels result', () => {
  it('the same model: shown, no tag', () => {
    expect(scopeOf(A, A)).toMatchObject({ match: 'same', visible: true, tag: '' });
    // A copy of the identity (a file read back) is the same model.
    expect(scopeOf({ ...A }, A).match).toBe('same');
  });
  it('a revision (same name, other content): shown, flagged, with the detached-targets note', () => {
    const s = scopeOf(A, A2);
    expect(s).toMatchObject({ match: 'revised', visible: true, tag: 'revised model' });
    expect(s.note).toContain('already be designed');
  });
  it('no model named: shown, tagged "model unknown"', () => {
    expect(scopeOf(undefined, A)).toMatchObject({ match: 'unknown', visible: true, tag: 'model unknown' });
    expect(scopeOf(null, A).match).toBe('unknown');
  });
  it('another model: hidden', () => {
    const s = scopeOf(A, B);
    expect(s).toMatchObject({ match: 'different', visible: false, tag: 'other model' });
    expect(s.note).toContain('FZK-Haus');
  });
  it('no model loaded: everything counts as current', () => {
    expect(scopeOf(A, null).visible).toBe(true);
    expect(scopeOf(undefined, undefined).match).toBe('same');
  });
  it('the name decides between revised and different, case and spaces aside', () => {
    expect(scopeOf({ ...A2, name: '  fzk-haus ' }, A).match).toBe('revised');
  });
});

describe('splitByScope: the Other models grouping', () => {
  interface Item { id: string; model?: ModelIdentity | null }
  const items: Item[] = [
    { id: 'a1', model: A }, { id: 'b1', model: B }, { id: 'u1' }, { id: 'a-old', model: A }, { id: 'c1', model: C }, { id: 'b2', model: { ...B } }, { id: 'r', model: A2 },
  ];
  it('on model A: A, the revision and the unknown stay, B and C go to Other models, grouped per model in first-seen order', () => {
    const s = splitByScope(items, (i) => i.model, A);
    expect(s.here.map((h) => h.item.id)).toEqual(['a1', 'u1', 'a-old', 'r']);
    expect(s.here.find((h) => h.item.id === 'u1')!.scope.match).toBe('unknown');
    expect(s.here.find((h) => h.item.id === 'r')!.scope.match).toBe('revised');
    expect(s.otherCount).toBe(3);
    expect(s.other.map((g) => [g.model.name, g.items.map((i) => i.id)])).toEqual([['Building', ['b1', 'b2']], ['Process plant', ['c1']]]);
  });
  it('on a revision of A, the old items are "revised" and shown; nothing is hidden for the same name', () => {
    const s = splitByScope(items.filter((i) => i.model === A || i.model === A2), (i) => i.model, A2);
    expect(s.otherCount).toBe(0);
    expect(s.here.map((h) => h.scope.match)).toEqual(['revised', 'revised', 'same']);
  });
  it('on model B the A items go to one group labelled with the model', () => {
    const s = splitByScope(items, (i) => i.model, B);
    const g = s.other.find((x) => x.model.name === 'FZK-Haus' && x.model.elementCount === 100)!;
    expect(g.items.map((i) => i.id)).toEqual(['a1', 'a-old']);
    expect(g.label).toBe('FZK-Haus (100 elements)');
  });
  it('an item opened on purpose is listed with the current ones', () => {
    const s = splitByScope(items, (i) => i.model, A, (i) => i.id === 'b1');
    expect(s.here.map((h) => h.item.id)).toContain('b1');
    expect(s.otherCount).toBe(2);
  });
  it('keys and labels', () => {
    expect(identityKey(A)).toBe(identityKey({ ...A, name: 'fzk-haus' }));
    expect(identityKey(A)).not.toBe(identityKey(A2));
    expect(identityKey(undefined)).toBe('unknown');
    expect(modelLabel(modelIdentity('One', 1, ['x']))).toBe('One (1 element)');
    expect(modelLabel(null)).toBe('unknown model');
  });
});

describe('loadedIdentity', () => {
  it('is computed once per model load, and null without a model', () => {
    const els = ids(5).map((g) => ({ globalId: g }));
    const app = { loaded: {} as object | null, modelName: 'X', controller: { model: { elements: els } } };
    const a = loadedIdentity(app);
    expect(a).toMatchObject({ name: 'X', elementCount: 5, guidCount: 5 });
    expect(loadedIdentity(app)).toBe(a);
    app.loaded = {};
    expect(loadedIdentity(app)).not.toBe(a);
    app.loaded = null;
    expect(loadedIdentity(app)).toBeNull();
  });
});

describe('markup files carry the model of each set', () => {
  const set = (id: string, model?: ModelIdentity | null): MarkupSet => ({
    id, title: id, author: 'me', created: '2026-11-01T10:00:00Z', updated: '2026-11-01T10:00:00Z', markups: [], nextNumber: 1,
    view: { id: 'v', name: id, created: '2026-11-01T10:00:00Z', camera: { position: [0, 0, 1], target: [0, 0, 0], fov: 50, projection: 'perspective' } } as never,
    camera: { position: [0, 0, 1], direction: [0, 0, -1], up: [0, 1, 0], fov: 50, aspect: 1.5 },
    ...(model !== undefined ? { model } : {}),
  });
  it('writes the model on each set (null when unknown) and reads it back', () => {
    const doc = buildMarkupDoc(A, [set('s1', A), set('s2', B), set('s3')]);
    const back = parseMarkupDoc(markupDocJson(doc));
    expect(back.error).toBeUndefined();
    expect(back.sets.map((s) => s.model?.name ?? null)).toEqual(['FZK-Haus', 'Building', null]);
    expect(back.sets[1]!.model).toEqual(B);
  });
  it('an older file (no model on the sets) gives its sets the model of the document', () => {
    const doc = JSON.parse(markupDocJson(buildMarkupDoc(A, [set('s1', A)]))) as { sets: Array<Record<string, unknown>> };
    delete doc.sets[0]!['model'];
    expect(parseMarkupDoc(doc).sets[0]!.model).toEqual(A);
    // And without a model on the document either, the set is unknown.
    const none = doc as unknown as Record<string, unknown>;
    delete none['model'];
    expect(parseMarkupDoc(none).sets[0]!.model).toBeUndefined();
  });
});

describe('BCF topics carry the model in the side file', () => {
  const topic = (model?: ModelIdentity): BcfTopic => ({
    guid: '11111111-2222-4333-8444-555555555555', topicType: 'Issue', topicStatus: 'Open', title: 'T', labels: [], referenceLinks: [], creationDate: '2026-11-04T09:00:00Z', creationAuthor: 'me',
    headerFiles: [], documentReferences: [], relatedTopics: [], comments: [], viewpoints: [], ...(model ? { model } : {}),
  });
  it('a topic with a model but no markup still gets a side file; one with neither does not', () => {
    expect(sidecarJson(topic(), '2.1')).toBeNull();
    const text = sidecarJson(topic(A), '2.1')!;
    expect(text).not.toBeNull();
    const t = topic();
    applySidecar(t, parseSidecar(text));
    expect(t.model).toEqual(A);
  });
  it('survives a BCF round trip, 2.1 and 3.0', async () => {
    for (const v of ['2.1', '3.0'] as const) {
      const p = emptyProject(v);
      p.topics.push(topic(B));
      const back = await parseBcf(await writeBcf(p, v));
      expect(back.topics[0]!.model).toEqual(B);
    }
  });
  it('a topic from another tool has no model', async () => {
    const p = emptyProject('2.1');
    p.topics.push(topic());
    const back = await parseBcf(await writeBcf(p, '2.1'));
    expect(back.topics[0]!.model).toBeUndefined();
  });
});

// ---------------------------------------------------------------- the controllers, on a stub viewer

interface StubApp {
  loaded: object | null;
  modelName: string;
  controller: { model: { elements: Array<{ globalId: string; bounds: number[]; ifcClass: string }>; byGlobalId: Map<string, number> } };
  [k: string]: unknown;
}
function stubApp(name: string, guids: string[]): StubApp {
  const elements = guids.map((g) => ({ globalId: g, bounds: [0, 0, 0, 1, 1, 1], ifcClass: 'IfcWall' }));
  return { loaded: {}, modelName: name, controller: { model: { elements, byGlobalId: new Map(guids.map((g, i) => [g, i])) } }, renderer: {}, canvas: {} };
}
/** What the viewer does on a model switch: a new loaded object, a new element list, then the plugins' onModel. */
function load(app: StubApp, name: string, guids: string[]): void {
  const n = stubApp(name, guids);
  app.loaded = n.loaded;
  app.modelName = name;
  app.controller = n.controller;
}

const mkSet = (id: string, model?: ModelIdentity | null): MarkupSet => ({
  id, title: id, author: 'me', created: '', updated: '', markups: [], nextNumber: 1, view: {} as never,
  camera: { position: [0, 0, 1], direction: [0, 0, -1], up: [0, 1, 0], fov: 50, aspect: 1.5 }, ...(model !== undefined ? { model } : {}),
});

describe('MarkupController on a model change', () => {
  it('hides the sets of the other model, shows them again when it is loaded again, and lists them under Other models', () => {
    const app = stubApp('FZK-Haus', ids(100));
    const c = new MarkupController(app as never);
    c.sets.push(mkSet('s1', c.modelIdentity()));
    c.activeId = 's1';
    expect(c.active?.id).toBe('s1');
    expect(c.visibleSets().map((x) => x.set.id)).toEqual(['s1']);

    load(app, 'Building', ids(50, 'b'));
    c.onModel();
    expect(c.active).toBeNull();
    expect(c.activeId).toBeNull();
    expect(c.visibleSets()).toEqual([]);
    expect(c.otherCount).toBe(1);
    expect(c.otherModels()[0]!.label).toBe('FZK-Haus (100 elements)');
    expect(c.list()).toEqual([]);
    expect(c.list({ all: true }).map((s) => [s.id, s.scope])).toEqual([['s1', 'different']]);
    // Exports default to the sets of this model.
    expect(() => c.exportJson()).toThrow(/No markup set/);

    load(app, 'FZK-Haus', ids(100));
    c.onModel();
    expect(c.visibleSets().map((x) => x.set.id)).toEqual(['s1']);
    expect(c.otherCount).toBe(0);
  });

  it('keeps a revision (flagged), tags a set without a model, and re-binds a set with Move to this model', () => {
    const app = stubApp('FZK-Haus', ids(100));
    const c = new MarkupController(app as never);
    c.sets.push(mkSet('s1', c.modelIdentity()), mkSet('nomodel'));
    load(app, 'FZK-Haus', ids(104));
    c.onModel();
    const here = c.visibleSets();
    expect(here.map((x) => [x.set.id, x.scope.match])).toEqual([['s1', 'revised'], ['nomodel', 'unknown']]);

    load(app, 'Building', ids(50, 'b'));
    c.onModel();
    expect(c.visibleSets().map((x) => [x.set.id, x.scope.match])).toEqual([['nomodel', 'unknown']]);
    const r = c.moveToModel('s1');
    expect(r).toMatchObject({ detached: 0 });
    expect(c.get('s1')!.model).toEqual(c.modelIdentity());
    expect(c.visibleSets().map((x) => x.set.id)).toEqual(['s1', 'nomodel']);
    expect(c.otherCount).toBe(0);
  });

  it('opening a set of another model on purpose shows it until the next model change', () => {
    const app = stubApp('FZK-Haus', ids(100));
    const c = new MarkupController(app as never);
    c.sets.push(mkSet('s1', c.modelIdentity()));
    load(app, 'Building', ids(50, 'b'));
    c.onModel();
    expect(c.openOther('s1')).toBe(true);
    expect(c.active?.id).toBe('s1');
    expect(c.visibleSets().map((x) => [x.set.id, x.scope.match])).toEqual([['s1', 'different']]);
    expect(c.otherCount).toBe(0);
    load(app, 'Process plant', ids(30, 'c'));
    c.onModel();
    expect(c.active).toBeNull();
    expect(c.otherCount).toBe(1);
  });

  it('deleting a set of another model works', () => {
    const app = stubApp('FZK-Haus', ids(100));
    const c = new MarkupController(app as never);
    c.sets.push(mkSet('s1', c.modelIdentity()));
    load(app, 'Building', ids(50, 'b'));
    c.onModel();
    c.deleteSet('s1');
    expect(c.otherCount).toBe(0);
    expect(c.sets).toEqual([]);
  });
});

describe('BcfController on a model change', () => {
  const topic = (guid: string, title: string, model?: ModelIdentity, pin = true): BcfTopic => ({
    guid, topicType: 'Issue', topicStatus: 'Open', title, labels: [], referenceLinks: [], creationDate: '2026-11-04T09:00:00Z', creationAuthor: 'me',
    headerFiles: [], documentReferences: [], relatedTopics: [], comments: [], viewpoints: [], ...(pin ? { pin: { position: [1, 2, 3] as [number, number, number] } } : {}), ...(model ? { model } : {}),
  });

  it('lists and pins only the topics of the loaded model; the others are under Other models; loading it again shows them', () => {
    const app = stubApp('FZK-Haus', ids(100));
    const c = new BcfController(app as never);
    c.project.topics.push(topic('t1', 'On A', c.modelIdentity()!), topic('t2', 'No model', undefined), topic('t3', 'Revised', modelIdentity('FZK-Haus', 90, ids(90))));
    c.selectedTopic = 't1';
    expect(c.currentTopics.map((t) => t.guid)).toEqual(['t1', 't2', 't3']);
    expect(c.pinnedTopics().map((t) => t.guid)).toEqual([]); // drawer closed: only the applied topic's pin
    c.setDrawerOpen(true);
    expect(c.pinnedTopics().map((t) => t.guid)).toEqual(['t1', 't2', 't3']);
    expect(c.scopeOf(c.topic('t2')!).tag).toBe('model unknown');
    expect(c.scopeOf(c.topic('t3')!).tag).toBe('revised model');

    load(app, 'Building', ids(50, 'b'));
    c.onModel();
    expect(c.currentTopics.map((t) => t.guid)).toEqual(['t2']); // the unknown one stays visible
    expect(c.pinnedTopics().map((t) => t.guid)).toEqual(['t2']);
    expect(c.selectedTopic).toBeNull();
    // The revision is another identity of the same name: its own group.
    expect(c.otherModels().map((g) => [g.model.name, g.items.map((t) => t.guid)])).toEqual([['FZK-Haus', ['t1']], ['FZK-Haus', ['t3']]]);
    expect(c.topics).toHaveLength(3);
    // A viewpoint of an other-model topic is refused, with the way out in the message.
    expect(c.applyViewpoint('t1').ok).toBe(false);
    expect(c.status).toContain('Other models');

    load(app, 'FZK-Haus', ids(100));
    c.onModel();
    expect(c.currentTopics.map((t) => t.guid)).toEqual(['t1', 't2', 't3']);
    expect(c.otherModels()).toEqual([]);
  });

  it('keeps annotations of an other-model topic out of the overlay', () => {
    const app = stubApp('FZK-Haus', ids(100));
    const c = new BcfController(app as never);
    const t = topic('t1', 'On A', c.modelIdentity()!, false);
    const ann: BcfAnnotation = { guid: 'a1', type: 'note', text: 'x', anchor: { kind: 'point', point: [0, 0, 0] }, offset: [0, 0] };
    t.viewpoints.push({ guid: 'v1', annotations: [ann] } as never);
    c.project.topics.push(t);
    c.applied = { topic: 't1', viewpoint: 'v1' };
    expect(c.visibleAnnotations()?.list).toHaveLength(1);
    load(app, 'Building', ids(50, 'b'));
    expect(c.visibleAnnotations()).toBeNull();
    c.onModel();
    expect(c.applied).toBeNull();
  });

  it('Open shows an other-model topic until the model changes; Move re-binds it; Delete removes it', () => {
    const app = stubApp('FZK-Haus', ids(100));
    const c = new BcfController(app as never);
    c.project.topics.push(topic('t1', 'On A', c.modelIdentity()!), topic('t2', 'Also A', c.modelIdentity()!));
    load(app, 'Building', ids(50, 'b'));
    c.onModel();
    expect(c.currentTopics).toEqual([]);
    c.openOther('t1');
    expect(c.currentTopics.map((t) => t.guid)).toEqual(['t1']);
    expect(c.otherModels()[0]!.items.map((t) => t.guid)).toEqual(['t2']);
    c.moveToModel('t2');
    expect(c.currentTopics.map((t) => t.guid)).toEqual(['t1', 't2']);
    expect(c.topic('t2')!.model).toEqual(c.modelIdentity());
    expect(c.otherModels()).toEqual([]);
    c.deleteTopic('t1');
    expect(c.topics.map((t) => t.guid)).toEqual(['t2']);
    load(app, 'Process plant', ids(30, 'c'));
    c.onModel();
    expect(c.currentTopics).toEqual([]); // t2 was moved to Building, so on the plant it is another model's
    expect(c.otherModels()).toHaveLength(1);
  });

  it('new topics belong to the loaded model', () => {
    const app = stubApp('FZK-Haus', ids(100));
    const c = new BcfController(app as never);
    const make = (c as unknown as { newTopic(o: { title: string }, a: string): BcfTopic }).newTopic.bind(c);
    expect(make({ title: 'x' }, 'me').model).toEqual(c.modelIdentity());
  });
});
