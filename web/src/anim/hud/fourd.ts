// The 4D part of the HUD (docs/design/4d-xer-animation.md section 5.5): while a `schedule4d` cue runs the layer draws the schedule date
// and ISO week (instead of the m:ss clock), % complete (planned, actual), the list of current activities with trade colour swatches,
// a small S-curve (planned vs actual), the milestone caption, a legend of the state colours and a data-date mark on the progress bar.
// Layout and drawing only; the numbers come from src/anim/fourd/live.ts. Draws with the same 2D calls as the rest of the layer.

import type { FourDView } from '../fourd/live';
import { AHEAD_RGB, BEHIND_RGB, CRITICAL_RGB, GLOW_RGB, toHex } from '../fourd/look';
import { legendContent, legendOn, stripOn } from '../fourd/legend';
import type { LegendContent } from '../fourd/legend';
import type { FourDPlan } from '../../schedule/types';
import { layoutLegend } from './legend';
import { paintStrip, stripGroups, stripHeight, stripLayout, stripRange } from './strip';
import { isoDate } from '../fourd/live';
import type { Rect } from './place';
import type { HudSettings } from './settings';
import { fitText } from './text';

type Ctx = CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D;

const FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif";
const PANEL = 'rgba(12, 16, 22, 0.8)';
const font = (size: number, bold = false): string => `${bold ? '700 ' : ''}${size}px ${FONT}`;
const PLANNED = '#8fb4ff';
const ACTUAL = '#ffb347';
const DATA_DATE = '#ffc447';

export interface FourDDescription {
  date: string;
  week: number;
  plannedPct: number;
  actualPct: number | null;
  /** The text that replaces the clock on the progress bar. */
  clockText: string;
  panel: Rect | null;
  activities: { rect: Rect; rows: Array<{ name: string; colour: string; elements: number }>; more: number; notInModel?: string } | null;
  curve: { rect: Rect; plannedPoints: number; actualPoints: number; marker: { x: number; y: number } } | null;
  milestone: { name: string; alpha: number; rect: Rect } | null;
  legend: { rect: Rect; entries: string[] } | null;
  /** The schedule strip along the bottom (additive). */
  strip?: { rect: Rect; rows: number; bars: number; marker: number } | null;
  dataDate: { x: number } | null;
}

export interface FourDLayoutInput {
  view: FourDView;
  /** The plan: gives the legend and the strip their content (absent: the legend falls back to what runs now, no strip). */
  plan?: FourDPlan;
  settings: HudSettings;
  W: number;
  H: number;
  margin: number;
  compact: boolean;
  /** Where the cue sits on the score, for the data-date mark on the progress bar (seconds) and the score length. */
  cueAt: number;
  cueDur: number;
  duration: number;
  /** Pixels the bottom-left corner is lifted by the progress bar and the scale bar. */
  bottomLift: number;
  /** The compass sits top right: keep the S-curve below it. */
  compass: boolean;
  progressBar: boolean;
}

export interface FourDLayout {
  desc: FourDDescription;
  /** Draw calls to run in order (the caller runs them with the rest of the layer's paint list). */
  paint: Array<() => void>;
  /** Drawn after the progress bar (the data-date mark sits on it). */
  late: Array<() => void>;
  /** Rectangles the labels keep clear of. */
  occupied: Rect[];
  /** Bottom of the top-left stack (the "+N more" chip of the labels goes under it). */
  topLeftBottom: number;
}

function rr(ctx: Ctx, x: number, y: number, w: number, h: number, r: number): void {
  const k = Math.max(0, Math.min(r, w / 2, h / 2));
  ctx.beginPath();
  ctx.moveTo(x + k, y);
  ctx.lineTo(x + w - k, y);
  ctx.arcTo(x + w, y, x + w, y + k, k);
  ctx.lineTo(x + w, y + h - k);
  ctx.arcTo(x + w, y + h, x + w - k, y + h, k);
  ctx.lineTo(x + k, y + h);
  ctx.arcTo(x, y + h, x, y + h - k, k);
  ctx.lineTo(x, y + k);
  ctx.arcTo(x, y, x + k, y, k);
  ctx.closePath();
}

