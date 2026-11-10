// The picture side of d3-edge in the browser: what the official processor and backbone do before and after the vision encoder, in plain
// TypeScript (no DOM, no libraries), so it runs in the page and in Node and is checked against the official PyTorch model.
//
//   preprocessPicture  RGBA pixels -> the resized picture (smart_resize, factor 32) -> patches in merge-block order, normalised ((x/255 - 0.5)/0.5)
//   visionInputs       the position inputs of the vision graph: patch rows and columns, the 4 bilinear taps (and weights) into the 48 x 48 learned table
//   expandImagePads    the <|image_pad|> of the prompt, one per picture, becomes one token per merged patch (what the processor does to the text)
//   mropePositions     the 3 rows (T, H, W) of the multimodal rotary positions of a token sequence (Qwen3.5 get_rope_index)
//
// Sources: transformers 5.17.0 (image_processing_qwen2_vl.py, vision_utils.py, modeling_qwen3_5.py) and d3_runtime.py of vllm-sr/d3-edge
// (revision bee5e872f75b9c5d1405767bf244a6948b95c0af): patch 16, temporal patch 2 (a still picture is two equal frames, which the export folds into
// one), merge 2, at most 1,638,400 and at least 65,536 pixels per picture.

export interface VisionParams {
  patchSize: number;
  mergeSize: number;
  posGrid: number;
  minPixels: number;
  maxPixels: number;
}

export const VISION_DEFAULTS: VisionParams & { imageToken: string; mean: number; std: number } = {
  patchSize: 16,
  mergeSize: 2,
  posGrid: 48,
  minPixels: 65_536,
  maxPixels: 1_638_400,
  imageToken: '<|image_pad|>',
  mean: 0.5,
  std: 0.5,
};

export interface Rgba {
  data: ArrayLike<number>;
  width: number;
  height: number;
}

/** Port of smart_resize: both sides a multiple of `factor`, the pixel count within the limits, the aspect ratio kept as near as possible. */
export function smartResize(height: number, width: number, factor = 32, minPixels = VISION_DEFAULTS.minPixels, maxPixels = VISION_DEFAULTS.maxPixels): [number, number] {
  if (Math.max(height, width) / Math.min(height, width) > 200) throw new Error(`The picture has an aspect ratio over 200 (${width} x ${height}).`);
  // Python's round() goes to the nearest even number on a tie.
  const pyRound = (x: number): number => {
    const f = Math.floor(x);
    const d = x - f;
    return d < 0.5 ? f : d > 0.5 ? f + 1 : f % 2 === 0 ? f : f + 1;
  };
  let h = pyRound(height / factor) * factor;
  let w = pyRound(width / factor) * factor;
  if (h * w > maxPixels) {
    const beta = Math.sqrt((height * width) / maxPixels);
    h = Math.max(factor, Math.floor(height / beta / factor) * factor);
    w = Math.max(factor, Math.floor(width / beta / factor) * factor);
  } else if (h * w < minPixels) {
    const beta = Math.sqrt(minPixels / (height * width));
    h = Math.ceil((height * beta) / factor) * factor;
    w = Math.ceil((width * beta) / factor) * factor;
  }
  return [h, w];
}

/** Number of tokens a picture takes in the prompt after the vision merger. */
export function pictureTokens(width: number, height: number, p: Pick<VisionParams, 'patchSize' | 'mergeSize'> = VISION_DEFAULTS): number {
  const [h, w] = smartResize(height, width, p.patchSize * p.mergeSize);
  return (h / p.patchSize) * (w / p.patchSize) / (p.mergeSize * p.mergeSize);
}

/**
 * Resize RGBA to (dw, dh), three channels, uint8 result: separable bicubic (Keys, a = -0.5) with the kernel widened on a reduction (antialias),
 * which is what Pillow and torchvision's `antialias=True` do. It runs only when the picture is not already a multiple of 32 pixels; the pictures
 * of the viewer are, so they are never resized. Not bit-identical with torchvision (rounding between the two passes).
 */
