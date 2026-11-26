// Decisions, loops and your own commands of the animation script language: if, repeat while|until, repeat with, handlers (`on`),
// functions, and the playback statements (overlays, fade). Flow control is decided when the script compiles, so every test looks at
// the score that comes out.
import { describe, expect, it } from 'vitest';
import { compileScript, LIMITS } from '../src/anim/script/compiler';
import type { CompileOptions } from '../src/anim/script/compiler';
import { parseScript } from '../src/anim/script/parser';
import { highlightLine } from '../src/anim/script/highlight';
import type { Cue, ElementRef, Score } from '../src/anim/score';
import { DOCS_PLANS } from './director-helpers';

/** A fake model: three doors (two on Level 1), one pump, nothing else. */
const DOORS = ['d1', 'd2', 'd3'];
const resolve = (ref: ElementRef): string[] | null => {
  if ('all' in ref) return [...DOORS, 'p1'];
  if ('globalIds' in ref) return ref.globalIds;
  if ('set' in ref) return ref.set === 'Pumps' ? ['p1'] : [];
  if ('selection' in ref) return [];
  if ('schedule' in ref) return null;
  const q = ref.query;
  if (q.includes('IfcDoor') && q.includes('Level 1')) return ['d1', 'd2'];
  if (q.includes('IfcDoor')) return DOORS;
  if (q.includes('IfcPump')) return ['p1'];
  if (q.includes("'Level 2'")) return ['w1'];
  if (q.includes("'Level 3'")) return ['w1', 'w2'];
  return [];
};
const MODEL: CompileOptions = { resolve, setNames: () => ['Pumps', 'Walls'], plans: DOCS_PLANS };

const ok = (src: string, opts: CompileOptions = MODEL): Score => {
  const r = compileScript(src, opts);
  expect(r.errors.filter((e) => e.severity === 'error'), src).toEqual([]);
  return r.score!;
};
const errs = (src: string, opts: CompileOptions = MODEL) => compileScript(src, opts).errors.filter((e) => e.severity === 'error');
const titles = (s: Score): string[] => s.cues.filter((c): c is Extract<Cue, { kind: 'caption' }> => c.kind === 'caption').map((c) => c.title ?? '');
const run = (src: string, opts?: CompileOptions): string[] => titles(ok(src, opts));

describe('conditions', () => {
  it('compares numbers', () => {
    expect(run('put 3 into n\nif n > 2 then\n caption "big"\nelse\n caption "small"\nend if')).toEqual(['big']);
    expect(run('put 1 into n\nif n > 2 then\n caption "big"\nelse\n caption "small"\nend if')).toEqual(['small']);
    for (const [expr, want] of [['n = 3', true], ['n <> 3', false], ['n != 3', false], ['n <= 3', true], ['n >= 4', false], ['n < 4', true], ['n == 3', true], ['n ≠ 3', false], ['n ≥ 3', true], ['n ≤ 2', false]] as const) {
      expect(run(`put 3 into n\nif ${expr} then caption "y"`), expr).toEqual(want ? ['y'] : []);
    }
  });

  it('compares text without regard to case', () => {
    expect(run('put "Level 1" into s\nif s = "level 1" then caption "same"')).toEqual(['same']);
    expect(run('put "Level 1" into s\nif s <> "LEVEL 1" then caption "other"')).toEqual([]);
    expect(run('if "apple" < "Banana" then caption "before"')).toEqual(['before']);
    expect(run('if "Level 2" < "Level 10" then caption "natural"')).toEqual(['natural']);
  });

  it('compares a number with text that reads as a number, and refuses the rest', () => {
    expect(run('if 3 = "3" then caption "y"')).toEqual(['y']);
    expect(errs('if 3 = "abc" then caption "y"')[0]!.message).toMatch(/cannot be compared/);
  });

  it('joins with and, or, not and parentheses', () => {
    const t = (cond: string): boolean => run(`if ${cond} then caption "y"`).length === 1;
    expect(t('1 < 2 and 2 < 3')).toBe(true);
    expect(t('1 > 2 or 2 < 3')).toBe(true);
    expect(t('not 1 > 2')).toBe(true);
    expect(t('not (1 < 2 and 2 < 3)')).toBe(false);
    expect(t('1 > 2 or 1 > 3 and 2 < 3')).toBe(false); // and binds tighter than or
    expect(t('(1 > 2 or 1 < 3) and 2 < 3')).toBe(true);
    expect(t('true and not false')).toBe(true);
  });

  it('works out arithmetic and & inside a comparison', () => {
    expect(run('put 4 into n\nif n * 2 + 1 = 9 then caption "y"')).toEqual(['y']);
    expect(run('put 2 into n\nif "Level " & n = "level 2" then caption "y"')).toEqual(['y']);
  });

  it('stops at the first answer: the rest is not worked out', () => {
    expect(run('put 0 into n\nif n > 0 and 10 / n > 1 then caption "y" ')).toEqual([]);
    expect(run('put 0 into n\nif n = 0 or 10 / n > 1 then caption "y" ')).toEqual(['y']);
  });

  it('yes/no values can be kept', () => {
    expect(run('put 3 > 2 into big\nif big then caption "y"')).toEqual(['y']);
    expect(run('put there are class IfcDoor into has\nif has = true then caption "y"')).toEqual(['y']);
  });

  it('a condition must be a yes/no', () => {
    const e = errs('put 3 into n\nif n then caption "y"');
    expect(e[0]).toMatchObject({ line: 2 });
    expect(e[0]!.message).toMatch(/not a yes\/no condition/);
  });
});

