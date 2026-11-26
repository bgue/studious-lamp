// The 4D storyboard: still frames of the film at chosen dates laid out in a grid on landscape pages with a title block, a caption per
// frame (date, week number, the top three active activities) and the colour legend once per page. This file is pure: the dates of the
// frames (`every`), the captions, the page maths and the PDF assembly with pdf-lib handed in (the browser loads it lazily, the
// xray-4d CLI imports it in node). Rendering the frames is the viewer's job (Recorder.stills); the layout is the same in both.

import { isoDate, isoWeek } from '../anim/fourd/live';
import { legendContent } from '../anim/fourd/legend';
import type { LegendContent, LegendEntry } from '../anim/fourd/legend';
import type { FourDPlan } from './types';

const DAY = 86400000;

export type Every = { kind: 'week' } | { kind: 'month' } | { kind: 'milestone' } | { kind: 'count'; n: number };
export const MAX_FRAMES = 200;

/** `week`, `month`, `milestone` or a whole number of frames (2 or more spread over the film; 1 is the last day). Null when it is none of them. */
export function parseEvery(text: string | undefined): Every | null {
  const t = (text ?? 'week').trim().toLowerCase();
  if (t === 'week' || t === 'month' || t === 'milestone') return { kind: t };
  if (/^\d+$/.test(t) && Number(t) >= 1) return { kind: 'count', n: Number(t) };
  return null;
}

/** The plan times (ms, increasing, inside the window) of the frames. The first frame is the start of the window, the last its end. */
export function storyboardDates(plan: FourDPlan, every: Every): number[] {
  const { from, to } = plan.window;
  const out: number[] = [];
  const clip = (a: number[]): number[] => [...new Set(a.filter((x) => x >= from && x <= to))].sort((a, b) => a - b);
  switch (every.kind) {
    case 'week':
      for (let t = from; t <= to && out.length < MAX_FRAMES; t += 7 * DAY) out.push(t);
      break;
    case 'month': {
      out.push(from);
      const d = new Date(from);
      let y = d.getUTCFullYear();
      let m = d.getUTCMonth() + 1;
      for (;;) {
        const t = Date.UTC(y, m, 1);
        if (t > to || out.length >= MAX_FRAMES) break;
        if (t > from) out.push(t);
        m++;
        if (m > 11) { m = 0; y++; }
      }
      break;
    }
    case 'milestone': {
      const ms = clip(plan.milestones.map((x) => x.at));
      if (ms.length) return ms.slice(0, MAX_FRAMES);
      return storyboardDates(plan, { kind: 'count', n: 6 });
    }
    case 'count': {
      const n = Math.min(MAX_FRAMES, Math.max(1, Math.round(every.n)));
      if (n === 1) return [to];
      for (let i = 0; i < n; i++) out.push(Math.round(from + ((to - from) * i) / (n - 1)));
      return clip(out);
    }
  }
  if (out[out.length - 1]! < to && out.length < MAX_FRAMES) out.push(to);
  return clip(out);
}

export interface FrameCaption {
  /** `2027-03-14` and the ISO week. */
  date: string;
  week: number;
  weekYear: number;
  /** First line: "2027-03-14  Week 10". */
  title: string;
  /** Up to three activity names (the ones with most elements), then "+N more". */
  lines: string[];
}

export const CAPTION_ACTIVITIES = 3;

export function captionAt(plan: FourDPlan, ms: number): FrameCaption {
  const wk = isoWeek(ms);
  const date = isoDate(ms);
  const running = plan.tasks.filter((k) => !k.milestone && k.start <= ms && ms < k.end && k.elements > 0).sort((a, b) => b.elements - a.elements || a.code.localeCompare(b.code));
  const lines = running.slice(0, CAPTION_ACTIVITIES).map((k) => k.name);
  if (running.length > CAPTION_ACTIVITIES) lines.push(`+${running.length - CAPTION_ACTIVITIES} more`);
  if (lines.length === 0) lines.push(ms >= plan.window.to ? 'Complete' : 'No work in the model');
  return { date, week: wk.week, weekYear: wk.year, title: `${date}  Week ${wk.week}`, lines };
}

// ---------------------------------------------------------------- page maths

export type PageSize = 'A3' | 'A4';
/** Landscape points. */
export const PAGE_POINTS: Record<PageSize, { w: number; h: number }> = { A4: { w: 841.89, h: 595.28 }, A3: { w: 1190.55, h: 841.89 } };

export interface PageLayoutInput {
  page: PageSize;
  cols: number;
  count: number;
  /** Frame width / height (default 16/9). */
  aspect?: number;
  /** Height of the legend block at the foot of a page. */
  legendH: number;
}

export interface PlacedFrame {
  /** Index into the list of frames. */
  index: number;
  /** Top left in points, y measured from the top of the page. */
  x: number;
  y: number;
  w: number;
  h: number;
  /** Top of the caption under the frame. */
  captionY: number;
}

