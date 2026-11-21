// The viewer side of the 4D looks: implements LookSink (schedule4d) and TintTarget (tint cue) on the renderer state of a ViewerApp.
//   hidden  -> the user hides of the overrides (so the x-ray sightlines ignore hidden elements too), applied once per frame that changes any
//   alpha   -> renderer.state.alpha, written again after every controller step (the x-ray smoothing writes the alpha of occluders)
//   tint    -> renderer.state.color: the element's own colour mixed toward the tint, written every frame, the original kept for the restore
//   glow    -> renderer.setEdgeGlow with the critical elements as a red accent
//   focus   -> the selection (quietly: the camera does not fly), which is what the x-ray focus is made from
// reset() puts hides, alphas, colours, glow and selection back as they were at begin().

import type { ViewerApp } from '../../app';
import type { ElementId } from '../../types';
import { getCinematic } from '../../plugins/cinematic';
import { CRITICAL_RGB, GLOW_RGB } from './look';
import type { LookSink } from './runner';
import type { TintTarget } from './cues';

export const GLOW_STRENGTH = 0.55;

export interface SinkHooks {
  /** Hidden elements changed: the x-ray sightlines should run again soon. */
  sightlinesDirty(): void;
  /** Select quietly (no fly-to). */
  select(ids: ElementId[]): void;
}

interface Tint {
  r: number;
  g: number;
  b: number;
  a: number;
}

export class ViewerLookSink implements LookSink, TintTarget {
  private n = 0;
  private baseHides = new Set<ElementId>();
  private ours = new Set<ElementId>();
  private hidesDirty = false;
  private alphaOvr = new Float32Array(0);
  private alphaIds = new Set<ElementId>();
  private origColor = new Float32Array(0);
  private tints = new Map<ElementId, Tint>();
  private glow = new Map<ElementId, 1 | 2>();
  private glowDirty = false;
  private glowOn = false;
  private touchWanted = false;
  private began = false;

  constructor(private readonly app: ViewerApp, private readonly hooks: SinkHooks) {}

  private get ov() {
    return this.app.settings.overrides;
  }

  /** Remember the hides of this moment; the arrays are sized to the model. */
  begin(): void {
    const n = this.app.renderer.state.alpha.length;
    if (this.began) this.reset();
    this.n = n;
    this.baseHides = new Set(this.ov.userHides);
    this.ours.clear();
    this.alphaOvr = new Float32Array(n).fill(1);
    this.alphaIds.clear();
    this.origColor = new Float32Array(n * 3).fill(NaN);
    this.tints.clear();
    this.glow.clear();
    this.hidesDirty = false;
    this.glowDirty = false;
    this.touchWanted = false;
    this.began = true;
  }

  get active(): boolean {
    return this.began;
  }

  // ---------------------------------------------------------------- LookSink

  setHidden(id: number, hidden: boolean): void {
    if (!this.began || id < 0 || id >= this.n) return;
    const hides = this.ov.userHides;
    if (hidden) {
      if (!hides.has(id)) {
        hides.add(id);
        this.hidesDirty = true;
      }
      this.ov.userPins.delete(id);
      this.ours.add(id);
    } else if (this.ours.delete(id)) {
      if (!this.baseHides.has(id)) {
        hides.delete(id);
        this.hidesDirty = true;
      }
    }
  }

  setAlpha(id: number, alpha: number): void {
    if (!this.began || id < 0 || id >= this.n) return;
    if (alpha >= 0.999) {
      if (this.alphaIds.delete(id)) {
        this.alphaOvr[id] = 1;
        this.app.renderer.state.alpha[id] = 1;
        this.touchWanted = true;
      }
    } else {
      this.alphaIds.add(id);
      this.alphaOvr[id] = alpha;
    }
  }

  getTint(id: number): { rgb: readonly [number, number, number]; amount: number } | null {
    const t = this.tints.get(id);
    return t ? { rgb: [t.r, t.g, t.b], amount: t.a } : null;
  }

  setTint(id: number, rgb: readonly [number, number, number] | null, amount: number): void {
    if (!this.began || id < 0 || id >= this.n) return;
    const color = this.app.renderer.state.color;
    const o = id * 3;
    if (rgb === null || amount <= 0.001) {
      if (this.tints.delete(id)) {
        if (!Number.isNaN(this.origColor[o]!)) {
          color[o] = this.origColor[o]!;
          color[o + 1] = this.origColor[o + 1]!;
          color[o + 2] = this.origColor[o + 2]!;
          this.origColor[o] = NaN;
        }
        this.touchWanted = true;
      }
      return;
    }
    if (Number.isNaN(this.origColor[o]!)) {
      this.origColor[o] = color[o]!;
      this.origColor[o + 1] = color[o + 1]!;
      this.origColor[o + 2] = color[o + 2]!;
    }
    const cur = this.tints.get(id);
    if (cur) {
      cur.r = rgb[0];
      cur.g = rgb[1];
      cur.b = rgb[2];
      cur.a = amount;
    } else this.tints.set(id, { r: rgb[0], g: rgb[1], b: rgb[2], a: amount });
  }

