// The HUD layer: draws everything that shows over the 3D view while a score plays (captions, element labels, the hover card,
// the progress bar, the compass and the scale bar) into a 2D canvas context. One implementation for the screen (overlay.ts) and the
// video export (src/anim/hud.ts contract). It is stateless apart from the score: what it draws depends on `frame.t`, the size and
// the projection of the frame only, so a video that steps frame by frame gets the same picture as the screen.
//
// The layer reads the model through a HudSource (src/anim/hud/appSource.ts in the viewer, a fake in the tests).

import type { HudFrame, HudLayer } from '../hud';
import type { ElementRef, Score, V3 } from '../score';
import { formatValue, placeCard, propLabel } from '../../ui/hoverCard';
import type { CardContent } from '../../ui/hoverCard';
import { labelLines } from './fields';
import type { HudElement } from './fields';
import { nearestOnRect, placeLabels } from './place';
import type { LabelIn, Rect } from './place';
import type { HudSettings } from './settings';
import { fitText, wrapText } from './text';
import { activeCues, anyItemAt, chaptersOf, clock, niceScale, scaleText } from './timing';

type Ctx = CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D;

/** What the layer needs from the viewer. */
export interface HudSource {
  /** The element ids of a reference (resolved once per play by the score host). */
  elementIds(ref: ElementRef, key: string): number[];
  element(id: number): HudElement | null;
  /** [minx, miny, minz, maxx, maxy, maxz] in viewer coordinates. */
  bounds(id: number): [number, number, number, number, number, number] | null;
  /** The hover card content of an element (title, subtitle, rows). */
  card(id: number): CardContent | null;
  /** The camera now: the point it looks at, its right vector (unit) and the distance to the point. Null without a camera. */
  camera(): { focus: V3; right: V3; distance: number } | null;
  /** Degrees by which true north is turned counter-clockwise from project +Y, seen from above (0: project +Y is north). */
  northDeg(): number;
}

/** What the last draw put where (for tests and smoke checks). Rectangles are in CSS pixels of the frame. */
export interface HudDescription {
  t: number;
  caption: { title: string; text: string; alpha: number; rect: Rect } | null;
  labels: Array<{ id: number; lines: string[]; alpha: number; rect: Rect; ax: number; ay: number }>;
  more: number;
  hover: { id: number; alpha: number; rect: Rect } | null;
  progress: { fraction: number; chapters: number[]; rect: Rect } | null;
  compass: { rect: Rect; angle: number } | null;
  scale: { metres: number; rect: Rect } | null;
}

const FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif";
const ACCENT = '#3b9cff';
const PANEL = 'rgba(12, 16, 22, 0.8)';
const MAX_CANDIDATES = 40;
const MAX_PROJECTED = 6000;

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

const font = (size: number, bold = false): string => `${bold ? '700 ' : ''}${size}px ${FONT}`;

export class ScoreHudLayer implements HudLayer {
  private score: Score | null = null;
  private chapters: number[] = [];
  /** What the last draw drew. */
  last: HudDescription | null = null;

  constructor(
    private readonly src: HudSource,
    private readonly settings: () => HudSettings,
  ) {}

  setScore(score: Score | null): void {
    this.score = score;
    this.chapters = score ? chaptersOf(score) : [];
    this.last = null;
  }

  get hasScore(): boolean {
    return this.score !== null;
  }

  active(t: number): boolean {
    const s = this.score;
    if (!s) return false;
    const st = this.settings();
    return st.progress || st.compass || st.scaleBar || anyItemAt(s, t);
  }