describe('model predicates', () => {
  it('the count of elements', () => {
    expect(run('put the count of class IfcDoor into n\ncaption "Doors: " & n')).toEqual(['Doors: 3']);
    expect(run('caption "Doors: " & the count of class IfcDoor')).toEqual(['Doors: 3']);
    expect(run('if the count of class IfcDoor > 2 then caption "many"')).toEqual(['many']);
    expect(run('if the count of class IfcDoor >= 4 then caption "many"')).toEqual([]);
    expect(run('put the count of where class = IfcDoor and storey = "Level 1" into n\ncaption "n=" & n')).toEqual(['n=2']);
  });

  it('a where in parentheses can be followed by more', () => {
    expect(run('if the count of (where class = IfcDoor and storey = "Level 1") = 2 and there are class IfcPump then caption "y"')).toEqual(['y']);
    expect(run('put (the count of (where class = IfcDoor)) * 2 into n\ncaption "n=" & n')).toEqual(['n=6']);
  });

  it('there are / there is / there are no', () => {
    expect(run('if there are class IfcDoor then caption "doors"')).toEqual(['doors']);
    expect(run('if there is class IfcPump then caption "pump"')).toEqual(['pump']);
    expect(run('if there are class IfcFan then\n caption "fans"\nelse\n caption "no fans"\nend if')).toEqual(['no fans']);
    expect(run('if there are no class IfcFan then caption "none"')).toEqual(['none']);
    expect(run('if there are set "Pumps" then caption "set"')).toEqual(['set']);
    expect(run('if there are where class = IfcDoor then caption "y"')).toEqual(['y']);
    expect(run('if not there are class IfcFan then caption "y"')).toEqual(['y']);
  });

  it('inside repeat for each, `it` is the element', () => {
    expect(run('repeat for each element in class IfcDoor\n if there are it then caption "has " & it\nend repeat')).toEqual(['has d1', 'has d2', 'has d3']);
  });

  it('needs a model; the elements of a running schedule cannot be counted', () => {
    expect(errs('if there are class IfcDoor then caption "y"', {})[0]!.message).toMatch(/needs the model/);
    expect(errs('put the count of active into n', MODEL)[0]!.message).toMatch(/running schedule/);
  });
});

