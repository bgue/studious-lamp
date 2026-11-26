// Element properties, text tests, lists and chunks, loop exits, maths, seeded random, parameters and libraries.
import { describe, expect, it } from 'vitest';
import { compileScript } from '../src/anim/script/compiler';
import type { CompileOptions } from '../src/anim/script/compiler';
import { parseScript } from '../src/anim/script/parser';
import type { Cue, ElementRef } from '../src/anim/score';

interface El { name: string; cls: string; storey: string; fire?: string }
const EL: Record<string, El> = {
  w1: { name: 'Wall A', cls: 'IfcWall', storey: 'Level 1', fire: 'EI 60' },
  w2: { name: 'Wall B', cls: 'IfcWall', storey: 'Level 2' },
  d1: { name: 'Door 1', cls: 'IfcDoor', storey: 'Level 1', fire: 'EI 30' },
};
const resolve = (ref: ElementRef): string[] | null => {
  if ('globalIds' in ref) return ref.globalIds;
  if ('all' in ref) return Object.keys(EL);
  if ('query' in ref) return Object.entries(EL).filter(([, e]) => ref.query.includes(`'${e.cls}'`) || (ref.query.includes('IfcWall') && e.cls === 'IfcWall') || (ref.query.includes('IfcDoor') && e.cls === 'IfcDoor')).map(([g]) => g);
  return [];
};
const elementField = (g: string, f: string): string | number | boolean | null => {
  const e = EL[g];
  if (!e) return null;
  if (f === 'name') return e.name;
  if (f === 'class') return e.cls;
  if (f === 'storey') return e.storey;
  if (f === 'Pset_WallCommon.FireRating') return e.fire ?? null;
  return null;
};
const MODEL: CompileOptions = { resolve, elementField, setNames: () => [] };
const titles = (src: string, o: CompileOptions = MODEL): string[] => {
  const r = compileScript(src, o);
  expect(r.errors.filter((e) => e.severity === 'error'), src).toEqual([]);
  return r.score!.cues.filter((c): c is Extract<Cue, { kind: 'caption' }> => c.kind === 'caption').map((c) => c.title ?? '');
};
const errs = (src: string, o: CompileOptions = MODEL) => compileScript(src, o).errors.filter((e) => e.severity === 'error');
const one = (expr: string, o?: CompileOptions): string => titles(`caption ${expr}`, o)[0]!;

describe('element properties', () => {
  it('reads facts of it', () => {
    expect(titles('repeat for each element in class IfcWall\n caption the name of it && the storey of it\nend repeat')).toEqual(['Wall A Level 1', 'Wall B Level 2']);
    expect(titles('repeat for each element in class IfcDoor\n caption the class of it & "/" & the globalid of it\nend repeat')).toEqual(['IfcDoor/d1']);
  });
  it('reads a property; missing is empty text', () => {
    expect(titles('repeat for each element in class IfcWall\n put property "Pset_WallCommon.FireRating" of it into r\n caption "[" & r & "]"\nend repeat')).toEqual(['[EI 60]', '[]']);
  });
  it('takes a GlobalId as text', () => {
    expect(one('the name of "d1"')).toBe('Door 1');
    expect(one('the name of "nope" & "!"')).toBe('!');
  });
  it('errors: it outside a loop, no model, a number', () => {
    expect(errs('caption the name of it')[0]).toMatchObject({ line: 1 });
    expect(errs('caption the name of "w1"', { resolve })[0]!.message).toMatch(/needs the model/);
    expect(errs('caption the name of 3')[0]!.message).toMatch(/not an element/);
  });
  it('lists names and globalids, comma separated', () => {
    expect(one('the names of class IfcWall')).toBe('Wall A,Wall B');
    expect(one('the globalids of class IfcDoor')).toBe('d1');
    expect(titles('repeat for each item n in the names of class IfcWall\n caption n\nend repeat')).toEqual(['Wall A', 'Wall B']);
  });
});

