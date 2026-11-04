// Recordable fly-through: keyframes (camera, target, selection, toggles), a Catmull-Rom path through
// them, a clock-driven player, JSON persistence and a canvas recorder. Everything except the
// recorder is pure (three math only) and covered by tests.

import { Vector3 } from 'three';

export const FLYTHROUGH_SCHEMA = 'xray-flythrough/1';
export const FLYTHROUGH_KEY_PREFIX = 'xray.flythrough.';
export const DEFAULT_SEGMENT_S = 2.5;

/** The cinematic toggles stored with a keyframe and re-applied when playback reaches it. */
export interface KeyframeToggles {
  reveal?: boolean;
  sweep?: boolean;
  depthGrade?: boolean;
  bloom?: boolean;
  edgeGlow?: boolean;
  ao?: boolean;
  vignette?: boolean;
}

export interface Keyframe {
  position: [number, number, number];
  target: [number, number, number];
  /** Selected elements, by IFC GlobalId so the keyframe survives a reconversion. */
  selection: string[];
  toggles: KeyframeToggles;
  name?: string;
}

export function flythroughKey(modelName: string): string {
  return FLYTHROUGH_KEY_PREFIX + modelName;
}

// ---------------------------------------------------------------- spline

/**
 * Uniform Catmull-Rom (tension 0.5) between p1 and p2 with neighbours p0 and p3, at t in [0, 1].
 * t = 0 gives p1 and t = 1 gives p2 exactly.
 */
export function catmullRom(p0: Vector3, p1: Vector3, p2: Vector3, p3: Vector3, t: number, out = new Vector3()): Vector3 {
  const t2 = t * t;
  const t3 = t2 * t;
  const f = (a: number, b: number, c: number, d: number): number =>
    0.5 * (2 * b + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t2 + (-a + 3 * b - 3 * c + d) * t3);
  return out.set(f(p0.x, p1.x, p2.x, p3.x), f(p0.y, p1.y, p2.y, p3.y), f(p0.z, p1.z, p2.z, p3.z));
}

/**
 * Point on the spline through `pts` at the keyframe-index parameter `u` in [0, n - 1]
 * (integer u hits pts[u]). The ends are clamped (the first/last point is repeated as neighbour).
 */
export function sampleSplineAt(pts: readonly Vector3[], u: number, out = new Vector3()): Vector3 {
  const n = pts.length;
  if (n === 0) return out.set(0, 0, 0);
  if (n === 1) return out.copy(pts[0]!);
  const uc = Math.min(Math.max(u, 0), n - 1);
  const i = Math.min(Math.floor(uc), n - 2);
  const t = uc - i;
  return catmullRom(pts[Math.max(i - 1, 0)]!, pts[i]!, pts[i + 1]!, pts[Math.min(i + 2, n - 1)]!, t, out);
}

/** Spline sample at normalised t in [0, 1] over the whole path: t = 0 is the first point, t = 1 the last, equal time per segment. */
export function sampleSpline(pts: readonly Vector3[], t: number, out = new Vector3()): Vector3 {
  return sampleSplineAt(pts, Math.min(Math.max(t, 0), 1) * Math.max(pts.length - 1, 0), out);
}

// ---------------------------------------------------------------- player

export interface PlaybackSample {
  /** Keyframe-index parameter, 0..n-1. */
  u: number;
  /** Index of the last keyframe reached (floor of u, with a tiny tolerance). */
  index: number;
  done: boolean;
}

/** Plays a path through keyframes at a fixed time per segment. */
export class FlyPlayer {
  private readonly pos: Vector3[];
  private readonly tgt: Vector3[];
  private t0 = Number.NaN;
  /** Highest keyframe index already reported through `reached`. */
  private reported = -1;

  constructor(keys: readonly Pick<Keyframe, 'position' | 'target'>[], readonly segmentMs: number) {
    this.pos = keys.map((k) => new Vector3(...k.position));
    this.tgt = keys.map((k) => new Vector3(...k.target));
  }

  get count(): number {
    return this.pos.length;
  }

  get durationMs(): number {
    return Math.max(0, this.pos.length - 1) * Math.max(1, this.segmentMs);
  }

  /** Write the pose at clock time `now` (ms). The first call starts the clock. */
  sample(now: number, outPos: Vector3, outTarget: Vector3): PlaybackSample {
    if (Number.isNaN(this.t0)) this.t0 = now;
    const n = this.pos.length;
    const seg = Math.max(1, this.segmentMs);
    const u = n <= 1 ? 0 : Math.min(n - 1, Math.max(0, (now - this.t0) / seg));
    sampleSplineAt(this.pos, u, outPos);
    sampleSplineAt(this.tgt, u, outTarget);
    return { u, index: Math.min(n - 1, Math.floor(u + 1e-9)), done: n <= 1 || u >= n - 1 };
  }

