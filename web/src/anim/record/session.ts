// The video export of the viewer: plays a score frame by frame at a fixed step and encodes it. This file is the glue between the
// pure parts (schedule, size, encoder choice, frame loop, sinks) and the viewer (renderer size, frame loop, score player, HUD).
//
// How a frame is made: the viewer's own animation loop is stopped; for frame i the exporter advances the score player by 1 / fps,
// calls app.stepFrame (plugin hooks, controller step, renderer draw, post effects) with its own clock, copies the WebGL canvas
// into a 2D canvas of the video size, draws the HUD layer over it and hands the canvas to the encoder. Nothing reads the wall
// clock for the animation, so a slow machine makes a slow export, not a stuttering video.

import { Vector3 } from 'three';
import type { ViewerApp } from '../../app';
import { CanvasRecorder, downloadBlob } from '../../cinematic/flythrough';
import { getHudLayer } from '../hud';
import type { HudFrame } from '../hud';
import type { ScorePlayer } from '../player';
import type { Score } from '../score';
import { scoreEnd } from '../score';
import { bitrateFor, browserSupportFn, chooseEncoder } from './encoder';
import type { EncoderChoice } from './encoder';
import { runFrameLoop } from './frames';
import type { CanvasLike, ExportFile, FrameSink } from './frames';
import { fileBase, sanitizeOptions } from './options';
import type { ExportOptions } from './options';
import { frameCount } from './schedule';
import { PngZipSink, VideoFileSink, canvasToPng } from './sinks';
import { hudPixelRatio, resolveOutputSize, withOutputSize } from './size';
import type { OutputSize } from './size';
import { openBusyOverlay } from './ui';
import type { BusyOverlay } from './ui';

/** What the exporter needs of the plugin that owns the player. */
export interface RecordLink {
  player: ScorePlayer;
  /** On: the player is stepped by the exporter, settings apply on every frame, the camera path overlay is off. Off: back to normal. */
  setExporting(on: boolean): void;
}

export interface RecordResult {
  ok: boolean;
  cancelled?: boolean;
  /** Why it failed or what changed (shown to the person). */
  message: string;
  /** Which way it was recorded. */
  path?: 'frames' | 'realtime';
  file?: { name: string; bytes: number; mime: string; frames: number; description: string; width: number; height: number; fps: number };
}

export interface Capabilities {
  webcodecs: boolean;
  mediaRecorder: boolean;
}

export function capabilities(): Capabilities {
  return { webcodecs: browserSupportFn() !== null, mediaRecorder: CanvasRecorder.supported };
}

/** One sentence for the dialog about what this browser records with. */
export function describeCapabilities(c: Capabilities): string {
  if (c.webcodecs) return 'This browser encodes video frame by frame, so a slow machine still gives a smooth video.';
  if (c.mediaRecorder) return 'This browser cannot encode frame by frame. Automatic format records in real time at the window size instead.';
  return 'This browser cannot record video. Automatic format writes PNG frames in a zip file instead.';
}

const yieldTurn = (): Promise<void> =>
  new Promise((res) => {
    const ch = new MessageChannel();
    ch.port1.onmessage = () => {
      ch.port1.close();
      res();
    };
    ch.port2.postMessage(0);
  });

export class Recorder {
  busy = false;
  last: RecordResult | null = null;
  /** The file of the last successful recording (for tests and scripts; dropped with the next recording). */
  lastBlob: Blob | null = null;
  private cancelled = false;
  private realtimeStop: (() => void) | null = null;
  /** Set while a real-time recording composites frames from afterFrame(). */
  private compositor: (() => void) | null = null;

  constructor(
    private readonly app: ViewerApp,
    private readonly link: RecordLink,
  ) {}

  cancel(): void {
    this.cancelled = true;
    this.realtimeStop?.();
  }

  /** The viewer's frame hook calls this after every draw (the real-time path composites its frame here). */
  afterFrame(): void {
    this.compositor?.();
  }

  windowSize(): OutputSize {
    return { width: this.app.canvas.width || 1280, height: this.app.canvas.height || 720 };
  }

