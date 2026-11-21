import { describe, expect, it } from 'vitest';
import { compileScript, DEFAULT_SECONDS, LIMITS, MODE_PRESETS } from '../src/anim/script/compiler';
import type { CompileOptions } from '../src/anim/script/compiler';
import { runScript, NO_PLAYER_MESSAGE } from '../src/anim/script/runner';
import { EXAMPLES } from '../src/anim/script/examples';
import { fakePlan } from './director-helpers';
import { MODES } from '../src/ui/topBar';
import { SCORE_SCHEMA, scoreEnd } from '../src/anim/score';
import type { Cue, PlayOptions, Score, ScorePlayerApi } from '../src/anim/score';

const ok = (src: string, opts?: CompileOptions): Score => {
  const r = compileScript(src, opts);
  expect(r.errors.filter((e) => e.severity === 'error'), src).toEqual([]);
  return r.score!;
};
const errs = (src: string, opts?: CompileOptions) => compileScript(src, opts).errors;
const cue = (s: Score, i = 0): Cue => s.cues[i]!;

const model = (ids: string[]): CompileOptions => ({ resolve: () => ids, setNames: () => ['Pumps', 'Walls'] });

describe('compiler: the score', () => {
  it('makes a v1 score that remembers its source', () => {
    const s = ok('wait 1\nmode solid', { name: 'demo' });
    expect(s.schema).toBe(SCORE_SCHEMA);
    expect(s.source).toEqual({ kind: 'script', name: 'demo', text: 'wait 1\nmode solid' });
    expect(s.duration).toBe(1);
  });

  it('an empty script is a score with no cues', () => {
    expect(ok('-- nothing\n')).toMatchObject({ cues: [], duration: 0 });
  });

  it('sequences statements: each starts when the one before it ends', () => {
    const s = ok('fly to everything over 3 seconds\nwait 1\norbit 90 degrees over 2 seconds\nmode ghost');
    expect(s.cues.map((c) => [c.kind, c.at, c.dur])).toEqual([['camera', 0, 3], ['camera', 4, 2], ['preset', 6, 0]]);
    expect(s.duration).toBe(6);
  });

  it('sets cue.line to the source line', () => {
    const s = ok('-- c\n\nwait 1\nselect nothing\n  mode glow');
    expect(s.cues.map((c) => c.line)).toEqual([4, 5]);
  });

  it('a trailing wait counts in the duration', () => {
    expect(ok('mode solid\nwait 5').duration).toBe(5);
  });
});

