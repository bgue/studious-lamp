// The picture side of d3-edge in the browser (providers/d3Vision.ts) against what the OFFICIAL processor and backbone give
// (tests/fixtures/d3-vision-golden.json, written by bench/d3/vision_golden.py with transformers 5.17.0): the resize rule, the patches, the position taps,
// the expanded prompt and the 3-row rotary positions. The same code feeds the vision graph in the page and in Node.

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { D3_CODES, d3Render } from '../src/classify/providers/d3Format';
import { expandImagePads, mropePositions, pictureTokens, preprocessPicture, resizeRgb, smartResize, textPositions, visionInputs } from '../src/classify/providers/d3Vision';

interface Golden {
  smart_resize: Array<{ h: number; w: number; out: [number, number] }>;
  pictures: Array<{
    w: number; h: number; gridH: number; gridW: number; patches: number; pixelSum: number; pixelAbsMax: number;
    pixelSamples: Array<{ patch: number; values: number[] }>; idxSum: number; idxSamples: Array<{ patch: number; idx: number[]; w: number[] }>; wSum: number;
  }>;
  prompt: { text: string; tokens: number[]; grids: number[][]; positions: number[][]; imageTokenId: number };
}
const G = JSON.parse(readFileSync(fileURLToPath(new URL('./fixtures/d3-vision-golden.json', import.meta.url)), 'utf8')) as Golden;

/** The procedural picture of bench/d3/vision_golden.py: pixel(x, y, c) = (7 x + 13 y + 50 c + 31 (x y % 5)) % 256, as RGBA. */
function picture(w: number, h: number): { data: Uint8Array; width: number; height: number } {
  const data = new Uint8Array(w * h * 4).fill(255);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) for (let c = 0; c < 3; c++) data[(y * w + x) * 4 + c] = (7 * x + 13 * y + 50 * c + 31 * ((x * y) % 5)) % 256;
  return { data, width: w, height: h };
}

describe('smart_resize', () => {
  it('gives the sizes of the official processor (factor 32, 65,536 to 1,638,400 pixels)', () => {
    for (const c of G.smart_resize) expect(smartResize(c.h, c.w), `${c.w} x ${c.h}`).toEqual(c.out);
  });
  it('refuses an aspect ratio over 200 and counts the tokens', () => {
    expect(() => smartResize(10, 3000)).toThrow(/aspect ratio/);
    expect(pictureTokens(384, 384)).toBe(144);
    expect(pictureTokens(256, 256)).toBe(64);
    expect(pictureTokens(512, 512)).toBe(256);
  });
  it('leaves the pictures of the viewer alone: every multiple of 32 from 256 to 512 needs no resize', () => {
    for (let s = 256; s <= 512; s += 32) expect(smartResize(s, s)).toEqual([s, s]);
  });
});

