import { describe, expect, it } from 'vitest';
import * as PDFLib from 'pdf-lib';
import { buildDemoPlan } from '../src/anim/fourd/demoPlan';
import type { DemoModel } from '../src/anim/fourd/demoPlan';
import { legendContent, legendOn, stripOn } from '../src/anim/fourd/legend';
import { stripGroups, stripLayout, stripHeight, MAX_STRIP_ROWS } from '../src/anim/hud/strip';
import { captionAt, buildStoryboardPdf, pageLayout, parseEvery, planStoryboard, storyboardDates, winAnsi, PAGE_POINTS } from '../src/schedule/storyboard';
import type { FourDPlan } from '../src/schedule/types';

const classes = ['IfcSlab', 'IfcWall', 'IfcColumn', 'IfcDuctSegment', 'IfcCovering', 'IfcWindow'];
const model: DemoModel = {
  name: 'T',
  storeys: [{ id: 0, name: 'L1', elevation: 0 }, { id: 1, name: 'L2', elevation: 3 }, { id: 2, name: 'L3', elevation: 6 }],
  elements: Array.from({ length: 120 }, (_, i) => ({ globalId: `e${i}`, ifcClass: classes[i % classes.length]!, storey: i % 3, bounds: [i, 0, 0, i + 1, 1, 1] })),
};
const plan = buildDemoPlan(model, { seconds: 20 });
const DAY = 86400000;
const latin1 = (b: Uint8Array): string => Array.from(b, (c) => String.fromCharCode(c)).join('');
// a 1x1 baseline JPEG
const JPEG = Uint8Array.from(atob('/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAMCAgICAgMCAgIDAwMDBAYEBAQEBAgGBgUGCQgKCgkICQkKDA8MCgsOCwkJDRENDg8QEBEQCgwSExIQEw8QEBD/yQALCAABAAEBAREA/8wABgAQEAX/2gAIAQEAAD8A0s8g/9k='), (c) => c.charCodeAt(0));