describe('compiler: every statement', () => {
  it('fly to', () => {
    const c = cue(ok('fly to class IfcPump over 3 seconds ease out margin 2.5'));
    expect(c).toMatchObject({ kind: 'camera', at: 0, dur: 3, ease: 'out', to: { frame: { query: "class = 'IfcPump'" }, margin: 2.5 } });
  });
  it('fly to defaults: 2 seconds, in out', () => {
    expect(cue(ok('fly to the selection'))).toMatchObject({ dur: DEFAULT_SECONDS.fly, ease: 'inOut', to: { frame: { selection: true } } });
  });
  it('fly to a set, everything and GlobalIds', () => {
    expect(cue(ok('fly to set "Pumps"'))).toMatchObject({ to: { frame: { set: 'Pumps' } } });
    expect(cue(ok('fly to everything'))).toMatchObject({ to: { frame: { all: true } } });
    expect(cue(ok('fly to elements "a", "b"'))).toMatchObject({ to: { frame: { globalIds: ['a', 'b'] } } });
  });
  it('fly to a saved view', () => {
    expect(cue(ok('fly to view "Plant room" over 4s'))).toMatchObject({ kind: 'camera', dur: 4, to: { view: 'Plant room' } });
  });
  it('rejects a margin outside 1 to 6', () => {
    const [e] = errs('fly to everything margin 9');
    expect(e).toMatchObject({ severity: 'error', line: 1 });
    expect(e!.message).toMatch(/outside 1 to 6/);
  });
  it('orbit', () => {
    expect(cue(ok('orbit 90 degrees about class IfcPump over 6 seconds'))).toMatchObject({ kind: 'camera', dur: 6, to: { orbitDeg: 90, about: { query: "class = 'IfcPump'" } } });
    expect(cue(ok('orbit -45'))).toMatchObject({ dur: DEFAULT_SECONDS.orbit, to: { orbitDeg: -45 } });
  });
  it('set: a number blends with an ease, other values switch', () => {
    expect(cue(ok('set cinematic.glowStrength to 1.2 over 2 seconds'))).toMatchObject({ kind: 'param', path: 'cinematic.glowStrength', to: 1.2, dur: 2, ease: 'inOut' });
    expect(cue(ok('set a.b to 3 over 2 ease linear'))).toMatchObject({ ease: 'linear' });
    expect(cue(ok('set a.b to 3'))).toMatchObject({ dur: 0, to: 3 });
    expect(cue(ok('set a.b to off'))).toMatchObject({ to: false });
    expect(cue(ok('set a.b to "text"'))).toMatchObject({ to: 'text' });
    expect(cue(ok('set imaging.style to radiograph'))).toMatchObject({ to: 'radiograph' });
    expect(cue(ok('set a.b to 1, 0.5, 0.25'))).toMatchObject({ to: [1, 0.5, 0.25] });
  });
  it('set uses a variable for a word', () => {
    expect(cue(ok('put 4 into level\nset a.b to level', {}), 0)).toMatchObject({ to: 4 });
  });
  it('mode maps to the preset of the top bar', () => {
    for (const m of MODES) expect(cue(ok(`mode ${m.id.toUpperCase()}`))).toMatchObject({ kind: 'preset', id: m.presetId, dur: 0 });
    expect(Object.keys(MODE_PRESETS).sort()).toEqual(MODES.map((m) => m.id).sort());
  });
  it('mode: an unknown mode is an error with the nearest', () => {
    const [e] = errs('mode radiogram');
    expect(e!.hint).toMatch(/radiograph/);
  });
  it('apply preset resolves an id or a name when the presets are known', () => {
    const presets = [{ id: 'peelback', name: 'Peelback' }, { id: 'mri-scan', name: 'MRI scan' }];
    expect(cue(ok('apply preset "mri SCAN"', { presets }))).toMatchObject({ kind: 'preset', id: 'mri-scan' });
    expect(cue(ok('apply preset "peelback"', { presets }))).toMatchObject({ id: 'peelback' });
    const [e] = errs('apply preset "Peelbck"', { presets });
    expect(e!.hint).toMatch(/Peelback/);
    expect(cue(ok('apply preset "Anything"'))).toMatchObject({ id: 'Anything' });
  });
  it('show, hide, isolate: instant or fading', () => {
    expect(cue(ok('hide class IfcSlab'))).toMatchObject({ kind: 'visibility', dur: 0, hide: { query: "class = 'IfcSlab'" } });
    expect(cue(ok('hide class IfcSlab fading over 2 seconds'))).toMatchObject({ dur: 2 });
    expect(cue(ok('show set "Pumps" fading 1'))).toMatchObject({ dur: 1, show: { set: 'Pumps' } });
    expect(cue(ok('isolate class IfcPump'))).toMatchObject({ isolate: { query: "class = 'IfcPump'" } });
  });
  it('show everything and isolate everything use showAll; hide everything hides all', () => {
    expect(cue(ok('show everything fading over 1.5 seconds'))).toMatchObject({ showAll: true, dur: 1.5 });
    expect(cue(ok('isolate everything'))).toMatchObject({ showAll: true });
    expect(cue(ok('hide everything'))).toMatchObject({ hide: { all: true } });
  });
  it('select', () => {
    expect(cue(ok('select where storey = "Level 2"'))).toMatchObject({ kind: 'select', elements: { query: "storey = 'Level 2'" }, dur: 0 });
    expect(cue(ok('select nothing'))).toMatchObject({ kind: 'select', elements: null });
  });
  it('caption lasts its time and holds the sequence', () => {
    const s = ok('caption "Title" "More text" for 4 seconds\nwait 1');
    expect(cue(s)).toMatchObject({ kind: 'caption', title: 'Title', text: 'More text', dur: 4 });
    expect(s.duration).toBe(5);
    expect(cue(ok('caption "T"'))).toMatchObject({ dur: DEFAULT_SECONDS.caption });
    expect(cue(ok('caption "T"')).kind === 'caption' && 'text' in cue(ok('caption "T"'))).toBe(false);
  });
  it('caption joins text, names and numbers', () => {
    expect(cue(ok('put 2 * 3 into n\ncaption "Step " & n & " of " & (n + 1)'))).toMatchObject({ title: 'Step 6 of 7' });
  });
  it('label and hover', () => {
    expect(cue(ok('label class IfcPump with Name, storey, "Pset_X.Prop" for 5 seconds'))).toMatchObject({ kind: 'label', fields: ['name', 'storey', 'Pset_X.Prop'], dur: 5 });
    expect(cue(ok('hover set "Pumps"'))).toMatchObject({ kind: 'hover', dur: DEFAULT_SECONDS.hover, elements: { set: 'Pumps' } });
    const h = ok('repeat for each element in everything\nhover it for 1\nend repeat', model(['a']));
    expect(cue(h)).toMatchObject({ elements: { globalIds: ['a'] }, dur: 1 });
  });
  it('label warns about an unknown plain field but still compiles', () => {
    const r = compileScript('label everything with nmae');
    expect(r.score).not.toBeNull();
    expect(r.errors[0]).toMatchObject({ severity: 'warning', line: 1 });
    expect(r.errors[0]!.hint).toMatch(/name/);
  });
  it('wait and put with expressions', () => {
    const s = ok('put 1.5 into gap\nwait gap * 2 + 1 seconds\nmode solid');
    expect(cue(s).at).toBe(4);
  });
  it('variables: unknown names, reserved names, division by zero, negative time', () => {
    expect(errs('wait gapp')[0]!.message).toMatch(/do not know the name `gapp`/);
    expect(errs('put 1 into gap\nwait gapp')[0]!.hint).toMatch(/gap/);
    expect(errs('put 1 into over')[0]!.message).toMatch(/word of the language/);
    expect(errs('wait 1 / 0')[0]!.message).toMatch(/divides by zero/);
    expect(errs('wait -1')[0]!.message).toMatch(/cannot be negative/);
    expect(errs('fly to everything over 5000')[0]!.message).toMatch(/longer than the limit/);
  });
  it('a semantic error gives a null score and a position; the other statements are still checked', () => {
    const r = compileScript('wait x\nwait y\nmode ghost');
    expect(r.score).toBeNull();
    expect(r.errors.map((e) => e.line)).toEqual([1, 2]);
  });
  it('a syntax error stops before the compile', () => {
    const r = compileScript('wait x\nflyy');
    expect(r.errors.map((e) => e.line)).toEqual([2]);
  });
});

