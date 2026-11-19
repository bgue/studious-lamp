// STEP (ISO 10303-21) text helpers: string escapes, a statement tokenizer, an argument parser and formatter, and line builders.
// Pure: no DOM, no WASM.

// ---------------------------------------------------------------- strings

/** Encode a JS string as the body of a STEP string (without the quotes). */
export function encodeString(s: string): string {
  let out = '';
  let run = ''; // pending run of characters that need \X2\ (UTF-16) or \X4\ (astral)
  let runKind: 2 | 4 | 0 = 0;
  const flush = (): void => {
    if (runKind) out += (runKind === 2 ? '\\X2\\' : '\\X4\\') + run + '\\X0\\';
    run = '';
    runKind = 0;
  };
  for (const ch of s) {
    const cp = ch.codePointAt(0)!;
    if (cp === 0x27) {
      flush();
      out += "''";
    } else if (cp === 0x5c) {
      flush();
      out += '\\\\';
    } else if (cp < 0x20) {
      flush();
      out += '\\X\\' + cp.toString(16).toUpperCase().padStart(2, '0');
    } else if (cp <= 0x7e) {
      flush();
      out += ch;
    } else if (cp <= 0xffff) {
      if (runKind !== 2) flush();
      runKind = 2;
      run += cp.toString(16).toUpperCase().padStart(4, '0');
    } else {
      if (runKind !== 4) flush();
      runKind = 4;
      run += cp.toString(16).toUpperCase().padStart(8, '0');
    }
  }
  flush();
  return out;
}

/** A complete STEP string literal, quotes included. */
export const stepString = (s: string): string => `'${encodeString(s)}'`;

/** Decode the body of a STEP string (without quotes). Understands '' \\ \X\HH \X2\..\X0\ \X4\..\X0\ \S\c and ignores \P?\ page directives. */
export function decodeString(body: string): string {
  if (body.indexOf('\\') < 0 && body.indexOf("'") < 0) return body;
  let out = '';
  for (let i = 0; i < body.length; ) {
    const c = body[i]!;
    if (c === "'" && body[i + 1] === "'") {
      out += "'";
      i += 2;
    } else if (c === '\\') {
      if (body[i + 1] === '\\') {
        out += '\\';
        i += 2;
      } else if (body.startsWith('\\X2\\', i) || body.startsWith('\\X4\\', i)) {
        const w = body[i + 2] === '2' ? 4 : 8;
        const end = body.indexOf('\\X0\\', i + 4);
        const hex = body.slice(i + 4, end < 0 ? body.length : end);
        for (let k = 0; k + w <= hex.length; k += w) out += String.fromCodePoint(parseInt(hex.slice(k, k + w), 16));
        i = end < 0 ? body.length : end + 4;
      } else if (body.startsWith('\\X\\', i)) {
        out += String.fromCharCode(parseInt(body.slice(i + 3, i + 5), 16));
        i += 5;
      } else if (body.startsWith('\\S\\', i)) {
        out += String.fromCharCode(body.charCodeAt(i + 3) + 128);
        i += 4;
      } else if (/^\\P[A-I]\\/.test(body.slice(i, i + 4))) {
        i += 4;
      } else {
        out += c;
        i++;
      }
    } else {
      out += c;
      i++;
    }
  }
  return out;
}

/** Cut a string to at most `max` code points (IfcLabel and IfcIdentifier hold 255). */
export function cutChars(s: string, max: number): string {
  let n = 0;
  let i = 0;
  for (const ch of s) {
    if (n === max) return s.slice(0, i);
    n++;
    i += ch.length;
  }
  return s;
}

// ---------------------------------------------------------------- statements

export interface StepStatement {
  /** Offset of the first character (not whitespace, not a comment). */
  start: number;
  /** Offset just after the terminating semicolon. */
  end: number;
  text: string;
}

