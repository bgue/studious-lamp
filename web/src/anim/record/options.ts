// Export options: the shape, the defaults, the check and the file name. Pure (the dialog is in ui.ts).

import type { Quality, VideoFormat } from './encoder';
import { bitrateFor } from './encoder';
import { FPS_CHOICES, frameCount } from './schedule';
import type { SizeChoice } from './size';
import { SIZE_CHOICES } from './size';

export interface ExportOptions {
  size: SizeChoice;
  fps: number;
  quality: Quality;
  format: VideoFormat;
  /** Composite the HUD layer (captions, labels, progress bar) into the frames. */
  hud: boolean;
  /** File name without the extension. */
  name: string;
}

export const DEFAULT_OPTIONS: ExportOptions = { size: '1920x1080', fps: 30, quality: 'medium', format: 'auto', hud: true, name: '' };

export const OPTIONS_KEY = 'xray.record.options';

const FORMATS: VideoFormat[] = ['auto', 'mp4', 'webm', 'png'];
const QUALITIES: Quality[] = ['low', 'medium', 'high'];

function customSize(v: string): boolean {
  const m = /^(\d{2,5})x(\d{2,5})$/.exec(v);
  return !!m && Number(m[1]) >= 16 && Number(m[2]) >= 16 && Number(m[1]) <= 16384 && Number(m[2]) <= 16384;
}

/** A options object from anything (stored text, a script's argument): unknown or bad fields fall back to `base`. */
export function sanitizeOptions(v: unknown, base: ExportOptions = DEFAULT_OPTIONS): ExportOptions {
  const o = (v && typeof v === 'object' ? v : {}) as Record<string, unknown>;
  const out: ExportOptions = { ...base };
  // A listed size, or a custom WxH (scripts and tests: 16 to 16384 pixels per side).
  if (typeof o['size'] === 'string' && (SIZE_CHOICES.some((s) => s.id === o['size']) || customSize(o['size']))) out.size = o['size'] as SizeChoice;
  if (typeof o['fps'] === 'number' && (FPS_CHOICES as readonly number[]).includes(o['fps'])) out.fps = o['fps'];
  if (typeof o['quality'] === 'string' && QUALITIES.includes(o['quality'] as Quality)) out.quality = o['quality'] as Quality;
  if (typeof o['format'] === 'string' && FORMATS.includes(o['format'] as VideoFormat)) out.format = o['format'] as VideoFormat;
  if (typeof o['hud'] === 'boolean') out.hud = o['hud'];
  if (typeof o['name'] === 'string') out.name = o['name'];
  return out;
}

/** A file name base from a fly-through or script name: letters, digits, dots, dashes and underscores. */
export function fileBase(name: string, fallback = 'fly-through'): string {
  const s = name
    .trim()
    .replace(/[\\/:*?"<>|\u0000-\u001f]+/g, ' ')
    .replace(/\s+/g, '-')
    .replace(/^[-.]+|[-.]+$/g, '')
    .slice(0, 80);
  return s || fallback;
}

/** What the dialog tells before the start: frames, and a rough size of the file. */
export function summarize(duration: number, o: ExportOptions, width: number, height: number): { frames: number; megabytes: number } {
  const frames = frameCount(duration, o.fps);
  const bytes = o.format === 'png' ? frames * width * height * 0.9 : (bitrateFor(width, height, o.fps, o.quality) * (frames / o.fps)) / 8;
  return { frames, megabytes: bytes / 1e6 };
}

export function loadOptions(storage: Pick<Storage, 'getItem'> | null): ExportOptions {
  try {
    const t = storage?.getItem(OPTIONS_KEY);
    return t ? sanitizeOptions(JSON.parse(t)) : { ...DEFAULT_OPTIONS };
  } catch {
    return { ...DEFAULT_OPTIONS };
  }
}

export function saveOptions(storage: Pick<Storage, 'setItem'> | null, o: ExportOptions): void {
  try {
    storage?.setItem(OPTIONS_KEY, JSON.stringify({ ...o, name: '' }));
  } catch {
    /* private mode */
  }
}
