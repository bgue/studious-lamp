// Pure timing rules of the HUD: fades, which cues are on at a time, chapter marks, clock text, scale bar length. No DOM.

import type { Cue, Score } from '../score';

/** Seconds of the fade in and the fade out of captions, labels and the hover card. */
export const FADE_S = 0.3;

/** 0..1: rises over the first `fade` seconds of [start, end], falls over the last; both shrink to half the span of a short item. */
export function fadeAlpha(t: number, start: number, end: number, fade = FADE_S): number {
  const span = end - start;
  if (!(span > 0) || t < start || t > end) return 0;
  const f = Math.min(fade, span / 2);
  if (f <= 0) return 1;
  return Math.max(0, Math.min(1, Math.min((t - start) / f, (end - t) / f)));
}

export type CueOf<K extends Cue['kind']> = Extract<Cue, { kind: K }>;

/** The cues of one kind that are on at `t` (from their start to their end), with their index in the score and their fade alpha. */
export function activeCues<K extends Cue['kind']>(score: Score, kind: K, t: number, fade = FADE_S): Array<{ cue: CueOf<K>; index: number; alpha: number }> {
  const out: Array<{ cue: CueOf<K>; index: number; alpha: number }> = [];
  score.cues.forEach((c, index) => {
    if (c.kind !== kind) return;
    const a = fadeAlpha(t, c.at, c.at + c.dur, fade);
    if (a > 0) out.push({ cue: c as CueOf<K>, index, alpha: a });
  });
  return out;
}

/** True when a caption, label or hover cue shows at `t`. */
export function anyItemAt(score: Score, t: number): boolean {
  return score.cues.some((c) => (c.kind === 'caption' || c.kind === 'label' || c.kind === 'hover') && t >= c.at && t <= c.at + c.dur && c.dur > 0);
}

/**
 * The chapter marks of the progress bar, in seconds. A fly-through: the arrival at each keyframe (the end of its view cue).
 * A script (and any other score): the start of each caption and label cue. Sorted, within 0..duration, marks closer than
 * `minGap` seconds merged.
 */
export function chaptersOf(score: Score, duration = score.duration, minGap = 0.25): number[] {
  const times: number[] = [];
  if (score.source?.kind === 'keyframes') {
    for (const c of score.cues) if (c.kind === 'view') times.push(c.at + Math.max(0, c.dur));
  } else {
    for (const c of score.cues) if (c.kind === 'caption' || c.kind === 'label') times.push(c.at);
  }
  times.sort((a, b) => a - b);
  const out: number[] = [];
  for (const t of times) {
    if (!(t >= 0) || t > duration + 1e-9) continue;
    if (out.length === 0 || t - out[out.length - 1]! >= minGap) out.push(t);
  }
  return out;
}

/** `m:ss` of seconds (rounded down, so the clock never shows the end before the end). */
export function clock(s: number): string {
  const t = Math.max(0, Math.floor(s + 1e-9));
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}`;
}

/** A round length in metres (1, 2, 5 times a power of ten) whose bar is between `minPx` and `maxPx` wide; null when none fits. */
export function niceScale(pxPerMetre: number, minPx = 60, maxPx = 140): { metres: number; px: number } | null {
  if (!(pxPerMetre > 0) || !Number.isFinite(pxPerMetre)) return null;
  const lo = minPx / pxPerMetre;
  const hi = maxPx / pxPerMetre;
  const exp = Math.floor(Math.log10(lo));
  for (let e = exp; e <= exp + 2; e++) {
    for (const m of [1, 2, 5]) {
      const metres = m * 10 ** e;
      if (metres >= lo - 1e-12 && metres <= hi + 1e-12) return { metres, px: metres * pxPerMetre };
    }
  }
  return null;
}

/** `5 m`, `200 m`, `2 km`, `0.5 m`, `20 cm`. */
export function scaleText(metres: number): string {
  if (metres >= 1000) return `${metres / 1000} km`;
  if (metres >= 1) return `${metres} m`;
  if (metres >= 0.01) return `${Math.round(metres * 100)} cm`;
  return `${Math.round(metres * 1000)} mm`;
}
