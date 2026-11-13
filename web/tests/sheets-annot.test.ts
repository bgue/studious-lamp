import { describe, expect, it } from 'vitest';
import { newMarkup } from '../src/markup/model';
import type { Markup, MarkupKind } from '../src/markup/model';
import { DEFAULT_AUTHOR, authorFor, colourOf, hexToRgb, isOwnNm, makeNm, markupToSpec, parseNm, specToMarkups, weightFor, widthPt } from '../src/sheets/annot';
import type { AnnotSpec } from '../src/sheets/annot';
import { buildAppearance, hexText } from '../src/sheets/appearance';
import { anchorGeometry, layoutSheetMarkup } from '../src/sheets/layout';
import { displayToUser, docIdOf, parseSheetId, sheetIdOf, sheetUnit, userToDisplay } from '../src/sheets/model';
import type { Sheet } from '../src/sheets/model';

const sheet = (rotation: 0 | 90 | 180 | 270 = 0, box?: [number, number, number, number]): Sheet => {
  const turned = rotation === 90 || rotation === 270;
  const b = box ?? [0, 0, 842, 595];
  const w0 = b[2] - b[0];
  const h0 = b[3] - b[1];
  return { id: 'doc-0123456789abcdef-p1', docId: 'doc-0123456789abcdef', page: 1, name: 'A', widthPt: turned ? h0 : w0, heightPt: turned ? w0 : h0, rotation, ...(box ? { box } : {}) };
};

const shape = (pts: Array<[number, number]>) => ({ points: pts, depth: 0 });
const ctx = { set: 's1abc', title: 'Review', date: '2026-02-01T10:00:00.000Z' };

function mk(kind: MarkupKind, extra: Partial<Markup> = {}): Markup {
  return newMarkup(kind, { id: `m${kind}`, number: 3, author: 'unknown', text: 'note', created: '2026-02-01T10:00:00.000Z', ...extra });
}

const CASES: Array<{ name: string; m: Markup; subtype: AnnotSpec['subtype']; check?: (s: AnnotSpec) => void }> = [
  { name: 'cloud (rectangle)', m: mk('cloud', { shape: shape([[100, 100], [300, 220]]) }), subtype: 'Polygon', check: (s) => { expect(s.cloud).toBe(true); expect(s.intent).toBe('PolygonCloud'); expect(s.vertices).toHaveLength(8); } },
  { name: 'cloud (outline)', m: mk('cloud', { shape: shape([[100, 100], [300, 120], [320, 240], [90, 230], [60, 160]]) }), subtype: 'Polygon', check: (s) => { expect(s.cloud).toBe(true); expect(s.vertices).toHaveLength(10); } },
  { name: 'rectangle', m: mk('rect', { shape: shape([[120, 80], [320, 200]]) }), subtype: 'Square' },
  { name: 'filled rectangle', m: mk('rect', { fill: true, shape: shape([[120, 80], [320, 200]]) }), subtype: 'Square', check: (s) => expect(s.interior).toBeDefined() },
  { name: 'ellipse', m: mk('ellipse', { colour: 'blue', shape: shape([[120, 80], [320, 200]]) }), subtype: 'Circle' },
  { name: 'line', m: mk('line', { shape: shape([[50, 60], [400, 300]]) }), subtype: 'Line', check: (s) => expect(s.lineEnding).toEqual(['None', 'None']) },
  { name: 'arrow', m: mk('arrow', { shape: shape([[50, 60], [400, 300]]) }), subtype: 'Line', check: (s) => expect(s.lineEnding).toEqual(['None', 'ClosedArrow']) },
  { name: 'polyline', m: mk('polyline', { shape: shape([[50, 60], [150, 90], [220, 40], [300, 100]]) }), subtype: 'PolyLine' },
  { name: 'polygon', m: mk('polygon', { colour: 'green', shape: shape([[50, 60], [150, 90], [220, 40]]) }), subtype: 'Polygon', check: (s) => expect(s.cloud).toBeUndefined() },
  { name: 'freehand', m: mk('pen', { shape: shape([[50, 60], [60, 70], [75, 66], [90, 80]]) }), subtype: 'Ink', check: (s) => expect(s.inkList).toHaveLength(1) },
  { name: 'marker', m: mk('highlight', { colour: 'yellow', weight: 3, shape: shape([[50, 60], [60, 70], [75, 66], [90, 80]]) }), subtype: 'Ink', check: (s) => expect(s.opacity).toBeLessThan(1) },
  { name: 'highlight box', m: mk('highlightBox', { colour: 'yellow', shape: shape([[120, 80], [320, 200]]) }), subtype: 'Square', check: (s) => { expect(s.opacity).toBeLessThan(1); expect(s.interior).toBeDefined(); } },
  { name: 'text', m: mk('text', { text: 'Move the wall 50 mm', anchor: { kind: 'point', point: [200, 300, 0] }, offset: [0.05, -0.04] }), subtype: 'FreeText', check: (s) => { expect(s.intent).toBeUndefined(); expect(s.textLines?.join(' ')).toBe('Move the wall 50 mm'); } },
  { name: 'callout', m: mk('callout', { text: 'Fire door', anchor: { kind: 'point', point: [200, 300, 0] }, offset: [0.1, -0.09] }), subtype: 'FreeText', check: (s) => { expect(s.intent).toBe('FreeTextCallout'); expect(s.callout).toHaveLength(4); expect(s.callout!.slice(0, 2)).toEqual([200, 300]); } },
];