  draw(ctx: Ctx, frame: HudFrame): void {
    const score = this.score;
    this.last = null;
    if (!score || frame.width <= 0 || frame.height <= 0) return;
    const st = this.settings();
    const W = frame.width;
    const H = frame.height;
    const t = frame.t;
    const compact = W < 520;
    const margin = Math.max(12, Math.round(W * 0.04));
    const measure = (f: string) => (text: string): number => {
      ctx.font = f;
      return ctx.measureText(text).width;
    };
    ctx.save();
    ctx.scale(frame.pixelRatio, frame.pixelRatio);
    ctx.textBaseline = 'top';
    ctx.lineJoin = 'round';
    const desc: HudDescription = { t, caption: null, labels: [], more: 0, hover: null, progress: null, compass: null, scale: null };
    const occupied: Rect[] = [];
    const paint: Array<() => void> = [];

    // ---- compass and scale bar geometry first: the caption keeps clear of them
    const cam = st.compass || st.scaleBar ? this.src.camera() : null;
    const barLift = st.progress ? 18 : 0;

    // ---- caption
    const caps = activeCues(score, 'caption', t);
    caps.sort((a, b) => a.cue.at - b.cue.at || a.index - b.index);
    const cap = caps[caps.length - 1];
    if (cap && (cap.cue.title || cap.cue.text)) {
      const titleSize = compact ? 16 : 17;
      const textSize = compact ? 15 : 15;
      const padX = 14;
      const padY = 9;
      const maxBox = Math.min(640, W - 2 * margin);
      const inner = Math.max(40, maxBox - 2 * padX - 3);
      const tm = measure(font(titleSize, true));
      const xm = measure(font(textSize));
      const titleLines = cap.cue.title ? wrapText(tm, cap.cue.title, inner) : [];
      const textLines = cap.cue.text ? wrapText(xm, cap.cue.text, inner) : [];
      if (titleLines.length + textLines.length > 0) {
        const titleH = titleLines.length * titleSize * 1.3;
        const textH = textLines.length * textSize * 1.4;
        const gapH = titleLines.length && textLines.length ? 3 : 0;
        const bw = Math.min(maxBox, Math.max(...titleLines.map(tm), ...textLines.map(xm), 20) + 2 * padX + 3);
        const bh = titleH + gapH + textH + 2 * padY;
        const x = Math.round((W - bw) / 2);
        let y: number;
        if (st.captionPosition === 'top') y = margin + (compact && st.compass ? 52 : 0);
        else y = H - Math.max(margin, Math.round(H * 0.07)) - barLift - (compact && st.scaleBar ? 22 : 0) - bh;
        y = Math.max(margin / 2, Math.round(y));
        const rect: Rect = { x, y, w: bw, h: bh };
        desc.caption = { title: cap.cue.title ?? '', text: cap.cue.text ?? '', alpha: cap.alpha, rect };
        occupied.push(rect);
        paint.push(() => {
          ctx.globalAlpha = cap.alpha;
          ctx.fillStyle = PANEL;
          rr(ctx, rect.x, rect.y, rect.w, rect.h, 6);
          ctx.fill();
          ctx.fillStyle = ACCENT;
          ctx.fillRect(rect.x, rect.y + 3, 3, rect.h - 6);
          let ty = rect.y + padY;
          ctx.fillStyle = '#f8fafc';
          ctx.font = font(titleSize, true);
          for (const l of titleLines) {
            ctx.fillText(l, rect.x + padX + 3, ty);
            ty += titleSize * 1.3;
          }
          ty += gapH;
          ctx.fillStyle = 'rgba(241, 245, 249, 0.92)';
          ctx.font = font(textSize);
          for (const l of textLines) {
            ctx.fillText(l, rect.x + padX + 3, ty);
            ty += textSize * 1.4;
          }
          ctx.globalAlpha = 1;
        });
      }
    }

    // ---- compass and scale rectangles
    if (st.compass && cam) {
      const r = 22;
      const cx = W - margin - r;
      const cy = margin + r;
      const north = this.northScreen(frame, cam);
      const rect: Rect = { x: cx - r, y: cy - r, w: 2 * r, h: 2 * r };
      desc.compass = { rect, angle: north };
      occupied.push(rect);
      paint.push(() => this.drawCompass(ctx, cx, cy, r, north));
    }
    if (st.scaleBar && cam) {
      const sc = this.scaleOf(frame, cam);
      if (sc) {
        const x = margin;
        const y = H - 14 - barLift;
        const rect: Rect = { x, y: y - 18, w: sc.px, h: 18 };
        desc.scale = { metres: sc.metres, rect };
        occupied.push(rect);
        paint.push(() => this.drawScale(ctx, x, y, sc.px, scaleText(sc.metres)));
      }
    }

    // ---- hover card
    const hovers = activeCues(score, 'hover', t);
    hovers.sort((a, b) => a.cue.at - b.cue.at || a.index - b.index);
    const hv = hovers[hovers.length - 1];
    if (hv) {
      const id = this.src.elementIds(hv.cue.elements, `${hv.index}:elements`)[0];
      const content = id === undefined ? null : this.src.card(id);
      const centre = id === undefined ? null : this.centreOf(id, frame);
      if (id !== undefined && content && centre) {
        const lay = this.layoutCard(ctx, content, W, margin);
        const pos = placeCard(centre, { w: lay.w, h: lay.h }, { w: W, h: H }, 34, 8);
        const rect: Rect = { x: pos.x, y: pos.y, w: lay.w, h: lay.h };
        desc.hover = { id, alpha: hv.alpha, rect };
        occupied.push(rect);
        paint.push(() => {
          ctx.globalAlpha = hv.alpha;
          this.leader(ctx, rect, centre.x, centre.y);
          this.drawCard(ctx, rect, lay);
          ctx.globalAlpha = 1;
        });
      }
    }

    // ---- labels
    const labelCues = activeCues(score, 'label', t);
    if (labelCues.length > 0) {
      const size = st.labelSize;
      const lm = measure(font(size));
      const bm = measure(font(size, true));
      type Cand = { id: number; x: number; y: number; d: number; fields: string[]; alpha: number };
      const cands: Cand[] = [];
      const seen = new Set<number>();
      let budget = MAX_PROJECTED;
      for (const lc of labelCues) {
        for (const id of this.src.elementIds(lc.cue.elements, `${lc.index}:elements`)) {
          if (seen.has(id)) continue;
          if (budget-- <= 0) break;
          const p = this.centreOf(id, frame);
          if (!p) continue;
          seen.add(id);
          cands.push({ id, x: p.x, y: p.y, d: Math.hypot(p.x - W / 2, p.y - H / 2), fields: lc.cue.fields, alpha: lc.alpha });
        }
      }
      cands.sort((a, b) => a.d - b.d || a.id - b.id);
      const top = cands.slice(0, MAX_CANDIDATES);
      const info = new Map<number, { lines: string[]; alpha: number }>();
      const items: LabelIn[] = [];
      const padX = 6;
      const padY = 4;
      for (const c of top) {
        const el = this.src.element(c.id);
        if (!el) continue;
        const lines = labelLines(el, c.fields).map((l, i) => fitText(i === 0 ? bm : lm, l, Math.min(240, W - 2 * margin - 2 * padX)));
        const w = Math.max(...lines.map((l, i) => (i === 0 ? bm(l) : lm(l)))) + 2 * padX;
        const h = lines.length * size * 1.3 + 2 * padY;
        info.set(c.id, { lines, alpha: c.alpha });
        items.push({ key: c.id, x: c.x, y: c.y, w, h });
      }
      const { placed, more } = placeLabels(items, { w: W, h: H }, occupied, { margin: Math.min(margin, 10) });
      desc.more = more + (cands.length - top.length);
      for (const p of placed) {
        const i = info.get(p.key)!;
        const rect: Rect = { x: p.x, y: p.y, w: p.w, h: p.h };
        desc.labels.push({ id: p.key, lines: i.lines, alpha: i.alpha, rect, ax: p.ax, ay: p.ay });
        paint.unshift(() => {
          ctx.globalAlpha = i.alpha;
          this.leader(ctx, rect, p.ax, p.ay);
          ctx.fillStyle = PANEL;
          rr(ctx, rect.x, rect.y, rect.w, rect.h, 4);
          ctx.fill();
          ctx.strokeStyle = 'rgba(59, 156, 255, 0.9)';
          ctx.lineWidth = 1;
          ctx.stroke();
          ctx.fillStyle = '#f8fafc';
          let ty = rect.y + padY;
          i.lines.forEach((l, n) => {
            ctx.font = font(size, n === 0);
            ctx.fillStyle = n === 0 ? '#f8fafc' : 'rgba(226, 232, 240, 0.92)';
            ctx.fillText(l, rect.x + padX, ty + size * 0.15);
            ty += size * 1.3;
          });
          ctx.globalAlpha = 1;
        });
      }
      if (desc.more > 0) {
        const text = `+${desc.more} more`;
        const alpha = Math.max(...labelCues.map((l) => l.alpha));
        paint.push(() => {
          ctx.globalAlpha = alpha;
          ctx.font = font(11);
          const w = ctx.measureText(text).width + 12;
          ctx.fillStyle = PANEL;
          rr(ctx, margin, margin, w, 20, 10);
          ctx.fill();
          ctx.fillStyle = '#f8fafc';
          ctx.fillText(text, margin + 6, margin + 4);
          ctx.globalAlpha = 1;
        });
      }
    }

    // ---- progress bar
    if (st.progress && frame.duration > 0) {
      const f = Math.min(1, Math.max(0, t / frame.duration));
      const rect: Rect = { x: 0, y: H - 3, w: W, h: 3 };
      desc.progress = { fraction: f, chapters: this.chapters, rect };
      paint.push(() => {
        ctx.fillStyle = 'rgba(255, 255, 255, 0.28)';
        ctx.fillRect(0, H - 3, W, 3);
        ctx.fillStyle = ACCENT;
        ctx.fillRect(0, H - 3, W * f, 3);
        ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
        for (const c of this.chapters) {
          if (c <= 0 || c >= frame.duration) continue;
          ctx.fillRect(Math.round((c / frame.duration) * W) - 1, H - 8, 2, 8);
        }
        const text = `${clock(t)} / ${clock(frame.duration)}`;
        ctx.font = font(11);
        const w = ctx.measureText(text).width + 10;
        ctx.fillStyle = 'rgba(12, 16, 22, 0.6)';
        // bottom left: the bottom right is where the gizmo and the pointer buttons sit
        rr(ctx, 6, H - 24, w, 15, 4);
        ctx.fill();
        ctx.fillStyle = '#f1f5f9';
        ctx.fillText(text, 11, H - 22);
      });
    }

    // labels were put in front with unshift (they draw first, under the caption and the card)
    for (const p of paint) p();
    ctx.restore();
    this.last = desc;
  }