describe('compiler: together', () => {
  it('starts its statements at the same time and lasts as long as the longest', () => {
    const s = ok('wait 1\ntogether\n  fly to everything over 3 seconds\n  caption "x" for 5 seconds\n  hide class IfcSlab fading over 1 seconds\nend together\nmode ghost');
    expect(s.cues.map((c) => [c.kind, c.at, c.dur])).toEqual([['camera', 1, 3], ['caption', 1, 5], ['visibility', 1, 1], ['preset', 6, 0]]);
    expect(s.duration).toBe(6);
  });
  it('nested blocks keep their own sequence inside', () => {
    const s = ok('together\n  repeat 2 times\n    fly to everything over 2 seconds\n  end repeat\n  caption "a" for 1 seconds\nend together\nmode solid');
    expect(s.cues.map((c) => [c.kind, c.at])).toEqual([['camera', 0], ['caption', 0], ['camera', 2], ['preset', 4]]);
  });
  it('an empty block warns and takes no time', () => {
    const r = compileScript('together\nend together\nmode solid');
    expect(r.score!.cues[0]!.at).toBe(0);
    expect(r.errors[0]).toMatchObject({ severity: 'warning' });
  });
  it('cues come out sorted by start time', () => {
    const s = ok('together\n  wait 5\n  mode glow\nend together');
    expect(s.cues.map((c) => c.at)).toEqual([0]);
  });
});