describe('sheet shape to PDF annotation, and back', () => {
  for (const rotation of [0, 90, 180, 270] as const) {
    describe(`page rotation ${rotation}`, () => {
      const sh = sheet(rotation, rotation === 0 ? undefined : [10, 20, 852, 615]);
      for (const c of CASES) {
        it(`${c.name}: maps to /${c.subtype} and gives the same shape back`, () => {
          const spec = markupToSpec(c.m, sh, ctx)!;
          expect(spec).toBeTruthy();
          expect(spec.subtype).toBe(c.subtype);
          expect(spec.name).toBe(makeNm('s1abc', c.m.id));
          expect(spec.contents).toBe(c.m.text);
          expect(spec.author).toBe(DEFAULT_AUTHOR);
          expect(spec.width).toBeCloseTo(c.m.kind === 'highlightBox' ? 0 : widthPt(c.m.kind, c.m.weight, sh), 5);
          c.check?.(spec);
          const back = specToMarkups(spec, sh, { id: c.m.id })[0]!;
          expect(back.kind).toBe(c.m.kind);
          expect(back.colour).toBe(c.m.colour);
          expect(back.weight).toBe(c.m.weight);
          expect(back.fill).toBe(c.m.fill);
          expect(back.text).toBe(c.m.text);
          if (c.m.shape) expect(back.shape!.points).toEqual(c.m.shape.points.map((p) => [Math.round(p[0] * 1000) / 1000, Math.round(p[1] * 1000) / 1000]));
          if (c.m.anchor) {
            expect(back.anchor!.point[0]).toBeCloseTo(c.m.anchor.point[0], 2);
            expect(back.anchor!.point[1]).toBeCloseTo(c.m.anchor.point[1], 2);
            expect(back.offset![0]).toBeCloseTo(c.m.offset![0], 4);
          }
          // The rectangle of every annotation holds its geometry.
          const [x0, y0, x1, y1] = spec.rect;
          for (const [px, py] of c.m.shape?.points ?? []) {
            expect(px).toBeGreaterThanOrEqual(x0 - 0.01);
            expect(px).toBeLessThanOrEqual(x1 + 0.01);
            expect(py).toBeGreaterThanOrEqual(y0 - 0.01);
            expect(py).toBeLessThanOrEqual(y1 + 0.01);
          }
        });
        it(`${c.name}: has an appearance stream`, () => {
          const spec = markupToSpec(c.m, sh, ctx)!;
          const ap = buildAppearance(spec, sh)!;
          expect(ap).toBeTruthy();
          expect(ap.content.startsWith('q')).toBe(true);
          expect(ap.content.trimEnd().endsWith('Q')).toBe(true);
          expect(ap.bbox).toEqual(spec.rect);
          expect(ap.font).toBe(c.m.kind === 'text' || c.m.kind === 'callout');
        });
      }
    });
  }

  it('without the private keys the shape is rebuilt from the standard keys alone', () => {
    const sh = sheet();
    for (const c of CASES) {
      const spec = markupToSpec(c.m, sh, ctx)!;
      delete spec.xray;
      const back = specToMarkups(spec, sh)[0]!;
      const want = c.m.kind === 'highlight' ? 'pen' : c.m.kind; // a marker is a pen stroke without its private key unless it is wide
      expect([c.m.kind, want, 'highlight']).toContain(back.kind);
      if (c.m.kind !== 'highlight') expect(back.kind).toBe(c.m.kind);
      expect(back.text).toBe(c.m.text);
    }
  });

  it('keeps a text box where it was drawn', () => {
    const sh = sheet(90, [0, 0, 842, 595]);
    const m = mk('callout', { text: 'Check', anchor: { kind: 'point', point: [300, 200, 0] }, offset: [0.12, -0.08] });
    const g = anchorGeometry(m, sh)!;
    const spec = markupToSpec(m, sh, ctx)!;
    const rd = spec.rd!;
    const inner: [number, number, number, number] = [spec.rect[0] + rd[0], spec.rect[1] + rd[1], spec.rect[2] - rd[2], spec.rect[3] - rd[3]];
    const a = displayToUser(sh, g.box.x, g.box.y);
    const b = displayToUser(sh, g.box.x + g.box.w, g.box.y + g.box.h);
    expect(inner[0]).toBeCloseTo(Math.min(a[0], b[0]), 2);
    expect(inner[3]).toBeCloseTo(Math.max(a[1], b[1]), 2);
  });

  it('writes the author the user typed, else "X-ray", and never a stray name', () => {
    expect(authorFor(undefined)).toBe('X-ray');
    expect(authorFor('unknown')).toBe('X-ray');
    expect(authorFor('  ')).toBe('X-ray');
    expect(authorFor('Ada')).toBe('Ada');
    const sh = sheet();
    expect(markupToSpec(mk('rect', { shape: shape([[1, 1], [9, 9]]), author: 'unknown' }), sh, { ...ctx, author: 'unknown' })!.author).toBe('X-ray');
    expect(markupToSpec(mk('rect', { shape: shape([[1, 1], [9, 9]]) }), sh, { ...ctx, author: 'Ada' })!.author).toBe('Ada');
  });

  it('names annotations with a stable id that says its sketch and markup', () => {
    const nm = makeNm('s1abc', 'm9z');
    expect(isOwnNm(nm)).toBe(true);
    expect(parseNm(nm)).toEqual({ set: 's1abc', id: 'm9z' });
    expect(isOwnNm('foreign-1')).toBe(false);
    expect(parseNm('xray-bad name')).toBeNull();
  });

  it('keeps a custom colour and tells palette colours from custom ones', () => {
    expect(colourOf(hexToRgb('#e5262b'))).toEqual({ colour: 'red' });
    expect(colourOf([0.2, 0.5, 0.7]).hex).toBe('#3380b3');
    const sh = sheet();
    const m = mk('rect', { hex: '#3380b3', shape: shape([[10, 10], [60, 50]]) });
    const spec = markupToSpec(m, sh, ctx)!;
    expect(spec.color[0]).toBeCloseTo(0.2, 2);
    expect(specToMarkups(spec, sh)[0]!.hex).toBe('#3380b3');
  });

  it('recovers the weight from the width, scaled by the sheet size', () => {
    const small = sheet();
    const big = { ...sheet(), widthPt: 3370, heightPt: 2384 };
    expect(sheetUnit(big)).toBeGreaterThan(sheetUnit(small));
    for (const w of [1, 2, 3, 4] as const) {
      expect(weightFor('rect', widthPt('rect', w, big), big)).toBe(w);
      expect(weightFor('rect', widthPt('rect', w, small), small)).toBe(w);
    }
  });

  it('encodes text for the appearance stream in WinAnsi hex', () => {
    expect(hexText('Ab')).toBe('<4162>');
    expect(hexText('€')).toBe('<3f>');
  });

  it('lays a sheet markup out in pixels, the same at any rotation', () => {
    for (const rotation of [0, 90] as const) {
      const sh = sheet(rotation);
      const L = layoutSheetMarkup(mk('rect', { shape: shape([[100, 100], [300, 220]]) }), sh, { scale: 2 });
      expect(L.ops.length).toBeGreaterThan(0);
      expect(L.hit!.pts.length).toBeGreaterThanOrEqual(8);
      const path = L.ops.find((o) => o.op === 'path') as { points: number[] };
      const [dx, dy] = userToDisplay(sh, 100, 100);
      expect(Math.min(...path.points.filter((_v, i) => i % 2 === 0))).toBeLessThanOrEqual(Math.max(dx, userToDisplay(sh, 300, 220)[0]) * 2 + 0.01);
      expect(dy).toBeGreaterThan(-1);
    }
    const t = layoutSheetMarkup(mk('callout', { text: 'Hi', anchor: { kind: 'point', point: [200, 300, 0] }, offset: [0.1, -0.09] }), sheet(), { scale: 1 });
    expect(t.ops.some((o) => o.op === 'text' && o.role === 'box')).toBe(true);
  });
});