export function resizeRgb(src: Rgba, dw: number, dh: number): Uint8Array {
  const { width: sw, height: sh } = src;
  const taps = (inSize: number, outSize: number): { start: Int32Array; w: Float64Array[] } => {
    const scale = inSize / outSize;
    const filterScale = Math.max(scale, 1);
    const support = 2 * filterScale;
    const start = new Int32Array(outSize);
    const w: Float64Array[] = [];
    const key = (x: number): number => {
      x = Math.abs(x);
      const a = -0.5;
      if (x < 1) return ((a + 2) * x - (a + 3)) * x * x + 1;
      if (x < 2) return (((x - 5) * x + 8) * x - 4) * a;
      return 0;
    };
    for (let o = 0; o < outSize; o++) {
      const center = (o + 0.5) * scale;
      const lo = Math.max(0, Math.floor(center - support + 0.5));
      const hi = Math.min(inSize, Math.floor(center + support + 0.5));
      const ws = new Float64Array(hi - lo);
      let sum = 0;
      for (let i = lo; i < hi; i++) { const v = key((i + 0.5 - center) / filterScale); ws[i - lo] = v; sum += v; }
      for (let i = 0; i < ws.length; i++) ws[i]! /= sum || 1;
      start[o] = lo;
      w.push(ws);
    }
    return { start, w };
  };
  const tx = taps(sw, dw);
  const ty = taps(sh, dh);
  const mid = new Float64Array(dw * sh * 3);
  for (let y = 0; y < sh; y++) {
    for (let x = 0; x < dw; x++) {
      const ws = tx.w[x]!;
      const s0 = tx.start[x]!;
      for (let c = 0; c < 3; c++) {
        let acc = 0;
        for (let i = 0; i < ws.length; i++) acc += ws[i]! * src.data[((y * sw) + s0 + i) * 4 + c]!;
        mid[(y * dw + x) * 3 + c] = Math.min(255, Math.max(0, Math.round(acc)));
      }
    }
  }
  const out = new Uint8Array(dw * dh * 3);
  for (let y = 0; y < dh; y++) {
    const ws = ty.w[y]!;
    const s0 = ty.start[y]!;
    for (let x = 0; x < dw; x++) {
      for (let c = 0; c < 3; c++) {
        let acc = 0;
        for (let i = 0; i < ws.length; i++) acc += ws[i]! * mid[((s0 + i) * dw + x) * 3 + c]!;
        out[(y * dw + x) * 3 + c] = Math.min(255, Math.max(0, Math.round(acc)));
      }
    }
  }
  return out;
}

export interface Patches {
  /** [N, 3 * patch * patch] float32, patches in merge-block order, channel-major inside a patch. */
  pixels: Float32Array;
  gridH: number;
  gridW: number;
  /** Rows and columns of the patches, [N, 2] (the vision graph's `pos_hw`). */
  hw: BigInt64Array;
  /** Tokens after the merger. */
  tokens: number;
  resized: boolean;
}

/** RGBA of a picture (alpha is dropped: the processor converts to RGB) -> the inputs of the vision graph, except the position taps. */
export function preprocessPicture(img: Rgba, p: VisionParams = VISION_DEFAULTS): Patches {
  const factor = p.patchSize * p.mergeSize;
  const [rh, rw] = smartResize(img.height, img.width, factor, p.minPixels, p.maxPixels);
  const resized = rh !== img.height || rw !== img.width;
  const rgb = resized ? resizeRgb(img, rw, rh) : null;
  const px = (x: number, y: number, c: number): number => (rgb ? rgb[(y * rw + x) * 3 + c]! : img.data[(y * img.width + x) * 4 + c]!);
  const gh = rh / p.patchSize;
  const gw = rw / p.patchSize;
  const m = p.mergeSize;
  const ps = p.patchSize;
  const dim = 3 * ps * ps;
  const pixels = new Float32Array(gh * gw * dim);
  const hw = new BigInt64Array(gh * gw * 2);
  let n = 0;
  const k = 1 / 255 / VISION_DEFAULTS.std;
  const off = -VISION_DEFAULTS.mean / VISION_DEFAULTS.std;
  for (let bh = 0; bh < gh / m; bh++) {
    for (let bw = 0; bw < gw / m; bw++) {
      for (let mh = 0; mh < m; mh++) {
        for (let mw = 0; mw < m; mw++) {
          const row = bh * m + mh;
          const col = bw * m + mw;
          let o = n * dim;
          for (let c = 0; c < 3; c++) {
            for (let y = 0; y < ps; y++) {
              for (let x = 0; x < ps; x++) pixels[o++] = Math.fround(Math.fround(px(col * ps + x, row * ps + y, c) * k) + off);
            }
          }
          hw[n * 2] = BigInt(row);
          hw[n * 2 + 1] = BigInt(col);
          n++;
        }
      }
    }
  }
  return { pixels, gridH: gh, gridW: gw, hw, tokens: (gh * gw) / (m * m), resized };
}