describe('compiler: repeat', () => {
  it('repeat N times repeats the body in sequence, with index', () => {
    const s = ok('repeat 3 times\n  orbit 90 degrees over index seconds\nend repeat');
    expect(s.cues.map((c) => [c.at, c.dur])).toEqual([[0, 1], [1, 2], [3, 3]]);
  });
  it('repeat 0 times does nothing', () => {
    expect(ok('repeat 0 times\n  wait 1\nend repeat').cues).toEqual([]);
  });
  it('needs a whole count, within the cap', () => {
    expect(errs('repeat 1.5 times\nend repeat')[0]!.message).toMatch(/whole number/);
    expect(errs('repeat 501 times\n  wait 1\nend repeat')[0]!.message).toMatch(/at most 500/);
    expect(errs('repeat -1 times\nend repeat')[0]!.message).toMatch(/whole number/);
    expect(ok('repeat 500 times\n  mode solid\nend repeat').cues.length).toBe(500);
  });
  it('for each element expands at compile time, with it as the element', () => {
    const s = ok('repeat for each element in class IfcPump\n  fly to it over 2 seconds\n  select it\nend repeat', model(['g1', 'g2', 'g3']));
    expect(s.cues.map((c) => [c.kind, c.at, c.kind === 'camera' ? (c.to as { frame: unknown }).frame : (c as { elements: unknown }).elements])).toEqual([
      ['camera', 0, { globalIds: ['g1'] }], ['select', 2, { globalIds: ['g1'] }],
      ['camera', 2, { globalIds: ['g2'] }], ['select', 4, { globalIds: ['g2'] }],
      ['camera', 4, { globalIds: ['g3'] }], ['select', 6, { globalIds: ['g3'] }],
    ]);
  });
  it('gives the resolver the reference of the elements', () => {
    let got: unknown = null;
    ok('repeat for each element in where class = IfcPump\nend repeat', { resolve: (r) => { got = r; return []; } });
    expect(got).toEqual({ query: "class = 'IfcPump'" });
  });
  it('for each element needs a model and caps the number of elements', () => {
    expect(errs('repeat for each element in everything\nend repeat')[0]!.message).toMatch(/needs the model/);
    expect(errs('repeat for each element in everything\nend repeat', { resolve: () => null })[0]!.message).toMatch(/needs the model/);
    const many = Array.from({ length: 501 }, (_, i) => `g${i}`);
    const [e] = errs('repeat for each element in everything\n  wait 1\nend repeat', model(many));
    expect(e!.message).toMatch(/501.*at most 500/);
    expect(e!.hint).toMatch(/where/);
    expect(ok('repeat for each element in everything\n  select it\nend repeat', model(many.slice(0, 500))).cues.length).toBe(500);
  });
  it('for each element with no match warns and does nothing', () => {
    const r = compileScript('repeat for each element in everything\n  wait 1\nend repeat', model([]));
    expect(r.score!.cues).toEqual([]);
    expect(r.errors[0]).toMatchObject({ severity: 'warning' });
  });
  it('for each set uses the set names as it', () => {
    const s = ok('repeat for each set in sets\n  select it\n  caption "Set " & it for 2 seconds\nend repeat', model([]));
    expect(s.cues.map((c) => c.kind)).toEqual(['select', 'caption', 'select', 'caption']);
    expect(cue(s, 0)).toMatchObject({ elements: { set: 'Pumps' } });
    expect(cue(s, 1)).toMatchObject({ title: 'Set Pumps' });
    expect(cue(s, 2)).toMatchObject({ elements: { set: 'Walls' }, at: 2 });
  });
  it('for each set needs the sets', () => {
    expect(errs('repeat for each set in sets\nend repeat')[0]!.message).toMatch(/needs the stored selection sets/);
  });
  it('it outside a loop is an error with a hint', () => {
    const [e] = errs('select it');
    expect(e!.message).toMatch(/`it` has no meaning here/);
    expect(e!.hint).toMatch(/repeat for each/);
    expect(errs('wait it')[0]!.message).toMatch(/`it` is not a number/);
  });
  it('index and it are restored after the loop; an outer index survives an inner loop', () => {
    const s = ok('repeat 2 times\n  repeat 2 times\n    wait 0\n  end repeat\n  wait index\n  mode solid\nend repeat');
    expect(s.cues.map((c) => c.at)).toEqual([1, 3]);
  });
  it('caps the total number of statements run by nested loops', () => {
    const r = compileScript('repeat 500 times\n  repeat 500 times\n    wait 0\n  end repeat\nend repeat');
    expect(r.score).toBeNull();
    expect(r.errors[0]!.message).toMatch(/more than 20000 statements/);
  });
  it('caps the cue count and the total duration (one hour)', () => {
    const cues = compileScript('repeat 400 times\n  repeat 20 times\n    select nothing\n  end repeat\nend repeat', { limits: { maxSteps: 1e9 } });
    expect(cues.errors[0]!.message).toMatch(/more than 5000 cues/);
    const long = compileScript('repeat 100 times\n  wait 100\nend repeat\nmode solid');
    expect(long.score).toBeNull();
    expect(long.errors[0]!.message).toMatch(/longer than 1 hour/);
    expect(ok('wait 3600\nmode solid').duration).toBe(3600);
    expect(LIMITS).toMatchObject({ maxIterations: 500, maxCues: 5000, maxDuration: 3600 });
  });
  it('reports an error inside a loop once', () => {
    const r = compileScript('repeat 5 times\n  wait nope\nend repeat');
    expect(r.errors.length).toBe(1);
  });
});