describe('if', () => {
  it('else if and else pick the first branch that is true', () => {
    const src = (n: number): string => `put ${n} into n\nif n < 3 then\n caption "low"\nelse if n < 6 then\n caption "mid"\nelse if n < 9 then\n caption "high"\nelse\n caption "top"\nend if`;
    expect([1, 4, 7, 10].map((n) => run(src(n)))).toEqual([['low'], ['mid'], ['high'], ['top']]);
  });

  it('a block takes time like the statements in it, and nothing when no branch is true', () => {
    const s = ok('put 1 into n\nif n = 1 then\n wait 2\n fly to everything over 1 seconds\nend if\nmode solid');
    expect(s.cues.map((c) => [c.kind, c.at])).toEqual([['camera', 2], ['preset', 3]]);
    expect(ok('if 1 > 2 then\n wait 5\nend if\nmode solid').cues.map((c) => c.at)).toEqual([0]);
  });

  it('the one-line form holds one statement', () => {
    const s = ok('put 2 into n\nif n = 2 then wait 3\nif n = 5 then wait 10\nmode solid');
    expect(s.cues[0]!.at).toBe(3);
    expect(ok('if true then fly to class IfcPump over 2 seconds margin 2').cues[0]).toMatchObject({ kind: 'camera', dur: 2 });
  });

  it('keeps the line of the statements in the branch', () => {
    const s = ok('put 1 into n\nif n = 1 then\n\n  caption "a"\nend if');
    expect(s.cues[0]!.line).toBe(4);
  });

  it('nests', () => {
    expect(run('put 2 into a\nput 3 into b\nif a = 2 then\n if b = 3 then\n  caption "both"\n else\n  caption "a only"\n end if\nend if')).toEqual(['both']);
  });

  it('an if inside together starts with the others', () => {
    const s = ok('together\n if true then\n  caption "a" for 2 seconds\n end if\n fly to everything over 3 seconds\nend together');
    expect(s.cues.map((c) => c.at)).toEqual([0, 0]);
  });

  it('errors say the line and column', () => {
    const e = errs('put 1 into n\nif n > then\n caption "x"\nend if');
    expect(e.length).toBeGreaterThan(0);
    expect(e[0]).toMatchObject({ line: 2 });
    expect(e[0]!.col).toBeGreaterThan(1);
    expect(errs('if 1 < 2\n caption "x"\nend if')[0]!.message).toMatch(/Expected `then`/);
  });
});

describe('repeat while and until', () => {
  it('while runs as long as the condition holds', () => {
    expect(run('put 1 into n\nrepeat while n < 4\n caption "n" & n\n put n + 1 into n\nend repeat')).toEqual(['n1', 'n2', 'n3']);
  });
  it('until runs until the condition holds', () => {
    expect(run('put 1 into n\nrepeat until n > 3\n caption "n" & n\n put n + 1 into n\nend repeat')).toEqual(['n1', 'n2', 'n3']);
    expect(run('repeat until true\n caption "never"\nend repeat')).toEqual([]);
  });
  it('the body takes time one pass after another', () => {
    const s = ok('put 0 into n\nrepeat while n < 3\n wait 1\n mode solid\n put n + 1 into n\nend repeat');
    expect(s.cues.map((c) => c.at)).toEqual([1, 2, 3]);
  });
  it('an infinite loop is stopped by the iteration limit, with the line', () => {
    const e = errs('wait 1\nrepeat while true\n wait 0\nend repeat');
    expect(e).toHaveLength(1);
    expect(e[0]).toMatchObject({ line: 2 });
    expect(e[0]!.message).toMatch(new RegExp(`ran ${LIMITS.maxIterations} times and was stopped`));
    expect(e[0]!.hint).toMatch(/put n \+ 1 into n/);
    expect(errs('repeat until false\n wait 0\nend repeat')[0]!.message).toMatch(/repeat until/);
  });
  it('the overall step limit still applies', () => {
    const e = errs('repeat 400 times\n repeat 400 times\n  wait 0\n end repeat\nend repeat');
    expect(e[0]!.message).toMatch(/more than 20000 statements/);
  });
  it('a custom iteration limit is honoured', () => {
    const e = compileScript('put 0 into n\nrepeat while n < 10\n put n + 1 into n\nend repeat', { ...MODEL, limits: { maxIterations: 5 } }).errors;
    expect(e[0]!.message).toMatch(/ran 5 times/);
  });
});