describe('legend content', () => {
  it('lists the trades that appear in the film and the state key', () => {
    const c = legendContent(plan);
    const trades = new Set(plan.tasks.filter((k) => !k.milestone && k.elements > 0).map((k) => k.trade ?? 'Work'));
    expect(c.trades.map((t) => t.label).sort()).toEqual([...trades].sort());
    expect(c.trades.every((t) => /^#[0-9a-f]{6}$/i.test(t.colour))).toBe(true);
    const labels = c.states.map((s) => s.label);
    expect(labels).toEqual(expect.arrayContaining(['Active', 'Built', 'Critical', 'Behind', 'Ahead']));
    expect(labels).not.toContain('Removed');
  });

  it('adds Planned for a ghost view, Removed and Existing when the plan has them, temporary works when it carries colours', () => {
    const p: FourDPlan = JSON.parse(JSON.stringify(plan));
    p.style.unbuilt = 'ghost';
    p.elements[0]!.intervals.push({ from: 0, to: 1, state: 'removed', task: 'x' });
    p.elements[1]!.intervals.unshift({ from: 0, to: 1, state: 'existing', task: 'x' });
    (p as unknown as { temporary: unknown }).temporary = [{ colour: '#aa5500', label: 'Scaffold' }];
    const labels = legendContent(p).states.map((s) => s.label);
    expect(labels).toEqual(expect.arrayContaining(['Planned', 'Removed', 'Existing', 'Scaffold']));
  });

  it('leaves Behind and Ahead out without actuals and the legend / strip default to on', () => {
    const p: FourDPlan = { ...plan, progress: plan.progress.map(({ at, planned }) => ({ at, planned })), style: { ...plan.style, view: 'planned' } };
    expect(legendContent(p).states.map((s) => s.label)).not.toContain('Behind');
    expect(legendOn(plan)).toBe(true);
    expect(stripOn(plan)).toBe(true);
    expect(legendOn({ ...plan, style: { ...plan.style, legend: 'off' } })).toBe(false);
    expect(stripOn({ ...plan, style: { ...plan.style, strip: 'off' } })).toBe(false);
  });

  it('keeps at most eight trades and counts the rest', () => {
    const p: FourDPlan = { ...plan, tasks: Array.from({ length: 12 }, (_, i) => ({ code: `T${i}`, name: `t${i}`, start: i, end: i + 5, critical: false, milestone: false, trade: `trade${i}`, elements: 3 })) };
    const c = legendContent(p);
    expect(c.trades).toHaveLength(8);
    expect(c.moreTrades).toBe(4);
  });
});

describe('schedule strip layout', () => {
  const rect = { x: 20, y: 400, w: 800, h: 90 };
  it('groups by trade, one bar per activity, inside the band', () => {
    const l = stripLayout(plan, rect, plan.window.from);
    expect(l.rows.map((r) => r.label).sort()).toEqual([...new Set(plan.tasks.filter((k) => !k.milestone).map((k) => k.trade ?? 'Work'))].sort());
    expect(l.rows.reduce((n, r) => n + r.bars.length, 0)).toBe(plan.tasks.filter((k) => !k.milestone).length);
    for (const r of l.rows) for (const b of r.bars) {
      expect(b.x).toBeGreaterThanOrEqual(rect.x - 1e-6);
      expect(b.x + b.w).toBeLessThanOrEqual(rect.x + rect.w + 1.5);
    }
    expect(l.milestones).toHaveLength(plan.milestones.length);
  });

  it('puts the marker at the date and highlights the running bars', () => {
    const { from, to } = plan.window;
    expect(stripLayout(plan, rect, from).marker.x).toBeCloseTo(rect.x, 6);
    expect(stripLayout(plan, rect, to).marker.x).toBeCloseTo(rect.x + rect.w, 6);
    const mid = from + (to - from) / 2;
    expect(stripLayout(plan, rect, mid).marker.x).toBeCloseTo(rect.x + rect.w / 2, 6);
    const l = stripLayout(plan, rect, mid);
    const running = plan.tasks.filter((k) => !k.milestone && k.start <= mid && mid < k.end).length;
    expect(l.rows.flatMap((r) => r.bars).filter((b) => b.active)).toHaveLength(running);
    expect(l.rows.flatMap((r) => r.bars).filter((b) => b.critical).length).toBe(plan.tasks.filter((k) => !k.milestone && k.critical).length);
  });

  it('folds trades beyond twelve rows into one summary row', () => {
    const p: FourDPlan = { ...plan, tasks: Array.from({ length: 20 }, (_, i) => ({ code: `T${i}`, name: `t${i}`, start: plan.window.from + i * DAY, end: plan.window.from + (i + 3) * DAY, critical: false, milestone: false, trade: `trade${i}`, elements: 1 })) };
    const g = stripGroups(p);
    expect(g).toHaveLength(MAX_STRIP_ROWS);
    expect(g[MAX_STRIP_ROWS - 1]!.label).toBe('Other');
    expect(g[MAX_STRIP_ROWS - 1]!.tasks).toHaveLength(20 - (MAX_STRIP_ROWS - 1));
    const l = stripLayout(p, rect, plan.window.from);
    expect(l.summarised).toBe(20 - (MAX_STRIP_ROWS - 1));
    expect(stripHeight(12, true, 7)).toBeLessThan(130);
  });
});

describe('storyboard frame dates', () => {
  const { from, to } = plan.window;
  it('week: every seven days from the start, ending on the last day', () => {
    const d = storyboardDates(plan, { kind: 'week' });
    expect(d[0]).toBe(from);
    expect(d[1]! - d[0]!).toBe(7 * DAY);
    expect(d[d.length - 1]).toBe(to);
    expect(d.length).toBe(Math.floor((to - from) / (7 * DAY)) + 1 + ((to - from) % (7 * DAY) > 0 ? 1 : 0));
  });
  it('month: the start, each first of the month, the end', () => {
    const d = storyboardDates(plan, { kind: 'month' });
    expect(d[0]).toBe(from);
    for (const t of d.slice(1, -1)) expect(new Date(t).getUTCDate()).toBe(1);
    expect(d[d.length - 1]).toBe(to);
    expect(d.every((t, i) => i === 0 || t > d[i - 1]!)).toBe(true);
  });
  it('milestone: one frame per milestone, in order', () => {
    const d = storyboardDates(plan, { kind: 'milestone' });
    expect(d).toEqual([...new Set(plan.milestones.map((m) => m.at))].sort((a, b) => a - b));
  });
  it('N: N frames spread from the start to the end; 1 is the last day', () => {
    const d = storyboardDates(plan, { kind: 'count', n: 5 });
    expect(d).toHaveLength(5);
    expect(d[0]).toBe(from);
    expect(d[4]).toBe(to);
    expect(storyboardDates(plan, { kind: 'count', n: 1 })).toEqual([to]);
  });
  it('parses the option', () => {
    expect(parseEvery('week')).toEqual({ kind: 'week' });
    expect(parseEvery('Month')).toEqual({ kind: 'month' });
    expect(parseEvery('milestone')).toEqual({ kind: 'milestone' });
    expect(parseEvery('8')).toEqual({ kind: 'count', n: 8 });
    expect(parseEvery(undefined)).toEqual({ kind: 'week' });
    expect(parseEvery('fortnight')).toBeNull();
    expect(parseEvery('0')).toBeNull();
  });
});

describe('captions', () => {
  it('names the date, the week and the top three activities with "+N more"', () => {
    const t = plan.window.from + 20 * DAY;
    const c = captionAt(plan, t);
    const running = plan.tasks.filter((k) => !k.milestone && k.start <= t && t < k.end && k.elements > 0);
    expect(c.title).toMatch(/^\d{4}-\d\d-\d\d {2}Week \d+$/);
    expect(c.lines.slice(0, 3)).toHaveLength(Math.min(3, running.length));
    if (running.length > 3) expect(c.lines[3]).toBe(`+${running.length - 3} more`);
    else expect(c.lines).toHaveLength(running.length);
  });
  it('says Complete at the end', () => {
    expect(captionAt({ ...plan, tasks: [] }, plan.window.to).lines).toEqual(['Complete']);
  });
});

describe('page layout', () => {
  it('fits a grid of columns by rows inside the page and splits the frames over pages', () => {
    const l = pageLayout({ page: 'A4', cols: 3, count: 20, legendH: 40 });
    expect(l.cols).toBe(3);
    expect(l.rows).toBeGreaterThanOrEqual(1);
    expect(l.perPage).toBe(l.cols * l.rows);
    expect(l.pages.length).toBe(Math.ceil(20 / l.perPage));
    expect(l.pages.flat().map((f) => f.index)).toEqual(Array.from({ length: 20 }, (_, i) => i));
    for (const f of l.pages.flat()) {
      expect(f.x).toBeGreaterThanOrEqual(l.margin);
      expect(f.x + f.w).toBeLessThanOrEqual(PAGE_POINTS.A4.w - l.margin + 1e-6);
      expect(f.captionY + l.captionH - 4).toBeLessThanOrEqual(l.legendY);
      expect(f.y).toBeGreaterThanOrEqual(l.margin + l.titleH);
    }
    expect(l.frameW / l.frameH).toBeCloseTo(16 / 9, 6);
  });
  it('A3 holds more frames than A4 at the same columns, and one frame still makes one page', () => {
    expect(pageLayout({ page: 'A3', cols: 4, count: 30, legendH: 40 }).perPage).toBeGreaterThan(pageLayout({ page: 'A4', cols: 4, count: 30, legendH: 40 }).perPage - 1);
    expect(pageLayout({ page: 'A4', cols: 3, count: 1, legendH: 40 }).pages).toHaveLength(1);
  });
});

describe('PDF assembly', () => {
  it('writes one landscape page per layout page with the title block, captions and the legend', async () => {
    const sb = planStoryboard(plan, { kind: 'count', n: 14 });
    const frames = sb.captions.map((caption) => ({ jpeg: JPEG, width: 960, height: 540, caption }));
    const { data, pages } = await buildStoryboardPdf(PDFLib, { project: 'Test tower', dataDate: '2027-01-20', generated: '2027-02-01', every: 'every 14 frames', page: 'A4', cols: 3, frames, legend: sb.legend });
    const doc = await PDFLib.PDFDocument.load(data);
    expect(doc.getPageCount()).toBe(pages);
    expect(pages).toBeGreaterThan(1);
    const { width, height } = doc.getPage(0).getSize();
    expect(width).toBeGreaterThan(height);
    expect(String.fromCharCode(...data.slice(0, 4))).toBe('%PDF');
    // pdf-lib compresses content streams: read them back through the page content
    const streams = doc.getPages().map((pg) => {
      const refs = pg.node.Contents();
      const arr = refs && 'asArray' in refs ? (refs as unknown as { asArray(): unknown[] }).asArray() : [refs];
      return arr.length;
    });
    expect(streams.every((n) => n >= 1)).toBe(true);
    expect(doc.getTitle()).toBe('Test tower 4D storyboard');
  });

  it('keeps the text in the content stream when it is read uncompressed', async () => {
    const sb = planStoryboard(plan, { kind: 'count', n: 3 });
    const frames = sb.captions.map((caption) => ({ jpeg: JPEG, width: 960, height: 540, caption }));
    const lib = PDFLib;
    const { data } = await buildStoryboardPdf(lib, { project: 'Tower', generated: '2027-02-01', page: 'A3', cols: 3, frames, legend: sb.legend });
    const doc = await PDFLib.PDFDocument.load(data);
    const { decodePDFRawStream } = PDFLib;
    const page = doc.getPage(0);
    const c = page.node.Contents() as unknown as { asArray?(): unknown[] };
    const parts = (c.asArray ? c.asArray() : [c]).map((r) => doc.context.lookup(r as never) as unknown as PDFLib.PDFRawStream);
    const raw = parts.map((s) => latin1(decodePDFRawStream(s).decode())).join('\n');
    // pdf-lib writes shown text as hex strings: decode them back to the words
    const content = [...raw.matchAll(/<([0-9A-Fa-f]+)> Tj/g)].map((m) => latin1(Uint8Array.from(m[1]!.match(/../g)!, (h) => parseInt(h, 16)))).join('\n');
    expect(content).toContain('Page 1 of 1');
    expect(content).toContain('Tower  4D storyboard');
    expect(content).toContain('Trades');
    expect(content).toContain('Active');
    expect(content).toContain(sb.captions[0]!.date);
    expect(content).toContain('Week');
  });

  it('turns characters outside WinAnsi into question marks', () => {
    expect(winAnsi('Gebäude 中文')).toBe('Gebäude ??');
  });
});