  maxSide(): number {
    try {
      return this.app.renderer.maxOutputSide();
    } catch {
      return 4096;
    }
  }

  /** Check what blocks an export; null when it can start. */
  blocker(): string | null {
    if (this.busy) return 'A video is already being recorded.';
    if (!this.app.loaded) return 'Open a model first.';
    if (this.app.renderer.xrPresenting) return 'Leave the headset session before you record.';
    return null;
  }

  // ---------------------------------------------------------------- export

  /** Record `score`. Never throws: the result says what happened. Downloads the file unless `download` is false. */
  async run(score: Score, optsIn: Partial<ExportOptions>, hooks: { download?: boolean; onDone?: (r: RecordResult) => void } = {}): Promise<RecordResult> {
    const why = this.blocker();
    if (why) return this.finish({ ok: false, message: why }, hooks);
    const opts = sanitizeOptions(optsIn);
    const name = fileBase(opts.name);
    this.busy = true;
    this.cancelled = false;
    let overlay: BusyOverlay | null = null;
    try {
      if (this.link.player.playing) this.link.player.stop();
      const plan = await this.plan(opts);
      if (plan.kind === 'error') return this.finish({ ok: false, message: plan.message }, hooks);
      overlay = openBusyOverlay(plan.kind === 'realtime' ? 'Recording in real time' : 'Recording a video', () => this.cancel(), { dim: plan.kind !== 'realtime' });
      const res = plan.kind === 'realtime' ? await this.runRealtime(score, opts, plan.prefer, overlay) : await this.runFrames(score, opts, plan, overlay);
      if (res.cancelled) return this.finish({ ok: false, cancelled: true, message: 'Recording cancelled.' }, hooks);
      const file = res.file!;
      this.lastBlob = file.blob;
      if (hooks.download !== false) downloadBlob(file.blob, `${name}.${file.extension}`);
      return this.finish(
        {
          ok: true,
          path: plan.kind === 'realtime' ? 'realtime' : 'frames',
          message: `Saved ${name}.${file.extension} (${(file.blob.size / 1024 / 1024).toFixed(1)} MB, ${file.description}, ${file.frames} frames).`,
          file: { name: `${name}.${file.extension}`, bytes: file.blob.size, mime: file.mime, frames: file.frames, description: file.description, width: res.width, height: res.height, fps: res.fps },
        },
        hooks,
      );
    } catch (e) {
      console.error('video export failed', e);
      return this.finish({ ok: false, message: `The video could not be recorded: ${e instanceof Error ? e.message : String(e)}` }, hooks);
    } finally {
      overlay?.close();
      this.busy = false;
      this.compositor = null;
      this.realtimeStop = null;
    }
  }

  private finish(r: RecordResult, hooks: { onDone?: (r: RecordResult) => void }): RecordResult {
    this.last = r;
    hooks.onDone?.(r);
    return r;
  }

  /** Decide how to record: which size, which encoder, or the fallback. */
  private async plan(opts: ExportOptions): Promise<
    | { kind: 'video'; size: OutputSize; choice: EncoderChoice; bitrate: number }
    | { kind: 'png'; size: OutputSize }
    | { kind: 'realtime'; prefer: 'webm' | 'mp4' }
    | { kind: 'error'; message: string }
  > {
    const size = resolveOutputSize(opts.size, this.windowSize(), this.maxSide());
    if (opts.format === 'png') return { kind: 'png', size };
    const support = browserSupportFn();
    if (support) {
      const bitrate = bitrateFor(size.width, size.height, opts.fps, opts.quality);
      const choice = await chooseEncoder(opts.format, { width: size.width, height: size.height, fps: opts.fps, bitrate }, support);
      if (choice) return { kind: 'video', size, choice, bitrate };
      if (opts.format !== 'auto') return { kind: 'error', message: `This browser cannot encode ${opts.format === 'mp4' ? 'MP4 (H.264)' : 'WebM'} at ${size.width} x ${size.height}. Try Automatic, a smaller size, or PNG frames.` };
    }
    if (opts.format === 'auto' || !support) {
      if (CanvasRecorder.supported) return { kind: 'realtime', prefer: opts.format === 'mp4' ? 'mp4' : 'webm' };
      return { kind: 'png', size };
    }
    return { kind: 'error', message: 'This browser cannot record video.' };
  }

