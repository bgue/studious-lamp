// Sketches and issues: linking (one sketch, at most one issue, both ways), the drawing of a viewpoint as a projection of its
// sketch, BCF import into linked sketches, migration of legacy comments and status, and the additive file formats.

import { describe, expect, it } from 'vitest';
import { parseBcf } from '../src/bcf/parse';
import { writeBcf } from '../src/bcf/write';
import { emptyProject, newGuid } from '../src/bcf/model';
import type { BcfAnnotation, BcfProject, BcfTopic, Vec3 } from '../src/bcf/model';
import { MARKUP_SCHEMA, addComment, addMarkup, buildMarkupDoc, hasLegacyReview, newMarkup, parseMarkupDoc } from '../src/markup/model';
import type { MarkupSet } from '../src/markup/model';
import {
  annotationToMarkup, clearLegacyReview, issueOfSketch, legacyIssueOf, legacySketches, linkSketch, markupToAnnotation, reconcileLinks,
  sketchAnnotations, sketchFromViewpoint, sketchesOfIssue, syncViewpoint, unlinkSketch,
} from '../src/issues/link';
import { isOpenStatus } from '../src/issues/controller';

const SHIFT: Vec3 = [6, 5, 3.058846];
const CAMERA = { position: [20, -10, 8] as Vec3, direction: [-0.8, 0.5, -0.3] as Vec3, up: [0, 0, 1] as Vec3, fov: 38, aspect: 1.6 };

function sketch(id = 's1', title = 'Duct clash'): MarkupSet {
  const set: MarkupSet = {
    id, title, author: 'Ana', created: '2026-01-01T10:00:00.000Z', updated: '2026-01-01T10:00:00.000Z',
    view: { id: 'v1', name: title, created: '2026-01-01T10:00:00.000Z', updated: '2026-01-01T10:00:00.000Z', camera: { position: [6, 5.5, 13], target: [0, 0, 0], up: [0, 1, 0], fov: 38, ortho: false }, selection: [], params: {} },
    camera: { ...CAMERA }, markups: [], nextNumber: 1,
  };
  addMarkup(set, newMarkup('cloud', { author: 'Ana', shape: { points: [[0.2, 0.2], [0.5, 0.4]], depth: 12 }, text: 'Clash' }));
  addMarkup(set, newMarkup('rect', { author: 'Ana', shape: { points: [[0.6, 0.2], [0.8, 0.4]], depth: 12 } }));
  addMarkup(set, newMarkup('arrow', { author: 'Ana', shape: { points: [[0.1, 0.8], [0.4, 0.6]], depth: 12 } }));
  addMarkup(set, newMarkup('callout', { author: 'Ana', text: 'Move pipe', anchor: { kind: 'element', point: [1, 2, 3], elementGuid: 'ABCDEFGHIJKLMNOPQRSTUV' }, offset: [0.1, -0.09] }));
  return set;
}

function topic(title = 'Issue A'): BcfTopic {
  const g = newGuid();
  return {
    guid: newGuid(), topicType: 'Issue', topicStatus: 'Open', title, labels: [], referenceLinks: [], creationDate: '2026-01-02T10:00:00Z', creationAuthor: 'Ana',
    headerFiles: [], documentReferences: [], relatedTopics: [], comments: [],
    viewpoints: [{ guid: g, data: { guid: g, camera: { kind: 'perspective', ...CAMERA }, selection: [], visibility: null, coloring: [], clipping: [], lines: [] } }],
  };
}

