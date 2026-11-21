import { describe, expect, it } from 'vitest';
import { buildQuery, parseScript } from '../src/anim/script/parser';
import type { Stmt } from '../src/anim/script/parser';
import { lexLine } from '../src/anim/script/lexer';
import type { Tok } from '../src/anim/script/lexer';
import { parseQuery } from '../src/query/parser';

const one = (src: string): Stmt => {
  const r = parseScript(src);
  expect(r.errors, src).toEqual([]);
  expect(r.program.body.length, src).toBe(1);
  return r.program.body[0]!;
};
const err = (src: string) => parseScript(src).errors;

describe('parser: statements', () => {
  it('fly to with options in any order', () => {
    const s = one('Fly To class IfcPump margin 3 ease in out over 2.5 seconds');
    expect(s).toMatchObject({ kind: 'flyTo', ease: 'inOut', target: { k: 'query', query: "class = 'IfcPump'" }, line: 1 });
    if (s.kind === 'flyTo') {
      expect(s.over).toMatchObject({ k: 'num', v: 2.5 });
      expect(s.margin).toMatchObject({ k: 'num', v: 3 });
    }
  });

  it('fly to a saved view', () => {
    expect(one('fly to view "Plant room" over 4s')).toMatchObject({ kind: 'flyView', name: 'Plant room' });
  });

  it('orbit with and without about', () => {
    expect(one('orbit 90 degrees over 5 seconds')).toMatchObject({ kind: 'orbit', degrees: { v: 90 } });
    expect(one('orbit -45 about set "Pumps" over 5 seconds ease out')).toMatchObject({ kind: 'orbit', about: { k: 'set', name: 'Pumps' }, ease: 'out', degrees: { k: 'neg' } });
  });

  it('set with a number, a list, a boolean, text and a word', () => {
    expect(one('set xray.alphaMax to 0.3 over 2 seconds ease linear')).toMatchObject({ kind: 'set', path: 'xray.alphaMax', ease: 'linear', value: { k: 'list' } });
    expect(one('set a.b to 1, 2, 3')).toMatchObject({ value: { k: 'list', items: [{ v: 1 }, { v: 2 }, { v: 3 }] } });
    expect(one('set a.b to off')).toMatchObject({ value: { k: 'bool', v: false } });
    expect(one('set a.b to ON over 1')).toMatchObject({ value: { k: 'bool', v: true } });
    expect(one('set a.b to "text"')).toMatchObject({ value: { k: 'str', v: 'text' } });
    expect(one('set imaging.style to radiograph')).toMatchObject({ value: { k: 'word', text: 'radiograph' } });
    expect(one('set a.b to gap * 2')).toMatchObject({ value: { k: 'list' } });
  });

  it('mode, apply preset', () => {
    expect(one('mode Ghost')).toMatchObject({ kind: 'mode', mode: 'Ghost' });
    expect(one('apply preset "Peelback"')).toMatchObject({ kind: 'preset', name: 'Peelback' });
  });

  it('show, hide, isolate with fading', () => {
    expect(one('show everything fading over 2 seconds')).toMatchObject({ kind: 'visibility', op: 'show', target: { k: 'everything' }, fading: { v: 2 } });
    expect(one('hide where class = IfcSlab fading 1')).toMatchObject({ op: 'hide', fading: { v: 1 } });
    expect(one('isolate set "Pumps"')).toMatchObject({ op: 'isolate', target: { k: 'set', name: 'Pumps' } });
  });

  it('select, caption, label, hover, wait, put', () => {
    expect(one('select nothing')).toMatchObject({ kind: 'select', target: null });
    expect(one('select the selection')).toMatchObject({ target: { k: 'selection' } });
    expect(one('select elements "a", "b"')).toMatchObject({ target: { k: 'gids', ids: ['a', 'b'] } });
    const c = one('caption "Title" "More" for 4 seconds');
    expect(c).toMatchObject({ kind: 'caption', title: { parts: [{ k: 'text', v: 'Title' }] }, text: { parts: [{ k: 'text', v: 'More' }] }, for: { v: 4 } });
    expect(one('caption "Set: " & it for 2')).toMatchObject({ title: { parts: [{ k: 'text' }, { k: 'name', name: 'it' }] } });
    expect(one('label class IfcPump with name, storey, "Pset_X.Prop" for 5 seconds')).toMatchObject({ kind: 'label', fields: ['name', 'storey', 'Pset_X.Prop'], for: { v: 5 } });
    expect(one('hover it for 1')).toMatchObject({ kind: 'hover', target: { k: 'it' } });
    expect(one('wait 2')).toMatchObject({ kind: 'wait', seconds: { v: 2 } });
    expect(one('put (1 + 2) * 3 into gap')).toMatchObject({ kind: 'put', name: 'gap', value: { k: 'bin', op: '*' } });
  });

  it('numbers: precedence, unary minus, parentheses', () => {
    const s = one('wait 1 + 2 * 3 - 4 / 2');
    expect(s.kind === 'wait' && s.seconds).toMatchObject({ k: 'bin', op: '-', a: { k: 'bin', op: '+', b: { k: 'bin', op: '*' } }, b: { k: 'bin', op: '/' } });
  });

  it('blocks nest and keep their body', () => {
    const r = parseScript(`together
  fly to everything
  repeat 2 times
    wait 1
  end repeat
end together
repeat for each element in class IfcPump
  select it
end repeat
repeat for each set in sets
  select it
end repeat`);
    expect(r.errors).toEqual([]);
    const [a, b, c] = r.program.body;
    expect(a).toMatchObject({ kind: 'together' });
    expect(a!.kind === 'together' && a!.body.map((x) => x.kind)).toEqual(['flyTo', 'repeat']);
    expect(b).toMatchObject({ kind: 'forEach', each: 'element', target: { k: 'query' } });
    expect(c).toMatchObject({ kind: 'forEach', each: 'set' });
  });

  it('ignores comments, blank lines, indentation and case', () => {
    const r = parseScript('-- a\n\n   WAIT 1 # x\n   Mode SOLID');
    expect(r.errors).toEqual([]);
    expect(r.program.body.map((s) => s.line)).toEqual([3, 4]);
  });
});