/** Split STEP text into statements. A semicolon inside a string or a comment does not end one. Comments are skipped. */
export function* scanStatements(text: string): Generator<StepStatement> {
  const n = text.length;
  let i = 0;
  let start = -1;
  while (i < n) {
    const c = text.charCodeAt(i);
    if (c === 0x27) {
      if (start < 0) start = i;
      i++;
      while (i < n && text.charCodeAt(i) !== 0x27) i++;
      i++; // '' inside a string closes and re-opens, which this loop handles by running once more
    } else if (c === 0x2f && text.charCodeAt(i + 1) === 0x2a) {
      const e = text.indexOf('*/', i + 2);
      i = e < 0 ? n : e + 2;
    } else if (c === 0x3b) {
      if (start >= 0) yield { start, end: i + 1, text: text.slice(start, i + 1) };
      start = -1;
      i++;
    } else {
      if (start < 0 && c > 0x20) start = i;
      i++;
    }
  }
}

// ---------------------------------------------------------------- arguments

export type StepValue =
  | { t: 'null' }
  | { t: 'derived' }
  | { t: 'ref'; id: number }
  | { t: 'str'; v: string }
  | { t: 'num'; v: string }
  | { t: 'enum'; v: string }
  | { t: 'bin'; v: string }
  | { t: 'list'; v: StepValue[] }
  | { t: 'typed'; name: string; args: StepValue[] };

export const NULL: StepValue = { t: 'null' };
export const ref = (id: number): StepValue => ({ t: 'ref', id });
export const str = (v: string): StepValue => ({ t: 'str', v });
export const list = (v: StepValue[]): StepValue => ({ t: 'list', v });

class Eof extends Error {}

/**
 * Parse the text between the outer parentheses of an entity ("'abc',$,#5,(#1,#2)") into values.
 * With `partial`, a text that ends early returns the complete top-level arguments read so far instead of throwing.
 */
export function parseArgs(text: string, partial = false): StepValue[] {
  let i = 0;
  const n = text.length;
  const ws = (): void => {
    for (;;) {
      while (i < n && text.charCodeAt(i) <= 0x20) i++;
      if (text.charCodeAt(i) === 0x2f && text.charCodeAt(i + 1) === 0x2a) {
        const e = text.indexOf('*/', i + 2);
        i = e < 0 ? n : e + 2;
      } else return;
    }
  };
  const value = (): StepValue => {
    ws();
    if (i >= n) throw new Eof();
    const c = text[i]!;
    if (c === '$') {
      i++;
      return NULL;
    }
    if (c === '*') {
      i++;
      return { t: 'derived' };
    }
    if (c === '#') {
      let j = i + 1;
      while (j < n && text.charCodeAt(j) >= 48 && text.charCodeAt(j) <= 57) j++;
      const id = Number(text.slice(i + 1, j));
      i = j;
      return { t: 'ref', id };
    }
    if (c === "'") {
      let j = i + 1;
      for (;;) {
        if (j >= n) throw new Eof();
        if (text[j] === "'") {
          if (text[j + 1] === "'") j += 2;
          else break;
        } else j++;
      }
      const body = text.slice(i + 1, j);
      i = j + 1;
      return { t: 'str', v: decodeString(body) };
    }
    if (c === '"') {
      const e = text.indexOf('"', i + 1);
      if (e < 0) throw new Eof();
      const v = text.slice(i + 1, e);
      i = e + 1;
      return { t: 'bin', v };
    }
    if (c === '.') {
      const e = text.indexOf('.', i + 1);
      if (e < 0) throw new Eof();
      const v = text.slice(i + 1, e);
      i = e + 1;
      return { t: 'enum', v };
    }
    if (c === '(') {
      i++;
      const items: StepValue[] = [];
      ws();
      if (text[i] === ')') {
        i++;
        return { t: 'list', v: items };
      }
      for (;;) {
        items.push(value());
        ws();
        if (i >= n) throw new Eof();
        if (text[i] === ',') i++;
        else if (text[i] === ')') {
          i++;
          return { t: 'list', v: items };
        } else throw new Error(`STEP: unexpected "${text[i]}" at ${i}`);
      }
    }
    let j = i;
    while (j < n && /[A-Za-z0-9_+\-.]/.test(text[j]!)) j++;
    if (j === i) throw new Error(`STEP: unexpected "${c}" at ${i}`);
    const word = text.slice(i, j);
    i = j;
    ws();
    if (text[i] === '(') {
      i++;
      const args: StepValue[] = [];
      ws();
      if (text[i] === ')') i++;
      else
        for (;;) {
          args.push(value());
          ws();
          if (i >= n) throw new Eof();
          if (text[i] === ',') i++;
          else if (text[i] === ')') {
            i++;
            break;
          } else throw new Error(`STEP: unexpected "${text[i]}" at ${i}`);
        }
      return { t: 'typed', name: word.toUpperCase(), args };
    }
    return { t: 'num', v: word };
  };
  const out: StepValue[] = [];
  try {
    ws();
    if (i >= n) return out;
    for (;;) {
      out.push(value());
      ws();
      if (i >= n) return out;
      if (text[i] === ',') i++;
      else throw new Error(`STEP: unexpected "${text[i]}" at ${i}`);
    }
  } catch (e) {
    if (partial && e instanceof Eof) return out;
    throw e;
  }
}