describe('linking a sketch to an issue', () => {
  it('links by id, both ways, and finds the issue from the sketch', () => {
    const s = sketch();
    const t = topic();
    expect(linkSketch([t], [s], s.id, t.guid, t.viewpoints[0]!.guid)).toEqual({ ok: true });
    expect(t.viewpoints[0]!.sketchId).toBe(s.id);
    expect(s.issue).toEqual({ topic: t.guid, viewpoint: t.viewpoints[0]!.guid });
    expect(issueOfSketch([t], s.id)?.topic).toBe(t);
    expect(sketchesOfIssue(t, [s])).toEqual([s]);
  });

  it('refuses a second issue: a sketch belongs to at most one', () => {
    const s = sketch();
    const a = topic('A');
    const b = topic('B');
    expect(linkSketch([a, b], [s], s.id, a.guid, a.viewpoints[0]!.guid).ok).toBe(true);
    const r = linkSketch([a, b], [s], s.id, b.guid, b.viewpoints[0]!.guid);
    expect(r.ok).toBe(false);
    expect(!r.ok && r.error).toMatch(/already belongs to the issue "A"/);
    expect(b.viewpoints[0]!.sketchId).toBeUndefined();
    // the same link again is fine
    expect(linkSketch([a, b], [s], s.id, a.guid, a.viewpoints[0]!.guid).ok).toBe(true);
  });

  it('refuses a viewpoint that already has another sketch', () => {
    const s1 = sketch('s1');
    const s2 = sketch('s2', 'Other');
    const t = topic();
    linkSketch([t], [s1, s2], 's1', t.guid, t.viewpoints[0]!.guid);
    expect(linkSketch([t], [s1, s2], 's2', t.guid, t.viewpoints[0]!.guid).ok).toBe(false);
  });

  it('unlinking cuts both sides and drops the drawing but keeps the camera', () => {
    const s = sketch();
    const t = topic();
    linkSketch([t], [s], s.id, t.guid, t.viewpoints[0]!.guid);
    syncViewpoint(s, t.viewpoints[0]!, SHIFT);
    expect(t.viewpoints[0]!.annotations?.length).toBe(4);
    unlinkSketch([t], [s], s.id);
    expect(t.viewpoints[0]!.sketchId).toBeUndefined();
    expect(t.viewpoints[0]!.annotations).toBeUndefined();
    expect(t.viewpoints[0]!.data?.camera).toBeTruthy();
    expect(s.issue).toBeUndefined();
  });

  it('reconcile repairs dangling and mirrored links', () => {
    const s = sketch();
    const t = topic();
    t.viewpoints[0]!.sketchId = s.id; // the viewpoint says so, the sketch does not know
    expect(reconcileLinks([t], [s])).toBe(1);
    expect(s.issue?.topic).toBe(t.guid);
    s.issue = { topic: 'gone', viewpoint: 'gone' };
    t.viewpoints[0]!.sketchId = 'missing-sketch';
    reconcileLinks([t], [s]);
    expect(t.viewpoints[0]!.sketchId).toBeUndefined();
    expect(s.issue).toBeUndefined();
  });
});

describe('the drawing of a viewpoint follows its sketch', () => {
  it('serialises every kind of markup and keeps them in markup order', () => {
    const s = sketch();
    const list = sketchAnnotations(s, SHIFT);
    expect(list.map((a) => a.type)).toEqual(['freehand', 'rect', 'freehand', 'callout']);
    expect(list[0]!.shape!.points.length).toBeGreaterThan(4); // the cloud is closed
    expect(list[1]!.shape!.points).toEqual([[0.6, 0.2], [0.8, 0.4]]);
    expect(list[2]!.shape!.points.length).toBe(5); // the arrow has its head
    expect(list[3]!.anchor.elementGuid).toBe('ABCDEFGHIJKLMNOPQRSTUV');
    expect(list.map((a) => a.guid)).toEqual(s.markups.map((m) => m.id));
    expect(list[0]!.text).toBe('1. Clash');
  });

  it('editing the sketch changes the viewpoint on the next sync, and only then', () => {
    const s = sketch();
    const t = topic();
    const vp = t.viewpoints[0]!;
    linkSketch([t], [s], s.id, t.guid, vp.guid);
    expect(syncViewpoint(s, vp, SHIFT)).toBe(true);
    expect(syncViewpoint(s, vp, SHIFT)).toBe(false); // nothing changed
    expect(vp.snapshotView).toEqual(s.camera);
    s.markups[0]!.text = 'Clash moved';
    s.markups.pop();
    expect(syncViewpoint(s, vp, SHIFT)).toBe(true);
    expect(vp.annotations?.length).toBe(3);
    expect(vp.annotations![0]!.text).toBe('1. Clash moved');
    s.markups = [];
    syncViewpoint(s, vp, SHIFT);
    expect(vp.annotations).toBeUndefined();
  });

  it('puts the annotated elements in the viewpoint selection and takes them out again', () => {
    const s = sketch();
    const t = topic();
    const vp = t.viewpoints[0]!;
    linkSketch([t], [s], s.id, t.guid, vp.guid);
    syncViewpoint(s, vp, SHIFT);
    expect(vp.data!.selection.map((c) => c.ifcGuid)).toContain('ABCDEFGHIJKLMNOPQRSTUV');
    s.markups = s.markups.filter((m) => m.kind !== 'callout');
    syncViewpoint(s, vp, SHIFT);
    expect(vp.data!.selection).toEqual([]);
  });

  it('a markup round trip through an annotation keeps kind, text, anchor and shape', () => {
    const s = sketch();
    const a = markupToAnnotation(s.markups[3]!, s.camera, SHIFT)!;
    const m = annotationToMarkup(a, 4, 'Ana')!;
    expect(m.kind).toBe('callout');
    expect(m.text).toBe('Move pipe');
    expect(m.anchor?.elementGuid).toBe('ABCDEFGHIJKLMNOPQRSTUV');
    const r = markupToAnnotation(s.markups[1]!, s.camera, SHIFT)!;
    const back = annotationToMarkup(r, 2, 'Ana')!;
    expect(back.kind).toBe('rect');
    expect(back.shape).toEqual(s.markups[1]!.shape);
  });
});

