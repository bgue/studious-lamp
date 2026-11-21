// Blending of settings snapshots for the score player: leaves of a params document, a blend of the numbers between two
// states, and the setting paths of docs/SETTINGS.md (dotted keys of the `xray-params/1` document). Pure.

import type { Ease } from './score';
import { clamp01, easeInOutCubic } from '../cinematic/easing';

export type Leaf = string | number | boolean | null | unknown[];
export type Keys = string[];

function isObj(v: unknown): v is Record<string, unknown> {
  return !!v && typeof v === 'object' && !Array.isArray(v);
}

/** Apply an ease to a progress value in [0, 1]. */
export function easeValue(ease: Ease | undefined, t: number): number {
  const c = clamp01(t);
  switch (ease) {
    case 'in':
      return c * c * c;
    case 'out':
      return 1 - Math.pow(1 - c, 3);
    case 'inOut':
      return easeInOutCubic(c);
    default:
      return c;
  }
}

/** Where in a cue (0 to 1) a discrete change happens. */
export function switchPoint(at: 'start' | 'mid' | 'end' | undefined, fallback: 'start' | 'mid' | 'end' = 'end'): number {
  const a = at ?? fallback;
  return a === 'start' ? 0 : a === 'mid' ? 0.5 : 1;
}

/** Leaves of a nested document: objects recurse, arrays and scalars are leaves. */
export function leaves(doc: unknown, prefix: Keys = [], out: Array<{ keys: Keys; value: Leaf }> = []): Array<{ keys: Keys; value: Leaf }> {
  if (isObj(doc)) {
    for (const [k, v] of Object.entries(doc)) leaves(v, [...prefix, k], out);
  } else if (doc !== undefined && prefix.length > 0) out.push({ keys: prefix, value: doc as Leaf });
  return out;
}

export function getAt(doc: unknown, keys: readonly string[]): unknown {
  let cur: unknown = doc;
  for (const k of keys) {
    if (!isObj(cur)) return undefined;
    cur = cur[k];
  }
  return cur;
}

/** A nested object holding the given leaves. */
export function nest(items: ReadonlyArray<{ keys: readonly string[]; value: unknown }>): Record<string, unknown> {
  const root: Record<string, unknown> = {};
  for (const it of items) {
    let cur = root;
    for (let i = 0; i < it.keys.length - 1; i++) {
      const k = it.keys[i]!;
      if (!isObj(cur[k])) cur[k] = {};
      cur = cur[k] as Record<string, unknown>;
    }
    cur[it.keys[it.keys.length - 1]!] = Array.isArray(it.value) ? JSON.parse(JSON.stringify(it.value)) : it.value;
  }
  return root;
}

export interface ParamDiff {
  /** Numbers that differ: blended over the cue. */
  nums: Array<{ keys: Keys; from: number; to: number }>;
  /** Everything else that differs (booleans, strings, arrays, numbers whose start is unknown): switched at the switch point. */
  discrete: Array<{ keys: Keys; value: unknown }>;
}

function sameLeaf(a: unknown, b: unknown): boolean {
  return a === b || (typeof a === 'object' && JSON.stringify(a) === JSON.stringify(b));
}

/** What changes between the current state `from` and the target `to`. Leaves that `to` does not name stay as they are. */
export function diffParams(from: unknown, to: unknown): ParamDiff {
  const nums: ParamDiff['nums'] = [];
  const discrete: ParamDiff['discrete'] = [];
  for (const l of leaves(to)) {
    const cur = getAt(from, l.keys);
    if (sameLeaf(cur, l.value)) continue;
    if (typeof l.value === 'number' && typeof cur === 'number' && Number.isFinite(cur) && Number.isFinite(l.value)) nums.push({ keys: l.keys, from: cur, to: l.value });
    else discrete.push({ keys: l.keys, value: l.value });
  }
  return { nums, discrete };
}

/** The blended document of the numbers at progress p (an eased value in [0, 1]); p = 1 gives the exact target values. */
export function blendNumbers(nums: ParamDiff['nums'], p: number): Record<string, unknown> {
  return nest(nums.map((n) => ({ keys: n.keys, value: p >= 1 ? n.to : n.from + (n.to - n.from) * p })));
}

/** A setting path ("cinematic.glowStrength") as keys. */
export function pathKeys(path: string): Keys {
  return path.split('.').filter((k) => k.length > 0);
}

/** Blend two numbers or switch other values: the value of a param cue at eased progress p, the switch at `sw` (0 to 1). */
export function blendValue(from: unknown, to: unknown, p: number, rawP: number, sw: number): unknown {
  if (typeof from === 'number' && typeof to === 'number') return p >= 1 ? to : from + (to - from) * p;
  return rawP >= sw ? to : from;
}