/**
 * Bilinear taps (align_corners = True) of the learned `posGrid` x `posGrid` position table for every patch of a grid, in the patch order of
 * `preprocessPicture`: the 4 indices into the flattened table and their weights (vision_utils.get_vision_interpolation_indices_and_weights).
 */
export function visionInputs(gridH: number, gridW: number, hw: BigInt64Array, side = VISION_DEFAULTS.posGrid): { idx: BigInt64Array; w: Float32Array } {
  const n = gridH * gridW;
  const idx = new BigInt64Array(n * 4);
  const w = new Float32Array(n * 4);
  const axis = (i: number, size: number): { t: [number, number]; w: [number, number] } => {
    const src = Math.fround(Math.fround(i * (side - 1)) / Math.max(size - 1, 1));
    const fl = Math.floor(src);
    const clamp = (v: number): number => Math.min(side - 1, Math.max(0, v));
    return { t: [clamp(fl), clamp(fl + 1)], w: [Math.max(0, 1 - Math.abs(src - fl)), Math.max(0, 1 - Math.abs(src - fl - 1))] };
  };
  for (let i = 0; i < n; i++) {
    const r = axis(Number(hw[i * 2]), gridH);
    const c = axis(Number(hw[i * 2 + 1]), gridW);
    for (let a = 0; a < 2; a++) {
      for (let b = 0; b < 2; b++) {
        idx[i * 4 + a * 2 + b] = BigInt(r.t[a]! * side + c.t[b]!);
        w[i * 4 + a * 2 + b] = Math.fround(r.w[a]! * c.w[b]!);
      }
    }
  }
  return { idx, w };
}

/** The prompt text with every picture placeholder expanded to its token count (the processor does this before it tokenizes). */
export function expandImagePads(text: string, counts: readonly number[], token: string = VISION_DEFAULTS.imageToken): string {
  let i = 0;
  const out = text.replace(new RegExp(token.replace(/[|]/g, '\\$&'), 'g'), () => {
    const n = counts[i++];
    if (n === undefined) throw new Error('The prompt has more picture placeholders than pictures.');
    return token.repeat(n);
  });
  if (i !== counts.length) throw new Error(`The prompt has ${i} picture placeholders for ${counts.length} pictures.`);
  return out;
}

/**
 * The multimodal rotary positions [3, L] (T, H, W rows, row-major, as int64) of a token sequence: text runs count up from the current position on
 * all 3 rows; a run of picture tokens takes the next grid (rows and columns after the merge) and gets (start, start + row, start + column), and the
 * position then moves on by max(rows, columns) (Qwen3_5Model.get_rope_index). `grids` are the merged grids [rows, columns] of the pictures in order.
 */
export function mropePositions(ids: ArrayLike<number>, imageTokenId: number, grids: ReadonlyArray<readonly [number, number]>): BigInt64Array {
  const L = ids.length;
  const out = new BigInt64Array(3 * L);
  let pos = 0;
  let g = 0;
  let i = 0;
  while (i < L) {
    const image = ids[i] === imageTokenId;
    let j = i;
    while (j < L && (ids[j] === imageTokenId) === image) j++;
    if (!image) {
      for (let k = i; k < j; k++) for (let r = 0; r < 3; r++) out[r * L + k] = BigInt(pos + (k - i));
      pos += j - i;
    } else {
      const grid = grids[g++];
      if (!grid) throw new Error('The prompt has more runs of picture tokens than pictures.');
      const [gh, gw] = grid;
      if (gh * gw !== j - i) throw new Error(`A run of ${j - i} picture tokens does not match its grid of ${gh} x ${gw}.`);
      for (let k = i; k < j; k++) {
        const t = k - i;
        out[k] = BigInt(pos);
        out[L + k] = BigInt(pos + Math.floor(t / gw));
        out[2 * L + k] = BigInt(pos + (t % gw));
      }
      pos += Math.max(gh, gw);
    }
    i = j;
  }
  if (g !== grids.length) throw new Error(`The prompt has ${g} runs of picture tokens for ${grids.length} pictures.`);
  return out;
}

/** Text positions: 0..L-1 on all 3 rows. */
export function textPositions(L: number): BigInt64Array {
  const out = new BigInt64Array(3 * L);
  for (let r = 0; r < 3; r++) for (let k = 0; k < L; k++) out[r * L + k] = BigInt(k);
  return out;
}