  setGlow(id: number, kind: 0 | 1 | 2): void {
    if (!this.began || id < 0 || id >= this.n) return;
    if (kind === 0) {
      if (this.glow.delete(id)) this.glowDirty = true;
    } else if (this.glow.get(id) !== kind) {
      this.glow.set(id, kind);
      this.glowDirty = true;
    }
  }

  setFocus(ids: readonly number[]): void {
    if (!this.began) return;
    this.hooks.select([...ids]);
  }

  commit(): void {
    if (this.hidesDirty) {
      this.hidesDirty = false;
      this.app.controller.refreshOverrides();
      this.hooks.sightlinesDirty();
    }
    if (this.touchWanted) {
      this.touchWanted = false;
      this.app.controller.touch();
    }
    this.applyFrame();
  }

  /** Write the overrides into the renderer state (after the controller step of every frame). */
  applyFrame(): void {
    if (!this.began) return;
    if (this.alphaIds.size === 0 && this.tints.size === 0 && this.glow.size === 0 && !this.glowOn) return; // a play without 4D: nothing to write
    const r = this.app.renderer;
    const alpha = r.state.alpha;
    for (const id of this.alphaIds) alpha[id] = this.alphaOvr[id]!;
    const color = r.state.color;
    for (const [id, t] of this.tints) {
      const o = id * 3;
      const k = this.origColor[o];
      if (k === undefined || Number.isNaN(k)) continue;
      color[o] = k + (t.r - k) * t.a;
      color[o + 1] = this.origColor[o + 1]! + (t.g - this.origColor[o + 1]!) * t.a;
      color[o + 2] = this.origColor[o + 2]! + (t.b - this.origColor[o + 2]!) * t.a;
    }
    if (this.glow.size > 0) {
      const all = new Set<number>(this.glow.keys());
      const red: number[] = [];
      for (const [id, k] of this.glow) if (k === 2) red.push(id);
      r.setEdgeGlow(all, [GLOW_RGB[0], GLOW_RGB[1], GLOW_RGB[2]], { strength: GLOW_STRENGTH, additive: true, accent: { ids: red, color: [CRITICAL_RGB[0], CRITICAL_RGB[1], CRITICAL_RGB[2]] } });
      this.glowOn = true;
    } else if (this.glowOn) {
      this.glowOn = false;
      getCinematic()?.applyGlow();
    }
    this.glowDirty = false;
    r.markDirty();
  }

  /** Put hides, alphas, colours and the glow back. The selection is the host's (its snapshot). */
  reset(): void {
    if (!this.began) return;
    this.began = false;
    const r = this.app.renderer;
    const hides = this.ov.userHides;
    for (const id of this.ours) if (!this.baseHides.has(id)) hides.delete(id);
    for (const id of this.baseHides) hides.add(id);
    this.ours.clear();
    const alpha = r.state.alpha;
    for (const id of this.alphaIds) alpha[id] = 1;
    this.alphaIds.clear();
    const color = r.state.color;
    for (const id of this.tints.keys()) {
      const o = id * 3;
      if (!Number.isNaN(this.origColor[o]!)) {
        color[o] = this.origColor[o]!;
        color[o + 1] = this.origColor[o + 1]!;
        color[o + 2] = this.origColor[o + 2]!;
      }
    }
    this.tints.clear();
    this.glow.clear();
    if (this.glowOn) {
      this.glowOn = false;
      getCinematic()?.applyGlow();
    }
    this.app.controller.refreshOverrides();
    this.app.controller.touch();
    r.markDirty();
  }

  /** Counts of what is applied now (smoke checks). */
  stats(): { hidden: number; alphaOverrides: number; tinted: number; glow: number } {
    return { hidden: this.ours.size, alphaOverrides: this.alphaIds.size, tinted: this.tints.size, glow: this.glow.size };
  }

  /** Drop everything without touching the viewer (the model changed). */
  abandon(): void {
    this.began = false;
    this.ours.clear();
    this.alphaIds.clear();
    this.tints.clear();
    this.glow.clear();
    this.glowOn = false;
  }
}