describe('text tests and joining', () => {
  it.each([
    ['"Fire wall" contains "FIRE"', true], ['"abc" begins with "AB"', true], ['"abc" ends with "bc"', true], ['"b" is in "abc"', true],
    ['"z" is not in "abc"', true], ['"z" is in "abc"', false], ['"abc" contains "z"', false],
  ])('%s', (c, want) => {
    expect(titles(`if ${c} then caption "y"`)).toEqual(want ? ['y'] : []);
  });
  it('&& joins with one space', () => {
    expect(one('"a" && "b" && 3')).toBe('a b 3');
    expect(titles('put "a" && "b" into x\ncaption x')).toEqual(['a b']);
  });
  it('combines with and/or', () => {
    expect(titles('if "abc" contains "a" and "abc" ends with "c" then caption "y"')).toEqual(['y']);
  });
});

describe('lists and chunks', () => {
  it('picks pieces', () => {
    expect(one('item 2 of "a, b, c"')).toBe('b');
    expect(one('word 3 of "x y z"')).toBe('z');
    expect(one('char 1 to 3 of "abcdef"')).toBe('abc');
    expect(one('item 9 of "a,b"')).toBe('');
    expect(one('item 2 to 3 of "a, b, c, d"')).toBe('b,c');
    expect(titles('put "one,two" into list\ncaption item 1 of list')).toEqual(['one']);
  });
  it('lines', () => {
    expect(titles('put "a" & newline & "b" into t\ncaption line 2 of t & the number of lines in t')).toEqual(['b2']);
  });
  it('counts', () => {
    expect(titles('put "a,b,c" into x\nwait the number of items in x\ncaption the number of items in x')).toEqual(['3']);
    expect(one('the number of words in "a b  c"')).toBe('3');
    expect(one('the number of chars in "abcd"')).toBe('4');
    expect(one('the number of items in ""')).toBe('0');
  });
  it('sorts', () => {
    expect(one('sort items of "b, c, a"')).toBe('a,b,c');
    expect(one('sort items of "b, c, a" descending')).toBe('c,b,a');
    expect(one('sort items of "10, 9, 100" numeric')).toBe('9,10,100');
    expect(one('sort items of "Level 10, Level 2"')).toBe('Level 2,Level 10');
    expect(errs('caption sort items of "a, 1" numeric')[0]!.message).toMatch(/not a number/);
  });
  it('loops over items and words', () => {
    expect(titles('repeat for each item v in "x, y"\n caption v & index\nend repeat')).toEqual(['x1', 'y2']);
    expect(titles('repeat for each word w in "p q"\n caption w\nend repeat')).toEqual(['p', 'q']);
  });
  it('keeps variables named item, word or line working', () => {
    expect(titles('put 3 into item\nput item + 1 into line\ncaption line')).toEqual(['4']);
  });
  it('errors for a bad chunk number', () => {
    expect(errs('caption item 0 of "a"')[0]!.message).toMatch(/whole number of 1 or more/);
  });
});

describe('loop exits', () => {
  it('exit repeat stops, next repeat skips, time is kept', () => {
    expect(titles('repeat with i from 1 to 9\n if i = 2 then next repeat\n if i > 3 then exit repeat\n caption "n" & i\nend repeat')).toEqual(['n1', 'n3']);
    const r = compileScript('repeat 3 times\n wait 1\n exit repeat\nend repeat\ncaption "x"', MODEL);
    expect(r.score!.cues[0]!.at).toBe(1);
  });
  it('works in while, for each element and inside together', () => {
    expect(titles('put 0 into n\nrepeat while n < 9\n put n + 1 into n\n together\n  caption "t" & n\n  if n = 2 then exit repeat\n end together\nend repeat')).toEqual(['t1', 't2']);
    expect(titles('repeat for each element in everything\n if index = 2 then exit repeat\n caption it\nend repeat')).toEqual(['w1']);
  });
  it('exit <handler>', () => {
    expect(titles('on early n\n if n > 1 then exit early\n caption "small"\nend early\nearly 1\nearly 2')).toEqual(['small']);
  });
  it('errors with line numbers', () => {
    const e1 = parseScript('wait 1\nexit repeat').errors[0]!;
    expect(e1).toMatchObject({ line: 2, severity: 'error' });
    expect(e1.message).toMatch(/outside a loop/);
    expect(parseScript('next repeat').errors[0]!.message).toMatch(/outside a loop/);
    expect(parseScript('on a\n exit b\nend a\non b\nend b').errors[0]!).toMatchObject({ line: 2 });
    expect(parseScript('exit foo').errors[0]!.message).toMatch(/do not know what to exit/);
    expect(parseScript('on a\n repeat 2 times\n  exit repeat\n end repeat\nend a\na').errors).toEqual([]);
  });
});