describe('compiler: checks against the app', () => {
  const paths = ['xray.alphaMax', 'xray.alphaMin', 'cinematic.glowStrength', 'cinematic.bloom.radius'];
  it('accepts a known path, fixes its case, and warns with the nearest for an unknown one', () => {
    expect(cue(ok('set xray.alphamax to 0.3', { paramPaths: paths }))).toMatchObject({ path: 'xray.alphaMax' });
    const r = compileScript('set xray.alphaMx to 0.3', { paramPaths: paths });
    expect(r.score).not.toBeNull();
    const e = r.errors[0]!;
    expect(e).toMatchObject({ severity: 'warning', line: 1, col: 5 });
    expect(e!.hint).toMatch(/xray\.alphaMax/);
    expect(errs('set alphaMax to 1', { paramPaths: paths })[0]!.hint).toMatch(/xray\.alphaMax/);
  });
  it('explains a group name', () => {
    const [e] = errs('set cinematic to 1', { paramPaths: paths });
    expect(e!.message).toMatch(/group of settings/);
    expect(e!.hint).toMatch(/cinematic\.glowStrength/);
  });
  it('warns once, and does not fail, when the paths cannot be listed', () => {
    const r = compileScript('set a.b to 1\nset c.d to 2');
    expect(r.score).not.toBeNull();
    expect(r.errors.filter((e) => e.severity === 'warning').length).toBe(1);
    expect(compileScript('set a.b to 1', { paramPaths: [] }).errors[0]).toMatchObject({ severity: 'warning' });
  });
  it('warns about an unknown set or saved view, with the nearest', () => {
    const r = compileScript('select set "Pumpz"\nfly to view "Plant"', { setNames: () => ['Pumps'], views: ['Plant room'] });
    expect(r.score).not.toBeNull();
    expect(r.errors.map((e) => e.severity)).toEqual(['warning', 'warning']);
    expect(r.errors[0]!.hint).toMatch(/Pumps/);
    expect(r.errors[1]!.hint).toMatch(/Plant room/);
  });
});

