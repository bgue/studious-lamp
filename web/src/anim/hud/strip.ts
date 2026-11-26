// The schedule strip of the 4D HUD: a thin Gantt band along the bottom with the film's date range, the activities as bars grouped by
// trade (at most MAX_STRIP_ROWS rows, the rest summarised in one row), critical activities emphasised, milestones as diamonds, the
// current date as a moving marker and the running bars highlighted. `stripLayout` is pure geometry (tested); `drawStrip` paints it with
// the plain 2D calls the rest of the HUD uses. Fixed light-on-dark colours: the same on screen, in a video and in the storyboard.

import type { FourDPlan } from '../../schedule/types';
import { tradeColour } from '../fourd/look';
import type { Rect } from './place';

type Ctx = CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D;

export const MAX_STRIP_ROWS = 12;
const OTHER = 'Other';

export interface StripBar {
  code: string;
  x: number;
  w: number;
  critical: boolean;
  active: boolean;
}

export interface StripRow {
  label: string;
  colour: string;
  /** Activities in the row. */
  count: number;
  y: number;
  bars: StripBar[];
}

export interface StripLayout {
  rect: Rect;
  /** x range of the date axis (CSS px), the label column excluded. */
  axis: { x: number; w: number };
  rows: StripRow[];
  /** Summarised rows (trades past the row limit) went into the last row. */
  summarised: number;
  milestones: Array<{ x: number; y: number; name: string }>;
  /** The current date marker, x in CSS px. */
  marker: { x: number };
  from: number;
  to: number;
  rowH: number;
}

export interface StripOptions {
  /** Row height in px (default 7; the phone layout passes 4). */
  rowH?: number;
  /** Width of the label column; 0 draws no labels (default 0: the band is the thin version). */
  labelW?: number;
  maxRows?: number;
}

/** The height a strip of `rows` trade rows (and a milestone row) takes. */
export function stripHeight(rows: number, hasMilestones: boolean, rowH: number): number {
  return 12 + (hasMilestones ? rowH + 3 : 0) + rows * (rowH + 1) + 3;
}

/** The rows a plan's strip has, before geometry: trades by first start, extra trades folded into "Other". */
export function stripGroups(plan: FourDPlan, maxRows = MAX_STRIP_ROWS): Array<{ label: string; colour: string; tasks: FourDPlan['tasks']; folded: number }> {
  const by = new Map<string, FourDPlan['tasks']>();
  for (const k of plan.tasks) {
    if (k.milestone || k.end < plan.window.from || k.start > plan.window.to) continue;
    const key = k.trade ?? 'Work';
    if (!by.has(key)) by.set(key, []);
    by.get(key)!.push(k);
  }
  const groups = [...by.entries()]
    .map(([label, tasks]) => ({ label, tasks, first: Math.min(...tasks.map((t) => t.start)) }))
    .sort((a, b) => a.first - b.first || a.label.localeCompare(b.label));
  const out = groups.slice(0, Math.max(1, maxRows)).map((g) => ({ label: g.label, colour: tradeColour(g.label === 'Work' ? undefined : g.label, plan.style.colours), tasks: g.tasks, folded: 0 }));
  if (groups.length > maxRows) {
    const rest = groups.slice(maxRows - 1);
    out.length = maxRows - 1;
    out.push({ label: OTHER, colour: '#94a3b8', tasks: rest.flatMap((g) => g.tasks), folded: rest.length });
  }
  return out;
}

/** The date range of the strip: the plan window, ending at the last activity and its milestones (a finale is film time after it, not plan time). */
export function stripRange(plan: FourDPlan): [number, number] {
  const from = plan.window.from;
  const ends = [...plan.tasks.filter((k) => k.end >= from && k.start <= plan.window.to).map((k) => k.end), ...plan.milestones.map((m) => m.at)];
  const last = ends.length ? Math.min(plan.window.to, Math.max(...ends)) : plan.window.to;
  return [from, Math.max(from + 1, last)];
}

