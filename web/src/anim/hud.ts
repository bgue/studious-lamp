// The HUD contract: everything drawn over the 3D view during playback (captions, element labels, the hover card, the progress bar,
// compass and scale bar) is drawn by ONE layer into a 2D canvas context. On screen the layer draws into an overlay canvas over the
// viewer; the video exporter (src/anim/record) composites the WebGL frame and the same layer into each video frame, so what you see
// is what you record.
//
// Contract between the HUD work (phase 2) and the video export work (phase 3). Change it ADDITIVELY only.

import type { V3 } from './score';

export interface HudFrame {
  /** Seconds into the score (the player's clock, also when the exporter steps frame by frame). */
  t: number;
  /** Score duration in seconds (for the progress bar). */
  duration: number;
  /** Size of the target in CSS pixels (on screen: the viewer canvas; in a video: the video size divided by `pixelRatio`). */
  width: number;
  height: number;
  /** Device pixels per CSS pixel of the target; the layer scales its own drawing by this. */
  pixelRatio: number;
  /** World point to target CSS pixels for THIS frame's camera and size; null when behind the camera or off the frame. */
  project(p: V3): { x: number; y: number } | null;
  /** True while exporting a video (the layer may hide on-screen-only bits such as hints). */
  recording: boolean;
}

export interface HudLayer {
  /** Draw this frame. The context is already cleared to transparent and sized to width*pixelRatio x height*pixelRatio. */
  draw(ctx: CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D, frame: HudFrame): void;
  /** True when the layer has something to draw at `t` (the exporter skips compositing otherwise). */
  active(t: number): boolean;
}

let layer: HudLayer | null = null;
export function setHudLayer(l: HudLayer | null): void {
  layer = l;
}
export function getHudLayer(): HudLayer | null {
  return layer;
}