describe('the patches', () => {
  for (const g of G.pictures) {
    it(`${g.w} x ${g.h}: the same patches, in the same order, as the official processor`, () => {
      const p = preprocessPicture(picture(g.w, g.h));
      expect(p.resized).toBe(false);
      expect([p.gridH, p.gridW]).toEqual([g.gridH, g.gridW]);
      expect(p.hw.length / 2).toBe(g.patches);
      expect(p.pixels.length).toBe(g.patches * 768);
      let sum = 0;
      for (const v of p.pixels) sum += v;
      expect(sum).toBeCloseTo(g.pixelSum, 0);
      for (const s of g.pixelSamples) {
        [0, 1, 255, 256, 511, 512, 767].forEach((k, i) => expect(p.pixels[s.patch * 768 + k]!, `patch ${s.patch} value ${k}`).toBeCloseTo(s.values[i]!, 5));
      }
      expect(p.tokens).toBe(g.patches / 4);
    });
    it(`${g.w} x ${g.h}: the same position taps and weights as the official code`, () => {
      const p = preprocessPicture(picture(g.w, g.h));
      const t = visionInputs(p.gridH, p.gridW, p.hw);
      let idxSum = 0, wSum = 0;
      for (const v of t.idx) idxSum += Number(v);
      for (const v of t.w) wSum += v;
      expect(idxSum).toBe(g.idxSum);
      expect(wSum).toBeCloseTo(g.wSum, 2);
      for (const s of g.idxSamples) {
        expect(Array.from(t.idx.slice(s.patch * 4, s.patch * 4 + 4), Number)).toEqual(s.idx);
        s.w.forEach((w, k) => expect(t.w[s.patch * 4 + k]!).toBeCloseTo(w, 5));
      }
    });
  }
  it('resizes a picture that is not a multiple of 32 (separable bicubic with a widened kernel) and keeps a flat colour flat', () => {
    const flat = { data: new Uint8Array(300 * 500 * 4).fill(200), width: 300, height: 500 };
    const p = preprocessPicture(flat);
    expect(p.resized).toBe(true);
    const [h, w] = smartResize(500, 300);
    expect([p.gridH * 16, p.gridW * 16]).toEqual([h, w]);
    const expected = Math.fround(Math.fround((200 / 255) / 0.5) - 1);
    let worst = 0;
    for (const v of p.pixels) worst = Math.max(worst, Math.abs(v - expected));
    expect(worst).toBeLessThan(1e-6);
    expect(resizeRgb({ data: new Uint8Array(4 * 4 * 4).fill(10), width: 4, height: 4 }, 2, 2)).toEqual(new Uint8Array(12).fill(10));
  });
});

describe('the prompt and the rotary positions', () => {
  const ids = G.prompt.tokens;
  const pad = G.prompt.imageTokenId;
  it('writes the placeholders before the text and expands each to its token count', () => {
    const q = { type: 'choice' as const, instructions: 'Pick', criteria: { x: 'first', y: 'second' } };
    // byte for byte the text of the official chat template with two picture placeholders before the text of the request
    const short = d3Render('hello', q, ['A', 'B'], 2);
    expect(short).toBe(G.prompt.text);
    expect(d3Render('hello', q, D3_CODES, 0)).not.toContain('<|vision_start|>');
    const counts = G.prompt.grids.map((g) => (g[1]! * g[2]!) / 4);
    expect(expandImagePads(short, counts).split('<|image_pad|>').length - 1).toBe(counts[0]! + counts[1]!);
    expect(() => expandImagePads(short, [4])).toThrow(/more picture placeholders than pictures/);
    expect(() => expandImagePads(short, [4, 4, 4])).toThrow(/2 picture placeholders for 3 pictures/);
    expect(() => expandImagePads('no picture', [4])).toThrow(/0 picture placeholders for 1/);
  });
  it('gives the same 3 rows of positions as get_rope_index of the backbone (two pictures between text)', () => {
    const L = ids.length;
    const grids = G.prompt.grids.map((g) => [g[1]! / 2, g[2]! / 2] as const);
    const got = mropePositions(ids, pad, grids);
    for (let r = 0; r < 3; r++) expect(Array.from(got.slice(r * L, (r + 1) * L), Number), `row ${r}`).toEqual(G.prompt.positions[r]);
  });
  it('rejects a run of picture tokens that does not match its grid', () => {
    expect(() => mropePositions([1, pad, pad, 2], pad, [[2, 2]])).toThrow(/does not match its grid/);
    expect(() => mropePositions([1, 2], pad, [[1, 1]])).toThrow(/0 runs of picture tokens for 1 pictures/);
    expect(() => mropePositions([1, pad, 2], pad, [])).toThrow(/more runs of picture tokens than pictures/);
  });
  it('counts 0..L-1 on all three rows for text', () => {
    const t = textPositions(4);
    expect(Array.from(t, Number)).toEqual([0, 1, 2, 3, 0, 1, 2, 3, 0, 1, 2, 3]);
    expect(Array.from(mropePositions([5, 6, 7, 8], pad, []), Number)).toEqual(Array.from(t, Number));
  });
});
