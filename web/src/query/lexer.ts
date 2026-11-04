// Tokenizer for the criteria query language (a subset of the SQL WHERE clause). Pure module, no DOM.

/** A parse or tokenize error. `pos` is the 0-based character offset in the query text. */
export class QueryError extends Error {
  constructor(
    message: string,
    readonly pos: number,
  ) {
    super(`${message} (at character ${pos + 1})`);
    this.name = 'QueryError';
  }
  /** The message without the position suffix. */
  get bare(): string {
    return this.message.replace(/ \(at character \d+\)$/, '');
  }
}

export type TokenType =
  | 'ident' // bare identifier, may contain dots: Pset_WallCommon.IsExternal
  | 'qident' // "double quoted identifier"
  | 'string' // 'single quoted string'
  | 'number'
  | 'keyword' // AND OR NOT LIKE IN BETWEEN IS NULL TRUE FALSE (upper-cased in `value`)
  | 'op' // = != <> < <= > >=
  | 'punct' // ( ) , -
  | 'eof';

export interface Token {
  type: TokenType;
  value: string;
  /** Numeric value of a number token. */
  num?: number;
  pos: number;
  end: number;
}

export const KEYWORDS = new Set(['AND', 'OR', 'NOT', 'LIKE', 'IN', 'BETWEEN', 'IS', 'NULL', 'TRUE', 'FALSE']);

const isIdentStart = (c: string): boolean => /[A-Za-z_À-￿]/.test(c);
const isIdentPart = (c: string): boolean => /[A-Za-z0-9_À-￿]/.test(c);
const isDigit = (c: string): boolean => c >= '0' && c <= '9';

/** Split a query into tokens. Throws QueryError for an unterminated string or an unknown character. */
export function tokenize(src: string): Token[] {
  const out: Token[] = [];
  let i = 0;
  const n = src.length;
  while (i < n) {
    const c = src[i]!;
    if (c === ' ' || c === '\t' || c === '\n' || c === '\r') {
      i++;
      continue;
    }
    const start = i;
    // Quoted string or identifier; the quote doubled inside stands for itself ('it''s', "a""b").
    if (c === "'" || c === '"') {
      let s = '';
      i++;
      for (;;) {
        if (i >= n) throw new QueryError(c === "'" ? 'Unterminated string: a closing \' is missing' : 'Unterminated name: a closing " is missing', start);
        const d = src[i]!;
        if (d === c) {
          if (src[i + 1] === c) {
            s += c;
            i += 2;
            continue;
          }
          i++;
          break;
        }
        s += d;
        i++;
      }
      if (c === '"' && s.length === 0) throw new QueryError('Empty column name ""', start);
      out.push({ type: c === "'" ? 'string' : 'qident', value: s, pos: start, end: i });
      continue;
    }
    if (isDigit(c) || (c === '.' && isDigit(src[i + 1] ?? ''))) {
      const m = /^(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?/.exec(src.slice(i))!;
      i += m[0].length;
      if (i < n && isIdentPart(src[i]!)) throw new QueryError(`Unexpected "${src[i]}" after the number ${m[0]}`, i);
      out.push({ type: 'number', value: m[0], num: Number(m[0]), pos: start, end: i });
      continue;
    }
    if (isIdentStart(c)) {
      // Segments joined by dots: Pset_WallCommon.IsExternal, Qto_WallBaseQuantities.NetVolume.
      while (i < n && isIdentPart(src[i]!)) i++;
      while (src[i] === '.' && i + 1 < n && isIdentPart(src[i + 1]!)) {
        i++;
        while (i < n && isIdentPart(src[i]!)) i++;
      }
      const word = src.slice(start, i);
      const up = word.toUpperCase();
      if (KEYWORDS.has(up)) out.push({ type: 'keyword', value: up, pos: start, end: i });
      else out.push({ type: 'ident', value: word, pos: start, end: i });
      continue;
    }
    const two = src.slice(i, i + 2);
    if (two === '!=' || two === '<>' || two === '<=' || two === '>=' || two === '==') {
      out.push({ type: 'op', value: two === '==' ? '=' : two === '<>' ? '!=' : two, pos: start, end: i + 2 });
      i += 2;
      continue;
    }
    if (c === '=' || c === '<' || c === '>') {
      out.push({ type: 'op', value: c, pos: start, end: i + 1 });
      i++;
      continue;
    }
    if (c === '(' || c === ')' || c === ',' || c === '-') {
      out.push({ type: 'punct', value: c, pos: start, end: i + 1 });
      i++;
      continue;
    }
    throw new QueryError(`Unexpected character "${c}"`, i);
  }
  out.push({ type: 'eof', value: '', pos: n, end: n });
  return out;
}