  // ---------------------------------------------------------------- geometry

  private centreOf(id: number, frame: HudFrame): { x: number; y: number } | null {
    const b = this.src.bounds(id);
    if (!b) return null;
    return frame.project([(b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2]);
  }

  /** Screen angle (radians, canvas axes: 0 right, clockwise positive) of north at the focus point. */
  private northScreen(frame: HudFrame, cam: { focus: V3; distance: number }): number {
    const r = (this.src.northDeg() * Math.PI) / 180;
    // Project north is (-sin r, cos r) in IFC X, Y; the viewer frame has x = X, z = -Y.
    const d = Math.max(cam.distance * 0.1, 1e-6);
    const a = frame.project(cam.focus);
    const b = frame.project([cam.focus[0] - Math.sin(r) * d, cam.focus[1], cam.focus[2] - Math.cos(r) * d]);
    if (!a || !b || Math.hypot(b.x - a.x, b.y - a.y) < 1e-3) return -Math.PI / 2;
    return Math.atan2(b.y - a.y, b.x - a.x);
  }

  private scaleOf(frame: HudFrame, cam: { focus: V3; right: V3; distance: number }): { metres: number; px: number } | null {
    const d = Math.max(cam.distance * 0.1, 1e-6);
    const a = frame.project(cam.focus);
    const b = frame.project([cam.focus[0] + cam.right[0] * d, cam.focus[1] + cam.right[1] * d, cam.focus[2] + cam.right[2] * d]);
    if (!a || !b) return null;
    const ppm = Math.hypot(b.x - a.x, b.y - a.y) / d;
    return niceScale(ppm);
  }

  // ---------------------------------------------------------------- drawing

  private leader(ctx: Ctx, rect: Rect, ax: number, ay: number): void {
    const n = nearestOnRect(rect, ax, ay);
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.85)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(n.x, n.y);
    ctx.lineTo(ax, ay);
    ctx.stroke();
    ctx.fillStyle = ACCENT;
    ctx.beginPath();
    ctx.arc(ax, ay, 3, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = '#ffffff';
    ctx.stroke();
  }

  private layoutCard(ctx: Ctx, c: CardContent, W: number, margin: number): { w: number; h: number; title: string; sub: string; rows: string[] } {
    const maxW = Math.min(300, W - 2 * margin);
    const inner = maxW - 20;
    const m = (f: string) => (s: string): number => {
      ctx.font = f;
      return ctx.measureText(s).width;
    };
    const title = fitText(m(font(13, true)), c.title, inner);
    const sub = c.subtitle ? fitText(m(font(11.5)), c.subtitle, inner) : '';
    const rm = m(font(11.5));
    const rows = c.rows.map(([k, v]) => fitText(rm, `${propLabel(k)}: ${formatValue(v)}`, inner));
    const w = Math.min(maxW, Math.max(140, m(font(13, true))(title), sub ? rm(sub) : 0, ...rows.map(rm)) + 20);
    const h = 10 + 17 + (sub ? 15 : 0) + rows.length * 15 + (rows.length ? 4 : 0) + 8;
    return { w, h, title, sub, rows };
  }

  private drawCard(ctx: Ctx, r: Rect, lay: { title: string; sub: string; rows: string[] }): void {
    ctx.fillStyle = 'rgba(20, 24, 32, 0.94)';
    rr(ctx, r.x, r.y, r.w, r.h, 6);
    ctx.fill();
    ctx.strokeStyle = 'rgba(120, 140, 170, 0.8)';
    ctx.lineWidth = 1;
    ctx.stroke();
    let y = r.y + 10;
    ctx.font = font(13, true);
    ctx.fillStyle = '#ffffff';
    ctx.fillText(lay.title, r.x + 10, y);
    y += 17;
    if (lay.sub) {
      ctx.font = font(11.5);
      ctx.fillStyle = 'rgba(160, 180, 205, 0.95)';
      ctx.fillText(lay.sub, r.x + 10, y);
      y += 15;
    }
    y += lay.rows.length ? 4 : 0;
    ctx.font = font(11.5);
    ctx.fillStyle = 'rgba(226, 232, 240, 0.95)';
    for (const row of lay.rows) {
      ctx.fillText(row, r.x + 10, y);
      y += 15;
    }
  }

  private drawCompass(ctx: Ctx, cx: number, cy: number, r: number, angle: number): void {
    ctx.fillStyle = 'rgba(12, 16, 22, 0.6)';
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.fill();
    const ux = Math.cos(angle);
    const uy = Math.sin(angle);
    const tip = r - 7;
    ctx.fillStyle = '#ef4444';
    ctx.beginPath();
    ctx.moveTo(cx + ux * tip, cy + uy * tip);
    ctx.lineTo(cx - uy * 5 - ux * 2, cy + ux * 5 - uy * 2);
    ctx.lineTo(cx + uy * 5 - ux * 2, cy - ux * 5 - uy * 2);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = 'rgba(241, 245, 249, 0.9)';
    ctx.beginPath();
    ctx.moveTo(cx - ux * tip * 0.7, cy - uy * tip * 0.7);
    ctx.lineTo(cx - uy * 4 - ux * 2, cy + ux * 4 - uy * 2);
    ctx.lineTo(cx + uy * 4 - ux * 2, cy - ux * 4 - uy * 2);
    ctx.closePath();
    ctx.fill();
    ctx.font = font(11, true);
    ctx.fillStyle = '#ffffff';
    ctx.fillText('N', cx + ux * (r - 3) - 4, cy + uy * (r - 3) - 6);
  }

  private drawScale(ctx: Ctx, x: number, y: number, px: number, text: string): void {
    ctx.fillStyle = 'rgba(12, 16, 22, 0.6)';
    rr(ctx, x - 4, y - 20, Math.max(px, 40) + 8, 24, 4);
    ctx.fill();
    ctx.strokeStyle = '#f8fafc';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(x, y - 4);
    ctx.lineTo(x, y);
    ctx.lineTo(x + px, y);
    ctx.lineTo(x + px, y - 4);
    ctx.stroke();
    ctx.font = font(11);
    ctx.fillStyle = '#f8fafc';
    ctx.fillText(text, x + 1, y - 17);
  }
}
