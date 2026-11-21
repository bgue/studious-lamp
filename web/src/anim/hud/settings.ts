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
}

export const LABEL_SIZE_MIN = 9;
export const LABEL_SIZE_MAX = 28;

export const DEFAULT_HUD: HudSettings = { progress: true, compass: false, scaleBar: false, labelSize: 12, captionPosition: 'bottom' };

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
  if (o['captionPosition'] === 'top' || o['captionPosition'] === 'bottom') out.captionPosition = o['captionPosition'];
  return out;
}

export function isDefaultHud(h: HudSettings): boolean {
  return (Object.keys(DEFAULT_HUD) as Array<keyof HudSettings>).every((k) => h[k] === DEFAULT_HUD[k]);
}