export interface PageLayout {
  pageW: number;
  pageH: number;
  margin: number;
  titleH: number;
  cols: number;
  rows: number;
  perPage: number;
  pages: PlacedFrame[][];
  frameW: number;
  frameH: number;
  captionH: number;
  legendY: number;
}

export const MARGIN = 28;
export const TITLE_H = 50;
export const GAP = 10;
export const CAPTION_LINES = 1 + CAPTION_ACTIVITIES + 1;
export const CAPTION_LINE_H = 9.5;

export function pageLayout(inp: PageLayoutInput): PageLayout {
  const { w: pageW, h: pageH } = PAGE_POINTS[inp.page];
  const cols = Math.max(1, Math.min(8, Math.round(inp.cols)));
  const aspect = inp.aspect && inp.aspect > 0 ? inp.aspect : 16 / 9;
  const usableW = pageW - 2 * MARGIN;
  const frameW = (usableW - GAP * (cols - 1)) / cols;
  const frameH = frameW / aspect;
  const captionH = CAPTION_LINES * CAPTION_LINE_H + 4;
  const bodyTop = MARGIN + TITLE_H;
  const legendY = pageH - MARGIN - inp.legendH;
  const bodyH = legendY - 8 - bodyTop;
  const cellH = frameH + captionH;
  const rows = Math.max(1, Math.floor((bodyH + GAP) / (cellH + GAP)));
  const perPage = cols * rows;
  const pages: PlacedFrame[][] = [];
  for (let i = 0; i < Math.max(1, inp.count); i += perPage) {
    const page: PlacedFrame[] = [];
    for (let k = 0; k < perPage && i + k < inp.count; k++) {
      const c = k % cols;
      const r = Math.floor(k / cols);
      const y = bodyTop + r * (cellH + GAP);
      page.push({ index: i + k, x: MARGIN + c * (frameW + GAP), y, w: frameW, h: frameH, captionY: y + frameH + 3 });
    }
    pages.push(page);
  }
  return { pageW, pageH, margin: MARGIN, titleH: TITLE_H, cols, rows, perPage, pages, frameW, frameH, captionH, legendY };
}

// ---------------------------------------------------------------- the PDF

export interface StoryboardFrame {
  jpeg: Uint8Array;
  /** Frame size in pixels (for the aspect). */
  width: number;
  height: number;
  caption: FrameCaption;
}

export interface StoryboardInput {
  /** Project name for the title block. */
  project: string;
  dataDate?: string;
  /** Text for "Generated" (the caller gives the date: this function reads no clock). */
  generated: string;
  /** What was asked for, for the title block ("every week"). */
  every?: string;
  page: PageSize;
  cols: number;
  frames: StoryboardFrame[];
  legend: LegendContent;
}

/** Helvetica takes WinAnsi: anything else becomes "?". */
export function winAnsi(s: string): string {
  return s.replace(/[^ -~ -ÿ]/g, '?');
}

function hexRgb(h: string): [number, number, number] {
  const m = /^#?([0-9a-f]{6})$/i.exec(h);
  const n = m ? parseInt(m[1]!, 16) : 0x999999;
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}

type Measure = (text: string, size: number) => number;

/** Legend flow for the PDF: rows of entries wrapped to `width`. Pure; also gives the height the page layout reserves. */
export function legendRows(c: LegendContent, width: number, measure: Measure, size = 7.5): { rows: Array<Array<{ e: LegendEntry | null; text: string; x: number }>>; height: number } {
  const rows: Array<Array<{ e: LegendEntry | null; text: string; x: number }>> = [];
  const sw = 9;
  const gap = 10;
  const headW = (t: string): number => measure(t, size) + gap;
  const flow = (list: LegendEntry[], extra: string | null, head: string): void => {
    let row: Array<{ e: LegendEntry | null; text: string; x: number }> = [{ e: null, text: head, x: 0 }];
    let x = headW(head);
    for (const it of extra ? [...list, extra] : list) {
      const label = typeof it === 'string' ? it : it.label;
      const w = (typeof it === 'string' ? 0 : sw + 3) + measure(label, size);
      if (x + w > width && row.length > 1) {
        rows.push(row);
        row = [];
        x = headW(head);
      }
      row.push({ e: typeof it === 'string' ? null : it, text: label, x });
      x += w + gap;
    }
    rows.push(row);
  };
  if (c.trades.length) flow(c.trades, c.moreTrades > 0 ? `+${c.moreTrades} more` : null, 'Trades');
  flow(c.states, null, 'State');
  return { rows, height: rows.length * (size + 4) + 6 };
}