describe('maths', () => {
  it.each([
    ['round(2.5)', '3'], ['round(-2.5)', '-3'], ['round(2.456, 2)', '2.46'], ['trunc(-2.7)', '-2'], ['abs(-4)', '4'], ['min(3, 1, 2)', '1'], ['max(3, 1, 2)', '3'],
    ['sqrt(16)', '4'], ['7 mod 3', '1'], ['-7 mod 3', '2'], ['7 div 2', '3'], ['-7 div 2', '-4'], ['2 ^ 3 ^ 2', '512'], ['-2 ^ 2', '-4'], ['round(pi, 2)', '3.14'],
    ['2 * 3 ^ 2', '18'], ['number("4") + 1', '5'], ['floor(2.9) + ceil(2.1)', '5'],
  ])('%s = %s', (e, want) => {
    expect(one(e)).toBe(want);
  });
  it('errors', () => {
    expect(errs('caption sqrt(-4)')[0]!.message).toMatch(/square root/);
    expect(errs('caption 1 div 0')[0]!.message).toMatch(/divides by zero/);
    expect(errs('caption 1 mod 0')[0]!.message).toMatch(/divides by zero/);
    expect(errs('caption 0 ^ -1')[0]!.message).toMatch(/divides by zero/);
    expect(errs('caption round(1, 2, 3)')[0]!.message).toMatch(/round/);
    expect(errs('caption 1 / 0')[0]).toMatchObject({ line: 1 });
  });
  it('a function of the script wins over a built-in', () => {
    expect(one2('function round x\n return 99\nend round\ncaption round(1.4)')).toBe('99');
  });
});
const one2 = (src: string): string => titles(src)[0]!;

describe('seeded random', () => {
  const src = 'repeat 5 times\n caption random(1000)\nend repeat\ncaption random()';
  it('gives the same film every time', () => {
    expect(titles(src)).toEqual(titles(src));
  });
  it('differs with the script text and with the seed', () => {
    expect(titles(src + '\n-- x')).not.toEqual(titles(src));
    expect(titles('set the random seed to 5\n' + src)).not.toEqual(titles(src));
    expect(titles('set the random seed to 5\n' + src)).toEqual(titles('set the random seed to 5\n' + src));
  });
  it('random(n) is 1..n and random() is 0..1', () => {
    const t = titles('repeat 200 times\n caption random(3)\nend repeat').map(Number);
    expect(Math.min(...t)).toBe(1);
    expect(Math.max(...t)).toBe(3);
    const f = Number(titles('caption random()')[0]);
    expect(f).toBeGreaterThanOrEqual(0);
    expect(f).toBeLessThan(1);
  });
  it('errors for a bad n', () => {
    expect(errs('caption random(0)')[0]!.message).toMatch(/whole number of 1 or more/);
  });
});

describe('parameters', () => {
  const src = 'param floor default "Level 1"\nparam n default 2\nparam on_ default yes\ncaption floor & n & on_';
  it('uses the defaults', () => {
    expect(titles(src)).toEqual(['Level 12true']);
    const r = compileScript(src, MODEL);
    expect(r.params.map((p) => [p.name, p.kind, p.value])).toEqual([['floor', 'text', 'Level 1'], ['n', 'number', 2], ['on_', 'yesno', true]]);
  });
  it('takes values from outside, coerced to the type', () => {
    expect(titles(src, { ...MODEL, params: { FLOOR: 'Level 2', n: '5', on_: 'no' } })).toEqual(['Level 25false']);
    expect(titles(src, { ...MODEL, params: { n: 7 } })).toEqual(['Level 17true']);
  });
  it('warns about an unknown name and errors on a wrong type', () => {
    const r = compileScript(src, { ...MODEL, params: { flor: 'x' } });
    expect(r.score).not.toBeNull();
    expect(r.errors[0]).toMatchObject({ severity: 'warning', line: 1 });
    expect(r.errors[0]!.message).toMatch(/no parameter named "flor"/);
    expect(r.errors[0]!.hint).toMatch(/floor/);
    expect(errs(src, { ...MODEL, params: { n: 'abc' } })[0]).toMatchObject({ line: 2 });
  });
  it('is read from a script with errors elsewhere', () => {
    expect(compileScript('param a default 1\nfoo bar baz', MODEL).params).toHaveLength(1);
  });
  it('parse errors', () => {
    expect(parseScript('param a').errors[0]!.message).toMatch(/default/);
    expect(parseScript('if 1 = 1 then\n param a default 1\nend if').errors[0]!.message).toMatch(/top level/);
    expect(errs('param a default 1\nparam a default 2')[0]!).toMatchObject({ line: 2 });
    expect(errs('param wait default 1')[0]!.message).toMatch(/word of the language/);
  });
  it('changes the compiled caption', () => {
    const a = titles('param floor default "Level 1"\ncaption floor');
    const b = titles('param floor default "Level 1"\ncaption floor', { ...MODEL, params: { floor: 'Level 2' } });
    expect([a[0], b[0]]).toEqual(['Level 1', 'Level 2']);
  });
});

