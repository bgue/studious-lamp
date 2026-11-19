// The clip planes on the undo stack: what the section looks like (the renderer's planes and the section tool's settings), how two
// looks compare, and a small state machine that turns "the planes changed" into one settled change. Pure: no DOM, no three.js, so it
// runs in vitest. The plugin (src/plugins/undo.ts) reads the renderer, feeds `observe` once per frame and `settle` when the camera has
// settled, and applies a change back with `applyClip`.
//
// One step per settled change: a handle drag, a section switch (3D · Plan · Section), applying or clearing a BCF viewpoint's planes.
// When the camera moved in the same step (the switch and a viewpoint do both) the plugin joins the two into one entry.

import { cloneSection } from '../section/config';
import type { SectionConfig } from '../section/config';

export interface PlaneState {
  normal: [number, number, number];
  point: [number, number, number];
}

/** What the section is, as far as undo goes: the planes in force, and the settings of the section tool that may have made them. */
export interface ClipState {
  planes: PlaneState[] | null;
  cfg: SectionConfig | null;
  /** The planes in force are not the section tool's (a BCF viewpoint's, the Plan and Section switch's). */
  foreign: boolean;
}

export interface ClipChange {
  before: ClipState;
  after: ClipState;
}

const near = (a: ArrayLike<number>, b: ArrayLike<number>, eps: number): boolean => {
  for (let i = 0; i < 3; i++) if (Math.abs(a[i]! - b[i]!) > eps) return false;
  return true;
};

/** The same planes: same count, and each normal and point within `eps` (the point as a distance along the normal). */
export function planesSame(a: readonly PlaneState[] | null, b: readonly PlaneState[] | null, eps = 1e-6): boolean {
  const x = a ?? [];
  const y = b ?? [];
  if (x.length !== y.length) return false;
  for (let i = 0; i < x.length; i++) {
    const p = x[i]!;
    const q = y[i]!;
    if (!near(p.normal, q.normal, eps)) return false;
    const dp = p.normal[0] * p.point[0] + p.normal[1] * p.point[1] + p.normal[2] * p.point[2];
    const dq = q.normal[0] * q.point[0] + q.normal[1] * q.point[1] + q.normal[2] * q.point[2];
    if (Math.abs(dp - dq) > eps * Math.max(1, Math.abs(dp))) return false;
  }
  return true;
}

export function cfgSame(a: SectionConfig | null, b: SectionConfig | null): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

export function clipSame(a: ClipState, b: ClipState): boolean {
  return planesSame(a.planes, b.planes) && cfgSame(a.cfg, b.cfg) && a.foreign === b.foreign;
}

/** Read the state from the pieces: the renderer's planes (copied) and the section settings (cloned). */
export function readClipState(planes: ReadonlyArray<{ normal: ArrayLike<number>; point: ArrayLike<number> }> | null | undefined, cfg: SectionConfig | null | undefined, foreign = false): ClipState {
  return {
    foreign: foreign && !!planes && planes.length > 0,
    planes: planes && planes.length ? planes.map((p) => ({ normal: [p.normal[0]!, p.normal[1]!, p.normal[2]!], point: [p.point[0]!, p.point[1]!, p.point[2]!] })) : null,
    cfg: cfg ? cloneSection(cfg) : null,
  };
}

/** Words for the tooltip ("Undo section on"). */
export function describeClipChange(before: ClipState, after: ClipState): string {
  const a = before.planes?.length ?? 0;
  const b = after.planes?.length ?? 0;
  if (!a && b) return 'section on';
  if (a && !b) return 'section off';
  if (a !== b) return 'section';
  return 'section move';
}

/** Where the section tool and the renderer meet when a state is put back; the plugin hands in the real ones. */
export interface ClipTarget {
  /** Merge the tool's settings (SectionApi.set). Absent without a section tool. */
  setConfig?(cfg: SectionConfig): void;
  /** Whether the settings ask for planes (box or plane enabled). */
  wantsPlanes?(cfg: SectionConfig): boolean;
  /** Put planes on the renderer (null removes them). */
  setPlanes(planes: PlaneState[] | null, cap: boolean): void;
}

/**
 * Put a state back. Planes the section tool makes are given back to the tool (its settings are merged, which makes it take the planes
 * back from whoever set them; it pushes them on its next frame). Any other planes (a viewpoint's, a switch's, none) go on the
 * renderer as they were; the tool's settings come back too when it is not the one that made them.
 */
export function applyClip(target: ClipTarget, s: ClipState): void {
  const wants = !!s.cfg && !!target.wantsPlanes?.(s.cfg);
  if (wants && !s.foreign) {
    target.setConfig?.(s.cfg!);
    return;
  }
  if (s.cfg && !s.foreign) target.setConfig?.(s.cfg);
  target.setPlanes(s.planes, s.cfg?.caps ?? true);
}

/**
 * Turns the per-frame state of the planes into settled changes. `observe` keeps the committed state fresh while nothing happens, and
 * starts or extends a pending change when the renderer's plane version moves. `settle` hands the change out when the caller says it is
 * time (the camera and the planes have both been still for the settle time), or at once when forced (before an undo).
 */
export class ClipWatch {
  private committed: ClipState | null = null;
  private pending: { before: ClipState; last: number; since: number } | null = null;
  private version = -1;
  private fresh = -Infinity;

  /** The state is the new starting point: nothing pending. */
  baseline(state: ClipState, version: number): void {
    this.committed = state;
    this.pending = null;
    this.version = version;
  }

  get changing(): boolean {
    return this.pending !== null;
  }
  /** Time of the last change of the planes, or null when none is pending. */
  get lastChangeAt(): number | null {
    return this.pending ? this.pending.last : null;
  }
  /** Time the pending change began, or null. */
  get since(): number | null {
    return this.pending ? this.pending.since : null;
  }

  /**
   * One frame. `read` builds the state lazily (it clones the settings). While nothing is pending the committed state is read again
   * at most every `refreshMs`, so that its settings are those from just before a change.
   */
  observe(read: () => ClipState, version: number, t: number, refreshMs = 50): void {
    if (this.committed === null) {
      this.baseline(read(), version);
      return;
    }
    if (version !== this.version) {
      this.version = version;
      if (!this.pending) this.pending = { before: this.committed, last: t, since: t };
      else this.pending.last = t;
      return;
    }
    if (!this.pending && t - this.fresh >= refreshMs) {
      this.fresh = t;
      this.committed = read();
    }
  }

  /** The settled change, or null when nothing changed (a change that came back to where it started counts as none). */
  settle(read: () => ClipState): ClipChange | null {
    const p = this.pending;
    if (!p) return null;
    this.pending = null;
    const after = read();
    this.committed = after;
    return clipSame(p.before, after) ? null : { before: p.before, after };
  }
}

/**
 * What one settled step records. A camera move and a clip change in the same step are one entry (undo puts both back); a clip
 * change alone is a section entry. Null: nothing changed.
 */
export function composeStep<P>(cam: { before: P; after: P; label: string } | null, clip: ClipChange | null): { kind: 'view'; label: string; before: P; after: P; clip?: ClipChange } | { kind: 'section'; label: string; before: ClipState; after: ClipState } | null {
  if (cam && clip) return { kind: 'view', label: `${cam.label} and section`, before: cam.before, after: cam.after, clip };
  if (cam) return { kind: 'view', label: cam.label, before: cam.before, after: cam.after };
  if (clip) return { kind: 'section', label: describeClipChange(clip.before, clip.after), before: clip.before, after: clip.after };
  return null;
}
