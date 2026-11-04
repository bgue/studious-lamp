import { describe, expect, it } from 'vitest';
import { PackError, defaultModelName, parseArgs, parseCamera, parseList, parseSelect, unknownTools } from '../tools/pack/lib.mjs';

const fail = (argv: string[]): PackError => {
  try {
    parseArgs(argv);
  } catch (e) {
    expect(e).toBeInstanceOf(PackError);
    return e as PackError;
  }
  throw new Error(`expected a usage error for ${argv.join(' ')}`);
};

describe('xray-pack arguments', () => {
  it('parses a full command line', () => {
    const { help, inputs, options } = parseArgs([
      'a.ifc', 'b.ifczip', '-o', 'out.html', '--params', 'p.json', '--preset', 'Clean', '--select', 'abc, class:IfcDuctSegment',
      '--title', 'My model', '--name', 'm', '--tools', 'xray,section', '--open-tool', 'section', '--kiosk',
      '--camera', '1,2,3:4,5,6', '--ifc-reader', '--samples', '--force', '--quiet',
    ]);
    expect(help).toBe(false);
    expect(inputs).toEqual(['a.ifc', 'b.ifczip']);
    expect(options).toMatchObject({
      out: 'out.html', params: 'p.json', preset: 'Clean', select: ['abc', 'class:IfcDuctSegment'], title: 'My model', name: 'm',
      tools: ['xray', 'section'], openTool: 'section', kiosk: true, ifcReader: true, samples: true, force: true, quiet: true,
      camera: { position: [1, 2, 3], target: [4, 5, 6] },
    });
  });

  it('accepts --opt=value and defaults the flags to false', () => {
    const { options } = parseArgs(['m.glb', '--out=o.html', '--title=T']);
    expect(options.out).toBe('o.html');
    expect(options.title).toBe('T');
    expect(options).toMatchObject({ kiosk: false, ifcReader: false, samples: false, force: false, quiet: false });
  });

  it('--help needs nothing else', () => {
    expect(parseArgs(['--help']).help).toBe(true);
    expect(parseArgs(['-h']).help).toBe(true);
  });

  it('rejects bad command lines with exit code 1', () => {
    expect(fail([]).code).toBe(1);
    expect(fail(['a.ifc']).message).toMatch(/-o/);
    expect(fail(['-o', 'x.html']).message).toMatch(/no input/);
    expect(fail(['a.ifc', '-o', 'x.txt']).message).toMatch(/\.html/);
    expect(fail(['a.obj', '-o', 'x.html']).message).toMatch(/unsupported input/);
    expect(fail(['a.ifc', 'b.glb', '-o', 'x.html']).message).toMatch(/mix/);
    expect(fail(['a.glb', 'b.glb', '-o', 'x.html']).message).toMatch(/one \.glb/);
    expect(fail(['a.ifc', '-o', 'x.html', '--bogus']).message).toMatch(/unknown option/);
    expect(fail(['a.ifc', '-o']).message).toMatch(/needs a value/);
    expect(fail(['a.ifc', '-o', 'x.html', '--title']).message).toMatch(/needs a value/);
    expect(fail(['a.ifc', '-o', 'x.html', '-o', 'y.html']).message).toMatch(/twice/);
    expect(fail(['a.ifc', '-o', 'x.html', '--kiosk=1']).message).toMatch(/does not take a value/);
    expect(fail(['a.ifc', '-o', 'x.html', '--tools', 'xray', '--open-tool', 'measure']).message).toMatch(/not in --tools/);
    expect(fail(['a.ifc', '-o', 'x.html', '--camera', '1,2:3']).message).toMatch(/--camera/);
    expect(fail(['a.ifc', '-o', 'x.html', '--select', 'class:']).message).toMatch(/--select/);
    expect(fail(['a.ifc', '-o', 'x.html', '--name', ' ']).message).toMatch(/--name/);
  });

  it('error messages are one line', () => {
    for (const argv of [[], ['a.ifc'], ['a.obj', '-o', 'x.html'], ['a.ifc', '-o', 'x.html', '--camera', 'x']]) {
      expect(fail(argv).message).not.toContain('\n');
    }
  });
});

describe('xray-pack lists', () => {
  it('parseList trims, drops empties and duplicates', () => {
    expect(parseList(' a, b,, a ,c ')).toEqual(['a', 'b', 'c']);
    expect(parseList('')).toEqual([]);
  });

  it('parseSelect splits GlobalIds and classes', () => {
    const s = parseSelect('2O2Fr$t4X7Zf8NOew3FLOH, class:IfcDuctSegment ,CLASS:IfcWindow,3x$Abc');
    expect(s.gids).toEqual(['2O2Fr$t4X7Zf8NOew3FLOH', '3x$Abc']);
    expect(s.classes).toEqual(['IfcDuctSegment', 'IfcWindow']);
    expect(s.entries).toHaveLength(4);
  });

  it('parseSelect rejects empty lists and bad entries', () => {
    expect(() => parseSelect(' , ')).toThrow(PackError);
    expect(() => parseSelect('class:Duct')).toThrow(/class:IfcSomething/);
    expect(() => parseSelect('two words')).toThrow(/GlobalId/);
  });

  it('parseCamera needs six finite numbers', () => {
    expect(parseCamera('0,1.5,-2:3,4,5e0')).toEqual({ position: [0, 1.5, -2], target: [3, 4, 5] });
    for (const bad of ['', '1,2,3', '1,2,3:4,5', '1,2,3:4,5,x', '1,2,3:4,5,', '1,2,3:4,5,6:7,8,9']) expect(() => parseCamera(bad)).toThrow(PackError);
  });

  it('defaultModelName strips the directory and the extension', () => {
    expect(defaultModelName('/x/y/AC20-FZK-Haus.ifc')).toBe('AC20-FZK-Haus');
    expect(defaultModelName('C:\\m\\Plan.IFCZIP')).toBe('Plan');
    expect(defaultModelName('b.glb')).toBe('b');
  });

  it('unknownTools flags ids the registry does not reserve', () => {
    expect(unknownTools(['xray', 'section', 'mine'])).toEqual(['mine']);
    expect(unknownTools(undefined)).toEqual([]);
  });
});