export function clockTextOf(v: FourDView): string {
  return `${v.date}  W${String(v.week).padStart(2, '0')}`;
}

const fmtPct = (v: number): string => `${v.toFixed(1)} %`;

export function layoutFourD(ctx: Ctx, inp: FourDLayoutInput): FourDLayout {
  const { view: v, settings: st, W, H, margin, compact } = inp;
  const measure = (f: string) => (text: string): number => {
    ctx.font = f;
    return ctx.measureText(text).width;
  };
  const paint: Array<() => void> = [];
  const late: Array<() => void> = [];
  const occupied: Rect[] = [];
  const desc: FourDDescription = {
    date: v.date,
    week: v.week,
    plannedPct: v.plannedPct,
    actualPct: v.actualPct ?? null,
    clockText: clockTextOf(v),
    panel: null,
    activities: null,
    curve: null,
    milestone: null,
    legend: null,
    strip: null,
    dataDate: null,
  };
  let y = margin;
  const x = margin;

  // ---- date, week and % complete
  if (st.scheduleDate) {
    const dateSize = compact ? 17 : 22;
    const sub = 12;
    const pad = 9;
    const line1 = v.date;
    const line2 = `Week ${v.week} · ${v.weekYear}`;
    const line3 = v.actualPct !== undefined ? `Planned ${fmtPct(v.plannedPct)}   Actual ${fmtPct(v.actualPct)}` : `Planned ${fmtPct(v.plannedPct)}`;
    const w = Math.min(W - 2 * margin, Math.max(measure(font(dateSize, true))(line1), measure(font(sub))(line2), measure(font(sub))(line3)) + 2 * pad);
    const h = pad * 2 + dateSize * 1.15 + sub * 1.4 * 2;
    const rect: Rect = { x, y, w, h };
    desc.panel = rect;
    occupied.push(rect);
    paint.push(() => {
      ctx.fillStyle = PANEL;
      rr(ctx, rect.x, rect.y, rect.w, rect.h, 6);
      ctx.fill();
      let ty = rect.y + pad;
      ctx.font = font(dateSize, true);
      ctx.fillStyle = '#f8fafc';
      ctx.fillText(line1, rect.x + pad, ty);
      ty += dateSize * 1.15;
      ctx.font = font(sub);
      ctx.fillStyle = 'rgba(226, 232, 240, 0.92)';
      ctx.fillText(line2, rect.x + pad, ty);
      ty += sub * 1.4;
      ctx.fillStyle = 'rgba(241, 245, 249, 0.95)';
      ctx.fillText(line3, rect.x + pad, ty);
      // a thin planned bar under the panel text
      const bw = rect.w - 2 * pad;
      ctx.fillStyle = 'rgba(255, 255, 255, 0.2)';
      ctx.fillRect(rect.x + pad, rect.y + rect.h - 5, bw, 2);
      ctx.fillStyle = PLANNED;
      ctx.fillRect(rect.x + pad, rect.y + rect.h - 5, (bw * Math.min(100, v.plannedPct)) / 100, 2);
    });
    y = rect.y + rect.h + 6;
  }

  // ---- current activities
  if (st.activities && (v.activities.length > 0 || v.notInModel)) {
    const size = compact ? 11 : 12;
    const pad = 8;
    const rowH = size * 1.55;
    const maxW = Math.min(compact ? W - 2 * margin : 300, W - 2 * margin);
    const nm = measure(font(size));
    const cm = measure(font(size, true));
    const nowN = v.activities.length + v.moreActivities;
    const head = nowN > 0 ? `Now: ${nowN} ${nowN === 1 ? 'activity' : 'activities'}` : 'Now';
    const outText = v.notInModel ? `Also under way (not in the model): ${v.notInModel.names.join(', ')}${v.notInModel.more ? ` +${v.notInModel.more} more` : ''}` : '';
    const countW = v.activities.length ? Math.max(...v.activities.map((a) => cm(String(a.elements)))) : 0;
    const inner = maxW - 2 * pad - 16 - countW - 6;
    const rows = v.activities.map((a) => ({ name: fitText(nm, a.name, Math.max(30, inner)), colour: a.colour, elements: a.elements, critical: a.critical }));
    const outLines = outText ? [fitText(nm, outText, maxW - 2 * pad)] : [];
    const w = Math.min(maxW, Math.max(cm(head), ...rows.map((r) => nm(r.name) + 16 + countW + 6), ...outLines.map((l) => nm(l))) + 2 * pad);
    const h = pad * 2 + rowH * (rows.length + 1 + outLines.length);
    const rect: Rect = { x, y, w, h };
    desc.activities = { rect, rows: rows.map((r) => ({ name: r.name, colour: r.colour, elements: r.elements })), more: v.moreActivities, ...(outText ? { notInModel: outText } : {}) };
    occupied.push(rect);
    paint.push(() => {
      ctx.fillStyle = PANEL;
      rr(ctx, rect.x, rect.y, rect.w, rect.h, 6);
      ctx.fill();
      let ty = rect.y + pad;
      ctx.font = font(size, true);
      ctx.fillStyle = '#f8fafc';
      ctx.fillText(head, rect.x + pad, ty);
      ty += rowH;
      for (const r of rows) {
        ctx.fillStyle = r.colour;
        ctx.fillRect(rect.x + pad, ty + 1, 10, size - 1);
        if (r.critical) {
          ctx.strokeStyle = toHex(CRITICAL_RGB);
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.moveTo(rect.x + pad - 1, ty);
          ctx.lineTo(rect.x + pad + 11, ty);
          ctx.lineTo(rect.x + pad + 11, ty + size + 1);
          ctx.lineTo(rect.x + pad - 1, ty + size + 1);
          ctx.closePath();
          ctx.stroke();
        }
        ctx.font = font(size);
        ctx.fillStyle = 'rgba(241, 245, 249, 0.95)';
        ctx.fillText(r.name, rect.x + pad + 16, ty);
        ctx.font = font(size, true);
        ctx.fillStyle = 'rgba(180, 196, 220, 0.95)';
        ctx.fillText(String(r.elements), rect.x + rect.w - pad - cm(String(r.elements)), ty);
        ty += rowH;
      }
      ctx.font = font(size);
      ctx.fillStyle = 'rgba(180, 196, 220, 0.8)';
      for (const l of outLines) { ctx.fillText(l, rect.x + pad, ty); ty += rowH; }
    });
    y = rect.y + rect.h + 6;
  }
  const topLeftBottom = y;

  // ---- S-curve, top right (below the compass)
  if (st.sCurve && v.curve.length >= 2 && !(compact && W < 380)) {
    const cw = compact ? 110 : 160;
    const ch = compact ? 64 : 88;
    const pad = 6;
    const rect: Rect = { x: W - margin - cw, y: margin + (inp.compass ? 52 : 0), w: cw, h: ch };
    const gx = rect.x + pad;
    const gy = rect.y + 14;
    const gw = rect.w - 2 * pad;
    const gh = rect.h - 14 - pad;
    const t0 = v.window.from;
    const span = Math.max(1, v.window.to - t0);
    const px = (at: number): number => gx + ((at - t0) / span) * gw;
    const py = (f: number): number => gy + gh - Math.min(1, Math.max(0, f)) * gh;
    const actual = v.curve.filter((q) => q.actual !== undefined);
    const nowX = Math.min(gx + gw, Math.max(gx, px(v.planMs)));
    const nowF = interpolate(v.curve.map((q) => [q.at, q.planned] as const), v.planMs);
    const marker = { x: nowX, y: py(nowF) };
    desc.curve = { rect, plannedPoints: v.curve.length, actualPoints: actual.length, marker };
    occupied.push(rect);
    paint.push(() => {
      ctx.fillStyle = PANEL;
      rr(ctx, rect.x, rect.y, rect.w, rect.h, 6);
      ctx.fill();
      ctx.font = font(10, true);
      ctx.fillStyle = '#f8fafc';
      ctx.fillText('S-curve', rect.x + pad, rect.y + 3);
      ctx.fillStyle = PLANNED;
      ctx.fillRect(rect.x + rect.w - pad - 70, rect.y + 6, 8, 3);
      ctx.font = font(9);
      ctx.fillStyle = 'rgba(226, 232, 240, 0.9)';
      ctx.fillText('plan', rect.x + rect.w - pad - 58, rect.y + 3);
      if (actual.length) {
        ctx.fillStyle = ACTUAL;
        ctx.fillRect(rect.x + rect.w - pad - 32, rect.y + 6, 8, 3);
        ctx.fillStyle = 'rgba(226, 232, 240, 0.9)';
        ctx.fillText('actual', rect.x + rect.w - pad - 20, rect.y + 3);
      }
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.25)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(gx, gy + gh);
      ctx.lineTo(gx + gw, gy + gh);
      ctx.moveTo(gx, gy);
      ctx.lineTo(gx, gy + gh);
      ctx.stroke();
      ctx.strokeStyle = PLANNED;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      v.curve.forEach((q, i) => (i === 0 ? ctx.moveTo(px(q.at), py(q.planned)) : ctx.lineTo(px(q.at), py(q.planned))));
      ctx.stroke();
      if (actual.length) {
        ctx.strokeStyle = ACTUAL;
        ctx.beginPath();
        actual.forEach((q, i) => (i === 0 ? ctx.moveTo(px(q.at), py(q.actual!)) : ctx.lineTo(px(q.at), py(q.actual!))));
        ctx.stroke();
      }
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.7)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(nowX, gy);
      ctx.lineTo(nowX, gy + gh);
      ctx.stroke();
      ctx.fillStyle = '#ffffff';
      ctx.beginPath();
      ctx.arc(marker.x, marker.y, 2.5, 0, Math.PI * 2);
      ctx.fill();
    });
  }

  // ---- milestone caption, top centre
  if (st.milestones && v.milestone) {
    const size = compact ? 14 : 17;
    const pad = 12;
    const maxW = Math.min(520, W - 2 * margin);
    const text = fitText(measure(font(size, true)), v.milestone.name, maxW - 2 * pad - 16);
    const w = measure(font(size, true))(text) + 2 * pad + 16;
    const h = size * 1.3 + 2 * 8;
    const rect: Rect = { x: Math.round((W - w) / 2), y: margin + (compact ? 0 : 4), w, h };
    const alpha = v.milestone.alpha;
    desc.milestone = { name: v.milestone.name, alpha, rect };
    occupied.push(rect);
    paint.push(() => {
      ctx.globalAlpha = alpha;
      ctx.fillStyle = PANEL;
      rr(ctx, rect.x, rect.y, rect.w, rect.h, 6);
      ctx.fill();
      ctx.fillStyle = DATA_DATE;
      ctx.beginPath();
      ctx.moveTo(rect.x + pad, rect.y + rect.h / 2 - 5);
      ctx.lineTo(rect.x + pad + 5, rect.y + rect.h / 2);
      ctx.lineTo(rect.x + pad, rect.y + rect.h / 2 + 5);
      ctx.lineTo(rect.x + pad - 5, rect.y + rect.h / 2);
      ctx.closePath();
      ctx.fill();
      ctx.font = font(size, true);
      ctx.fillStyle = '#f8fafc';
      ctx.fillText(text, rect.x + pad + 14, rect.y + 8);
      ctx.globalAlpha = 1;
    });
  }

  // ---- schedule strip (full width, above the progress bar) and colour legend (bottom left, above the strip)
  const bottomEdge = H - inp.bottomLift - 6;
  let legendBottom = H - inp.bottomLift - 14;
  const plan = inp.plan;
  if (plan && stripOn(plan)) {
    const rowH = compact ? 4 : 7;
    const gs = stripGroups(plan);
    const h = stripHeight(gs.length, plan.milestones.some((m) => m.at >= stripRange(plan)[0] && m.at <= stripRange(plan)[1]), rowH);
    const rect: Rect = { x: margin, y: bottomEdge - h, w: Math.max(40, W - 2 * margin), h };
    if (gs.length > 0 && rect.y >= topLeftBottom) {
      const lay = stripLayout(plan, rect, v.planMs, { rowH });
      desc.strip = { rect, rows: lay.rows.length, bars: lay.rows.reduce((n, r) => n + r.bars.length, 0), marker: lay.marker.x };
      occupied.push({ x: rect.x - 4, y: rect.y - 2, w: rect.w + 8, h: rect.h + 4 });
      paint.push(() => paintStrip(ctx, lay, { from: isoDate(lay.from), to: isoDate(lay.to), now: v.date }));
      legendBottom = rect.y - 8;
    }
  }
  if (st.legend && (!plan || legendOn(plan))) {
    const content = plan ? legendContent(plan) : legendFromView(v);
    const maxW = compact ? W - 2 * margin : Math.min(W - 2 * margin, 460);
    const size = compact ? 10 : 11;
    let lay = layoutLegend(ctx, content, { x, bottom: legendBottom, maxW, size, headings: true });
    if (lay && lay.rect.y < topLeftBottom) lay = layoutLegend(ctx, content, { x, bottom: legendBottom, maxW, size, headings: false });
    if (lay && lay.rect.y >= topLeftBottom && lay.rect.y + lay.rect.h <= H) {
      desc.legend = { rect: lay.rect, entries: lay.entries };
      occupied.push(lay.rect);
      paint.push(lay.paint);
    }
  }

  // ---- data-date mark on the progress bar
  if (inp.progressBar && v.dataDate !== null && inp.duration > 0) {
    const sec = inp.cueAt + v.dataDate * inp.cueDur;
    const xx = Math.round((sec / inp.duration) * W);
    desc.dataDate = { x: xx };
    late.push(() => {
      ctx.fillStyle = DATA_DATE;
      ctx.fillRect(xx - 1, H - 11, 3, 11);
    });
  }

  return { desc, paint, late, occupied, topLeftBottom };
}

