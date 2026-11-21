// Runners of the 4D helper cue kinds `tint`, `explode`, `collapse`, `focus` and `sectionBox`. Each works on a small target interface
// (the viewer implements it in src/anim/fourd/viewerTargets.ts, the tests use fakes), so the timing and the easing are tested without
// a viewer. Colours are #rrggbb.

import type { Cue, Ease, ElementRef } from '../score';
import { easeValue } from '../blend';
import type { CueRunner } from '../player';
import { hex } from './look';

export type Box = { min: [number, number, number]; max: [number, number, number] };

/** How far a `tint` cue goes toward its colour (the rest is the element's own colour). */
export const CUE_TINT_AMOUNT = 0.8;

export interface TintTarget {
  /** The tint an element has now (colour and amount), null when none. */
  getTint(id: number): { rgb: readonly [number, number, number]; amount: number } | null;
  setTint(id: number, rgb: readonly [number, number, number] | null, amount: number): void;
  commit(): void;
}

export interface ExplodeTarget {
  /** How far the building is exploded now (0..1 of the last explode that was started). */
  value(): number;
  /** Start (or re-aim) an explode of every element: `storeys` lifts each floor, `radial` pushes elements out from the centre. */
  begin(mode: 'storeys' | 'radial', factor: number): void;
  /** Set the eased progress 0..1. */
  set(k: number): void;
  /** Collapsed: drop the offsets. */
  clear(): void;
}

export interface FocusTarget {
  /** The x-ray focus; null gives it back (the selection as it was). */
  set(ids: readonly number[] | null): void;
}

export interface SectionTarget {
  /** The section box now, null when it is off. */
  current(): Box | null;
  /** The box of the whole model. */
  model(): Box | null;
  /** The box around elements, or around a storey by name; margin in metres. */
  around(ids: readonly number[]): Box | null;
  aroundStorey(name: string): Box | null;
  /** Set the box (enabled); null switches it off. */
  set(box: Box | null): void;
  /** Default margin when the cue has none. */
  margin(): number;
}

export interface CueEnv {
  resolve(ref: ElementRef, key: string): number[];
}

type CueOf<K extends Cue['kind']> = Extract<Cue, { kind: K }>;

const ease = (e: Ease | undefined, p: number): number => easeValue(e, p);

export function tintRunner(cue: CueOf<'tint'>, index: number, env: CueEnv, t: TintTarget): CueRunner {
  const ids = env.resolve(cue.elements, `${index}:elements`);
  if (ids.length === 0) return { update: () => undefined };
  const to = cue.colour === null ? null : hex(cue.colour);
  // A fade out starts from what the elements show now.
  const from = new Map<number, { rgb: readonly [number, number, number]; amount: number }>();
  if (to === null) for (const id of ids) {
    const cur = t.getTint(id);
    if (cur) from.set(id, cur);
  }
  return {
    update: (raw) => {
      const k = ease(cue.ease, raw);
      if (to) {
        const a = CUE_TINT_AMOUNT * k;
        for (const id of ids) t.setTint(id, to, a);
      } else {
        for (const id of ids) {
          const f = from.get(id);
          if (!f) continue;
          t.setTint(id, raw >= 1 ? null : f.rgb, f.amount * (1 - k));
        }
      }
      t.commit();
    },
  };
}

export function explodeRunner(cue: CueOf<'explode'>, t: ExplodeTarget): CueRunner {
  const start = t.value();
  const factor = typeof cue.factor === 'number' && Number.isFinite(cue.factor) ? cue.factor : 1;
  t.begin(cue.mode, factor);
  return { update: (raw) => t.set(start + (1 - start) * ease(cue.ease, raw)) };
}

export function collapseRunner(cue: CueOf<'collapse'>, t: ExplodeTarget): CueRunner {
  const start = t.value();
  return {
    update: (raw) => {
      const k = start * (1 - ease(cue.ease, raw));
      if (raw >= 1) t.clear();
      else t.set(k);
    },
  };
}

export function focusRunner(cue: CueOf<'focus'>, index: number, env: CueEnv, t: FocusTarget): CueRunner {
  let done = false;
  return {
    update: () => {
      if (done) return;
      done = true;
      t.set(cue.elements === null ? null : env.resolve(cue.elements, `${index}:elements`));
    },
  };
}

const lerp3 = (a: readonly number[], b: readonly number[], p: number): [number, number, number] => [a[0]! + (b[0]! - a[0]!) * p, a[1]! + (b[1]! - a[1]!) * p, a[2]! + (b[2]! - a[2]!) * p];

/** Grow a box by `m` metres on every side. */
export function growBox(b: Box, m: number): Box {
  return { min: [b.min[0] - m, b.min[1] - m, b.min[2] - m], max: [b.max[0] + m, b.max[1] + m, b.max[2] + m] };
}

export function sectionRunner(cue: CueOf<'sectionBox'>, index: number, env: CueEnv, t: SectionTarget): CueRunner | null {
  const margin = typeof cue.margin === 'number' && Number.isFinite(cue.margin) ? cue.margin : t.margin();
  let target: Box | null = null;
  if (cue.around !== null) {
    let b: Box | null;
    if ('storey' in cue.around) b = t.aroundStorey(cue.around.storey);
    else b = t.around(env.resolve(cue.around, `${index}:around`));
    if (!b) return null;
    target = growBox(b, margin);
  }
  const model = t.model();
  const from0 = t.current();
  // Closing in starts from the whole model; opening goes out to it and then switches off.
  const from: Box | null = from0 ?? (model ? growBox(model, margin) : null);
  const to: Box | null = target ?? (model ? growBox(model, margin) : null);
  if (!from || !to) {
    if (target === null) t.set(null);
    else t.set(target);
    return null;
  }
  return {
    update: (raw) => {
      const k = ease(cue.ease, raw);
      if (raw >= 1) {
        t.set(target);
        return;
      }
      t.set({ min: lerp3(from.min, to.min, k), max: lerp3(from.max, to.max, k) });
    },
  };
}