describe('parser: the where clause', () => {
  const q = (src: string): string => {
    const s = one(`select ${src}`);
    if (s.kind !== 'select' || !s.target || s.target.k !== 'query') throw new Error('not a query');
    return s.target.query;
  };

  it('turns bare words and double quoted text on the right into text values', () => {
    expect(q('where class = IfcPump and storey = "Level 2"')).toBe("class = 'IfcPump' AND storey = 'Level 2'");
  });
  it('keeps double quoted text on the left as a column', () => {
    expect(q('where "Pset_WallCommon.IsExternal"')).toBe('"Pset_WallCommon.IsExternal"');
    expect(q('where "Pset_A.B" = true')).toBe('"Pset_A.B" = TRUE');
  });
  it('handles like, in lists, between and negative numbers', () => {
    expect(q('where name like "Pump%"')).toBe("name LIKE 'Pump%'");
    expect(q('where class in (IfcPump, IfcValve) or sizeX > -2')).toBe("class IN ('IfcPump', 'IfcValve') OR sizeX > -2");
    expect(q('where volume between 1 and 5 and class = IfcWall')).toBe("volume BETWEEN 1 AND 5 AND class = 'IfcWall'");
    expect(q('where not (class = IfcPump)')).toBe("NOT (class = 'IfcPump')");
  });
  it('produces text the criteria parser accepts', () => {
    for (const w of ['class = IfcPump and storey = "Level 2"', 'name is null', 'class not in (A, B)', 'name not like "x%"']) expect(() => parseQuery(q(`where ${w}`))).not.toThrow();
  });
  it('stops at the option words', () => {
    const s = one('fly to where class = IfcPump over 2 seconds margin 3');
    expect(s).toMatchObject({ kind: 'flyTo', target: { query: "class = 'IfcPump'" }, over: { v: 2 } });
  });
  it('class lists', () => {
    expect(q('class IfcPump, IfcValve')).toBe("class IN ('IfcPump', 'IfcValve')");
    expect(q('class "IfcPump"')).toBe("class = 'IfcPump'");
  });
  it('buildQuery maps each token to its offset', () => {
    const t = lexLine('class = IfcPump', 1) as Tok[];
    const b = buildQuery(t);
    expect(b.text).toBe("class = 'IfcPump'");
    expect(b.starts).toEqual([0, 6, 8]);
  });
});

