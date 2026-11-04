// A small, strict XML reader and the escaping used by the writers. Pure TypeScript, no DOM, so the BCF code runs
// identically in the browser and in node tests (DOMParser does not exist in node, and its error reporting for malformed
// input is lenient and browser dependent).
//
// Supported: prolog, comments, processing instructions, CDATA, the five predefined entities and numeric references,
// namespace prefixes (dropped: elements and attributes are matched by local name), attributes in single or double quotes.
// A DOCTYPE is skipped without expanding anything (no custom entities, so no entity bombs). Rejected: mismatched or
// unclosed tags, duplicate attributes, unquoted attributes, text outside the root, several roots, unknown entities.

export interface XNode {
  /** Local name (prefix removed). */
  name: string;
  attrs: Record<string, string>;
  children: XNode[];
  /** Concatenated character data directly inside this element (not trimmed). */
  text: string;
}

export class XmlError extends Error {
  constructor(message: string, readonly offset: number) {
    super(`XML error at offset ${offset}: ${message}`);
  }
}

const NAME_START = /[A-Za-z_:À-￿]/;
const NAME_CHAR = /[A-Za-z0-9_:.\-·À-￿]/;

function localName(n: string): string {
  const i = n.indexOf(':');
  return i >= 0 ? n.slice(i + 1) : n;
}

function decodeEntities(s: string, at: number): string {
  if (s.indexOf('&') < 0) return s;
  return s.replace(/&(?:(#x[0-9A-Fa-f]+|#[0-9]+|[A-Za-z][A-Za-z0-9]*);)?/g, (m, e: string | undefined) => {
    if (e === undefined) throw new XmlError('bare "&"', at);
    if (e[0] === '#') {
      const cp = e[1] === 'x' ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10);
      if (!(cp >= 0 && cp <= 0x10ffff) || (cp >= 0xd800 && cp <= 0xdfff) || cp === 0) throw new XmlError(`bad character reference ${m}`, at);
      return String.fromCodePoint(cp);
    }
    switch (e) {
      case 'amp': return '&';
      case 'lt': return '<';
      case 'gt': return '>';
      case 'quot': return '"';
      case 'apos': return "'";
      default: throw new XmlError(`unknown entity ${m}`, at);
    }
  });
}

/** Decode bytes of an XML file: UTF-8 (BOM stripped) or UTF-16 with a BOM. */
export function decodeXmlBytes(bytes: Uint8Array): string {
  if (bytes.length >= 2 && bytes[0] === 0xff && bytes[1] === 0xfe) return new TextDecoder('utf-16le').decode(bytes.subarray(2));
  if (bytes.length >= 2 && bytes[0] === 0xfe && bytes[1] === 0xff) return new TextDecoder('utf-16be').decode(bytes.subarray(2));
  return new TextDecoder('utf-8').decode(bytes); // strips a UTF-8 BOM
}

