import { describe, expect, it } from 'vitest';
import { PAGE_SIZES, buildReport, fitImage, howToLines } from '../src/markup/report';
import type { ReportImage } from '../src/markup/report';
import { extractAttachments } from '../src/markup/pdf';
import { addComment, addMarkup, buildMarkupDoc, markupDocJson, modelIdentity, newMarkup, parseMarkupDoc } from '../src/markup/model';
import type { MarkupSet } from '../src/markup/model';

const jpeg = (w: number, h: number): ReportImage => ({ bytes: new Uint8Array([0xff, 0xd8, 0xff, 0xc0, 0, 17, 8, h >> 8, h & 255, w >> 8, w & 255, 3, 1, 0x22, 0, 2, 0x11, 1, 3, 0x11, 1, 0xff, 0xd9]), width: w, height: h });
const text = (b: Uint8Array): string => Array.from(b, (c) => String.fromCharCode(c)).join('');

function makeSet(n: number, title = 'Level 2: Küche (clash)'): MarkupSet {
  const set: MarkupSet = {
    id: 's' + title.length, title, author: 'Ana', created: '2026-01-01T10:00:00.000Z', updated: '2026-01-01T10:00:00.000Z',
    view: { id: 'v', name: title, created: '2026-01-01T10:00:00.000Z', updated: '2026-01-01T10:00:00.000Z', camera: { position: [1, 2, 3], target: [0, 0, 0], up: [0, 1, 0], fov: 45, ortho: false }, selection: [], params: {} },
    camera: { position: [1, -3, 2], direction: [0, 1, 0], up: [0, 0, 1], fov: 45, aspect: 1.6 }, markups: [], nextNumber: 1,
  };
  for (let i = 0; i < n; i++) {
    const m = addMarkup(set, newMarkup(i % 2 ? 'cloud' : 'rect', { author: 'Ana', text: `Markup text ${i + 1} with some words to wrap onto several lines of the narrow text column`, shape: { points: [[0.1, 0.1], [0.3, 0.3]], depth: 5 } }));
    addComment(m, 'Ben', 'A long comment that goes on and on about the clash, the (pipe) and the \\ duct. '.repeat(i % 3 + 1), '2026-01-02T08:00:00.000Z');
    if (i % 4 === 0) m.status = 'resolved';
  }
  return set;
}

function report(sets: MarkupSet[], page: 'A4' | 'Letter' = 'A4', link?: string): { bytes: Uint8Array; json: string; s: string } {
  const id = modelIdentity('fzk-haus.ifc', 10, ['a', 'b']);
  const doc = buildMarkupDoc(id, sets);
  const json = markupDocJson(doc);
  const bytes = buildReport(sets.map((set) => ({ set, clean: jpeg(1280, 720), marked: jpeg(1280, 720), ...(link ? { link } : {}) })), {
    page, model: id, author: 'Ana', date: new Date(2026, 0, 5, 9, 30), json: new TextEncoder().encode(json), jsonName: 'xray-markup-test.json',
  });
  return { bytes, json, s: text(bytes) };
}

describe('markup PDF report', () => {
  it('has the clean page, the marked page and a table page per set, landscape A4', () => {
    const { s } = report([makeSet(3)]);
    expect(s).toContain('/Type /Pages /Count 3');
    expect(s).toContain(`/MediaBox [0 0 ${PAGE_SIZES.A4.w} ${PAGE_SIZES.A4.h}]`);
    expect(PAGE_SIZES.A4.w).toBeGreaterThan(PAGE_SIZES.A4.h);
    // two images (clean, marked) and the page labels
    expect((s.match(/\/Subtype \/Image/g) ?? []).length).toBe(2);
    expect(s).toContain('(Page 1 of 3) Tj');
    expect(s).toContain('(Page 3 of 3) Tj');
  });

  it('writes Letter landscape when asked', () => {
    expect(report([makeSet(1)], 'Letter').s).toContain('/MediaBox [0 0 792 612]');
  });

  it('puts the model, the set title, the date, the author and the how-to block in the text', () => {
    const { s } = report([makeSet(2)]);
    expect(s).toContain('(fzk-haus.ifc) Tj');
    expect(s).toContain('Level 2: K\\374che \\(clash\\)');
    expect(s).toContain('(2026-01-05 09:30) Tj');
    expect(s).toContain('by Ana');
    expect(s).toContain('(How to get back to this view) Tj');
    expect(s).toContain('Drop this PDF');
    for (const l of howToLines(false, 'x.json')) expect(l.length).toBeGreaterThan(10);
  });

  it('lists every markup with number, type, status and comments, escaping the text', () => {
    const { s } = report([makeSet(3)]);
    expect(s).toContain('(Rectangle) Tj');
    expect(s).toContain('(Cloud) Tj');
    expect(s).toContain('(Resolved) Tj');
    expect(s).toContain('(Open) Tj');
    expect(s).toContain('\\(pipe\\)');
    expect(s).toContain('\\\\ duct');
    expect(s).toContain('Ben, 2026-01-02');
  });

  it('continues the table on more pages when it is long, repeating the header', () => {
    const { s } = report([makeSet(40)]);
    const pages = Number(/\/Type \/Pages \/Count (\d+)/.exec(s)![1]);
    expect(pages).toBeGreaterThanOrEqual(5);
    expect(s).toContain('Comment table, continued');
    expect((s.match(/\(Assigned to \/ due\) Tj/g) ?? []).length).toBe(pages - 2);
    expect(s).toContain(`(Page ${pages} of ${pages}) Tj`);
  });

  it('prints "no markups" for an empty set and still has the pages', () => {
    const { s } = report([makeSet(0)]);
    expect(s).toContain('This set has no markups.');
    expect(s).toContain('/Count 3');
  });

  it('makes one block of pages per set for several sets, and one attachment', async () => {
    const { s, bytes } = report([makeSet(2, 'One'), makeSet(2, 'Two!')]);
    expect(s).toContain('/Count 6');
    expect((await extractAttachments(bytes)).length).toBe(1);
  });

  it('adds a link annotation only with a link', () => {
    expect(report([makeSet(1)]).s).not.toContain('/Subtype /Link');
    const l = report([makeSet(1)], 'A4', 'https://example.org/v/?model=fzk-haus#view=AbC_-1');
    expect(l.s).toContain('/Subtype /Link');
    expect(l.s).toContain('/URI (https://example.org/v/?model=fzk-haus#view=AbC_-1)');
    expect(l.s).toContain('Open this view in the viewer');
  });

  it('attaches the JSON byte for byte, and it parses back to the same sets', async () => {
    const sets = [makeSet(4)];
    const { bytes, json } = report(sets);
    const files = await extractAttachments(bytes);
    expect(files[0]!.name).toBe('xray-markup-test.json');
    expect(files[0]!.mime).toBe('application/json');
    expect(new TextDecoder().decode(files[0]!.data)).toBe(json);
    const back = parseMarkupDoc(new TextDecoder().decode(files[0]!.data));
    expect(back.error).toBeUndefined();
    expect(back.sets[0]).toEqual(buildMarkupDoc(modelIdentity('x', 0, []), sets).sets[0]);
  });

  it('fits an image into a box keeping its aspect', () => {
    const r = fitImage(1600, 800, { x: 10, y: 20, w: 400, h: 400 });
    expect(r.w).toBe(400);
    expect(r.h).toBe(200);
    expect(r.x).toBe(10);
    expect(r.y).toBe(120);
  });
});
