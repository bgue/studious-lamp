import { describe, expect, it } from 'vitest';
import { child, childText, decodeXmlBytes, esc, parseXml } from '../src/bcf/xml';

describe('bcf xml reader', () => {
  it('parses elements, attributes, entities, CDATA, comments and prefixes', () => {
    const n = parseXml(`<?xml version="1.0"?>\n<!DOCTYPE x [<!ENTITY e "boom">]>\n<x:Root xmlns:x="u" a='1' x:b="&lt;2&gt;"><!-- c --><Kid>a &amp; b &#65;&#x42;</Kid><Raw><![CDATA[<z>]]></Raw><Empty/></x:Root>`);
    expect(n.name).toBe('Root');
    expect(n.attrs).toEqual({ a: '1', b: '<2>' });
    expect(childText(n, 'Kid')).toBe('a & b AB');
    expect(childText(n, 'Raw')).toBe('<z>');
    expect(child(n, 'Empty')).toBeDefined();
  });

  it('does not expand custom entities', () => {
    expect(() => parseXml('<!DOCTYPE x [<!ENTITY e "boom">]><x>&e;</x>')).toThrow(/unknown entity/);
  });

  it.each([
    ['<a><b></a>', /does not match/],
    ['<a>', /unclosed/],
    ['<a></a><b/>', /more than one root/],
    ['<a x=1/>', /quoted/],
    ['<a x="1" x="2"/>', /duplicate/],
    ['text<a/>', /outside/],
    ['<a>&</a>', /bare/],
    ['', /no root/],
  ])('rejects malformed input %s', (src, re) => {
    expect(() => parseXml(src)).toThrow(re);
  });

  it('decodes UTF-8 BOM and UTF-16', () => {
    const u8 = new Uint8Array([0xef, 0xbb, 0xbf, ...new TextEncoder().encode('<a>é</a>')]);
    expect(childText(parseXml(decodeXmlBytes(u8)), 'x')).toBeUndefined();
    expect(parseXml(decodeXmlBytes(u8)).text).toBe('é');
    const s = '<a>ü</a>';
    const u16 = new Uint8Array(2 + s.length * 2);
    u16[0] = 0xff;
    u16[1] = 0xfe;
    for (let i = 0; i < s.length; i++) {
      u16[2 + i * 2] = s.charCodeAt(i) & 255;
      u16[3 + i * 2] = s.charCodeAt(i) >> 8;
    }
    expect(parseXml(decodeXmlBytes(u16)).text).toBe('ü');
  });

  it('escapes text and drops characters XML forbids', () => {
    expect(esc('a<b>&"c"\u0001\u0008x')).toBe('a&lt;b&gt;&amp;&quot;c&quot;x');
    expect(parseXml(`<a>${esc('1 < 2 & "3"')}</a>`).text).toBe('1 < 2 & "3"');
  });
});