describe('repeat with', () => {
  it('counts up, down and by a step', () => {
    expect(run('repeat with i from 1 to 3\n caption "i" & i\nend repeat')).toEqual(['i1', 'i2', 'i3']);
    expect(run('repeat with i from 3 down to 1\n caption "i" & i\nend repeat')).toEqual(['i3', 'i2', 'i1']);
    expect(run('repeat with i from 0 to 10 by 5\n caption "i" & i\nend repeat')).toEqual(['i0', 'i5', 'i10']);
    expect(run('repeat with i from 10 down to 1 by 4\n caption "i" & i\nend repeat')).toEqual(['i10', 'i6', 'i2']);
    expect(run('repeat with i from 0 to 1 by 0.25\n caption "" & i\nend repeat')).toEqual(['0', '0.25', '0.5', '0.75', '1']);
  });
  it('the bounds are expressions evaluated once', () => {
    expect(run('put 2 into n\nrepeat with i from n to n * 2\n caption "i" & i\n put 9 into n\nend repeat')).toEqual(['i2', 'i3', 'i4']);
  });
  it('restores the name after the loop', () => {
    expect(run('put 99 into i\nrepeat with i from 1 to 2\n wait 0\nend repeat\ncaption "i=" & i')).toEqual(['i=99']);
    const e = errs('repeat with j from 1 to 2\n wait 0\nend repeat\ncaption "j=" & j');
    expect(e[0]!.message).toMatch(/do not know the name `j`/);
  });
  it('nests with index', () => {
    expect(run('repeat with i from 1 to 2\n repeat 2 times\n  caption i & "." & index\n end repeat\nend repeat')).toEqual(['1.1', '1.2', '2.1', '2.2']);
  });
  it('a loop that cannot run warns; a bad step and too many passes are errors', () => {
    const r = compileScript('repeat with i from 5 to 1\n wait 1\nend repeat', MODEL);
    expect(r.errors.map((e) => e.severity)).toEqual(['warning']);
    expect(r.errors[0]!.hint).toMatch(/down to/);
    expect(errs('repeat with i from 1 to 5 by 0\n wait 1\nend repeat')[0]!.message).toMatch(/more than 0/);
    expect(errs('repeat with i from 1 to 5000\n wait 0\nend repeat')[0]!.message).toMatch(/at most 500 times/);
    expect(errs('repeat with over from 1 to 2\n wait 0\nend repeat')[0]!.message).toMatch(/word of the language/);
  });
  it('a syntax slip names the line', () => {
    const e = parseScript('repeat with i 1 to 5\n wait 1\nend repeat').errors;
    expect(e[0]).toMatchObject({ line: 1 });
    expect(e[0]!.message).toMatch(/Expected `from`/);
  });
});