  // ---------------------------------------------------------------- the frame loop path

  private async runFrames(
    score: Score,
    opts: ExportOptions,
    plan: { kind: 'video'; size: OutputSize; choice: EncoderChoice; bitrate: number } | { kind: 'png'; size: OutputSize },
    overlay: BusyOverlay | null,
    limit?: number,
  ): Promise<{ cancelled: boolean; file?: ExportFile; width: number; height: number; fps: number }> {
    const sink: FrameSink = limit !== undefined ? nullSink() : plan.kind === 'video' ? new VideoFileSink({ choice: plan.choice, fps: opts.fps, bitrate: plan.bitrate }) : new PngZipSink(canvasToPng, fileBase(opts.name));
    const total = frameCount(Math.max(score.duration, scoreEnd(score.cues)), opts.fps);
    const frames = limit !== undefined ? Math.min(limit, total) : total;
    const out = await this.drive(score, opts, plan.size, frames, sink, overlay);
    return { cancelled: out.kind === 'cancelled', ...(out.kind === 'done' ? { file: out.file } : {}), width: plan.size.width, height: plan.size.height, fps: opts.fps };
  }

  /** Time a few frames at the options (for the dialog's estimate): milliseconds per frame, or null. */
  async timeFrames(score: Score, optsIn: Partial<ExportOptions>): Promise<number | null> {
    if (this.blocker()) return null;
    if (!browserSupportFn() && optsIn.format !== 'png') return null;
    const opts = sanitizeOptions(optsIn);
    const size = resolveOutputSize(opts.size, this.windowSize(), this.maxSide());
    this.busy = true;
    this.cancelled = false;
    try {
      const marks: number[] = [];
      const total = frameCount(Math.max(score.duration, scoreEnd(score.cues)), opts.fps);
      await this.drive(score, opts, size, Math.min(4, total), nullSink(), null, (p) => void marks.push(p.elapsedMs));
      if (marks.length < 2) return marks.length === 1 ? marks[0]! : null;
      // The first frame pays for the shader compile and the buffers; the others show the steady cost.
      return (marks[marks.length - 1]! - marks[0]!) / (marks.length - 1);
    } catch {
      return null;
    } finally {
      this.busy = false;
    }
  }

  private async drive(
    score: Score,
    opts: ExportOptions,
    size: OutputSize,
    frames: number,
    sink: FrameSink,
    overlay: BusyOverlay | null,
    onProgress?: (p: import('./frames').Progress) => void,
  ): ReturnType<typeof runFrameLoop> {
    const app = this.app;
    const link = this.link;
    const duration = Math.max(score.duration, scoreEnd(score.cues));
    const cssHeight = app.canvas.clientHeight || size.height;
    const hudScale = hudPixelRatio(size, cssHeight);
    const hud = opts.hud ? getHudLayer() : null;
    const vbase = performance.now();
    const restoreLoop = app.pauseLoop();
    link.setExporting(true);
    let slowNoted = false;
    const v = new Vector3();
    const cssW = size.width / hudScale;
    const cssH = size.height / hudScale;
    try {
      return await withOutputSize(app.renderer, size, async () => {
        if (!link.player.play(score, { restore: true })) throw new Error('The score player did not start');
        try {
          app.renderer.markDirty();
          return await runFrameLoop({
            frames,
            fps: opts.fps,
            width: size.width,
            height: size.height,
            duration,
            step: (i) => {
              if (i > 0) link.player.advance(1 / opts.fps);
              app.stepFrame(vbase + (i * 1000) / opts.fps);
              return link.player.time;
            },
            source: app.canvas,
            project: ((p) => {
              v.set(p[0], p[1], p[2]).project(app.renderer.camera);
              if (!(v.z > -1 && v.z < 1)) return null;
              const x = ((v.x + 1) / 2) * cssW;
              const y = ((1 - v.y) / 2) * cssH;
              return x < 0 || y < 0 || x > cssW || y > cssH ? null : { x, y };
            }) as HudFrame['project'],
            hud,
            hudPixelRatio: hudScale,
            sink,
            isCancelled: () => this.cancelled,
            onProgress: (p) => {
              overlay?.progress(p);
              onProgress?.(p);
              if (!slowNoted && p.done >= 5 && p.etaMs !== null && p.etaMs > 5 * 60 * 1000) {
                slowNoted = true;
                overlay?.note('This takes a long time on this machine. Cancel and pick a smaller size or a lower frame rate to go faster.');
              }
            },
            yieldTurn,
            now: () => performance.now(),
            makeCanvas: (w, h) => {
              const c = document.createElement('canvas');
              c.width = w;
              c.height = h;
              return c as CanvasLike;
            },
          });
        } finally {
          // Back to the state before the export (camera, selection, hides, settings), while the size is still the video size.
          if (link.player.playing) link.player.stop();
        }
      });
    } finally {
      link.setExporting(false);
      restoreLoop();
      app.renderer.markDirty();
    }
  }

