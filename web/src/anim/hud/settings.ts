// HUD settings: what the overlay shows besides captions, labels and the hover card. They live in the fly-through document
// (src/anim/store.ts, `hud`), not in params or share links. Pure.

export type CaptionPosition = 'bottom' | 'top';

export interface HudSettings {
  /** The thin progress bar at the bottom with chapter marks and the time. */
  progress: boolean;
  /** North arrow at the top right. */
  compass: boolean;
  /** Scale bar at the bottom left (metres at the depth of the screen centre). */
  scaleBar: boolean;
  /** Font size of the element labels, in CSS pixels. */
  labelSize: number;
  captionPosition: CaptionPosition;
  // ---- 4D (additive): shown only while a `schedule4d` cue runs
  /** The schedule date and ISO week, % complete (planned, actual) in a panel top left; the date also replaces the m:ss clock on the progress bar. */
  scheduleDate: boolean;
  /** The small S-curve of planned and actual progress, top right. */
  sCurve: boolean;
  /** The list of current activities (the five with most elements) with trade colour swatches. */
  activities: boolean;
  /** The milestone captions of the plan, held for the plan's milestone hold. */
  milestones: boolean;
  /** The legend of the state colours (active trades, critical, behind, ahead) bottom left. */
  legend: boolean;
}

export const LABEL_SIZE_MIN = 9;
export const LABEL_SIZE_MAX = 28;

export const DEFAULT_HUD: HudSettings = { progress: true, compass: false, scaleBar: false, labelSize: 12, captionPosition: 'bottom', scheduleDate: true, sCurve: true, activities: true, milestones: true, legend: true };

export function defaultHud(): HudSettings {
  return { ...DEFAULT_HUD };
}

/** Read stored or imported settings; anything wrong falls back to the default. */
export function sanitizeHud(raw: unknown): HudSettings {
  const out = defaultHud();
  if (!raw || typeof raw !== 'object') return out;
  const o = raw as Record<string, unknown>;
  if (typeof o['progress'] === 'boolean') out.progress = o['progress'];
  if (typeof o['compass'] === 'boolean') out.compass = o['compass'];
  if (typeof o['scaleBar'] === 'boolean') out.scaleBar = o['scaleBar'];
  if (typeof o['labelSize'] === 'number' && Number.isFinite(o['labelSize'])) out.labelSize = Math.min(LABEL_SIZE_MAX, Math.max(LABEL_SIZE_MIN, Math.round(o['labelSize'])));
  for (const k of ['scheduleDate', 'sCurve', 'activities', 'milestones', 'legend'] as const) if (typeof o[k] === 'boolean') out[k] = o[k];
  if (o['captionPosition'] === 'top' || o['captionPosition'] === 'bottom') out.captionPosition = o['captionPosition'];
  return out;
}

export function isDefaultHud(h: HudSettings): boolean {
  return (Object.keys(DEFAULT_HUD) as Array<keyof HudSettings>).every((k) => h[k] === DEFAULT_HUD[k]);
}
