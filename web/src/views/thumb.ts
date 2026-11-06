// Thumbnail of the canvas for a saved view: a THUMB_W x THUMB_H JPEG data URL, cropped to cover.
// Same approach as the BCF snapshot (src/bcf/controller.ts): render a frame and read the canvas in the same task, so the
// WebGL context needs no preserveDrawingBuffer.

import type { ViewerApp } from '../app';
import { THUMB_H, THUMB_W } from './model';

/** Source rectangle of a cover crop: the largest centred part of a w x h image with the thumbnail's aspect. */
export function coverCrop(w: number, h: number, tw = THUMB_W, th = THUMB_H): { sx: number; sy: number; sw: number; sh: number } {
  const s = Math.max(tw / w, th / h);
  const sw = Math.min(w, tw / s);
  const sh = Math.min(h, th / s);
  return { sx: (w - sw) / 2, sy: (h - sh) / 2, sw, sh };
}

export function captureThumb(app: ViewerApp): string | undefined {
  try {
    const r = app.renderer;
    r.markDirty();
    r.render();
    const src = app.canvas;
    const w = src.width;
    const h = src.height;
    if (!w || !h) return undefined;
    const oc = document.createElement('canvas');
    oc.width = THUMB_W;
    oc.height = THUMB_H;
    const g = oc.getContext('2d');
    if (!g) return undefined;
    g.fillStyle = '#e9edf2'; // the clear colour of the renderer, under any transparent pixel
    g.fillRect(0, 0, THUMB_W, THUMB_H);
    g.imageSmoothingQuality = 'high';
    const c = coverCrop(w, h);
    g.drawImage(src, c.sx, c.sy, c.sw, c.sh, 0, 0, THUMB_W, THUMB_H);
    return oc.toDataURL('image/jpeg', 0.72);
  } catch {
    return undefined;
  }
}