describe('handlers', () => {
  it('runs the statements where it is called, with its parameters', () => {
    const s = ok('on greet who\n  caption "Hello " & who for 2 seconds\nend greet\ngreet "Ann"\ngreet "Bo"');
    expect(s.cues.map((c) => [c.kind === 'caption' ? c.title : '', c.at])).toEqual([['Hello Ann', 0], ['Hello Bo', 2]]);
  });
  it('may be defined after the call (hoisted) and in any case', () => {
    expect(run('Greet "x"\non GREET who\n  caption who\nend greet')).toEqual(['x']);
  });
  it('takes numbers and works them out in the caller', () => {
    const s = ok('on pause secs\n wait secs * 2\nend pause\nput 3 into n\npause n + 1\nmode solid');
    expect(s.cues[0]!.at).toBe(8);
  });
  it('a call without arguments, and several arguments', () => {
    expect(run('on hi\n caption "hi"\nend hi\nhi')).toEqual(['hi']);
    expect(run('on two a, b\n caption a & "-" & b\nend two\ntwo "x", 1 + 2')).toEqual(['x-3']);
  });
  it('parameters and names put inside are local; outer names can be read', () => {
    expect(run('put 5 into n\nput "out" into tag\non showit n\n  put n * 2 into local\n  caption tag & " " & local\nend showit\nshowit 1\ncaption "n=" & n')).toEqual(['out 2', 'n=5']);
    expect(errs('on a\n put 1 into inner\nend a\na\ncaption "" & inner')[0]!.message).toMatch(/do not know the name `inner`/);
  });
  it('a put inside does not change a global of the same name', () => {
    expect(run('put 1 into x\non change\n put 2 into x\n caption "in " & x\nend change\nchange\ncaption "out " & x')).toEqual(['in 2', 'out 1']);
  });
  it('sees `it` and the where clause can use a parameter', () => {
    expect(run('on describe\n caption "it=" & it\nend describe\nrepeat for each element in set "Pumps"\n describe\nend repeat')).toEqual(['it=p1']);
    const s = ok('on floor name\n  hide where storey = name\nend floor\nfloor "Level 3"\nfloor "Level4"');
    const q = s.cues.map((c) => (c.kind === 'visibility' && c.hide && 'query' in c.hide ? c.hide.query : ''));
    expect(q).toEqual(["storey = 'Level 3'", "storey = 'Level4'"]);
    const t = ok('on kind c\n  show class c\nend kind\nkind "IfcWall"');
    expect(t.cues[0]).toMatchObject({ show: { query: "class = 'IfcWall'" } });
    const u = ok('put 4 into n\nhide where level = n');
    expect(u.cues[0]).toMatchObject({ hide: { query: 'level = 4' } });
  });
  it('a handler may call another, and the line of the handler is the cue line', () => {
    const s = ok('on inner\n  caption "i"\nend inner\non outer\n  inner\n  inner\nend outer\nouter');
    expect(s.cues.map((c) => [c.line, c.at])).toEqual([[2, 0], [2, 3]]);
  });
  it('return ends a handler early', () => {
    expect(run('on early n\n  if n > 1 then return\n  caption "small"\nend early\nearly 5\nearly 1')).toEqual(['small']);
  });
  it('the first of a loop calls', () => {
    const s = ok('on beat\n  wait 1\n  mode solid\nend beat\nrepeat 3 times\n  beat\nend repeat');
    expect(s.cues.map((c) => c.at)).toEqual([1, 2, 3]);
  });
});