export function formatValue(v: StepValue): string {
  switch (v.t) {
    case 'null':
      return '$';
    case 'derived':
      return '*';
    case 'ref':
      return `#${v.id}`;
    case 'str':
      return stepString(v.v);
    case 'num':
      return v.v;
    case 'enum':
      return `.${v.v}.`;
    case 'bin':
      return `"${v.v}"`;
    case 'list':
      return `(${v.v.map(formatValue).join(',')})`;
    case 'typed':
      return `${v.name}(${v.args.map(formatValue).join(',')})`;
  }
}

export const formatArgs = (vs: readonly StepValue[]): string => vs.map(formatValue).join(',');

export interface ParsedStatement {
  /** Express id, or undefined for a header statement such as FILE_SCHEMA(...). */
  id?: number;
  /** Upper-case type name. */
  type: string;
  args: StepValue[];
}

/** Parse one statement ("#12=IFCWALL('x',$);" or "FILE_SCHEMA(('IFC4'));"). Null when it has no type and parentheses. */
export function parseStatement(text: string, partial = false): ParsedStatement | null {
  const m = /^\s*(?:#(\d+)\s*=\s*)?([A-Za-z0-9_]+)\s*\(/.exec(text);
  if (!m) return null;
  let body = text.slice(m[0].length);
  if (!partial) {
    const semi = body.lastIndexOf(';');
    if (semi >= 0) body = body.slice(0, semi);
    const close = body.lastIndexOf(')');
    if (close >= 0) body = body.slice(0, close);
  }
  return { ...(m[1] ? { id: Number(m[1]) } : {}), type: m[2]!.toUpperCase(), args: parseArgs(body, partial) };
}

// ---------------------------------------------------------------- line builders

/** A STEP real: always with a decimal point or exponent. */
export function stepReal(x: number): string {
  if (!Number.isFinite(x)) return '0.';
  const s = String(x);
  if (/e/i.test(s)) return s.includes('.') ? s.toUpperCase() : s.replace(/e/i, '.E').toUpperCase();
  return s.includes('.') ? s : `${s}.`;
}

/** `#id=TYPE(a,b,…);` from already formatted argument texts. */
export const entityLine = (id: number, type: string, args: readonly string[]): string => `#${id}=${type}(${args.join(',')});`;

export const REF = (id: number): string => `#${id}`;
export const LIST = (items: readonly string[]): string => `(${items.join(',')})`;
export const NULLTXT = '$';