describe('BCF import makes sketches linked to their issue', () => {
  async function exported(): Promise<BcfProject> {
    const s = sketch();
    const p = emptyProject('2.1');
    const t = topic('Imported issue');
    p.topics.push(t);
    linkSketch(p.topics, [s], s.id, t.guid, t.viewpoints[0]!.guid);
    syncViewpoint(s, t.viewpoints[0]!, SHIFT);
    t.viewpoints[0]!.snapshot = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 1, 2, 3, 4]);
    t.viewpoints[0]!.snapshotMime = 'image/png';
    const bytes = await writeBcf(p, '2.1', { composeSnapshot: async () => null });
    return parseBcf(bytes);
  }

  it('a viewpoint with annotations becomes a sketch of the same issue', async () => {
    const p = await exported();
    const t = p.topics[0]!;
    const ref = t.viewpoints[0]!;
    expect(ref.sketchId).toBeUndefined(); // the file does not carry the session link
    expect(ref.annotations?.length).toBe(4);
    const set = sketchFromViewpoint(t, ref, { author: 'Ana', shift: SHIFT, camera: ref.snapshotView! })!;
    expect(set).toBeTruthy();
    expect(set.fromViewpoint).toBe(true);
    expect(set.markups.map((m) => m.kind)).toEqual(['pen', 'rect', 'pen', 'callout']);
    expect(set.markups.map((m) => m.number)).toEqual([1, 2, 3, 4]);
    expect(set.markups[0]!.text).toBe('Clash'); // the numbered label is taken apart again
    expect(ref.sketchId).toBe(set.id);
    expect(set.issue).toEqual({ topic: t.guid, viewpoint: ref.guid });
    expect(set.camera).toEqual(ref.snapshotView);
    // a second call does nothing: the viewpoint already has its sketch
    expect(sketchFromViewpoint(t, ref, { author: 'Ana', shift: SHIFT, camera: ref.snapshotView! })).toBeNull();
    // and the viewpoint's drawing is the same as the sketch's, up to the shape points (kept as they are)
    const again = sketchAnnotations(set, SHIFT);
    expect(again.length).toBe(4);
  });

  it('a viewpoint without annotations makes no sketch', () => {
    const t = topic();
    expect(sketchFromViewpoint(t, t.viewpoints[0]!, { author: 'x', shift: SHIFT, camera: CAMERA })).toBeNull();
  });

  it('a drawing that cannot become markup (foreign lines) keeps the viewpoint as it is', () => {
    const t = topic();
    const lines: BcfAnnotation = { guid: newGuid(), type: 'freehand', text: '', anchor: { kind: 'point', point: [0, 0, 0] }, offset: [0, 0], attach: { kind: 'lines', lines: [{ a: [0, 0, 0], b: [1, 1, 1] }] } as never };
    t.viewpoints[0]!.annotations = [lines];
    expect(sketchFromViewpoint(t, t.viewpoints[0]!, { author: 'x', shift: SHIFT, camera: CAMERA })).toBeNull();
    expect(t.viewpoints[0]!.sketchId).toBeUndefined();
  });
});