describe('functions', () => {
  it('gives back a value in an expression', () => {
    expect(run('function double x\n  return x * 2\nend double\ncaption "d=" & double(4)')).toEqual(['d=8']);
    expect(run('function add a, b\n  return a + b\nend add\nput add(1, 2) * add(3, 4) into n\ncaption "" & n')).toEqual(['21']);
  });
  it('is usable where a number goes, and may be defined after its use', () => {
    const s = ok('wait twice(1.5) seconds\nmode solid\nfunction twice x\n return x * 2\nend twice');
    expect(s.cues[0]!.at).toBe(3);
  });
  it('returns text and yes/no', () => {
    expect(run('function levelName n\n return "Level " & n\nend levelName\ncaption levelName(3)')).toEqual(['Level 3']);
    expect(run('function big n\n return n > 10\nend big\nif big(11) and not big(2) then caption "y"')).toEqual(['y']);
  });
  it('return in the middle: if and loops', () => {
    expect(run('function firstOver limit\n  repeat with i from 1 to 100\n    if i * i > limit then return i\n  end repeat\n  return 0\nend firstOver\ncaption "" & firstOver(50)')).toEqual(['8']);
  });
  it('recursion works up to the depth limit', () => {
    expect(run('function fact n\n  if n <= 1 then return 1\n  return n * fact(n - 1)\nend fact\ncaption "" & fact(5)')).toEqual(['120']);
    expect(run('function countdown n\n  if n <= 0 then return 0\n  return countdown(n - 1)\nend countdown\ncaption "" & countdown(15)')).toEqual(['0']);
  });
  it('recursion deeper than 16 is an error that says so', () => {
    const e = errs('function countdown n\n  if n <= 0 then return 0\n  return countdown(n - 1)\nend countdown\ncaption "" & countdown(40)');
    expect(e.length).toBeGreaterThan(0);
    expect(e.some((x) => /16 levels deep/.test(x.message))).toBe(true);
    expect(e.every((x) => !/ended without/.test(x.message))).toBe(true);
    const h = errs('on again\n  again\nend again\nagain');
    expect(h[0]!.message).toMatch(/16 levels deep/);
    expect(h[0]!.hint).toMatch(/`if` that stops it/);
  });
  it('a recursive handler places its statements in order', () => {
    const s = ok('on count n\n  if n < 1 then return\n  caption "n" & n for 1 seconds\n  count n - 1\nend count\ncount 3');
    expect(titles(s)).toEqual(['n3', 'n2', 'n1']);
    expect(s.cues.map((c) => c.at)).toEqual([0, 1, 2]);
  });
  it('only computes: no statements for the timeline', () => {
    const e = parseScript('function f x\n  fly to everything\n  return x\nend f').errors;
    expect(e[0]).toMatchObject({ line: 2 });
    expect(e[0]!.message).toMatch(/function cannot do this/);
    expect(parseScript('function f x\n  wait 1\n  return x\nend f').errors).toHaveLength(1);
  });
  it('a function that runs off its end', () => {
    const e = errs('function f x\n  if x > 5 then return 1\nend f\ncaption "" & f(1)');
    expect(e[0]!.message).toMatch(/ended without giving a value back/);
    expect(e[0]).toMatchObject({ line: 4 });
  });
});

describe('handler and function errors', () => {
  it('return outside a function', () => {
    const e = parseScript('wait 1\nreturn 5').errors;
    expect(e[0]).toMatchObject({ line: 2, col: 1 });
    expect(e[0]!.message).toMatch(/`return` is outside a function/);
    expect(parseScript('on h\n return 3\nend h').errors[0]!.message).toMatch(/does not return a value/);
    expect(parseScript('function f\n return\nend f').errors[0]!.message).toMatch(/needs one/);
  });
  it('an unknown handler is an unknown statement, with a suggestion', () => {
    const e = parseScript('on greet who\n caption who\nend greet\ngreat "x"').errors;
    expect(e[0]).toMatchObject({ line: 4 });
    expect(e[0]!.message).toMatch(/do not know the statement `great`/);
    expect(e[0]!.hint).toMatch(/greet/);
    expect(errs('caption "" & nope(1)')[0]!.message).toMatch(/do not know the function `nope`/);
    expect(errs('function double x\n return x * 2\nend double\ncaption "" & doubel(1)')[0]!.hint).toMatch(/double/);
  });
  it('wrong argument count', () => {
    const e = errs('on two a, b\n wait a\nend two\ntwo 1');
    expect(e[0]).toMatchObject({ line: 4 });
    expect(e[0]!.message).toMatch(/takes 2 values \(a, b\), but this call gives 1/);
    expect(e[0]!.hint).toMatch(/two a, b/);
    expect(errs('function f x\n return x\nend f\nput f() into n')[0]!.message).toMatch(/takes 1 value \(x\), but this call gives 0/);
    expect(errs('on h\n wait 1\nend h\nh 5')[0]!.message).toMatch(/takes no values/);
  });
  it('a handler is not a function and the other way round', () => {
    expect(errs('on h\n wait 1\nend h\nput h() into n')[0]!.message).toMatch(/is a handler, not a function/);
    expect(parseScript('function f x\n return x\nend f\nf 3').errors).toEqual([]);
    expect(errs('function f x\n return x\nend f\nf 3')[0]!.message).toMatch(/is a function/);
  });
  it('names that clash with the language, or with each other', () => {
    expect(errs('on show\n wait 1\nend show')[0]!.message).toMatch(/word of the language and cannot name a handler/);
    expect(errs('function if x\n return x\nend if')[0]).toBeDefined();
    expect(errs('on a\n wait 1\nend a\non a\n wait 2\nend a\na')[0]!.message).toMatch(/already defined on line 1/);
    expect(errs('on a over\n wait 1\nend a\na 1')[0]!.message).toMatch(/cannot be a parameter/);
    expect(errs('on a x, x\n wait 1\nend a\na 1, 2')[0]!.message).toMatch(/listed twice/);
  });
  it('definitions go at the top level', () => {
    const e = parseScript('repeat 2 times\n on a\n  wait 1\n end a\nend repeat').errors;
    expect(e[0]).toMatchObject({ line: 2 });
    expect(e[0]!.message).toMatch(/top level/);
  });
  it('an unclosed handler and a wrong end', () => {
    expect(parseScript('on a\n wait 1').errors[0]!.message).toMatch(/The `on a` on line 1 has no `end a`/);
    const e = parseScript('on a\n wait 1\nend b').errors;
    expect(e[0]!.message).toMatch(/does not match/);
    expect(e[0]!.hint).toMatch(/end a/);
  });
  it('a handler nobody calls is a warning', () => {
    const r = compileScript('on lonely\n wait 1\nend lonely\nmode solid', MODEL);
    expect(r.errors).toHaveLength(1);
    expect(r.errors[0]).toMatchObject({ severity: 'warning', line: 1 });
    expect(r.score).not.toBeNull();
  });
  it('an error inside a handler names where it was called from, once per place', () => {
    const e = errs('on bad\n  mode nope\nend bad\nbad');
    expect(e).toHaveLength(1);
    expect(e[0]).toMatchObject({ line: 2 });
    expect(e[0]!.message).toMatch(/inside `bad`, called on line 4/);
  });
});

