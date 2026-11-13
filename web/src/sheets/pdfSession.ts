// The lazy half of sheets: this module and everything it imports (the PDF libraries, the reader and the writer) are only loaded
// by a dynamic import from controller.ts, the first time a PDF is opened or exported. Nothing here is in the main chunk.

import type * as PdfJs from 'pdfjs-dist';
import { loadPdfLibs } from './pdfRuntime';
import type { PdfLibs } from './pdfRuntime';
import * as read from './pdfRead';
import * as write from './pdfWrite';

export interface PdfSession {
  libs: PdfLibs;
  read: typeof read;
  write: typeof write;
}

export async function session(): Promise<PdfSession> {
  const libs = await loadPdfLibs();
  return { libs, read, write };
}

export interface RenderRequest {
  page: PdfJs.PDFPageProxy;
  canvas: HTMLCanvasElement;
  /** Pixels per point. */
  scale: number;
  /** The part of the page to draw, in pixels at `scale` from the page's top left (default all). */
  region?: { x: number; y: number; w: number; h: number };
}

/** Draw a page (without its annotations: those are drawn by the viewer as sketches) onto a canvas. Returns a cancel function and the promise. */
export function renderPage(req: RenderRequest): { promise: Promise<void>; cancel: () => void } {
  const { page, canvas, scale } = req;
  const vp = page.getViewport({ scale, ...(req.region ? { offsetX: -req.region.x, offsetY: -req.region.y } : {}) });
  const w = req.region ? Math.max(1, Math.round(req.region.w)) : Math.max(1, Math.round(vp.width));
  const h = req.region ? Math.max(1, Math.round(req.region.h)) : Math.max(1, Math.round(vp.height));
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('No 2D canvas');
  const task = page.render({ canvasContext: ctx, viewport: vp, annotationMode: 0, background: '#ffffff' } as never);
  return { promise: task.promise.then(() => undefined), cancel: () => task.cancel() };
}