describe('libraries (use)', () => {
  const LIBS: Record<string, string> = {
    'Floor helpers': 'on showFloor name\n caption "Floor " & name\nend showFloor\nfunction twice x\n return x * 2\nend twice\ncaption "not run"',
    A: 'use "B"\non fromA\n caption "A"\nend fromA',
    B: 'use "A"\non fromB\n caption "B"\nend fromB',
    Bad: 'fly to',
    Own: 'on hello\n caption "lib"\nend hello',
  };
  const o: CompileOptions = { ...MODEL, library: (n) => LIBS[Object.keys(LIBS).find((k) => k.toLowerCase() === n.toLowerCase()) ?? ''] ?? null, libraryNames: () => Object.keys(LIBS) };
  it('pulls in handlers and functions only', () => {
    expect(titles('use "Floor helpers"\nshowFloor "L2"\nwait twice(1)\ncaption "done"', o)).toEqual(['Floor L2', 'done']);
  });
  it('finds a name without regard to case', () => {
    expect(titles('use "floor HELPERS"\nshowFloor 1', o)).toEqual(['Floor 1']);
  });
  it('a missing library is an error that names it', () => {
    const e = errs('use "Floor helper"', o)[0]!;
    expect(e).toMatchObject({ line: 1 });
    expect(e.message).toMatch(/"Floor helper"/);
    expect(e.hint).toMatch(/Floor helpers/);
    expect(errs('use "x"', MODEL)[0]!.message).toMatch(/not available/);
  });
  it('a cycle is an error', () => {
    const e = errs('use "A"', o)[0]!;
    expect(e.message).toMatch(/circle/);
    expect(e.message).toMatch(/"a" -> "b" -> "a"/);
    expect(errs('use "Self"', { ...o, name: 'Self', library: (n) => (n === 'Self' ? 'use "Self"' : null) })[0]!.message).toMatch(/circle/);
  });
  it('the script wins over a library, with a warning', () => {
    const r = compileScript('use "Own"\non hello\n caption "mine"\nend hello\nhello', o);
    expect(r.score!.cues.map((c) => (c as { title?: string }).title)).toEqual(['mine']);
    expect(r.errors.some((e) => e.severity === 'warning' && /script's own is used/.test(e.message))).toBe(true);
  });
  it('an error in a library is reported on the use line, or on the calling line', () => {
    expect(errs('use "Bad"', o)[0]).toMatchObject({ line: 1 });
    const l2: CompileOptions = { ...o, library: () => 'on boom\n wait 1 / 0\nend boom' };
    const e = errs('use "L"\nwait 1\nboom', l2)[0]!;
    expect(e.line).toBe(3);
    expect(e.message).toMatch(/In the library "L", line 2/);
  });
  it('cues of a library handler point at the calling line', () => {
    const r = compileScript('use "Floor helpers"\nwait 1\nshowFloor 1', o);
    expect((r.score!.cues[0] as Cue).line).toBe(3);
  });
});

describe('element forms in count and there are', () => {
  it('needs no where for the short forms', () => {
    expect(titles('caption the count of class IfcWall')).toEqual(['2']);
    expect(titles('if there are class IfcDoor then caption "doors"')).toEqual(['doors']);
    expect(titles('if the count of (where class = IfcWall) > 1 then caption "many"')).toEqual(['many']);
  });
  it('the error shows the where form', () => {
    const e = parseScript('caption the count of wall').errors[0]!;
    expect(e.hint).toMatch(/the count of \(where class = IfcDoor and storey = "Level 1"\)/);
  });
});