/** The PDF of a storyboard. `lib` is the pdf-lib module. */
export async function buildStoryboardPdf(lib: typeof import('pdf-lib'), inp: StoryboardInput): Promise<{ data: Uint8Array; pages: number }> {
  const doc = await lib.PDFDocument.create();
  const font = await doc.embedFont(lib.StandardFonts.Helvetica);
  const bold = await doc.embedFont(lib.StandardFonts.HelveticaBold);
  const wid: Measure = (t, s) => font.widthOfTextAtSize(winAnsi(t), s);
  const usableW = PAGE_POINTS[inp.page].w - 2 * MARGIN;
  const legend = legendRows(inp.legend, usableW, wid);
  const first = inp.frames[0];
  const aspect = first && first.height > 0 ? first.width / first.height : 16 / 9;
  const lay = pageLayout({ page: inp.page, cols: inp.cols, count: inp.frames.length, aspect, legendH: legend.height });
  doc.setTitle(winAnsi(`${inp.project} 4D storyboard`));
  doc.setProducer('X-ray viewer');
  doc.setCreator('X-ray viewer');
  const images = await Promise.all(inp.frames.map((f) => doc.embedJpg(f.jpeg)));
  const fit = (t: string, size: number, maxW: number, f = font): string => {
    let s = winAnsi(t);
    if (f.widthOfTextAtSize(s, size) <= maxW) return s;
    while (s.length > 1 && f.widthOfTextAtSize(s + '...', size) > maxW) s = s.slice(0, -1);
    return s + '...';
  };
  const total = lay.pages.length;
  lay.pages.forEach((frames, pi) => {
    const page = doc.addPage([lay.pageW, lay.pageH]);
    const Y = (top: number): number => lay.pageH - top; // top-down to pdf-lib's bottom-up
    page.drawText(fit(`${inp.project}  4D storyboard`, 16, usableW - 150, bold), { x: MARGIN, y: Y(MARGIN + 14), size: 16, font: bold, color: lib.rgb(0.06, 0.09, 0.13) });
    const sub = [inp.dataDate ? `Schedule data date ${inp.dataDate}` : 'No data date', `Generated ${inp.generated}`, `${inp.frames.length} frames${inp.every ? `, ${inp.every}` : ''}`].join('   |   ');
    page.drawText(fit(sub, 8.5, usableW - 150), { x: MARGIN, y: Y(MARGIN + 30), size: 8.5, font, color: lib.rgb(0.25, 0.3, 0.38) });
    const pn = `Page ${pi + 1} of ${total}`;
    page.drawText(pn, { x: lay.pageW - MARGIN - bold.widthOfTextAtSize(pn, 10), y: Y(MARGIN + 14), size: 10, font: bold, color: lib.rgb(0.06, 0.09, 0.13) });
    page.drawLine({ start: { x: MARGIN, y: Y(MARGIN + 40) }, end: { x: lay.pageW - MARGIN, y: Y(MARGIN + 40) }, thickness: 0.6, color: lib.rgb(0.7, 0.74, 0.8) });
    for (const pf of frames) {
      const fr = inp.frames[pf.index]!;
      page.drawImage(images[pf.index]!, { x: pf.x, y: Y(pf.y + pf.h), width: pf.w, height: pf.h });
      page.drawRectangle({ x: pf.x, y: Y(pf.y + pf.h), width: pf.w, height: pf.h, borderColor: lib.rgb(0.55, 0.6, 0.68), borderWidth: 0.5 });
      page.drawText(fit(fr.caption.title, 8, pf.w, bold), { x: pf.x, y: Y(pf.captionY + 8), size: 8, font: bold, color: lib.rgb(0.06, 0.09, 0.13) });
      fr.caption.lines.slice(0, CAPTION_ACTIVITIES + 1).forEach((l, k) => {
        page.drawText(fit(l, 7, pf.w), { x: pf.x, y: Y(pf.captionY + 8 + (k + 1) * CAPTION_LINE_H), size: 7, font, color: lib.rgb(0.2, 0.25, 0.32) });
      });
    }
    // the legend, once per page, at the foot
    let ly = lay.legendY + 3;
    for (const row of legend.rows) {
      for (const it of row) {
        let tx = MARGIN + it.x;
        if (it.e) {
          const [r, g, b] = hexRgb(it.e.colour);
          if (it.e.kind === 'outline') page.drawRectangle({ x: tx, y: Y(ly + 8), width: 9, height: 8, borderColor: lib.rgb(r, g, b), borderWidth: 1.5 });
          else page.drawRectangle({ x: tx, y: Y(ly + 8), width: 9, height: 8, color: lib.rgb(r, g, b), opacity: it.e.kind === 'ghost' ? 0.5 : 1, borderColor: lib.rgb(0.45, 0.5, 0.58), borderWidth: 0.4 });
          tx += 12;
        }
        page.drawText(winAnsi(it.text), { x: tx, y: Y(ly + 7), size: 7.5, font: it.e ? font : bold, color: it.e ? lib.rgb(0.1, 0.13, 0.18) : lib.rgb(0.4, 0.45, 0.52) });
      }
      ly += 11.5;
    }
  });
  return { data: await doc.save(), pages: total };
}

/** Everything but the rendering, for a plan: dates, captions and the legend (what the viewer and the CLI feed their frames into). */
export function planStoryboard(plan: FourDPlan, every: Every): { dates: number[]; captions: FrameCaption[]; legend: LegendContent } {
  const dates = storyboardDates(plan, every);
  return { dates, captions: dates.map((d) => captionAt(plan, d)), legend: legendContent(plan) };
}