export function parseXml(src: string): XNode {
  let i = 0;
  const n = src.length;
  let root: XNode | null = null;
  const stack: XNode[] = [];

  const ws = (c: string): boolean => c === ' ' || c === '\t' || c === '\n' || c === '\r';
  const skipWs = (): void => {
    while (i < n && ws(src[i]!)) i++;
  };
  const readName = (): string => {
    const s = i;
    if (i >= n || !NAME_START.test(src[i]!)) throw new XmlError('name expected', i);
    i++;
    while (i < n && NAME_CHAR.test(src[i]!)) i++;
    return src.slice(s, i);
  };

  if (src.charCodeAt(0) === 0xfeff) i = 1;
  while (i < n) {
    if (src[i] !== '<') {
      const end = src.indexOf('<', i);
      const stop = end < 0 ? n : end;
      const raw = src.slice(i, stop);
      if (stack.length === 0) {
        if (raw.trim() !== '') throw new XmlError('text outside the root element', i);
      } else {
        stack[stack.length - 1]!.text += decodeEntities(raw, i);
      }
      i = stop;
      continue;
    }
    if (src.startsWith('<!--', i)) {
      const e = src.indexOf('-->', i + 4);
      if (e < 0) throw new XmlError('unterminated comment', i);
      i = e + 3;
    } else if (src.startsWith('<![CDATA[', i)) {
      const e = src.indexOf(']]>', i + 9);
      if (e < 0 || stack.length === 0) throw new XmlError('bad CDATA section', i);
      stack[stack.length - 1]!.text += src.slice(i + 9, e);
      i = e + 3;
    } else if (src.startsWith('<?', i)) {
      const e = src.indexOf('?>', i + 2);
      if (e < 0) throw new XmlError('unterminated processing instruction', i);
      i = e + 2;
    } else if (src.startsWith('<!', i)) {
      // DOCTYPE: skip to the matching '>' honouring one level of [ ... ]
      let depth = 0;
      let j = i + 2;
      for (; j < n; j++) {
        const c = src[j];
        if (c === '[') depth++;
        else if (c === ']') depth--;
        else if (c === '>' && depth <= 0) break;
      }
      if (j >= n) throw new XmlError('unterminated declaration', i);
      i = j + 1;
    } else if (src[i + 1] === '/') {
      i += 2;
      const name = readName();
      skipWs();
      if (src[i] !== '>') throw new XmlError('">" expected in closing tag', i);
      i++;
      const top = stack.pop();
      if (!top) throw new XmlError(`unexpected closing tag </${name}>`, i);
      if (top.name !== localName(name)) throw new XmlError(`closing tag </${name}> does not match <${top.name}>`, i);
    } else {
      i++;
      const qname = readName();
      const node: XNode = { name: localName(qname), attrs: {}, children: [], text: '' };
      for (;;) {
        const before = i;
        skipWs();
        const c = src[i];
        if (c === '>' || c === '/') break;
        if (i === before) throw new XmlError('whitespace expected between attributes', i);
        if (i >= n) throw new XmlError('unterminated tag', i);
        const an = readName();
        skipWs();
        if (src[i] !== '=') throw new XmlError(`"=" expected after attribute ${an}`, i);
        i++;
        skipWs();
        const q = src[i];
        if (q !== '"' && q !== "'") throw new XmlError(`quoted value expected for attribute ${an}`, i);
        const e = src.indexOf(q, i + 1);
        if (e < 0) throw new XmlError('unterminated attribute value', i);
        const rawVal = src.slice(i + 1, e);
        if (rawVal.indexOf('<') >= 0) throw new XmlError('"<" in attribute value', i);
        const key = localName(an);
        if (an === 'xmlns' || an.startsWith('xmlns:')) {
          i = e + 1;
          continue;
        }
        if (key in node.attrs) throw new XmlError(`duplicate attribute ${an}`, i);
        node.attrs[key] = decodeEntities(rawVal.replace(/[\t\n\r]/g, ' '), i);
        i = e + 1;
      }
      let selfClose = false;
      if (src[i] === '/') {
        selfClose = true;
        i++;
      }
      if (src[i] !== '>') throw new XmlError('">" expected', i);
      i++;
      const parent = stack[stack.length - 1];
      if (parent) parent.children.push(node);
      else if (root) throw new XmlError('more than one root element', i);
      else root = node;
      if (!selfClose) stack.push(node);
    }
  }
  if (stack.length) throw new XmlError(`unclosed element <${stack[stack.length - 1]!.name}>`, n);
  if (!root) throw new XmlError('no root element', 0);
  return root;
}

// ---------------------------------------------------------------- tree helpers

export function child(n: XNode | undefined | null, name: string): XNode | undefined {
  return n?.children.find((c) => c.name === name);
}
export function childrenOf(n: XNode | undefined | null, name: string): XNode[] {
  return n ? n.children.filter((c) => c.name === name) : [];
}
export function textOf(n: XNode | undefined | null): string | undefined {
  if (!n) return undefined;
  return n.text.trim();
}
export function childText(n: XNode | undefined | null, name: string): string | undefined {
  return textOf(child(n, name));
}
export function childNum(n: XNode | undefined | null, name: string): number | undefined {
  const t = childText(n, name);
  if (t === undefined || t === '') return undefined;
  const v = Number(t);
  return Number.isFinite(v) ? v : undefined;
}

// ---------------------------------------------------------------- writing

/** Escape character data or an attribute value; control characters that XML 1.0 forbids are dropped. */
export function esc(s: string): string {
  // eslint-disable-next-line no-control-regex
  const clean = s.replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F￾￿]/g, '').replace(/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/g, '');
  return clean.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/** Number as xs:double text (no exponent surprises for tiny values, finite only). */
export function num(v: number): string {
  if (!Number.isFinite(v)) return '0';
  const r = Math.abs(v) < 1e-12 ? 0 : v;
  return String(r);
}