  // ---------------------------------------------------------------- still frames (the storyboard)

  /**
   * Render still frames of `score` at the given score times (seconds): for each the player seeks there (cues and 4D states are
   * evaluated from scratch, so the picture does not depend on the order), the viewer draws one frame at the still size and the canvas
   * is read as JPEG. No HUD: the storyboard puts the date and the legend around the frames. Never throws.
   */
  async stills(
    score: Score,
    times: readonly number[],
    o: { width?: number; height?: number; quality?: number; onProgress?: (done: number, total: number) => void } = {},
  ): Promise<{ ok: true; frames: Array<{ jpeg: Uint8Array; width: number; height: number }> } | { ok: false; cancelled?: boolean; message: string }> {
    const why = this.blocker();
    if (why) return { ok: false, message: why };
    const size = resolveOutputSize(`${o.width ?? 960}x${o.height ?? 540}`, this.windowSize(), this.maxSide());
    const q = Math.min(1, Math.max(0.3, o.quality ?? 0.85));
    const app = this.app;
    const link = this.link;
    this.busy = true;
    this.cancelled = false;
    const overlay = openBusyOverlay('Rendering storyboard frames', () => this.cancel(), { dim: true });
    const restoreLoop = app.pauseLoop();
    link.setExporting(true);
    const out: Array<{ jpeg: Uint8Array; width: number; height: number }> = [];
    try {
      if (link.player.playing) link.player.stop();
      const vbase = performance.now();
      await withOutputSize(app.renderer, size, async () => {
        if (!link.player.play(score, { restore: true })) throw new Error('The score player did not start');
        try {
          const c = document.createElement('canvas');
          c.width = size.width;
          c.height = size.height;
          const g = c.getContext('2d');
          if (!g) throw new Error('No 2D canvas for the frames');
          for (let i = 0; i < times.length; i++) {
            if (this.cancelled) throw new Error('cancelled');
            link.player.seek(Math.max(0, times[i]!));
            app.renderer.markDirty();
            // two frames: the second lets a camera that eases or a fade that started with the seek settle
            app.stepFrame(vbase + i * 40);
            app.stepFrame(vbase + i * 40 + 20);
            g.fillStyle = '#ffffff';
            g.fillRect(0, 0, size.width, size.height);
            g.drawImage(app.canvas, 0, 0, size.width, size.height);
            const blob: Blob | null = await new Promise((res) => c.toBlob(res, 'image/jpeg', q));
            if (!blob) throw new Error('A frame could not be written as JPEG');
            out.push({ jpeg: new Uint8Array(await blob.arrayBuffer()), width: size.width, height: size.height });
            overlay.note(`Frame ${i + 1} of ${times.length}`);
            o.onProgress?.(i + 1, times.length);
            await yieldTurn();
          }
        } finally {
          if (link.player.playing) link.player.stop();
        }
      });
      return { ok: true, frames: out };
    } catch (e) {
      if (this.cancelled) return { ok: false, cancelled: true, message: 'Storyboard cancelled.' };
      return { ok: false, message: `The storyboard frames could not be rendered: ${e instanceof Error ? e.message : String(e)}` };
    } finally {
      overlay.close();
      link.setExporting(false);
      restoreLoop();
      app.renderer.markDirty();
      this.busy = false;
    }
  }