describe('block errors', () => {
  it('an unclosed if', () => {
    const e = parseScript('if 1 < 2 then\n wait 1').errors;
    expect(e[0]).toMatchObject({ line: 1 });
    expect(e[0]!.message).toMatch(/The `if` on line 1 has no `end if`/);
    expect(e[0]!.hint).toMatch(/end if/);
  });
  it('end repeat closing an if', () => {
    const e = parseScript('if 1 < 2 then\n wait 1\nend repeat').errors;
    expect(e[0]).toMatchObject({ line: 3 });
    expect(e[0]!.message).toMatch(/`end repeat` does not match: the open block \(line 1\) is an `if`/);
    expect(e[0]!.hint).toMatch(/Write `end if`/);
  });
  it('end if closing a repeat', () => {
    expect(parseScript('repeat 2 times\n wait 1\nend if').errors[0]!.message).toMatch(/is a `repeat`/);
  });
  it('else without if', () => {
    const e = parseScript('wait 1\nelse\nwait 2').errors;
    expect(e[0]).toMatchObject({ line: 2, col: 1 });
    expect(e[0]!.message).toMatch(/`else` has no `if` before it/);
    const f = parseScript('if true then\n repeat 2 times\n wait 1\nelse\n wait 2\nend repeat\nend if').errors;
    expect(f[0]!.message).toMatch(/inside a `repeat`/);
  });
  it('a second else, and a statement after else', () => {
    expect(parseScript('if true then\n wait 1\nelse\n wait 2\nelse\n wait 3\nend if').errors[0]!.message).toMatch(/an `if` has one `else`/);
    expect(parseScript('if true then\n wait 1\nelse wait 2\nend if').errors[0]!.message).toMatch(/on the lines below/);
  });
  it('a block statement cannot follow `then` on the same line', () => {
    expect(parseScript('if true then repeat 2 times').errors[0]!.message).toMatch(/one-line `if` holds one plain statement/);
  });
  it('end with nothing open mentions the new blocks', () => {
    expect(parseScript('end if').errors[0]!.hint).toMatch(/end if/);
  });
  it('nesting limit', () => {
    const open = Array.from({ length: 10 }, () => 'if true then').join('\n');
    expect(parseScript(`${open}\n${'end if\n'.repeat(10)}`).errors.some((e) => /nested more than 8/.test(e.message))).toBe(true);
  });
});