function interpolate(pts: ReadonlyArray<readonly [number, number]>, at: number): number {
  if (pts.length === 0) return 0;
  if (at <= pts[0]![0]) return pts[0]![1];
  const last = pts[pts.length - 1]!;
  if (at >= last[0]) return last[1];
  for (let i = 1; i < pts.length; i++) {
    const b = pts[i]!;
    if (at <= b[0]) {
      const a = pts[i - 1]!;
      return b[0] > a[0] ? a[1] + ((at - a[0]) / (b[0] - a[0])) * (b[1] - a[1]) : b[1];
    }
  }
  return last[1];
}

/** The legend without a plan: the active trades now, critical, behind and ahead (what the HUD drew before the plan was passed in). */
function legendFromView(v: FourDView): LegendContent {
  const states: LegendContent['states'] = [];
  if (v.hasCritical) states.push({ label: 'Critical', colour: toHex(CRITICAL_RGB), kind: 'outline' });
  if (v.hasActual) {
    states.push({ label: 'Behind', colour: toHex(BEHIND_RGB), kind: 'fill' });
    states.push({ label: 'Ahead', colour: toHex(AHEAD_RGB), kind: 'fill' });
  }
  states.unshift({ label: 'Active', colour: toHex(GLOW_RGB), kind: 'glow' });
  return { trades: v.trades.slice(0, 4).map((t) => ({ label: t.trade, colour: t.colour, kind: 'fill' as const })), moreTrades: 0, states };
}
