import { describe, expect, it } from 'vitest';
import { lexLine, lexScript, MAX_SOURCE_LINES } from '../src/anim/script/lexer';
import { ScriptError, didYouMean, editDistance, nearest } from '../src/anim/script/diagnostics';

const toks = (s: string) => {
  const r = lexLine(s, 1);
  if (r instanceof ScriptError) throw r;
  return r;
};

describe('animation script lexer', () => {
  it('splits words, numbers, strings and signs with 1-based columns', () => {
    const t = toks('fly to "Level 2" over 2.5');
    expect(t.map((x) => [x.type, x.text])).toEqual([['word', 'fly'], ['word', 'to'], ['string', 'Level 2'], ['word', 'over'], ['number', '2.5']]);
    expect(t[0]).toMatchObject({ col: 1, end: 4 });
    expect(t[2]).toMatchObject({ col: 8, end: 17 });
    expect(t[4]!.num).toBe(2.5);
  });

  it('reads dotted words as one word', () => {
    expect(toks('set xray.alphaMax to 3').map((x) => x.text)).toEqual(['set', 'xray.alphaMax', 'to', '3']);
    expect(toks('Pset_WallCommon.IsExternal')[0]!.text).toBe('Pset_WallCommon.IsExternal');
  });

  it('drops comments that start with -- or #, but not inside a string', () => {
    expect(toks('wait 2 -- half a minute').map((x) => x.text)).toEqual(['wait', '2']);
    expect(toks('# nothing here')).toEqual([]);
    expect(toks('caption "a -- b # c"').map((x) => x.text)).toEqual(['caption', 'a -- b # c']);
  });

  it('accepts a glued s unit and curly quotes, and a doubled quote inside a string', () => {
    const t = toks('wait 2s');
    expect(t[1]).toMatchObject({ num: 2, unit: 's', end: 8 });
    expect(toks('caption “Hi”')[1]!.text).toBe('Hi');
    expect(toks('caption "say ""hi"""')[1]!.text).toBe('say "hi"');
  });

  it('keeps comparison operators in one token and minus apart', () => {
    expect(toks('a <= 3 != 4 <> 5 == 6 - 7').map((x) => x.text)).toEqual(['a', '<=', '3', '!=', '4', '<>', '5', '==', '6', '-', '7']);
  });

  it('reports an unterminated string at its start', () => {
    const e = lexLine('caption "oops', 4) as ScriptError;
    expect(e).toBeInstanceOf(ScriptError);
    expect([e.line, e.col]).toEqual([4, 9]);
    expect(e.message).toMatch(/no closing quote/);
  });

  it('reports letters glued to a number, single quotes and stray characters', () => {
    expect((lexLine('wait 2x', 1) as ScriptError).message).toMatch(/Unexpected `x`/);
    expect((lexLine("caption 'a'", 1) as ScriptError).message).toMatch(/double quotes/);
    const e = lexLine('wait 2 @', 3) as ScriptError;
    expect([e.line, e.col]).toEqual([3, 8]);
  });

  it('lexes a whole text, skips blank and comment lines, and keeps the line numbers', () => {
    const r = lexScript('\n-- c\nwait 1\r\n\nwait 2');
    expect(r.errors).toEqual([]);
    expect(r.lines.map((l) => l.line)).toEqual([3, 5]);
  });

  it('collects the error of each bad line and goes on', () => {
    const r = lexScript('wait 1\ncaption "x\nwait 2\nwait 3 @');
    expect(r.errors.map((e) => e.line)).toEqual([2, 4]);
    expect(r.lines.map((l) => l.line)).toEqual([1, 3]);
  });

  it('refuses a script with too many lines or characters', () => {
    expect(lexScript('\n'.repeat(MAX_SOURCE_LINES + 1)).errors[0]!.message).toMatch(/more than/);
    expect(lexScript('x'.repeat(300_000)).errors[0]!.message).toMatch(/too long/);
  });
});

describe('diagnostics helpers', () => {
  it('computes edit distances and nearest words', () => {
    expect(editDistance('kitten', 'sitting')).toBe(3);
    expect(nearest('fad', ['fading', 'for'])[0]).toBe('fading');
    expect(nearest('alphamax', ['xray.alphaMax', 'xray.alphaMin', 'display.edgeAlpha'])[0]).toBe('xray.alphaMax');
    expect(nearest('zzzzzz', ['fly', 'orbit'])).toEqual([]);
  });
  it('words a suggestion', () => {
    expect(didYouMean('fade', ['fading'])).toBe('Did you mean `fading`?');
    expect(didYouMean('hid', ['hide', 'hover'])).toMatch(/^Did you mean `hide`/);
    expect(didYouMean('qqqqqq', ['fly'])).toBe('');
  });
});
