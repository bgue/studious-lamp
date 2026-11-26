// The colour legend of the 4D HUD: trade colours of the film and the state key in a compact panel, wrapped to the width it is given.
// Fixed light-on-dark colours (independent of the viewer theme, so a video looks the same). `layoutLegend` measures and returns the
// rectangle and a paint call; the caller decides where it goes (bottom left, above the strip) and drops it when it does not fit.

import type { LegendContent, LegendEntry } from '../fourd/legend';
import type { Rect } from './place';

type Ctx = CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D;

const FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif";
const PANEL = 'rgba(12, 16, 22, 0.86)';
const font = (size: number, bold = false): string => `${bold ? '700 ' : ''}${size}px ${FONT}`;

export interface LegendLayout {
  rect: Rect;
  /** Labels in order (trades, then states). */
  entries: string[];
  paint(): void;
}

interface Placed {
  e: LegendEntry | null;
  text: string;
  head: boolean;
  x: number;
  y: number;
}

/**
 * Lay the legend out with its bottom left corner at (x, bottom), at most `maxW` wide. `headings`: "Trades" and "State" lead their rows;
 * without them (the compact form) the entries run on as one flow.
 */
export function layoutLegend(ctx: Ctx, c: LegendContent, o: { x: number; bottom: number; maxW: number; size: number; headings: boolean; compactStates?: boolean }): LegendLayout | null {
  const size = o.size;
  const pad = 6;
  const sw = 10;
  const gap = 9;
  const rowH = Math.round(size * 1.45);
  ctx.font = font(size);
  const tw = (t: string): number => ctx.measureText(t).width;
  const inner = Math.max(40, o.maxW - 2 * pad);
  const items: Placed[] = [];
  let y = pad;
  let widest = 0;
  const flow = (list: LegendEntry[], extra: string | null, head: string | null): void => {
    let cx = 0;
    if (head) {
      ctx.font = font(size - 1, true);
      items.push({ e: null, text: head, head: true, x: 0, y });
      cx = tw(head) + gap;
      ctx.font = font(size);
    }
    const all: Array<LegendEntry | string> = extra ? [...list, extra] : list;
    for (const it of all) {
      const label = typeof it === 'string' ? it : it.label;
      const w = (typeof it === 'string' ? 0 : sw + 4) + tw(label);
      if (cx > 0 && cx + w > inner) {
        y += rowH;
        cx = o.headings && head ? tw(head) + gap : 0;
      }
      items.push({ e: typeof it === 'string' ? null : it, text: label, head: false, x: cx, y });
      widest = Math.max(widest, cx + w);
      cx += w + gap;
    }
    widest = Math.max(widest, cx - gap);
    y += rowH;
  };
  const more = c.moreTrades > 0 ? `+${c.moreTrades} more` : null;
  if (o.headings) {
    if (c.trades.length) flow(c.trades, more, 'Trades');
    flow(c.states, null, 'State');
  } else {
    flow([...c.trades, ...c.states], more, null);
  }
  const w = Math.min(o.maxW, Math.ceil(widest) + 2 * pad);
  const h = y - (rowH - size) + pad;
  const rect: Rect = { x: o.x, y: o.bottom - h, w, h };
  if (rect.y < 0) return null;
  const entries = [...c.trades, ...c.states].map((e) => e.label);
  const paint = (): void => {
    ctx.fillStyle = PANEL;
    ctx.beginPath();
    const k = 5;
    ctx.moveTo(rect.x + k, rect.y);
    ctx.lineTo(rect.x + rect.w - k, rect.y);
    ctx.arcTo(rect.x + rect.w, rect.y, rect.x + rect.w, rect.y + k, k);
    ctx.lineTo(rect.x + rect.w, rect.y + rect.h - k);
    ctx.arcTo(rect.x + rect.w, rect.y + rect.h, rect.x + rect.w - k, rect.y + rect.h, k);
    ctx.lineTo(rect.x + k, rect.y + rect.h);
    ctx.arcTo(rect.x, rect.y + rect.h, rect.x, rect.y + rect.h - k, k);
    ctx.lineTo(rect.x, rect.y + k);
    ctx.arcTo(rect.x, rect.y, rect.x + k, rect.y, k);
    ctx.closePath();
    ctx.fill();
    for (const it of items) {
      const ix = rect.x + pad + it.x;
      const iy = rect.y + it.y;
      if (it.head) {
        ctx.font = font(size - 1, true);
        ctx.fillStyle = 'rgba(148, 163, 184, 0.95)';
        ctx.fillText(it.text, ix, iy + 1);
        continue;
      }
      let tx = ix;
      if (it.e) {
        paintSwatch(ctx, it.e, ix, iy + 1, sw, size - 2);
        tx = ix + sw + 4;
      }
      ctx.font = font(size);
      ctx.fillStyle = it.e ? 'rgba(241, 245, 249, 0.96)' : 'rgba(148, 163, 184, 0.95)';
      ctx.fillText(it.text, tx, iy);
    }
  };
  return { rect, entries, paint };
}

/** One swatch: a fill, a glow (fill with a bright edge), an outline or a faint ghost. Plain rectangles only. */
export function paintSwatch(ctx: Ctx, e: LegendEntry, x: number, y: number, w: number, h: number): void {
  if (e.kind === 'outline') {
    ctx.fillStyle = 'rgba(255, 255, 255, 0.12)';
    ctx.fillRect(x, y, w, h);
    ctx.fillStyle = e.colour;
    ctx.fillRect(x, y, w, 2);
    ctx.fillRect(x, y + h - 2, w, 2);
    ctx.fillRect(x, y, 2, h);
    ctx.fillRect(x + w - 2, y, 2, h);
    return;
  }
  if (e.kind === 'ghost') {
    ctx.globalAlpha = 0.5;
    ctx.fillStyle = e.colour;
    ctx.fillRect(x, y, w, h);
    ctx.globalAlpha = 1;
    return;
  }
  ctx.fillStyle = e.colour;
  ctx.fillRect(x, y, w, h);
  if (e.kind === 'glow') {
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(x, y, w, 1.5);
  }
}
