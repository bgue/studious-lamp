// The 4D statements of the animation script language: lexer (colours), parser (tree and errors), compiler (cues, times through the
// plan's time map, errors with line and column), element words, highlight.
import { describe, expect, it } from 'vitest';
import { compileScript } from '../src/anim/script/compiler';
import type { CompileOptions } from '../src/anim/script/compiler';
import { parseScript } from '../src/anim/script/parser';
import { lexLine } from '../src/anim/script/lexer';
import { highlightLine } from '../src/anim/script/highlight';
import type { Cue } from '../src/anim/score';
import { fakePlan } from './director-helpers';
import type { FourDPlan } from '../src/schedule/types';

const plan = fakePlan();
const opts: CompileOptions = { plans: (n) => (n === 'Tower A' ? plan : null), planNames: () => ['Tower A', 'Block B'] };
const compile = (text: string, o: CompileOptions = opts) => compileScript(text, o);
const cues = (text: string, o: CompileOptions = opts): Cue[] => {
  const r = compile(text, o);
  expect(r.errors.filter((e) => e.severity === 'error'), text).toEqual([]);
  return r.score!.cues;
};
const errs = (text: string, o: CompileOptions = opts) => compile(text, o).errors.filter((e) => e.severity === 'error');
const at = (iso: string): number => ((Date.parse(`${iso}Z`) - plan.window.from) / (plan.window.to - plan.window.from)) * 120;

describe('4D lexer', () => {
  it('reads #rrggbb as a colour and keeps other # as comments', () => {
    const t = lexLine('tint active #E53935 -- x', 1);
    expect(Array.isArray(t) && t.map((x) => [x.type, x.text])).toEqual([['word', 'tint'], ['word', 'active'], ['colour', '#e53935']]);
    for (const c of ['# a comment', '#abc', '#12345', '#1234567', '#ffffgg']) expect(lexLine(`tint active ${c}`, 1)).toHaveLength(2);
  });
  it('highlights colours and the 4D words', () => {
    const p = highlightLine('tint critical #e53935');
    expect(p.map((x) => x.cls).filter(Boolean)).toEqual(['kw', 'el', 'num']);
    expect(highlightLine('at date "2027-01-01"').filter((x) => x.cls).map((x) => x.cls)).toEqual(['kw', 'opt', 'str']);
    expect(highlightLine('# hello').map((x) => x.cls)).toEqual(['com']);
  });
});

describe('4D parser', () => {
  it('parses every statement', () => {
    const r = parseScript(`schedule "P" view actual from "2026-09-01" to "2028-05-30" over 120 seconds
at date "2027-01-18"
at milestone "Roof"
tint where class = IfcWall red fading over 1
tint active #e53935
tint everything off
explode storeys by 1.5 over 2 seconds
explode radial
collapse over 2
collapse
focus active
focus nothing
section box around storey "Level 3" over 1.5
section box around where class = IfcSlab
section box off over 1
section box off
`);
    expect(r.errors).toEqual([]);
    expect(r.program.body.map((s) => s.kind)).toEqual(['schedule', 'at', 'at', 'tint', 'tint', 'tint', 'explode', 'explode', 'collapse', 'collapse', 'focus', 'focus', 'section', 'section', 'section', 'section']);
  });

  it('takes a colour name after a where clause, but a value that looks like one stays a value', () => {
    const r = parseScript('tint where colour = red red\ntint where class = IfcWall blue');
    expect(r.errors).toEqual([]);
    const [a, b] = r.program.body as Array<{ kind: 'tint'; target: { k: string; query: string }; colour: { v: string } | null }>;
    expect(a!.target.query).toBe("colour = 'red'");
    expect(a!.colour!.v).toBe('red');
    expect(b!.target.query).toBe("class = 'IfcWall'");
    expect(b!.colour!.v).toBe('blue');
  });

  it('gives errors with line and column', () => {
    const e = (text: string) => parseScript(text).errors[0]!;
    expect(e('schedule over 5')).toMatchObject({ line: 1, col: 10, message: expect.stringMatching(/name of a 4D plan/) });
    expect(e('schedule "P" view sideways')).toMatchObject({ line: 1, col: 19, message: expect.stringMatching(/planned.*actual.*variance/) });
    expect(e('schedule "P" from 2027')).toMatchObject({ message: expect.stringMatching(/date in double quotes/) });
    expect(e('schedule "P" over 3 over 4').message).toMatch(/given twice/);
    expect(e('at 2027-01-01')).toMatchObject({ line: 1, col: 4, message: expect.stringMatching(/`date` or `milestone`/) });
    expect(e('at date 2027').message).toMatch(/in double quotes/);
    expect(e('at date "2027-01-01" now').message).toMatch(/did not expect/);
    expect(e('explode sideways')).toMatchObject({ col: 9, message: expect.stringMatching(/storeys.*radial/) });
    expect(e('section around active').message).toMatch(/`box`/);
    expect(e('section box over 2').message).toMatch(/`around` or `off`/);
    expect(e('tint active').message).toMatch(/Expected a colour/);
    expect(e('collapse fast').message).toMatch(/did not expect/);
    expect(e('focus active now').message).toMatch(/did not expect/);
  });

  it('knows the element words', () => {
    const r = parseScript('select active\nselect completed\nselect critical');
    expect(r.errors).toEqual([]);
    expect((r.program.body[1] as { target: object }).target).toMatchObject({ k: 'schedule', set: 'completed' });
  });
});

