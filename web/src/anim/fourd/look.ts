// What an element looks like in each 4D state: pure mapping from (state, where in its interval, the plan's style) to a Look the viewer
// applies. Trade colours come from style.colours, else a default palette by trade name.

import type { ElementState, FourDStyle, PlanTask } from '../../schedule/types';
import { S_ACTIVE, S_AHEAD, S_BEHIND, S_COMPLETE, S_EXISTING, S_FUTURE, S_REMOVED, STATE_NAMES } from './timeline';

export type RGB = [number, number, number];

/** Alpha of an unbuilt element in a ghost view. */
export const GHOST_ALPHA = 0.06;
/** Fade in / out and the green flash last this part of the interval, but at most FADE_VIDEO_S of video. */
export const FADE_FRACTION = 0.1;
export const FADE_VIDEO_S = 0.6;
export const TINT_ACTIVE = 0.7;
export const TINT_EXISTING = 0.22;
export const TINT_BEHIND = 0.6;
export const TINT_REMOVED = 0.8;
export const TINT_AHEAD = 0.8;
export const EXISTING_GREY: RGB = [0.72, 0.72, 0.72];
export const BEHIND_RGB: RGB = hex('#d64545');
export const AHEAD_RGB: RGB = hex('#2fbf5b');
export const REMOVED_RGB: RGB = hex('#e5484d');
/** Edge glow colours: active work, and critical work (red). */
export const GLOW_RGB: RGB = hex('#ffc447');
export const CRITICAL_RGB: RGB = hex('#ff2d2d');

export function hex(h: string): RGB {
  const m = /^#?([0-9a-f]{6})$/i.exec(h.trim());
  if (!m) return [0.8, 0.8, 0.8];
  const n = parseInt(m[1]!, 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}

export function toHex(c: readonly number[]): string {
  const b = (v: number): string => Math.round(Math.min(1, Math.max(0, v)) * 255).toString(16).padStart(2, '0');
  return `#${b(c[0]!)}${b(c[1]!)}${b(c[2]!)}`;
}

/** Default colours by trade keyword (first match wins), then a rotating palette by the trade text. */
const TRADE_WORDS: Array<[RegExp, string]> = [
  [/steel|struct.*steel|frame/i, '#3b82f6'],
  [/conc|struct|slab|found|core|pour/i, '#f59e0b'],
  [/mason|brick|block/i, '#b45309'],
  [/roof/i, '#f97316'],
  [/facade|envelope|clad|curtain|glaz|window|door/i, '#06b6d4'],
  [/elec|power|lighting/i, '#eab308'],
  [/plumb|water|drain|sanit/i, '#0ea5e9'],
  [/mep|hvac|mech|duct|pipe|fire/i, '#22c55e'],
  [/fit|interior|finish|partition|ceiling|floor/i, '#a855f7'],
  [/site|civil|ground|earth|landscape/i, '#84cc16'],
];
const ROTATING = ['#38bdf8', '#f472b6', '#facc15', '#34d399', '#fb923c', '#a78bfa', '#2dd4bf', '#f87171'];

export function tradeColour(trade: string | undefined, colours: Readonly<Record<string, string>> = {}): string {
  if (!trade) return '#f59e0b';
  const own = colours[trade] ?? colours[trade.toLowerCase()];
  if (own) return own;
  for (const [re, c] of TRADE_WORDS) if (re.test(trade)) return c;
  let h = 0;
  for (let i = 0; i < trade.length; i++) h = (h * 31 + trade.charCodeAt(i)) | 0;
  return ROTATING[Math.abs(h) % ROTATING.length]!;
}

export interface Look {
  /** Not drawn at all. */
  hidden: boolean;
  /** 1 = none. A hidden look has alpha 1 (it is hidden by the flag). */
  alpha: number;
  /** Tint colour and how far the element goes toward it (0..1); null: none. */
  tint: RGB | null;
  tintAmount: number;
  /** Edge glow: 0 none, 1 active work, 2 critical work (red). */
  glow: 0 | 1 | 2;
  /** Plan time (ms) until which the look changes with time (a fade or a flash); at or after it the look is the same: re-evaluate only while t < until. */
  until: number;
}

export interface LookInput {
  state: ElementState | number;
  /** Interval start and end (plan ms). */
  from: number;
  to: number;
  /** Plan time now. */
  t: number;
  /** The task of the interval (trade and critical flag), when the plan has it. */
  task?: Pick<PlanTask, 'trade' | 'critical'> | undefined;
  style: Pick<FourDStyle, 'unbuilt' | 'colours'>;
  /** Video seconds per plan ms around now (for the 0.6 s of video fade). */
  secPerMs: number;
}

const STATIC: Look = Object.freeze({ hidden: false, alpha: 1, tint: null, tintAmount: 0, glow: 0, until: -Infinity }) as Look;

/** Length of a fade or flash in plan ms: 10 % of the interval, at most 0.6 s of video (and at least 1 ms). */
export function fadeMs(from: number, to: number, secPerMs: number): number {
  const byVideo = secPerMs > 0 ? FADE_VIDEO_S / secPerMs : Infinity;
  const len = to - from;
  const byInterval = Number.isFinite(len) && len > 0 ? len * FADE_FRACTION : Infinity;
  const v = Math.min(byInterval, byVideo);
  return Number.isFinite(v) ? Math.max(1, v) : 1;
}

export function lookFor(inp: LookInput): Look {
  const code = typeof inp.state === 'number' ? inp.state : STATE_NAMES.indexOf(inp.state);
  switch (code) {
    case S_FUTURE:
      return inp.style.unbuilt === 'ghost' ? { ...STATIC, alpha: GHOST_ALPHA } : { ...STATIC, hidden: true };
    case S_EXISTING:
      return { ...STATIC, tint: EXISTING_GREY, tintAmount: TINT_EXISTING };
    case S_COMPLETE:
      return STATIC;
    case S_ACTIVE:
    case S_BEHIND: {
      const f = fadeMs(inp.from, inp.to, inp.secPerMs);
      const e = inp.t - inp.from;
      const a = code === S_ACTIVE ? Math.min(1, Math.max(0.02, e / f)) : 1;
      const critical = inp.task?.critical === true;
      const tint = code === S_BEHIND ? BEHIND_RGB : hex(tradeColour(inp.task?.trade, inp.style.colours));
      return {
        hidden: false,
        alpha: a,
        tint,
        tintAmount: code === S_BEHIND ? TINT_BEHIND : TINT_ACTIVE,
        glow: critical ? 2 : 1,
        until: code === S_ACTIVE ? inp.from + f : -Infinity,
      };
    }
    case S_REMOVED: {
      const f = fadeMs(inp.from, inp.to, inp.secPerMs);
      const e = inp.t - inp.from;
      if (e >= f) return { ...STATIC, hidden: true };
      return { hidden: false, alpha: Math.max(0.02, 1 - e / f), tint: REMOVED_RGB, tintAmount: TINT_REMOVED, glow: 0, until: inp.from + f };
    }
    case S_AHEAD: {
      const f = fadeMs(inp.from, inp.to, inp.secPerMs);
      const e = inp.t - inp.from;
      if (e >= f) return STATIC;
      return { hidden: false, alpha: 1, tint: AHEAD_RGB, tintAmount: TINT_AHEAD * (1 - e / f), glow: 0, until: inp.from + f };
    }
    default:
      return STATIC;
  }
}
