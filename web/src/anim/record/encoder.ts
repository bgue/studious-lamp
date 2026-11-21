// Which encoder a video export uses. Pure: `supported` is VideoEncoder.isConfigSupported behind a small function, so tests give a
// fake one. MP4 (H.264) where the browser can encode it, else WebM (VP9, else VP8).

export type VideoFormat = 'auto' | 'mp4' | 'webm' | 'png';
export type Quality = 'low' | 'medium' | 'high';
export const QUALITY_CHOICES: ReadonlyArray<{ id: Quality; label: string }> = [
  { id: 'low', label: 'Small file' },
  { id: 'medium', label: 'Balanced' },
  { id: 'high', label: 'High quality' },
];

/** Bits per pixel per frame of each quality. */
const BITS_PER_PIXEL: Record<Quality, number> = { low: 0.04, medium: 0.08, high: 0.16 };

/** Bitrate in bits per second for a size, frame rate and quality (between 1 and 120 Mbit/s). */
export function bitrateFor(width: number, height: number, fps: number, quality: Quality): number {
  const bps = width * height * fps * BITS_PER_PIXEL[quality];
  return Math.round(Math.min(120e6, Math.max(1e6, bps)));
}

export type Container = 'mp4' | 'webm';
/** The codec names of the muxer library (mediabunny). */
export type CodecName = 'avc' | 'vp9' | 'vp8';

export interface EncoderChoice {
  container: Container;
  codec: CodecName;
  /** The WebCodecs codec string that was found supported. */
  codecString: string;
}

export interface EncoderSpec {
  width: number;
  height: number;
  fps: number;
  bitrate: number;
}

export interface ProbeConfig {
  codec: string;
  width: number;
  height: number;
  framerate: number;
  bitrate: number;
}
export type SupportFn = (config: ProbeConfig) => Promise<boolean>;

/** H.264 level (hex of level * 10) for a frame size and rate, by the macroblock limits of the standard. */
export function avcLevel(width: number, height: number, fps: number): string {
  const mbs = Math.ceil(width / 16) * Math.ceil(height / 16);
  const rate = mbs * fps;
  const levels: Array<[string, number, number]> = [
    ['1F', 3600, 108000],
    ['28', 8192, 245760],
    ['2A', 8704, 522240],
    ['32', 22080, 589824],
    ['33', 36864, 983040],
    ['34', 36864, 2073600],
  ];
  for (const [hex, maxFs, maxRate] of levels) if (mbs <= maxFs && rate <= maxRate) return hex;
  return '34';
}

/** H.264 codec strings to try, best first: High, Main, Constrained Baseline. */
export function avcCandidates(width: number, height: number, fps: number): string[] {
  const lv = avcLevel(width, height, fps);
  return [`avc1.6400${lv}`, `avc1.4d00${lv}`, `avc1.4200${lv}`];
}

export const VP9_CANDIDATES = ['vp09.00.40.08', 'vp09.00.10.08', 'vp09.00.51.08', 'vp09.00.61.08', 'vp09.00.62.08'];

function vp9Candidates(width: number, height: number): string[] {
  // The level number of VP9 follows the frame size; offer the levels from a fitting one upwards.
  const px = width * height;
  const lv = px <= 983040 ? ['31', '40', '41', '50', '51', '52'] : px <= 2228224 ? ['40', '41', '50', '51', '52'] : px <= 8912896 ? ['50', '51', '52', '61'] : ['60', '61', '62'];
  return lv.map((l) => `vp09.00.${l}.08`);
}

async function firstSupported(codecs: string[], spec: EncoderSpec, supported: SupportFn): Promise<string | null> {
  for (const codec of codecs) {
    try {
      if (await supported({ codec, width: spec.width, height: spec.height, framerate: spec.fps, bitrate: spec.bitrate })) return codec;
    } catch {
      /* a browser that throws for a codec string does not support it */
    }
  }
  return null;
}

/**
 * Pick the encoder. `auto` tries H.264 (MP4), then VP9, then VP8 (WebM). `mp4` tries only H.264 and `webm` only VP9 then VP8, so a
 * person who asked for a container never gets another one. null: nothing fits (the caller falls back to a recorder or PNG frames).
 */
export async function chooseEncoder(format: Exclude<VideoFormat, 'png'>, spec: EncoderSpec, supported: SupportFn): Promise<EncoderChoice | null> {
  if (format === 'auto' || format === 'mp4') {
    const c = await firstSupported(avcCandidates(spec.width, spec.height, spec.fps), spec, supported);
    if (c) return { container: 'mp4', codec: 'avc', codecString: c };
    if (format === 'mp4') return null;
  }
  const v9 = await firstSupported([...vp9Candidates(spec.width, spec.height), ...VP9_CANDIDATES], spec, supported);
  if (v9) return { container: 'webm', codec: 'vp9', codecString: v9 };
  const v8 = await firstSupported(['vp8'], spec, supported);
  if (v8) return { container: 'webm', codec: 'vp8', codecString: v8 };
  return null;
}

/** The browser's check, for chooseEncoder; null when the browser has no WebCodecs video encoder. */
export function browserSupportFn(): SupportFn | null {
  const VE = (globalThis as { VideoEncoder?: { isConfigSupported(c: unknown): Promise<{ supported?: boolean }> } }).VideoEncoder;
  if (!VE || typeof VE.isConfigSupported !== 'function') return null;
  return async (c) => {
    const r = await VE.isConfigSupported({ codec: c.codec, width: c.width, height: c.height, framerate: c.framerate, bitrate: c.bitrate, latencyMode: 'quality' });
    return r.supported === true;
  };
}