  // ---------------------------------------------------------------- the real-time fallback

  private runRealtime(score: Score, opts: ExportOptions, prefer: 'webm' | 'mp4', overlay: BusyOverlay | null): Promise<{ cancelled: boolean; file?: ExportFile; width: number; height: number; fps: number }> {
    const app = this.app;
    const w = app.canvas.width || 1280;
    const h = app.canvas.height || 720;
    const comp = document.createElement('canvas');
    comp.width = w;
    comp.height = h;
    const g = comp.getContext('2d');
    if (!g) return Promise.reject(new Error('No 2D canvas for the recording'));
    const hudCanvas = document.createElement('canvas');
    hudCanvas.width = w;
    hudCanvas.height = h;
    const hg = hudCanvas.getContext('2d');
    const hud = opts.hud ? getHudLayer() : null;
    const scale = hudPixelRatio({ width: w, height: h }, app.canvas.clientHeight || h);
    const duration = Math.max(score.duration, scoreEnd(score.cues));
    const cam = app.renderer.camera;
    const v = new Vector3();
    this.compositor = () => {
      g.drawImage(app.canvas, 0, 0, w, h);
      const t = this.link.player.time;
      if (hud && hg && hud.active(t)) {
        hg.clearRect(0, 0, w, h);
        hud.draw(hg, {
          t,
          duration,
          width: w / scale,
          height: h / scale,
          pixelRatio: scale,
          recording: true,
          project: (p) => {
            v.set(p[0], p[1], p[2]).project(cam);
            if (!(v.z > -1 && v.z < 1)) return null;
            const x = ((v.x + 1) / 2) * (w / scale);
            const y = ((1 - v.y) / 2) * (h / scale);
            return x < 0 || y < 0 || x > w / scale || y > h / scale ? null : { x, y };
          },
        });
        g.drawImage(hudCanvas, 0, 0, w, h);
      }
    };
    return new Promise((resolve, reject) => {
      const rec = new CanvasRecorder();
      let stopTimer: ReturnType<typeof setTimeout> | null = null;
      let wasCancelled = false;
      const started = rec.start(
        comp,
        (r) => {
          if (stopTimer) clearTimeout(stopTimer);
          this.compositor = null;
          if (wasCancelled || !r || r.bytes === 0) return resolve({ cancelled: wasCancelled, width: w, height: h, fps: opts.fps });
          const ext = r.mime.includes('mp4') ? 'mp4' : 'webm';
          resolve({ cancelled: false, file: { blob: r.blob, mime: r.mime, extension: ext, frames: 0, description: `real-time recording, ${r.mime}` }, width: w, height: h, fps: opts.fps });
        },
        { prefer, fps: opts.fps },
      );
      if (!started) return reject(new Error('This browser cannot record video.'));
      this.realtimeStop = () => {
        wasCancelled = true;
        if (this.link.player.playing) this.link.player.stop();
        rec.stop();
      };
      overlay?.note('The fly-through plays at normal speed and the window size. Press Cancel to stop.');
      const ok = this.link.player.play(score, {
        restore: true,
        onEnd: () => {
          stopTimer = setTimeout(() => rec.stop(), 300);
        },
      });
      if (!ok) {
        rec.stop();
        reject(new Error('The score player did not start'));
      }
    });
  }
}

/** A sink that drops the frames (timing runs). */
function nullSink(): FrameSink {
  return {
    start: async () => {},
    add: async () => {},
    finish: async () => ({ blob: new Blob([]), mime: 'application/octet-stream', extension: 'bin', frames: 0, description: 'timing run' }),
    cancel: async () => {},
  };
}
