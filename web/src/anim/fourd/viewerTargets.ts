// The viewer side of the explode, focus and section box cues (targets of src/anim/fourd/cues.ts): the whole-model explode driven by
// the cue (not by the cinematic plugin's own selection-based explode, whose state it leaves alone), the x-ray focus through the
// selection, and the section tool (window.__xraySection).

import { Vector3 } from 'three';
import type { ViewerApp } from '../../app';
import type { SectionApi } from '../../plugins/section';
import { buildExplodeTable, explodeOffset, storeyRanks } from '../../cinematic/explode';
import type { ExplodeParams, ExplodeTable } from '../../cinematic/explode';
import { getCinematic } from '../../plugins/cinematic';
import { cloneSection } from '../../section/config';
import type { SectionConfig } from '../../section/config';
import { unionBounds } from '../../selectionSets';
import type { Box, ExplodeTarget, FocusTarget, SectionTarget } from './cues';

/** Median spacing of the storeys (m), the explode gap of a factor of 1; null with fewer than two storeys. */
export function storeySpacing(elevations: readonly number[]): number | null {
  const e = [...elevations].sort((a, b) => a - b);
  const gaps: number[] = [];
  for (let i = 1; i < e.length; i++) if (e[i]! - e[i - 1]! > 0.2) gaps.push(e[i]! - e[i - 1]!);
  if (gaps.length === 0) return null;
  gaps.sort((a, b) => a - b);
  return gaps[gaps.length >> 1]!;
}

export class ViewerExplode implements ExplodeTarget {
  private table: ExplodeTable | null = null;
  private params: ExplodeParams = { mode: 'storeys', factor: 1, storeyGap: 3, minPush: 0 };
  private k = 0;
  private readonly tmp = new Vector3();

  constructor(private readonly app: ViewerApp) {}

  value(): number {
    return this.k;
  }

  begin(mode: 'storeys' | 'radial', factor: number): void {
    const model = this.app.controller.model;
    if (!this.table) {
      const els = model.elements;
      const ids: number[] = [];
      for (let i = 0; i < els.length; i++) if (els[i]!.bounds) ids.push(i);
      this.table = buildExplodeTable(ids, { bounds: (id) => els[id]?.bounds, storeyOf: (id) => els[id]?.storey, ranks: storeyRanks(model.storeys) });
    }
    const spacing = storeySpacing(model.storeys.map((s) => s.elevation)) ?? getCinematic()?.cfg.explode.storeyGap ?? 3;
    this.params = { mode, factor, storeyGap: spacing * factor, minPush: 0 };
  }

  set(k: number): void {
    const t = this.table;
    if (!t) return;
    this.k = k;
    const r = this.app.renderer;
    for (let i = 0; i < t.ids.length; i++) {
      explodeOffset(t, i, this.params, k, this.tmp);
      r.setElementOffset(t.ids[i]!, this.tmp.x, this.tmp.y, this.tmp.z);
    }
    r.markDirty();
  }

  clear(): void {
    if (!this.table && this.k === 0) return;
    this.table = null;
    this.k = 0;
    this.app.renderer.clearElementOffsets();
    // The cinematic plugin's own explode (the user's) writes its offsets again.
    getCinematic()?.markExplodeDirty();
    this.app.renderer.markDirty();
  }

  abandon(): void {
    this.table = null;
    this.k = 0;
  }
}

export class ViewerFocus implements FocusTarget {
  constructor(private readonly select: (ids: number[]) => void, private readonly snapshot: () => number[]) {}

  set(ids: readonly number[] | null): void {
    this.select(ids === null ? this.snapshot() : [...ids]);
  }
}

const sectionApi = (): SectionApi | null => (window as unknown as { __xraySection?: SectionApi }).__xraySection ?? null;

export class ViewerSection implements SectionTarget {
  private snap: SectionConfig | null = null;

  constructor(private readonly app: ViewerApp) {}

  /** Remember the section as it is now (once per play). */
  begin(): void {
    const api = sectionApi();
    this.snap = api ? cloneSection(api.config) : null;
  }

  restore(): void {
    const api = sectionApi();
    const s = this.snap;
    this.snap = null;
    if (!api || !s) return;
    const box: Record<string, unknown> = { enabled: s.box.enabled };
    if (s.box.min && s.box.max) {
      box['min'] = s.box.min;
      box['max'] = s.box.max;
    }
    api.set({ box });
  }

  abandon(): void {
    this.snap = null;
  }

  current(): Box | null {
    const b = sectionApi()?.config.box;
    return b && b.enabled && b.min && b.max ? { min: [...b.min], max: [...b.max] } : null;
  }

  model(): Box | null {
    const b = this.app.loaded?.geometry.totalBounds();
    return b && !b.isEmpty() ? { min: [b.min.x, b.min.y, b.min.z], max: [b.max.x, b.max.y, b.max.z] } : null;
  }

  around(ids: readonly number[]): Box | null {
    const b = unionBounds(this.app.controller.model, ids);
    return b ? { min: [b[0], b[1], b[2]], max: [b[3], b[4], b[5]] } : null;
  }

  aroundStorey(name: string): Box | null {
    const m = this.app.controller.model;
    const want = name.trim().toLowerCase();
    const st = m.storeys.find((s) => s.name.trim().toLowerCase() === want);
    if (!st) return null;
    const ids: number[] = [];
    for (let i = 0; i < m.elements.length; i++) if (m.elements[i]!.storey === st.id) ids.push(i);
    return this.around(ids);
  }

  set(box: Box | null): void {
    const api = sectionApi();
    if (!api) return;
    if (box) api.set({ box: { enabled: true, min: box.min, max: box.max } });
    else api.set({ box: { enabled: false } });
  }

  margin(): number {
    return sectionApi()?.config.box.margin ?? 0.5;
  }
}