describe('legacy comments and status', () => {
  function legacy(): MarkupSet {
    const s = sketch('legacy', 'Old review');
    s.markups[0]!.status = 'resolved';
    addComment(s.markups[0]!, 'Ben', 'Checked on site', '2026-01-05T08:00:00.000Z');
    addComment(s.markups[3]!, 'Cleo', 'Still open', '2026-01-04T08:00:00.000Z');
    s.markups[3]!.assignee = 'Dana';
    s.markups[3]!.due = '2026-02-01';
    s.markups[1]!.due = '2026-01-20';
    return s;
  }

  it('a sketch with comments, a resolved status, an assignee or a due date has legacy review data', () => {
    expect(hasLegacyReview(sketch())).toBe(false);
    expect(hasLegacyReview(legacy())).toBe(true);
    const s = sketch();
    s.markups[2]!.status = 'resolved';
    expect(hasLegacyReview(s)).toBe(true);
  });

  it('the banner lists sketches with legacy data that are not part of an issue yet', () => {
    const a = legacy();
    const b = sketch('plain');
    const c = legacy();
    c.id = 'raised';
    c.issue = { topic: 't', viewpoint: 'v' };
    expect(legacySketches([a, b, c], hasLegacyReview).map((s) => s.id)).toEqual(['legacy']);
  });

  it('becomes an issue spec with the comments in time order, the first assignee and the earliest due date', () => {
    const spec = legacyIssueOf(legacy());
    expect(spec.title).toBe('Old review');
    expect(spec.status).toBe('Open'); // markups 2 to 4 are still open
    expect(spec.assignedTo).toBe('Dana');
    expect(spec.dueDate).toBe('2026-01-20');
    expect(spec.comments.map((c) => c.text)).toEqual(['4. Still open', '1. Checked on site']);
    expect(spec.comments[0]!.author).toBe('Cleo');
  });

  it('an all-resolved sketch becomes a Resolved issue; the note is the description', () => {
    const s = sketch();
    s.note = 'Beam and duct';
    for (const m of s.markups) m.status = 'resolved';
    const spec = legacyIssueOf(s);
    expect(spec.status).toBe('Resolved');
    expect(spec.description).toBe('Beam and duct');
  });

  it('clearing moves the review data out of the sketch', () => {
    const s = legacy();
    clearLegacyReview(s);
    expect(hasLegacyReview(s)).toBe(false);
    expect(s.markups[0]!.comments).toEqual([]);
  });

  it('open statuses: anything not resolved or closed counts as open', () => {
    expect(['Open', 'In Progress', 'Active', 'Reopened', ''].every(isOpenStatus)).toBe(true);
    expect(['Resolved', 'Closed', 'closed', 'Done'].some(isOpenStatus)).toBe(false);
  });
});

describe('file formats stay backward-compatible', () => {
  it('a document from before sketches (comments, status, no note, no link) still reads, with its review data', () => {
    const s = sketch('old');
    s.markups[0]!.status = 'resolved';
    addComment(s.markups[0]!, 'Ben', 'Checked', '2026-01-02T08:00:00.000Z');
    const doc = buildMarkupDoc({ name: 'm', elementCount: 1, guidCount: 1, guidHash: 'h' }, [s]);
    expect(doc.schema).toBe(MARKUP_SCHEMA);
    expect(MARKUP_SCHEMA).toBe('xray-markup-set/1'); // additive fields only: no new major version
    const p = parseMarkupDoc(JSON.stringify(doc));
    expect(p.error).toBeUndefined();
    const back = p.sets[0]!;
    expect(back.note).toBeUndefined();
    expect(back.issue).toBeUndefined();
    expect(back.markups[0]!.status).toBe('resolved');
    expect(back.markups[0]!.comments[0]!.text).toBe('Checked');
    expect(hasLegacyReview(back)).toBe(true);
  });

  it('the new fields (note, issue link, from-viewpoint flag) round trip', () => {
    const s = sketch('new');
    s.note = 'One line';
    s.issue = { topic: 'abc', viewpoint: 'def' };
    s.fromViewpoint = true;
    const p = parseMarkupDoc(JSON.stringify(buildMarkupDoc({ name: 'm', elementCount: 1, guidCount: 1, guidHash: 'h' }, [s])));
    expect(p.sets[0]!.note).toBe('One line');
    expect(p.sets[0]!.issue).toEqual({ topic: 'abc', viewpoint: 'def' });
    expect(p.sets[0]!.fromViewpoint).toBe(true);
  });

  it('a note is one line and is capped', () => {
    const doc = JSON.parse(JSON.stringify(buildMarkupDoc({ name: 'm', elementCount: 1, guidCount: 1, guidHash: 'h' }, [sketch()])));
    doc.sets[0].note = `first\nsecond   line ${'x'.repeat(600)}`;
    const note = parseMarkupDoc(doc).sets[0]!.note!;
    expect(note.startsWith('first second line')).toBe(true);
    expect(note.length).toBeLessThanOrEqual(400);
    expect(note).not.toMatch(/\n/);
  });
});