describe('parser: errors with positions', () => {
  it('names an unknown statement and suggests the nearest', () => {
    const [e] = err('flyy to everything');
    expect(e).toMatchObject({ line: 1, col: 1, severity: 'error' });
    expect(e!.message).toMatch(/do not know the statement `flyy`/);
    expect(e!.hint).toMatch(/Did you mean `fly`/);
  });

  it('suggests fading for fade', () => {
    const [e] = err('show everything fade over 2 seconds');
    expect([e!.line, e!.col]).toEqual([1, 17]);
    expect(e!.hint).toMatch(/Did you mean `fading`\?/);
  });

  it('points at a missing number after the last token', () => {
    const [e] = err('wait');
    expect(e!.message).toMatch(/Expected a number/);
    expect(e!.col).toBe(5);
  });

  it('points at the wrong token with the right column', () => {
    const [e] = err('fly to class IfcPump ovr 2');
    expect(e).toMatchObject({ line: 1, col: 22 });
    const [e2] = err('  mode ghost extra');
    expect(e2).toMatchObject({ line: 1, col: 14 });
  });

  it('reports the lines of several errors and keeps the good ones', () => {
    const r = parseScript('wait 1\nflyy\nwait 2\nhide\nwait 3');
    expect(r.errors.map((e) => e.line)).toEqual([2, 4]);
    expect(r.program.body.map((s) => s.line)).toEqual([1, 3, 5]);
  });

  it('maps a criteria error to the token that is wrong', () => {
    const [e] = err('select where class = IfcPump and and');
    expect(e!.message).toMatch(/^In the criteria:/);
    expect(e!.col).toBeGreaterThanOrEqual(34);
    const [e2] = err('select where storey = Level 2');
    expect(e2!.hint).toMatch(/double quotes/);
  });

  it('asks for a condition after where and rejects arithmetic in it', () => {
    expect(err('select where')[0]!.message).toMatch(/Expected a condition after `where`/);
    expect(err('select where a + b')[0]!.message).toMatch(/cannot be used in a criteria/);
  });

  it('explains unclosed and stray blocks', () => {
    const open = err('together\n  wait 1');
    expect(open[0]).toMatchObject({ line: 1 });
    expect(open[0]!.message).toMatch(/no `end together`/);
    const stray = err('wait 1\nend repeat');
    expect(stray[0]).toMatchObject({ line: 2 });
    expect(stray[0]!.message).toMatch(/no block to close/);
    const wrong = err('repeat 2 times\n  wait 1\nend together');
    expect(wrong[0]!.message).toMatch(/does not match/);
    expect(wrong[0]!.hint).toMatch(/end repeat/);
  });

  it('checks the shape of each statement', () => {
    expect(err('fly everything')[0]!.message).toMatch(/Expected `to`/);
    expect(err('set a.b 3')[0]!.message).toMatch(/Expected `to`/);
    expect(err('apply "x"')[0]!.message).toMatch(/Expected `preset`/);
    expect(err('apply preset x')[0]!.message).toMatch(/in double quotes/);
    expect(err('put 3 gap')[0]!.message).toMatch(/Expected `into`/);
    expect(err('repeat 3')[0]!.message).toMatch(/Expected `times`/);
    expect(err('repeat for each room in everything\nend repeat')[0]!.message).toMatch(/element. or .set/);
    expect(err('label class X name')[0]!.message).toMatch(/Expected `with`/);
    expect(err('select')[0]!.message).toMatch(/Expected which elements/);
    expect(err('select pumps')[0]!.message).toMatch(/Expected which elements/);
    expect(err('fly to everything ease sideways')[0]!.message).toMatch(/Expected `in`/);
    expect(err('fly to everything over 2 over 3')[0]!.message).toMatch(/given twice/);
    expect(err('caption')[0]!.message).toMatch(/Expected the caption text/);
    expect(err('wait (1 + 2')[0]!.message).toMatch(/Expected `\)`/);
    expect(err('select nothing now')[0]!.message).toMatch(/did not expect/);
    expect(err('42')[0]!.message).toMatch(/starts with a word/);
  });

  it('limits the nesting depth', () => {
    const deep = `${'repeat 1 times\n'.repeat(10)}wait 1\n${'end repeat\n'.repeat(10)}`;
    expect(err(deep).some((e) => /nested more than/.test(e.message))).toBe(true);
  });

  it('never throws on odd input', () => {
    for (const s of ['', '\n\n', '"', 'end', 'repeat', 'together together', 'set', 'where', '((((', 'a b c d e f g', '--', 'fly to where (']) {
      expect(() => parseScript(s)).not.toThrow();
    }
  });
});