/** The strip's geometry in `rect` for plan time `planMs`. */
export function stripLayout(plan: FourDPlan, rect: Rect, planMs: number, opts: StripOptions = {}): StripLayout {
  const rowH = opts.rowH ?? 7;
  const labelW = opts.labelW ?? 0;
  const groups = stripGroups(plan, opts.maxRows ?? MAX_STRIP_ROWS);
  const [from, to] = stripRange(plan);
  const axis = { x: rect.x + labelW, w: Math.max(1, rect.w - labelW) };
  const px = (ms: number): number => axis.x + (Math.min(to, Math.max(from, ms)) - from) / (to - from) * axis.w;
  const ms = plan.milestones.filter((m) => m.at >= from && m.at <= to);
  let y = rect.y + 12;
  const milestones: StripLayout['milestones'] = [];
  if (ms.length) {
    for (const m of ms) milestones.push({ x: px(m.at), y: y + rowH / 2, name: m.name });
    y += rowH + 3;
  }
  const rows: StripRow[] = groups.map((g) => {
    const row: StripRow = {
      label: g.label,
      colour: g.colour,
      count: g.tasks.length,
      y,
      bars: g.tasks
        .slice()
        .sort((a, b) => a.start - b.start || a.code.localeCompare(b.code))
        .map((k) => {
          const x0 = px(k.start);
          const x1 = px(k.end);
          return { code: k.code, x: x0, w: Math.max(1.5, x1 - x0), critical: k.critical, active: k.start <= planMs && planMs < k.end };
        }),
    };
    y += rowH + 1;
    return row;
  });
  return { rect, axis, rows, summarised: groups.reduce((n, g) => n + g.folded, 0), milestones, marker: { x: px(planMs) }, from, to, rowH };
}

const FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif";
const PANEL = 'rgba(12, 16, 22, 0.82)';

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

export function paintStrip(ctx: Ctx, s: StripLayout, dateLabels: { from: string; to: string; now: string }): void {
  const r = s.rect;
  ctx.fillStyle = PANEL;
  rr(ctx, r.x - 4, r.y - 2, r.w + 8, r.h + 4, 5);
  ctx.fill();
  ctx.font = `9px ${FONT}`;
  ctx.fillStyle = 'rgba(203, 213, 225, 0.9)';
  ctx.fillText(dateLabels.from, s.axis.x, r.y + 1);
  const toW = ctx.measureText(dateLabels.to).width;
  ctx.fillText(dateLabels.to, s.axis.x + s.axis.w - toW, r.y + 1);
  const nowW = ctx.measureText(dateLabels.now).width;
  const nx = Math.min(s.axis.x + s.axis.w - toW - nowW - 8, Math.max(s.axis.x + ctx.measureText(dateLabels.from).width + 8, s.marker.x - nowW / 2));
  if (nx + nowW < s.axis.x + s.axis.w - toW - 4) {
    ctx.fillStyle = '#ffffff';
    ctx.fillText(dateLabels.now, nx, r.y + 1);
  }
  const h = s.rowH;
  for (const row of s.rows) {
    ctx.fillStyle = 'rgba(255, 255, 255, 0.07)';
    ctx.fillRect(s.axis.x, row.y, s.axis.w, h);
    for (const b of row.bars) {
      ctx.globalAlpha = b.active ? 1 : 0.45;
      ctx.fillStyle = row.colour;
      ctx.fillRect(b.x, row.y + 1, b.w, h - 2);
      if (b.critical) {
        ctx.fillStyle = '#ff2d2d';
        ctx.fillRect(b.x, row.y, b.w, 1.5);
        ctx.fillRect(b.x, row.y + h - 1.5, b.w, 1.5);
      }
      if (b.active) {
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(b.x, row.y, b.w, 1);
      }
    }
    ctx.globalAlpha = 1;
  }
  ctx.fillStyle = '#ffc447';
  for (const m of s.milestones) {
    ctx.beginPath();
    ctx.moveTo(m.x, m.y - h / 2 - 1);
    ctx.lineTo(m.x + h / 2 + 1, m.y);
    ctx.lineTo(m.x, m.y + h / 2 + 1);
    ctx.lineTo(m.x - h / 2 - 1, m.y);
    ctx.closePath();
    ctx.fill();
  }
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(Math.round(s.marker.x) - 1, r.y + 9, 2, r.h - 9);
  ctx.beginPath();
  ctx.moveTo(s.marker.x - 3, r.y + 8);
  ctx.lineTo(s.marker.x + 3, r.y + 8);
  ctx.lineTo(s.marker.x, r.y + 11.5);
  ctx.closePath();
  ctx.fill();
}
