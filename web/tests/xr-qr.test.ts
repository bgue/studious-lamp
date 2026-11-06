// The dependency-free QR encoder (src/export/qr.ts). The reference symbol below was made by segno 1.6.1 (Python) for the same
// text, level M and mask 3 (with segno's extra zero padding byte switched off, which the standard does not ask for); the
// encoder matched segno bit for bit on 51 symbols with fixed masks, versions 1 to 26, during development.
import { describe, expect, it } from 'vitest';
import { alignmentPositions, dataCodewords, encodeQr, formatBits, penalty, qrSvg, rawDataModules, rsRemainder } from '../src/export/qr';

const REF = ['1fd2977f', '10585941', '174a845d', '1752c95d', '174d665d', '10438241', '1fd5557f', '00132d00', '16ea794b', '183c5f71', '13480406', '1b29f571', '1471de0c', '0b1f3747', '14f81fa7', '0f155192', '155647ba', '0213292e', '13f4f114', '039fdeb4', '0dc7edfc', '001f0d1f', '1fdd475a', '105cc519', '174909f7', '17553a19', '175a4625', '1048757a', '1fd44742'];

const rowsHex = (m: boolean[][]): string[] => m.map((r) => parseInt(r.map((v) => (v ? '1' : '0')).join(''), 2).toString(16).padStart(Math.ceil(r.length / 4), '0'));

describe('QR encoder', () => {
  it('matches a reference symbol bit for bit', () => {
    const q = encodeQr('https://example.com/xray/?model=fzk-haus', 'M', 3);
    expect(q.version).toBe(3);
    expect(q.size).toBe(29);
    expect(rowsHex(q.modules)).toEqual(REF);
  });

  it('computes the Reed-Solomon codewords of the standard example (HELLO WORLD, 1-M)', () => {
    // divisor of degree 10 through a 1-M symbol is internal; check the remainder against the published codewords
    const data = [32, 91, 11, 120, 209, 114, 220, 77, 67, 64, 236, 17, 236, 17, 236, 17];
    const gen = [216, 194, 159, 111, 199, 94, 95, 113, 157, 193];
    expect(rsRemainder(data, gen)).toEqual([196, 35, 39, 119, 235, 215, 231, 226, 93, 23]);
  });

  it('has the standard capacities, alignment positions and format bits', () => {
    expect(rawDataModules(1)).toBe(208);
    expect(dataCodewords(1, 'L')).toBe(19);
    expect(dataCodewords(1, 'M')).toBe(16);
    expect(dataCodewords(40, 'L')).toBe(2956);
    expect(alignmentPositions(1)).toEqual([]);
    expect(alignmentPositions(7)).toEqual([6, 22, 38]);
    expect(alignmentPositions(32)).toEqual([6, 34, 60, 86, 112, 138]);
    expect(formatBits('M', 0)).toBe(0b101010000010010);
    expect(formatBits('L', 4)).toBe(0b110011000101111);
  });

  it('grows the version with the text and picks the lowest-penalty mask', () => {
    const short = encodeQr('HELLO');
    const long = encodeQr('x'.repeat(600), 'L');
    expect(short.version).toBe(1);
    expect(long.version).toBeGreaterThan(10);
    expect(long.size).toBe(long.version * 4 + 17);
    const scores = Array.from({ length: 8 }, (_, k) => penalty(encodeQr('HELLO', 'M', k).modules));
    expect(penalty(short.modules)).toBe(Math.min(...scores));
    expect(() => encodeQr('x'.repeat(3000), 'L')).toThrow(/too long/);
  });

  it('draws the finder patterns and the timing lines', () => {
    const q = encodeQr('https://example.com/xray/?model=fzk-haus', 'M');
    const m = q.modules;
    const n = q.size;
    for (const [x0, y0] of [[0, 0], [n - 7, 0], [0, n - 7]] as const) {
      for (let i = 0; i < 7; i++) {
        expect(m[y0]![x0 + i]).toBe(true);
        expect(m[y0 + 6]![x0 + i]).toBe(true);
      }
      expect(m[y0 + 1]![x0 + 1]).toBe(false);
      expect(m[y0 + 3]![x0 + 3]).toBe(true);
    }
    for (let i = 8; i < n - 8; i++) expect(m[6]![i]).toBe(i % 2 === 0);
    expect(m[n - 8]![8]).toBe(true); // the dark module
  });

  it('writes an SVG with a quiet zone', () => {
    const svg = qrSvg(encodeQr('HELLO'), 4, 2);
    expect(svg).toMatch(/^<svg xmlns="http:\/\/www.w3.org\/2000\/svg" viewBox="0 0 29 29" width="58" height="58"/);
    expect(svg).toContain('M4 4h1v1h-1z');
  });
});