describe('sheet ids and page maths', () => {
  it('ids come from the content hash', () => {
    const d = docIdOf('0123456789abcdef0123456789abcdef');
    expect(d).toBe('doc-0123456789abcdef');
    expect(parseSheetId(sheetIdOf(d, 3))).toEqual({ docId: d, page: 3 });
    expect(parseSheetId('nope')).toBeNull();
  });

  it('turns points both ways for every rotation', () => {
    for (const rotation of [0, 90, 180, 270] as const) {
      const sh = sheet(rotation, [5, 7, 847, 602]);
      const [dx, dy] = userToDisplay(sh, 100, 200);
      expect(dx).toBeGreaterThanOrEqual(0);
      expect(dy).toBeGreaterThanOrEqual(0);
      expect(dx).toBeLessThanOrEqual(sh.widthPt);
      expect(dy).toBeLessThanOrEqual(sh.heightPt);
      const [x, y] = displayToUser(sh, dx, dy);
      expect(x).toBeCloseTo(100, 6);
      expect(y).toBeCloseTo(200, 6);
    }
    // The top left of an unrotated page is (0, height) in user space.
    expect(userToDisplay(sheet(0), 0, 595)).toEqual([0, 0]);
    // Turned a quarter clockwise, the bottom left corner of the page is at the top left of the display.
    expect(userToDisplay(sheet(90), 0, 0)).toEqual([0, 0]);
  });
});