  /** Keyframe indices newly reached since the last call (in order). Index 0 is reported on the first call. */
  reached(s: PlaybackSample): number[] {
    const out: number[] = [];
    for (let i = this.reported + 1; i <= s.index; i++) out.push(i);
    if (s.index > this.reported) this.reported = s.index;
    return out;
  }
}

// ---------------------------------------------------------------- persistence

function isVec3(v: unknown): v is [number, number, number] {
  return Array.isArray(v) && v.length === 3 && v.every((x) => typeof x === 'number' && Number.isFinite(x));
}

function parseToggles(v: unknown): KeyframeToggles {
  const out: KeyframeToggles = {};
  if (!v || typeof v !== 'object') return out;
  const o = v as Record<string, unknown>;
  for (const k of ['reveal', 'sweep', 'depthGrade', 'bloom', 'edgeGlow', 'ao', 'vignette'] as const) {
    if (typeof o[k] === 'boolean') out[k] = o[k] as boolean;
  }
  return out;
}

/** Validate a keyframe-like object; null when position/target are not three finite numbers. */
export function parseKeyframe(v: unknown): Keyframe | null {
  if (!v || typeof v !== 'object') return null;
  const o = v as Record<string, unknown>;
  if (!isVec3(o['position']) || !isVec3(o['target'])) return null;
  const sel = Array.isArray(o['selection']) ? o['selection'].filter((x): x is string => typeof x === 'string') : [];
  const k: Keyframe = { position: [...o['position']], target: [...o['target']], selection: sel, toggles: parseToggles(o['toggles']) };
  if (typeof o['name'] === 'string') k.name = o['name'];
  return k;
}

/** Parse stored or imported JSON: the export object or a bare array. Invalid entries are dropped; bad input gives null. */
export function parseKeyframes(text: string | null | undefined): Keyframe[] | null {
  if (!text) return null;
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    return null;
  }
  const list = Array.isArray(data) ? data : (data as { keyframes?: unknown } | null)?.keyframes;
  if (!Array.isArray(list)) return null;
  return list.map(parseKeyframe).filter((k): k is Keyframe => k !== null);
}

export function serializeKeyframes(modelName: string, keys: readonly Keyframe[], segmentS = DEFAULT_SEGMENT_S): string {
  return JSON.stringify({ schema: FLYTHROUGH_SCHEMA, model: modelName, segmentSeconds: segmentS, keyframes: keys }, null, 2);
}

// ---------------------------------------------------------------- recorder

/** Best supported webm mime type for MediaRecorder: vp9, else vp8, else plain webm; null when unsupported. */
export function pickRecorderMime(isTypeSupported: ((t: string) => boolean) | undefined): string | null {
  if (!isTypeSupported) return null;
  for (const m of ['video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm']) if (isTypeSupported(m)) return m;
  return null;
}

export interface Recording {
  blob: Blob;
  mime: string;
  bytes: number;
}

/** Records a canvas with MediaRecorder at 30 fps. start() returns false (and does nothing) when unsupported. */
export class CanvasRecorder {
  private rec: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  private stream: MediaStream | null = null;
  private onDone: ((r: Recording | null) => void) | null = null;

  static get supported(): boolean {
    return typeof MediaRecorder !== 'undefined' && typeof HTMLCanvasElement !== 'undefined' && 'captureStream' in HTMLCanvasElement.prototype;
  }

  get recording(): boolean {
    return this.rec !== null && this.rec.state === 'recording';
  }

  start(canvas: HTMLCanvasElement, onDone: (r: Recording | null) => void): boolean {
    if (!CanvasRecorder.supported) return false;
    const mime = pickRecorderMime((t) => MediaRecorder.isTypeSupported(t));
    if (!mime) return false;
    this.stream = canvas.captureStream(30);
    this.chunks = [];
    this.onDone = onDone;
    const rec = new MediaRecorder(this.stream, { mimeType: mime });
    rec.ondataavailable = (e: BlobEvent) => {
      if (e.data && e.data.size > 0) this.chunks.push(e.data);
    };
    rec.onstop = () => {
      const blob = new Blob(this.chunks, { type: mime });
      this.stream?.getTracks().forEach((t) => t.stop());
      this.stream = null;
      this.rec = null;
      const cb = this.onDone;
      this.onDone = null;
      cb?.({ blob, mime, bytes: blob.size });
    };
    rec.start(250);
    this.rec = rec;
    return true;
  }

  stop(): void {
    if (this.rec && this.rec.state !== 'inactive') this.rec.stop();
  }
}

/** Save a blob as a file download. */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}
