// Tokenizer of the animation script language (src/anim/script). Pure: no DOM, no storage, no network.
//
// The language is line based: one statement per line. A comment starts with `--` or `#` and runs to the end of the line.
// Strings are in double quotes (curly quotes from a pasted text work too); a quote doubled inside a string stands for itself.
// A number may carry the unit `s` right after it (`2s`). Words are letters, digits and underscores, joined by dots
// (`xray.alphaMax`, `Pset_WallCommon.IsExternal`).

import { ScriptError } from './diagnostics';

export type TokType = 'word' | 'string' | 'number' | 'punct';

export interface Tok {
  type: TokType;
  /** The text as written (a string without its quotes). */
  text: string;
  /** Number tokens: the value. */
  num?: number;
  /** Number tokens: the unit written right after the number (`s`), if any. */
  unit?: string;
  line: number;
  /** 1-based column of the first character. */
  col: number;
  /** Column after the last character. */
  end: number;
}

export interface SourceLine {
  /** 1-based line number. */
  line: number;
  tokens: Tok[];
  /** The line text, for messages. */
  text: string;
}

export interface LexResult {
  lines: SourceLine[];
  errors: ScriptError[];
}

/** Hard caps: a script is a short text. */
export const MAX_SOURCE_CHARS = 200_000;
export const MAX_SOURCE_LINES = 5000;

const isWordStart = (c: string): boolean => /[A-Za-z_À-￿]/.test(c);
const isWordPart = (c: string): boolean => /[A-Za-z0-9_À-￿]/.test(c);
const isDigit = (c: string): boolean => c >= '0' && c <= '9';
const OPEN_QUOTES = new Set(['"', '“', '”', '„']);
const CLOSE_QUOTES = new Set(['"', '”', '“']);
const NBSP = /[   ]/;

/** Split a text into lines of tokens. Lines with a lexical error are left out; the errors are collected. */
export function lexScript(source: string): LexResult {
  const errors: ScriptError[] = [];
  const out: SourceLine[] = [];
  if (source.length > MAX_SOURCE_CHARS) {
    errors.push(new ScriptError(`The script is too long (more than ${MAX_SOURCE_CHARS} characters).`, 1, 1, 2, 'Split it into several scripts.'));
    return { lines: out, errors };
  }
  const rawLines = source.split(/\r\n|\r|\n/);
  if (rawLines.length > MAX_SOURCE_LINES) {
    errors.push(new ScriptError(`The script has more than ${MAX_SOURCE_LINES} lines.`, MAX_SOURCE_LINES, 1, 2, 'Use `repeat` instead of writing the same lines again and again.'));
    return { lines: out, errors };
  }
  rawLines.forEach((text, idx) => {
    const lineNo = idx + 1;
    const r = lexLine(text, lineNo);
    if (r instanceof ScriptError) errors.push(r);
    else if (r.length > 0) out.push({ line: lineNo, tokens: r, text });
  });
  return { lines: out, errors };
}

/** Tokens of one line, or the first lexical error of it. */
export function lexLine(text: string, line: number): Tok[] | ScriptError {
  const toks: Tok[] = [];
  const n = text.length;
  let i = 0;
  while (i < n) {
    const c = text[i]!;
    if (c === ' ' || c === '\t' || NBSP.test(c)) {
      i++;
      continue;
    }
    if (c === '#' || (c === '-' && text[i + 1] === '-')) break; // a comment
    const start = i;
    if (OPEN_QUOTES.has(c)) {
      let s = '';
      i++;
      for (;;) {
        if (i >= n) return new ScriptError('This text has no closing quote.', line, start + 1, n + 1, 'End it with a double quote ".');
        const d = text[i]!;
        if (CLOSE_QUOTES.has(d)) {
          if (d === '"' && text[i + 1] === '"') {
            s += '"';
            i += 2;
            continue;
          }
          i++;
          break;
        }
        s += d;
        i++;
      }
      toks.push({ type: 'string', text: s, line, col: start + 1, end: i + 1 });
      continue;
    }
    if (isDigit(c) || (c === '.' && isDigit(text[i + 1] ?? ''))) {
      const m = /^(?:\d+\.?\d*|\.\d+)/.exec(text.slice(i))!;
      i += m[0].length;
      const tok: Tok = { type: 'number', text: m[0], num: Number(m[0]), line, col: start + 1, end: i + 1 };
      // A unit glued to the number: `2s`. Other letters are a typo.
      if (i < n && isWordPart(text[i]!)) {
        const wm = /^[A-Za-z_]+[A-Za-z0-9_]*/.exec(text.slice(i));
        const word = wm ? wm[0] : text[i]!;
        if (word.toLowerCase() === 's' || word.toLowerCase() === 'sec') {
          tok.unit = 's';
          i += word.length;
          tok.end = i + 1;
        } else {
          return new ScriptError(`Unexpected \`${word}\` right after the number ${m[0]}.`, line, i + 1, i + 1 + word.length, 'Write a space after the number, or use `s` for seconds (`2s`).');
        }
      }
      toks.push(tok);
      continue;
    }
    if (isWordStart(c)) {
      i++;
      while (i < n && isWordPart(text[i]!)) i++;
      while (text[i] === '.' && i + 1 < n && isWordPart(text[i + 1]!)) {
        i++;
        while (i < n && isWordPart(text[i]!)) i++;
      }
      toks.push({ type: 'word', text: text.slice(start, i), line, col: start + 1, end: i + 1 });
      continue;
    }
    const two = text.slice(i, i + 2);
    if (two === '!=' || two === '<>' || two === '<=' || two === '>=' || two === '==') {
      toks.push({ type: 'punct', text: two, line, col: start + 1, end: i + 3 });
      i += 2;
      continue;
    }
    if ('=<>(),+-*/&'.includes(c)) {
      toks.push({ type: 'punct', text: c, line, col: start + 1, end: i + 2 });
      i++;
      continue;
    }
    if (c === "'") return new ScriptError("Use double quotes \" for text, not single quotes '.", line, start + 1, start + 2);
    return new ScriptError(`Unexpected character \`${c}\`.`, line, start + 1, start + 2, 'A script line holds words, numbers, "quoted text" and a few signs: + - * / ( ) , = < >.');
  }
  return toks;
}

/** Lower-case word of a token, or ''. */
export const lowerWord = (t: Tok | undefined): string => (t && t.type === 'word' ? t.text.toLowerCase() : '');
