// Output sizes of a video export and the render-size switch: the renderer is resized to the video size for the export and put
// back exactly afterwards. Pure apart from the renderer it is given (an interface, tested with a fake).

/** A listed size, 'window', or a custom `WxH` string that a script passes. */
export type SizeChoice = 'window' | '1280x720' | '1920x1080' | '2560x1440' | '3840x2160' | (string & {});
export const SIZE_CHOICES: ReadonlyArray<{ id: SizeChoice; label: string }> = [
  { id: 'window', label: 'The window' },
  { id: '1280x720', label: '1280 x 720 (HD)' },
  { id: '1920x1080', label: '1920 x 1080 (Full HD)' },
  { id: '2560x1440', label: '2560 x 1440 (QHD)' },
  { id: '3840x2160', label: '3840 x 2160 (4K)' },
];

export interface OutputSize {
  width: number;
  height: number;
}

const even = (n: number): number => Math.max(2, Math.round(n / 2) * 2);

/** The size for a choice. Video encoders want even sides, so odd window sizes round. `maxSide` (the graphics card's limit) scales
 *  the size down, keeping the aspect ratio. */
export function resolveOutputSize(choice: SizeChoice, windowSize: OutputSize, maxSide = 8192): OutputSize {
  let w: number;
  let h: number;
  if (choice === 'window') {
    w = windowSize.width;
    h = windowSize.height;
  } else {
    const m = /^(\d+)x(\d+)$/.exec(choice);
    w = m ? Number(m[1]) : windowSize.width;
    h = m ? Number(m[2]) : windowSize.height;
  }
  if (!(w > 0) || !(h > 0)) {
    w = 1280;
    h = 720;
  }
  const k = Math.min(1, maxSide / Math.max(w, h));
  return { width: even(w * k), height: even(h * k) };
}

/** What the exporter needs of the renderer (XrayRenderer implements it). */
export interface SizableRenderer {
  /** Render at this size in pixels until clearOutputSize(). */
  setOutputSize(width: number, height: number): void;
  /** Back to the size of the canvas element. */
  clearOutputSize(): void;
  /** Pixels per side the graphics card can draw. */
  maxOutputSide?(): number;
  markDirty(): void;
}

/** Run `fn` with the renderer at `size`; the size is restored whatever happens (also when `fn` throws or rejects). */
export async function withOutputSize<T>(r: SizableRenderer, size: OutputSize, fn: () => Promise<T> | T): Promise<T> {
  r.setOutputSize(size.width, size.height);
  try {
    return await fn();
  } finally {
    try {
      r.clearOutputSize();
    } finally {
      r.markDirty();
    }
  }
}

/** The HUD scale of a video: pixels of the video per CSS pixel of the on-screen view, so captions have the size they have on screen
 *  relative to the picture (a 4K video does not get tiny text). */
export function hudPixelRatio(size: OutputSize, cssHeight: number): number {
  return Math.max(0.25, size.height / Math.max(1, cssHeight));
}