describe('playback statements', () => {
  it('overlays', () => {
    const s = ok('show issues\nwait 1\nhide issues\nshow drawings\nhide drawings\nshow issues and drawings\nhide issues, drawings');
    expect(s.cues.map((c) => c)).toMatchObject([
      { kind: 'overlays', at: 0, dur: 0, issues: true },
      { kind: 'overlays', at: 1, issues: false },
      { kind: 'overlays', at: 1, drawings: true },
      { kind: 'overlays', at: 1, drawings: false },
      { kind: 'overlays', at: 1, issues: true, drawings: true },
      { kind: 'overlays', at: 1, issues: false, drawings: false },
    ]);
    expect((s.cues[0] as unknown as Record<string, unknown>).drawings).toBeUndefined();
    expect(s.cues[0]!.line).toBe(1);
  });
  it('show and hide still take elements', () => {
    expect(ok('show class IfcPump').cues[0]).toMatchObject({ kind: 'visibility' });
    expect(errs('show issues drawings')[0]).toBeDefined();
    expect(errs('show issues\nisolate issues')[0]!.line).toBe(2);
  });
  it('fade new elements', () => {
    const s = ok('fade new elements over 1.5 seconds\nwait 2\nfade new elements instantly\nput 0.5 into f\nfade new elements over f');
    expect(s.cues).toMatchObject([
      { kind: 'fadeDefault', at: 0, dur: 0, seconds: 1.5 },
      { kind: 'fadeDefault', at: 2, seconds: 0 },
      { kind: 'fadeDefault', at: 2, seconds: 0.5 },
    ]);
    expect(errs('fade new elements over -1 seconds')[0]!.message).toMatch(/cannot be negative/);
    expect(errs('fade everything')[0]!.message).toMatch(/Expected `new elements`/);
  });
  it('`fade` is still a usable name', () => {
    expect(ok('put 1.5 into fade\nhide class IfcPump fading over fade seconds').cues[0]).toMatchObject({ dur: 1.5 });
  });
  it('schedule gains a fade clause', () => {
    const s = ok('schedule "Tower A" over 30 seconds fade 0.8 seconds');
    expect(s.cues[0]).toMatchObject({ kind: 'schedule4d', fadeIn: 0.8 });
    expect((ok('schedule "Tower A" over 30 seconds').cues[0] as unknown as Record<string, unknown>).fadeIn).toBeUndefined();
    expect(ok('schedule "Tower A" fade 0 over 30').cues[0]).toMatchObject({ fadeIn: 0, dur: 30 });
    expect(errs('schedule "Tower A" fade -2')[0]!.message).toMatch(/cannot be negative/);
  });
});

describe('backward compatibility', () => {
  it('words that became keywords are still fine inside expressions and the old names', () => {
    expect(ok('put 3 into count\nput count + 1 into count\ncaption "" & count').cues[0]).toMatchObject({ title: '4' });
    expect(ok('put 2 into step\nwait step').duration).toBe(2);
  });
  it('a bare word in a where stays text when no name matches', () => {
    expect(ok('hide where storey = Roof').cues[0]).toMatchObject({ hide: { query: "storey = 'Roof'" } });
  });
});

describe('highlighting', () => {
  it('colours the new keywords', () => {
    const kinds = (line: string): string[] => highlightLine(line).filter((p) => p.text.trim()).map((p) => `${p.text}:${p.cls}`);
    expect(kinds('if there are class IfcPump then')).toContain('if:kw');
    expect(kinds('if there are class IfcPump then')).toContain('then:opt');
    expect(kinds('else if x > 1 then')[0]).toBe('else:kw');
    expect(kinds('repeat while x < 3')).toContain('while:opt');
    expect(kinds('on showFloor name')[0]).toBe('on:kw');
    expect(kinds('return x')[0]).toBe('return:kw');
    expect(kinds('fade new elements over 2 seconds')[0]).toBe('fade:kw');
    expect(kinds('if a and not b then')).toContain('and:op');
  });
});
