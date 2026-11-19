import { describe, expect, it } from 'vitest';
import { decodeGuid, encodeGuid, hash128, isIfcGuid, xrayGuid } from '../src/ifcsave/ifcGuid';
import { cutChars, decodeString, encodeString, entityLine, formatArgs, parseArgs, parseStatement, scanStatements, stepReal, stepString } from '../src/ifcsave/stepText';
import { fileBytes, latin1, modelIfc } from './ifcsave-helpers';

describe('STEP strings', () => {
  const cases = ["plain", "it's", 'back\\slash', 'tab\tnl\n', 'Müller äöü ß', '中文 日本語', 'rocket \u{1F680} and \u{1F4A9}', "'''", '', 'mix \\X2\\0041\\X0\\ literal'];
  it('round-trips through encode and decode', () => {
    for (const s of cases) expect(decodeString(encodeString(s))).toBe(s);
  });
  it('writes only printable ASCII', () => {
    for (const s of cases) expect(/^[\x20-\x7e]*$/.test(encodeString(s))).toBe(true);
  });
  it('uses the documented escapes', () => {
    expect(encodeString("a'b")).toBe("a''b");
    expect(encodeString('a\\b')).toBe('a\\\\b');
    expect(encodeString('a\nb')).toBe('a\\X\\0Ab');
    expect(encodeString('ä')).toBe('\\X2\\00E4\\X0\\');
    expect(encodeString('\u{1F680}')).toBe('\\X4\\0001F680\\X0\\');
    expect(stepString('x')).toBe("'x'");
  });
  it('decodes \\X\\ and \\S\\ forms from other writers', () => {
    expect(decodeString('M\\X\\FCller')).toBe('Müller');
    expect(decodeString('\\S\\d')).toBe('ä');
  });
  it('cuts by code point', () => {
    expect(cutChars('abcdef', 3)).toBe('abc');
    expect(cutChars('\u{1F680}\u{1F680}\u{1F680}', 2)).toBe('\u{1F680}\u{1F680}');
    expect(cutChars('ab', 5)).toBe('ab');
  });
  it('formats reals with a decimal point', () => {
    expect(stepReal(1)).toBe('1.');
    expect(stepReal(0.25)).toBe('0.25');
    expect(stepReal(1e-7)).toBe('1.E-7');
  });
});

describe('statement tokenizer', () => {
  it('does not end a statement at a semicolon inside a string or a comment', () => {
    const text = "/* head; comment */\n#1=IFCWALL('a;b',$);\n#2=IFCSLAB('it''s; here' /* x; */,#1);\nENDSEC;";
    const st = [...scanStatements(text)].map((s) => s.text);
    expect(st).toEqual(["#1=IFCWALL('a;b',$);", "#2=IFCSLAB('it''s; here' /* x; */,#1);", 'ENDSEC;']);
    const p = parseStatement(st[1]!)!;
    expect(p.id).toBe(2);
    expect(p.type).toBe('IFCSLAB');
    expect(p.args).toEqual([{ t: 'str', v: "it's; here" }, { t: 'ref', id: 1 }]);
  });
  it('reports offsets', () => {
    const text = '  #1=A();\n#2=B();';
    const s = [...scanStatements(text)];
    expect(text.slice(s[1]!.start, s[1]!.end)).toBe('#2=B();');
  });
});

describe('parseArgs and formatArgs', () => {
  it('parses every value kind', () => {
    const v = parseArgs("'a',$,*,#5,.T.,1.5E-3,(#1,#2),IFCLABEL('x'),(),\"0F\"");
    expect(v.map((x) => x.t)).toEqual(['str', 'null', 'derived', 'ref', 'enum', 'num', 'list', 'typed', 'list', 'bin']);
  });
  it('a partial parse returns the complete leading arguments', () => {
    expect(parseArgs("'a',#2,'unfinished", true)).toEqual([{ t: 'str', v: 'a' }, { t: 'ref', id: 2 }]);
  });
  it('round-trips 200 real lines', () => {
    const text = latin1(fileBytes(modelIfc('AC20-FZK-Haus.ifc')));
    let n = 0;
    for (const s of scanStatements(text)) {
      const p = parseStatement(s.text);
      if (!p || p.id === undefined || p.args.length < 3) continue;
      const open = s.text.indexOf('(');
      const inner = s.text.slice(open + 1, s.text.lastIndexOf(')'));
      const again = formatArgs(p.args);
      expect(parseArgs(again)).toEqual(p.args);
      expect(again).toBe(inner.replace(/\s+(?=(?:[^']*'[^']*')*[^']*$)/g, ''));
      if (++n >= 200) break;
    }
    expect(n).toBe(200);
  });
  it('builds entity lines', () => {
    expect(entityLine(7, 'IFCX', ['$', "'a'"])).toBe("#7=IFCX($,'a');");
  });
});

describe('GUIDs', () => {
  it('are 22 characters, deterministic and well formed', () => {
    const g = xrayGuid('pset', 'a|b');
    expect(g).toBe(xrayGuid('pset', 'a|b'));
    expect(g).not.toBe(xrayGuid('pset', 'a|c'));
    expect(isIfcGuid(g)).toBe(true);
  });
  it('encode and decode are inverse', () => {
    for (const k of ['x', 'y', 'a long key with spaces']) {
      const w = hash128(k);
      expect(decodeGuid(encodeGuid(w))).toEqual(w);
    }
    expect(encodeGuid([0, 0, 0, 0])).toBe('0000000000000000000000');
    expect(encodeGuid([0xffffffff, 0xffffffff, 0xffffffff, 0xffffffff])[0]).toBe('3');
  });
  it('does not collide on 5000 keys', () => {
    const s = new Set<string>();
    for (let i = 0; i < 5000; i++) s.add(xrayGuid('k', String(i)));
    expect(s.size).toBe(5000);
  });
});
