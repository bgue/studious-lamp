// The frame loop of a video export: for every frame, apply it to the viewer (the caller's `step`), composite the WebGL canvas and the
// HUD layer into a 2D canvas of the video size, hand it to a sink (an encoder or a PNG zip). Nothing here reads the wall clock for
// the animation: frame i is score time i / fps however long the machine takes. Pure apart from the canvases it is given.

import type { HudFrame, HudLayer } from '../hud';
import type { V3 } from '../score';
import { etaMs, frameTime } from './schedule';

export interface FrameSink {
  /** Called once before the first frame, with the composite canvas that every `add` hands over again. */
  start(canvas: CanvasLike): Promise<void>;
  /** Encode or store the frame in `canvas` (the composite). Resolves when the sink can take the next one (backpressure). */
  add(canvas: CanvasLike, index: number, time: number, duration: number): Promise<void>;
  /** Finish the file. */
  finish(): Promise<ExportFile>;
  /** Abandon: free everything, produce nothing. Safe to call twice. */
  cancel(): Promise<void>;
}

export interface ExportFile {
  blob: Blob;
  mime: string;
  extension: string;
  /** Frames the sink took. */
  frames: number;
  /** What encoded it, for the message ("H.264 in MP4"). */
  description: string;
}

export interface Ctx2DLike {
  clearRect(x: number, y: number, w: number, h: number): void;
  drawImage(img: unknown, dx: number, dy: number, dw?: number, dh?: number): void;
  fillStyle: unknown;
  fillRect(x: number, y: number, w: number, h: number): void;
}
export interface CanvasLike {
  width: number;
  height: number;
  getContext(kind: '2d', opts?: unknown): unknown;
}

export interface Progress {
  done: number;
  total: number;
  elapsedMs: number;
  etaMs: number | null;
  /** Score time of the frame just done, seconds. */
  time: number;
}

export interface FrameLoopDeps {
  frames: number;
  fps: number;
  width: number;
  height: number;
  /** Score duration for the HUD's progress bar. */
  duration: number;
  /** Apply frame `index` at score time `t`: advance the player, run the viewer's frame, render. Returns the player clock. */
  step(index: number, t: number): number | void;
  /** The WebGL canvas, valid right after `step`. */
  source: unknown;
  /** World point to video pixels (CSS pixels of the HUD, see HudFrame.project). */
  project(p: V3): { x: number; y: number } | null;
  hud: HudLayer | null;
  /** Video pixels per HUD CSS pixel. */
  hudPixelRatio: number;
  sink: FrameSink;
  isCancelled(): boolean;
  onProgress(p: Progress): void;
  /** Give the browser a turn (progress UI, cancel button). */
  yieldTurn(): Promise<void>;
  now(): number;
  makeCanvas(width: number, height: number): CanvasLike;
}

export type FrameLoopResult = { kind: 'done'; file: ExportFile } | { kind: 'cancelled' };

/** Run the loop. The sink is cancelled on cancel and on error; on error the error is rethrown. */
export async function runFrameLoop(d: FrameLoopDeps): Promise<FrameLoopResult> {
  const out = d.makeCanvas(d.width, d.height);
  const g = out.getContext('2d') as Ctx2DLike | null;
  if (!g) throw new Error('No 2D canvas for the video frames');
  let hudCanvas: CanvasLike | null = null;
  let hg: Ctx2DLike | null = null;
  const t0 = d.now();
  const dur = 1 / d.fps;
  try {
    await d.sink.start(out);
    for (let i = 0; i < d.frames; i++) {
      if (d.isCancelled()) {
        await d.sink.cancel();
        return { kind: 'cancelled' };
      }
      const t = frameTime(i, d.fps);
      const clock = d.step(i, t);
      const ht = typeof clock === 'number' ? clock : t;
      g.drawImage(d.source, 0, 0, d.width, d.height);
      if (d.hud && d.hud.active(ht)) {
        if (!hudCanvas) {
          hudCanvas = d.makeCanvas(d.width, d.height);
          hg = hudCanvas.getContext('2d') as Ctx2DLike | null;
        }
        if (hg && hudCanvas) {
          hg.clearRect(0, 0, d.width, d.height);
          const frame: HudFrame = {
            t: ht,
            duration: d.duration,
            width: d.width / d.hudPixelRatio,
            height: d.height / d.hudPixelRatio,
            pixelRatio: d.hudPixelRatio,
            project: d.project,
            recording: true,
          };
          d.hud.draw(hg as unknown as CanvasRenderingContext2D, frame);
          g.drawImage(hudCanvas, 0, 0, d.width, d.height);
        }
      }
      await d.sink.add(out, i, t, dur);
      const elapsed = d.now() - t0;
      d.onProgress({ done: i + 1, total: d.frames, elapsedMs: elapsed, etaMs: etaMs(i + 1, d.frames, elapsed), time: t });
      await d.yieldTurn();
    }
    if (d.isCancelled()) {
      await d.sink.cancel();
      return { kind: 'cancelled' };
    }
    return { kind: 'done', file: await d.sink.finish() };
  } catch (e) {
    try {
      await d.sink.cancel();
    } catch {
      /* the first error is the one to report */
    }
    throw e;
  }
}
