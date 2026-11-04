// Tour mode: sequencing of selection sets. The state machine takes callbacks and uses the global
// timer functions at call time, so tests can drive it with fake timers.

import type { SceneModel } from '../types';

export interface TourStep {
  name: string;
  ids: number[];
}

export interface TourOptions {
  /** Time to hold on each step after the fly, ms. Read when each step is scheduled. */
  holdMs: () => number;
  /** Time reserved for the fly before the hold starts, ms. */
  flyMs: () => number;
  loop: () => boolean;
  /** Apply a step: select it and fly to it. */
  apply: (step: TourStep, index: number) => void;
  /** Called once when the tour stops, either because it ended or stop() was called. */
  onStop?: (reason: 'done' | 'stopped') => void;
}

export class Tour {
  steps: TourStep[] = [];
  index = -1;
  running = false;
  private timer: ReturnType<typeof setTimeout> | null = null;

  constructor(private readonly opts: TourOptions) {}

  /** Start from the first step. Returns false (and does nothing) when there are no steps. */
  start(steps: TourStep[]): boolean {
    this.stop(true);
    this.steps = steps.filter((s) => s.ids.length > 0);
    if (this.steps.length === 0) return false;
    this.running = true;
    this.index = -1;
    this.advance();
    return true;
  }

  stop(silent = false): void {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
    const was = this.running;
    this.running = false;
    if (was && !silent) this.opts.onStop?.('stopped');
  }

  private advance(): void {
    if (!this.running) return;
    let next = this.index + 1;
    if (next >= this.steps.length) {
      if (!this.opts.loop()) {
        this.running = false;
        this.timer = null;
        this.opts.onStop?.('done');
        return;
      }
      next = 0;
    }
    this.index = next;
    this.opts.apply(this.steps[next]!, next);
    this.timer = setTimeout(() => {
      this.timer = null;
      this.advance();
    }, Math.max(0, this.opts.flyMs()) + Math.max(0, this.opts.holdMs()));
  }
}

export const SETS_KEY_PREFIX = 'xray.sets.';

/** Parse the sidebar's stored sets: JSON array of { name, globalIds: string[] }. Unknown ids are dropped; bad input gives []. */
export function parseStoredSets(raw: string | null | undefined, byGlobalId: ReadonlyMap<string, number>): TourStep[] {
  if (!raw) return [];
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return [];
  }
  if (!Array.isArray(data)) return [];
  const steps: TourStep[] = [];
  for (const item of data) {
    if (!item || typeof item !== 'object') continue;
    const rec = item as { name?: unknown; globalIds?: unknown };
    if (!Array.isArray(rec.globalIds)) continue;
    const ids: number[] = [];
    for (const g of rec.globalIds) {
      const id = typeof g === 'string' ? byGlobalId.get(g) : undefined;
      if (id !== undefined) ids.push(id);
    }
    if (ids.length > 0) steps.push({ name: typeof rec.name === 'string' ? rec.name : `Set ${steps.length + 1}`, ids });
  }
  return steps;
}

/** One step per storey (ordered by elevation): the focus-class elements on it. Empty storeys are skipped. */
export function storeyFocusSteps(model: Pick<SceneModel, 'storeys' | 'elements'>, focusClasses: ReadonlySet<string>): TourStep[] {
  const steps: TourStep[] = [];
  const storeys = [...model.storeys].sort((a, b) => a.elevation - b.elevation || a.id - b.id);
  for (const st of storeys) {
    const ids = model.elements.filter((e) => e.storey === st.id && focusClasses.has(e.ifcClass)).map((e) => e.id);
    if (ids.length > 0) steps.push({ name: st.name, ids });
  }
  return steps;
}

/** Stored sets for the model if there are any, else the storey fallback. */
export function buildTourSteps(
  model: SceneModel,
  modelName: string,
  focusClasses: ReadonlySet<string>,
  storage: Pick<Storage, 'getItem'> | null,
): TourStep[] {
  let raw: string | null = null;
  try {
    raw = storage ? storage.getItem(SETS_KEY_PREFIX + modelName) : null;
  } catch {
    raw = null;
  }
  const stored = parseStoredSets(raw, model.byGlobalId);
  return stored.length > 0 ? stored : storeyFocusSteps(model, focusClasses);
}