describe('compiler: the examples', () => {
  const demo = fakePlan({ window: { from: Date.UTC(2027, 0, 4), to: Date.UTC(2027, 3, 1) }, timeMap: [[Date.UTC(2027, 0, 4), 0], [Date.UTC(2027, 3, 1), 40]], milestones: [] });
  const opts: CompileOptions = { plans: (n) => (n === 'Demo' ? demo : null), resolve: () => ['a', 'b', 'c', 'd'], setNames: () => ['Pumps', 'Walls'], paramPaths: ['cinematic.glowStrength'], presets: [{ id: 'coordination', name: 'Coordination' }] };
  for (const e of EXAMPLES) {
    it(`${e.id} compiles without errors or warnings`, () => {
      const r = compileScript(e.text, opts);
      expect(r.errors).toEqual([]);
      expect(r.score!.cues.length).toBeGreaterThan(3);
      expect(r.score!.duration).toBeGreaterThan(5);
      expect(scoreEnd(r.score!.cues)).toBeLessThanOrEqual(r.score!.duration);
    });
  }
  it('there are 3 to 5 of them with unique ids', () => {
    expect(EXAMPLES.length).toBeGreaterThanOrEqual(3);
    expect(new Set(EXAMPLES.map((x) => x.id)).size).toBe(EXAMPLES.length);
  });
});

// ---------------------------------------------------------------- a fake player

class FakePlayer implements ScorePlayerApi {
  playing = false;
  paused = false;
  time = 0;
  played: Score | null = null;
  opts: PlayOptions | undefined;
  accept = true;
  play(score: Score, opts?: PlayOptions): boolean {
    if (!this.accept) return false;
    this.played = score;
    this.opts = opts;
    this.playing = true;
    return true;
  }
  stop(): void { this.playing = false; }
  pause(): void { this.paused = true; }
  resume(): void { this.paused = false; }
  seek(t: number): void { this.time = t; }
  /** Starts every cue in order and ends. */
  runThrough(): void {
    this.played!.cues.forEach((c, i) => this.opts?.onCue?.(c, i));
    this.playing = false;
    this.opts?.onEnd?.();
  }
}

describe('runScript with a fake player', () => {
  it('plays the score and reports the line of each cue, then null at the end', () => {
    const p = new FakePlayer();
    const lines: Array<number | null> = [];
    let ended = 0;
    const r = runScript('mode ghost\nwait 1\nfly to everything over 2 seconds\ncaption "Hi" for 1 seconds', {}, p, { onLine: (l) => lines.push(l), onEnd: () => ended++ });
    expect(r.ok).toBe(true);
    expect(r.message).toMatch(/Playing: 3 cues, 4 seconds/);
    expect(p.played!.source).toMatchObject({ kind: 'script' });
    p.runThrough();
    expect(lines).toEqual([1, 3, 4, null]);
    expect(ended).toBe(1);
  });
  it('reports a missing player without throwing', () => {
    const r = runScript('mode ghost', {}, null);
    expect(r).toMatchObject({ ok: false, message: NO_PLAYER_MESSAGE });
    expect(r.score).not.toBeNull();
  });
  it('does not play a script with an error and says where', () => {
    const p = new FakePlayer();
    const r = runScript('mode ghost\nwait x', {}, p);
    expect(r.ok).toBe(false);
    expect(r.message).toMatch(/^Line 2, column 6:/);
    expect(p.played).toBeNull();
  });
  it('says so for a script with no cues and for a player that refuses', () => {
    expect(runScript('wait 2', {}, new FakePlayer()).message).toMatch(/no cues/);
    const p = new FakePlayer();
    p.accept = false;
    expect(runScript('mode ghost', {}, p).message).toMatch(/did not start/);
  });
  it('survives a player that throws', () => {
    const p = new FakePlayer();
    p.play = () => { throw new Error('boom'); };
    expect(runScript('mode ghost', {}, p).message).toMatch(/boom/);
  });
});