describe('4D compiler', () => {
  it('schedule: a schedule4d cue by plan name, over the time given, not waiting', () => {
    const c = cues('schedule "Tower A" view actual from "2026-09-01" to "2028-05-30" over 90 seconds\nfly to everything over 3 seconds');
    expect(c[0]).toMatchObject({ kind: 'schedule4d', at: 0, dur: 90, plan: { name: 'Tower A' }, view: 'actual', from: '2026-09-01', to: '2028-05-30' });
    expect(c[1]).toMatchObject({ kind: 'camera', at: 0 });
  });

  it('schedule: without over, the plan\'s film length; extra fields only when given', () => {
    const c = cues('schedule "Tower A"')[0]! as Extract<Cue, { kind: 'schedule4d' }>;
    expect(c.dur).toBe(120);
    expect(c.view).toBeUndefined();
    expect('from' in c).toBe(false);
  });

  it('at date: absolute times through the time map, scaled to the schedule\'s over, even before the end of earlier statements', () => {
    const c = cues('schedule "Tower A" over 60 seconds\ncaption "x" for 30 seconds\nat date "2027-06-15"\nfly to everything over 2 seconds\nat date "2026-10-01"\nexplode storeys') as Cue[];
    const fly = c.find((x) => x.kind === 'camera')!;
    expect(fly.at).toBeCloseTo(at('2027-06-15') / 2, 6);
    const ex = c.find((x) => x.kind === 'explode')!;
    expect(ex.at).toBeCloseTo(at('2026-10-01') / 2, 6);
    expect(ex.at).toBeLessThan(30); // earlier than the end of the caption above: allowed
    expect(compile('schedule "Tower A"\nat date "2027-01-01T12:30"').score!.cues[0]!.dur).toBe(120);
    const t = compile('schedule "Tower A"\nat date "2027-01-01T12:30"\nexplode storeys').score!.cues.find((x) => x.kind === 'explode')!;
    expect(t.at).toBeCloseTo(at('2027-01-01T12:30'), 6);
  });

  it('at milestone: the first second of the milestone, a later schedule statement takes over', () => {
    const c = cues('schedule "Tower A"\nat milestone "Frame complete"\ncaption "x"\nat milestone "envelope CLOSED"\ncaption "y"');
    const caps = c.filter((x) => x.kind === 'caption');
    expect(caps[0]!.at).toBeCloseTo(at('2027-06-15'), 6);
    expect(caps[1]!.at).toBeCloseTo(at('2027-11-02'), 6);
  });

  it('at milestone inside a hold: the hold starts there, and a wait reaches into it', () => {
    const p: FourDPlan = { ...plan, timeMap: [[plan.window.from, 0], [plan.milestones[0]!.at, 50], [plan.milestones[0]!.at, 52], [plan.window.to, 120]] };
    const c = cues('schedule "Tower A"\nat milestone "Frame complete"\nwait 1\ncaption "x"', { plans: () => p });
    expect(c.find((x) => x.kind === 'caption')!.at).toBeCloseTo(51, 6);
  });

  it('errors with line and column: unknown plan, bad date, unknown milestone, at before a schedule', () => {
    expect(errs('schedule "Tower B"')[0]).toMatchObject({ line: 1, col: 10, message: 'There is no 4D plan named "Tower B".', hint: expect.stringMatching(/Did you mean "Tower A"/) });
    expect(errs('schedule "Zzz"', { plans: () => null })[0]!.hint).toMatch(/Load the 4D plan first/);
    expect(errs('schedule "Tower A"\nat date "2027-13-01"')[0]).toMatchObject({ line: 2, col: 9, message: '"2027-13-01" is not a date.' });
    expect(errs('schedule "Tower A"\nat date "2027-02-30"')[0]!.message).toMatch(/is not a date/);
    expect(errs('schedule "Tower A"\nat date "tomorrow"')[0]!.hint).toMatch(/YYYY-MM-DD/);
    expect(errs('schedule "Tower A"\nat milestone "Frame compete"')[0]).toMatchObject({ line: 2, col: 14, hint: 'Did you mean "Frame complete"?' });
    expect(errs('schedule "Tower A" from "x"')[0]).toMatchObject({ line: 1, col: 25 });
    expect(errs('at date "2027-01-01"')[0]).toMatchObject({ line: 1, col: 1, message: expect.stringMatching(/needs a running schedule/) });
    expect(errs('explode storeys\nat milestone "x"')[0]!.line).toBe(2);
  });

  it('warns about a date outside the plan and counts it as the nearest end', () => {
    const r = compile('schedule "Tower A"\nat date "2030-01-01"\nexplode storeys');
    expect(r.score).not.toBeNull();
    expect(r.errors).toMatchObject([{ severity: 'warning', line: 2, message: expect.stringMatching(/outside the plan \(2026-09-01 to 2028-05-30\)/) }]);
    expect(r.score!.cues.find((x) => x.kind === 'explode')!.at).toBeCloseTo(120, 6);
  });

  it('uses the plan registry when no plans option is given', async () => {
    const { registerPlan, unregisterPlan } = await import('../src/anim/fourd/plans');
    registerPlan('Reg', plan);
    try {
      expect(compileScript('schedule "Reg" over 10 seconds').errors).toEqual([]);
    } finally {
      unregisterPlan('Reg');
    }
    expect(compileScript('schedule "Reg"').errors[0]!.message).toMatch(/no 4D plan/);
  });

  it('tint: colour names and #rrggbb, fading, off', () => {
    const c = cues('tint class IfcWall red fading over 1.5 seconds\ntint critical #E53935\ntint active off\ntint everything "blue"');
    expect(c[0]).toMatchObject({ kind: 'tint', at: 0, dur: 1.5, elements: { query: "class = 'IfcWall'" }, colour: '#e53935' });
    expect(c[1]).toMatchObject({ at: 1.5, dur: 0, elements: { schedule: 'critical' }, colour: '#e53935' });
    expect(c[2]).toMatchObject({ elements: { schedule: 'active' }, colour: null });
    expect(c[3]).toMatchObject({ colour: '#1e88e5' });
    const e = errs('tint active fuchsia')[0]!;
    expect(e).toMatchObject({ line: 1, col: 13, message: 'I do not know the colour "fuchsia".' });
  });

  it('explode, collapse, focus, section box', () => {
    const c = cues('explode storeys by 1.5 over 3 seconds\nexplode radial\ncollapse\nfocus active\nfocus nothing\nsection box around storey "Level 3"\nsection box around active over 2\nsection box off over 1');
    expect(c[0]).toMatchObject({ kind: 'explode', mode: 'storeys', factor: 1.5, at: 0, dur: 3, ease: 'inOut' });
    expect((c[1] as { factor?: number }).factor).toBeUndefined();
    expect(c[1]).toMatchObject({ mode: 'radial', at: 3, dur: 2 });
    expect(c[2]).toMatchObject({ kind: 'collapse', at: 5, dur: 2, ease: 'inOut' });
    expect(c[3]).toMatchObject({ kind: 'focus', at: 7, dur: 0, elements: { schedule: 'active' } });
    expect(c[4]).toMatchObject({ kind: 'focus', elements: null });
    expect(c[5]).toMatchObject({ kind: 'sectionBox', dur: 1.5, around: { storey: 'Level 3' } });
    expect(c[6]).toMatchObject({ kind: 'sectionBox', dur: 2, around: { schedule: 'active' } });
    expect(c[7]).toMatchObject({ kind: 'sectionBox', dur: 1, around: null });
    expect(errs('explode storeys by 0')[0]!.message).toMatch(/outside 0 to 10/);
  });

  it('the element words work wherever elements do', () => {
    const c = cues('fly to critical over 1 seconds margin 2\nlabel completed with activity, percent, finish for 2 seconds\nselect active');
    expect(c[0]).toMatchObject({ to: { frame: { schedule: 'critical' }, margin: 2 } });
    expect(c[1]).toMatchObject({ kind: 'label', elements: { schedule: 'completed' }, fields: ['activity', 'percent', 'finish'] });
    expect(compile('label active with name, percent for 2').errors).toEqual([]);
  });

  it('the 4D words cannot be names of variables', () => {
    for (const w of ['active', 'date', 'from', 'box']) expect(errs(`put 1 into ${w}`)[0]!.message).toMatch(/word of the language/);
  });
});
