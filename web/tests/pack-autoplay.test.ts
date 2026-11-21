// xray-pack --flythroughs / --scripts / --autoplay / --loop: argument rules, document checks and the boot document.
import { describe, expect, it } from 'vitest';
import { PackError, buildBoot, checkFlythroughs, checkScripts, parseArgs, parseAutoplay, scriptNameOf } from '../tools/pack/lib.mjs';

const fly = {
  schema: 'xray-flythroughs/1',
  flythroughs: [
    { id: 'a', name: 'Tour', keyframes: [{ id: 'k1' }, { id: 'k2' }] },
    { id: 'b', name: 'Empty', keyframes: [] },
  ],
};

const usage = (argv: string[]): string => {
  try {
    parseArgs(argv);
  } catch (e) {
    expect(e).toBeInstanceOf(PackError);
    return (e as PackError).message;
  }
  throw new Error('expected a usage error');
};
const base = ['m.glb', '-o', 'o.html'];

describe('xray-pack autoplay arguments', () => {
  it('parses the new options', () => {
    const { options } = parseArgs([...base, '--flythroughs', 'f.json', '--scripts', 'a.xrayanim, b.xrayanim', '--autoplay', 'flythrough:Tour', '--loop']);
    expect(options).toMatchObject({ flythroughs: 'f.json', scripts: ['a.xrayanim', 'b.xrayanim'], autoplay: { kind: 'flythrough', name: 'Tour' }, loop: true });
  });
  it('keeps spaces in names and accepts a script', () => {
    expect(parseAutoplay('script:Walk around the pumps')).toEqual({ kind: 'script', name: 'Walk around the pumps' });
    expect(parseAutoplay('Flythrough : Tour')).toEqual({ kind: 'flythrough', name: 'Tour' });
  });
  it('rejects bad combinations', () => {
    expect(usage([...base, '--autoplay', 'tour'])).toMatch(/expected flythrough/);
    expect(usage([...base, '--autoplay', 'flythrough:'])).toMatch(/expected flythrough/);
    expect(usage([...base, '--autoplay', 'flythrough:Tour'])).toMatch(/needs --flythroughs/);
    expect(usage([...base, '--autoplay', 'script:Tour'])).toMatch(/needs --scripts/);
    expect(usage([...base, '--loop'])).toMatch(/needs --autoplay/);
    expect(usage([...base, '--scripts', ' , '])).toMatch(/at least one file/);
  });
});

describe('xray-pack fly-through and script checks', () => {
  it('keeps fly-throughs with keyframes and warns about the others', () => {
    const r = checkFlythroughs(fly, { kind: 'flythrough', name: 'tour' });
    expect(r.names).toEqual(['Tour']);
    expect(r.warnings).toHaveLength(1);
    expect((r.doc as { flythroughs: unknown[] }).flythroughs).toHaveLength(1);
  });
  it('rejects other documents and an unknown autoplay name', () => {
    expect(() => checkFlythroughs({ schema: 'xray-views/1' })).toThrow(/not a fly-through document/);
    expect(() => checkFlythroughs({ schema: 'xray-flythroughs/1', flythroughs: [] })).toThrow(/no usable/);
    expect(() => checkFlythroughs(fly, { kind: 'flythrough', name: 'Nope' })).toThrow(/is not in the fly-through file/);
  });
  it('names a script by its file and checks the text', () => {
    expect(scriptNameOf('/x/y/Walk around.xrayanim')).toBe('Walk around');
    expect(scriptNameOf('C:\\x\\a.txt')).toBe('a');
    const r = checkScripts([{ path: 'a.xrayanim', text: '\uFEFFfly to everything over 3 seconds\r\n' }], { kind: 'script', name: 'A' });
    expect(r.scripts).toEqual([{ name: 'a', text: 'fly to everything over 3 seconds\n' }]);
    expect(() => checkScripts([{ path: 'a.xrayanim', text: '   ' }])).toThrow(/empty/);
    expect(() => checkScripts([{ path: 'a.xrayanim', text: 'a\u0000b' }])).toThrow(/not a text file/);
    expect(() => checkScripts([{ path: 'a.xrayanim', text: 'x' }], { kind: 'script', name: 'b' })).toThrow(/not among/);
  });
});

describe('xray-pack boot document with autoplay', () => {
  it('writes flythroughs, scripts and autoplay only when asked', () => {
    expect(buildBoot('m')).toEqual({ model: 'm' });
    const options = { autoplay: { kind: 'flythrough' as const, name: 'Tour' }, loop: true };
    const boot = buildBoot('m', options, undefined, undefined, { flythroughs: { schema: 'xray-flythroughs/1', flythroughs: [] }, scripts: [{ name: 'a', text: 'x' }] });
    expect(boot).toMatchObject({ flythroughs: { schema: 'xray-flythroughs/1' }, scripts: [{ name: 'a', text: 'x' }], autoplay: { flythrough: 'Tour', loop: true } });
    expect(buildBoot('m', { autoplay: { kind: 'script', name: 'a' }, loop: false }).autoplay).toEqual({ script: 'a' });
  });
});
