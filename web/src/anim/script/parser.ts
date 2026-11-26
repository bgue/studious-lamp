// Parser of the animation script language (src/anim/script). Pure: no DOM, no storage, no network, no eval.
//
// Grammar (case-insensitive keywords; one statement per line; `--` and `#` start a comment):
//
//   fly to <elements> [over N [seconds]] [ease E] [margin N]       options in any order
//   fly to view "name" [over N [seconds]] [ease E]
//   orbit N [degrees] [about <elements>] [over N [seconds]] [ease E]
//   set <path> to <value> [over N [seconds]] [ease E]               value: number, numbers with commas, on/off, "text" or a word
//   mode ghost|solid|radiograph|glow|cutaway
//   apply preset "id or name"
//   show|hide|isolate <elements> [fading [over] N [seconds]]
//   select <elements>   |   select nothing
//   caption "Title" ["More text"] [for N [seconds]]
//   label <elements> with <field>, <field>, ... [for N [seconds]]   field: name, class, storey or "Pset_X.Prop"
//   hover <elements> [for N [seconds]]
//   wait N [seconds]
//   together ... end together
//   repeat N times ... end repeat
//   repeat for each element in <elements> ... end repeat            `it` is the element
//   repeat for each set in sets ... end repeat                      `it` is the set name
//   put <expression> into <name>                                     a number, text (`"a" & b`) or a yes/no
//   if <condition> then ... [else if <condition> then ...] [else ...] end if      or one line: if <condition> then <statement>
//   repeat while <condition> ... end repeat   |   repeat until <condition> ... end repeat
//   repeat with i from A to|down to B [by S] ... end repeat
//   on <name> [param, param] ... end <name>                          a handler; called as a statement: name arg, arg
//   function <name> [param, param] ... return <expression> ... end <name>      called in an expression: name(arg, arg)
//   return [<expression>]                                            inside a function (with a value) or a handler (to stop early)
//   show|hide issues|drawings     |   fade new elements over N [seconds]|instantly
//   <condition> := comparisons (= <> != < > <= >=) of numbers and text, joined by and, or, not, with parentheses;
//                  the count of <elements>, there are|is [no] <elements>
//   schedule "plan" [view planned|actual|variance] [from "date"] [to "date"] [over N [seconds]] [fade N [seconds]]     4D: plays a plan
//   at date "YYYY-MM-DD[THH:MM]"   |   at milestone "name"                    4D: the next statements start at that moment of the schedule
//   tint <elements> <#rrggbb|colour name|off> [fading over N [seconds]]
//   explode storeys|radial [by N] [over N [seconds]]   |   collapse [over N [seconds]]
//   focus <elements>   |   focus nothing
//   section box around <elements> [over N [seconds]]   |   section box around storey "Name" [over N]   |   section box off [over N]
//
//   <elements> := where <criteria> | class A[, B] | set "Name" | the selection | everything | it | elements "gid", "gid"
//                 | active | completed | critical            (the 4D states of the running schedule)
//   <criteria> := the criteria query language of src/query; text values may be bare words or double quoted
//
// parseScript never throws: it returns the tree of the lines that are fine and the errors of the others.

import { QueryError } from '../../query/lexer';
import { parseQuery } from '../../query/parser';
import { ScriptError, didYouMean } from './diagnostics';
import type { ScriptDiagnostic } from './diagnostics';
import { lexScript, lowerWord } from './lexer';
import type { SourceLine, Tok } from './lexer';
import type { Ease, Elements, Num, Program, QuerySub, Span, Stmt, Str, StrPart, Text, Value } from './ast';

export * from './ast';

/** The statement words, in the order of the reference. */
export const STATEMENT_WORDS = ['fly', 'orbit', 'set', 'mode', 'apply', 'show', 'hide', 'isolate', 'select', 'caption', 'label', 'hover', 'wait', 'together', 'repeat', 'put', 'schedule', 'at', 'tint', 'explode', 'collapse', 'focus', 'section', 'if', 'else', 'on', 'function', 'return', 'fade', 'end'] as const;
/** The colour words of `tint` and their colours (#rrggbb). */
export const COLOUR_NAMES: Readonly<Record<string, string>> = {
  red: '#e53935', orange: '#fb8c00', yellow: '#fdd835', green: '#43a047', teal: '#00897b', cyan: '#00acc1', blue: '#1e88e5', indigo: '#3949ab',
  purple: '#8e24aa', magenta: '#d81b60', pink: '#f48fb1', brown: '#6d4c41', grey: '#9e9e9e', gray: '#9e9e9e', white: '#ffffff', black: '#212121',
};
const TINT_OFF = ['off', 'none', 'clear'];
export const MODE_WORDS = ['ghost', 'solid', 'radiograph', 'glow', 'cutaway'] as const;
export const MAX_NESTING = 8;

/** Words that end a `where` clause (the start of an option) and cannot be a bare column or value there. */
const STOP_WORDS = new Set(['over', 'ease', 'margin', 'fading', 'for', 'with', 'about', 'by', 'then', 'into']);
/** Statements that may stand in a function: it computes, it does not act on the timeline. */
const FUNCTION_KINDS = new Set(['put', 'if', 'while', 'repeat', 'repeatWith', 'return']);
/** Words that cannot follow `then` on the same line: they open or close a block. */
const BLOCK_WORDS = new Set(['together', 'repeat', 'if', 'on', 'function', 'else', 'end']);
const CMP_OPS = new Map<string, '=' | '<>' | '<' | '>' | '<=' | '>='>([['=', '='], ['==', '='], ['<>', '<>'], ['!=', '<>'], ['≠', '<>'], ['<', '<'], ['>', '>'], ['<=', '<='], ['≤', '<='], ['>=', '>='], ['≥', '>=']]);
const SCHEDULE_VIEWS = ['planned', 'actual', 'variance'] as const;
const SECOND_UNITS = new Set(['s', 'sec', 'secs', 'second', 'seconds']);
const DEGREE_UNITS = new Set(['degree', 'degrees', 'deg']);
const QUERY_KEYWORDS = new Set(['AND', 'OR', 'NOT', 'LIKE', 'IN', 'BETWEEN', 'IS', 'NULL', 'TRUE', 'FALSE']);
const BOOL_WORDS = new Map<string, boolean>([['true', true], ['on', true], ['yes', true], ['false', false], ['off', false], ['no', false]]);

const span = (a: Span, b: Span = a): Span => ({ line: a.line, col: a.col, end: b.end });
const tspan = (t: Tok): Span => ({ line: t.line, col: t.col, end: t.end });

/** Reads the tokens of one line. */
class Cursor {
  i = 0;
  /** Reading a full expression (text, comparisons, `there are`) rather than only a number. */
  rich = false;
  constructor(
    readonly toks: Tok[],
    readonly lineNo: number,
  ) {}
  get atEnd(): boolean {
    return this.i >= this.toks.length;
  }
  peek(k = 0): Tok | undefined {
    return this.toks[this.i + k];
  }
  next(): Tok {
    const t = this.toks[this.i++];
    if (!t) throw this.failEnd('The line ends too soon.');
    return t;
  }
  word(k = 0): string {
    return lowerWord(this.peek(k));
  }
  eatWord(...names: string[]): Tok | null {
    const t = this.peek();
    if (t && t.type === 'word' && names.includes(t.text.toLowerCase())) {
      this.i++;
      return t;
    }
    return null;
  }
  eatPunct(p: string): Tok | null {
    const t = this.peek();
    if (t && t.type === 'punct' && t.text === p) {
      this.i++;
      return t;
    }
    return null;
  }
  last(): Tok {
    return this.toks[Math.min(this.i, this.toks.length) - 1] ?? this.toks[0]!;
  }
  /** An error that points just after the last token read. */
  failEnd(message: string, hint?: string): ScriptError {
    const l = this.toks[this.toks.length - 1]!;
    return new ScriptError(message, this.lineNo, l.end, l.end + 1, hint);
  }
  /** An error that points at the next token (or the end of the line). */
  fail(message: string, hint?: string, tok: Tok | undefined = this.peek()): ScriptError {
    if (!tok) return this.failEnd(message, hint);
    return new ScriptError(message, tok.line, tok.col, tok.end, hint);
  }
}

const describe = (t: Tok | undefined): string => {
  if (!t) return 'the end of the line';
  if (t.type === 'string') return `the text "${t.text}"`;
  return `\`${t.text}\``;
};

// ---------------------------------------------------------------- numbers

function parseExpr(c: Cursor): Num {
  let left = parseTerm(c);
  for (;;) {
    const t = c.peek();
    if (t && t.type === 'punct' && (t.text === '+' || t.text === '-')) {
      c.i++;
      const right = parseTerm(c);
      left = { k: 'bin', op: t.text, a: left, b: right, ...span(left, right) };
    } else return left;
  }
}

function parseTerm(c: Cursor): Num {
  let left = parseUnary(c);
  for (;;) {
    const t = c.peek();
    if (t && t.type === 'punct' && (t.text === '*' || t.text === '/')) {
      c.i++;
      const right = parseUnary(c);
      left = { k: 'bin', op: t.text, a: left, b: right, ...span(left, right) };
    } else return left;
  }
}

function parseUnary(c: Cursor): Num {
  const t = c.peek();
  if (t && t.type === 'punct' && t.text === '-') {
    c.i++;
    const a = parseUnary(c);
    return { k: 'neg', a, line: t.line, col: t.col, end: a.end };
  }
  if (t && t.type === 'punct' && t.text === '+') {
    c.i++;
    return parseUnary(c);
  }
  return parsePrimary(c);
}

function parsePrimary(c: Cursor): Num {
  const t = c.peek();
  if (!t) throw c.failEnd('Expected a number here.', 'Write a number such as 2, or a name you set with `put`.');
  if (t.type === 'number') {
    c.i++;
    return { k: 'num', v: t.num!, ...tspan(t) };
  }
  if (t.type === 'string' && c.rich) {
    c.i++;
    return { k: 'str', v: t.text, ...tspan(t) };
  }
  if (t.type === 'word') {
    const w = t.text.toLowerCase();
    const n = c.peek(1);
    if (n && n.type === 'punct' && n.text === '(' && n.col === t.end && !['not', 'and', 'or'].includes(w)) return parseCall(c);
    if (w === 'the' && c.word(1) === 'count') {
      c.i += 2;
      if (!c.eatWord('of')) throw c.fail(`Expected \`of\` after \`the count\`, found ${describe(c.peek())}.`, 'For example: the count of class IfcDoor.');
      const target = parseElementsArg(c);
      return { k: 'count', target, ...span(tspan(t), target) };
    }
    if (c.rich) {
      if (BOOL_WORDS.has(w)) {
        c.i++;
        return { k: 'bool', v: BOOL_WORDS.get(w)!, ...tspan(t) };
      }
      if (w === 'there') {
        c.i++;
        if (!c.eatWord('is', 'are')) throw c.fail(`Expected \`is\` or \`are\` after \`there\`, found ${describe(c.peek())}.`, 'For example: there are class IfcDoor.');
        const none = !!c.eatWord('no');
        const target = parseElementsArg(c);
        return { k: 'there', target, none, ...span(tspan(t), target) };
      }
    }
    c.i++;
    return { k: 'var', name: t.text, ...tspan(t) };
  }
  if (t.type === 'punct' && t.text === '(') {
    c.i++;
    const e = c.rich ? parseOr(c) : parseExpr(c);
    const close = c.eatPunct(')');
    if (!close) throw c.fail(`Expected \`)\` to close the \`(\` at column ${t.col}, found ${describe(c.peek())}.`);
    return { ...e, line: t.line, col: t.col, end: close.end };
  }
  throw c.fail(`Expected a number, found ${describe(t)}.`, t.type === 'string' ? 'Numbers are written without quotes.' : undefined);
}

/** `name(arg, arg)`: the name and the `(` touch. */
function parseCall(c: Cursor): Num {
  const t = c.next();
  c.i++; // (
  const args: Num[] = [];
  if (!c.eatPunct(')')) {
    for (;;) {
      args.push(parseFull(c));
      if (c.eatPunct(',')) continue;
      break;
    }
    const close = c.eatPunct(')');
    if (!close) throw c.fail(`Expected \`,\` or \`)\` in the call of \`${t.text}\`, found ${describe(c.peek())}.`, `Close the call with \`)\`, like ${t.text}(1, 2).`);
    return { k: 'call', name: t.text, args, ...span(tspan(t), tspan(close)) };
  }
  return { k: 'call', name: t.text, args, ...span(tspan(t), tspan(c.last())) };
}

/** Elements after `the count of` / `there are`: as everywhere, or in parentheses (needed when more follows a `where`). */
function parseElementsArg(c: Cursor): Elements {
  const t = c.peek();
  if (t && t.type === 'punct' && t.text === '(') {
    let depth = 0;
    let j = c.i;
    for (; j < c.toks.length; j++) {
      const x = c.toks[j]!;
      if (x.type === 'punct' && x.text === '(') depth++;
      else if (x.type === 'punct' && x.text === ')' && --depth === 0) break;
    }
    if (j >= c.toks.length) throw c.fail(`Expected \`)\` to close the \`(\` at column ${t.col}.`, undefined, t);
    const inner = c.toks.slice(c.i + 1, j);
    if (inner.length === 0) throw c.fail('Expected which elements inside the parentheses.', ELEMENT_HELP, t);
    const ic = new Cursor(inner, c.lineNo);
    const e = parseElements(ic);
    if (!ic.atEnd) throw ic.fail(`I did not expect ${describe(ic.peek())} after the elements.`, 'Elements are `where <criteria>`, `class IfcDoor`, `set "Name"`, ... A criteria joins its tests with `and` inside the `where`: where class = IfcDoor and storey = "Level 1".');
    c.i = j + 1;
    return e;
  }
  return parseElements(c);
}

// ---- full expressions: or < and < not < comparison < & < arithmetic

/** A full expression: numbers, text, `&`, comparisons, `and` `or` `not`, `there are`, calls. */
export function parseFull(c: Cursor): Num {
  const was = c.rich;
  c.rich = true;
  try {
    return parseOr(c);
  } finally {
    c.rich = was;
  }
}

function parseOr(c: Cursor): Num {
  let left = parseAnd(c);
  for (;;) {
    if (!c.eatWord('or')) return left;
    const right = parseAnd(c);
    left = { k: 'or', a: left, b: right, ...span(left, right) };
  }
}

function parseAnd(c: Cursor): Num {
  let left = parseNot(c);
  for (;;) {
    if (!c.eatWord('and')) return left;
    const right = parseNot(c);
    left = { k: 'and', a: left, b: right, ...span(left, right) };
  }
}

function parseNot(c: Cursor): Num {
  const t = c.peek();
  if (t && t.type === 'word' && t.text.toLowerCase() === 'not') {
    c.i++;
    const a = parseNot(c);
    return { k: 'not', a, line: t.line, col: t.col, end: a.end };
  }
  return parseCmp(c);
}

function parseCmp(c: Cursor): Num {
  const left = parseCat(c);
  const t = c.peek();
  const op = t && (t.type === 'punct' || t.type === 'word') ? CMP_OPS.get(t.text) : undefined;
  if (!t || !op) return left;
  c.i++;
  const right = parseCat(c);
  const n = c.peek();
  if (n && (n.type === 'punct' || n.type === 'word') && CMP_OPS.has(n.text)) throw c.fail('Two comparisons in a row.', 'Join them with `and`: x > 1 and x < 5.');
  return { k: 'cmp', op, a: left, b: right, ...span(left, right) };
}

function parseCat(c: Cursor): Num {
  let left = parseExpr(c);
  while (c.eatPunct('&')) {
    const right = parseExpr(c);
    left = { k: 'cat', a: left, b: right, ...span(left, right) };
  }
  return left;
}

/** A number with an optional unit word after it. */
function parseQuantity(c: Cursor, units: Set<string>): Num {
  const n = parseExpr(c);
  const w = c.word();
  if (units.has(w)) c.i++;
  return n;
}

// ---------------------------------------------------------------- strings

function parseStr(c: Cursor, what: string): Str {
  const first = c.peek();
  if (!first) throw c.failEnd(`Expected ${what}.`, 'Write it in double quotes, like "Level 2".');
  const parts: StrPart[] = [];
  let endTok = first;
  for (;;) {
    const t = c.peek();
    if (!t) throw c.failEnd(`Expected ${what} after \`&\`.`);
    if (t.type === 'string') {
      c.i++;
      parts.push({ k: 'text', v: t.text });
    } else if (t.type === 'word' && ((c.peek(1)?.text === '(' && c.peek(1)!.col === t.end) || (t.text.toLowerCase() === 'the' && c.word(1) === 'count'))) {
      parts.push({ k: 'num', n: parseExpr(c) });
    } else if (t.type === 'word') {
      c.i++;
      parts.push({ k: 'name', name: t.text, span: tspan(t) });
    } else if (t.type === 'number' || (t.type === 'punct' && (t.text === '(' || t.text === '-'))) {
      parts.push({ k: 'num', n: parseExpr(c) });
    } else {
      throw c.fail(`Expected ${what}, found ${describe(t)}.`, 'Write it in double quotes, like "Level 2".');
    }
    endTok = c.last();
    if (!c.eatPunct('&')) break;
  }
  return { parts, ...span(tspan(first), tspan(endTok)) };
}

// ---------------------------------------------------------------- options

type OptionKey = 'over' | 'ease' | 'margin' | 'fading' | 'for' | 'by';
interface Options {
  by?: Num;
  over?: Num;
  ease?: Ease;
  margin?: Num;
  fading?: Num;
  for?: Num;
}

const OPTION_USAGE: Record<OptionKey, string> = {
  over: 'over N seconds',
  ease: 'ease in, ease out, ease in out or ease linear',
  margin: 'margin N',
  fading: 'fading over N seconds',
  for: 'for N seconds',
  by: 'by N',
};

function parseEase(c: Cursor): Ease {
  const t = c.peek();
  const w = lowerWord(t);
  if (w === 'linear') {
    c.i++;
    return 'linear';
  }
  if (w === 'inout' || w === 'inoutsine') {
    c.i++;
    return 'inOut';
  }
  if (w === 'in') {
    c.i++;
    if (c.eatWord('out')) return 'inOut';
    return 'in';
  }
  if (w === 'out') {
    c.i++;
    return 'out';
  }
  throw c.fail(`Expected \`in\`, \`out\`, \`in out\` or \`linear\` after \`ease\`, found ${describe(t)}.`, t ? didYouMean(t.text, ['in', 'out', 'linear']) : undefined);
}

function parseOptions(c: Cursor, allowed: OptionKey[]): Options {
  const o: Options = {};
  while (!c.atEnd) {
    const t = c.peek()!;
    const w = lowerWord(t) as OptionKey;
    if (t.type !== 'word' || !allowed.includes(w)) {
      const usage = allowed.map((k) => `\`${OPTION_USAGE[k]}\``).join(', ');
      const dym = t.type === 'word' ? didYouMean(t.text, allowed) : '';
      throw c.fail(`I did not expect ${describe(t)} here.`, `${dym ? `${dym} ` : ''}This statement can end with ${usage}.`);
    }
    if (o[w] !== undefined) throw c.fail(`\`${w}\` is given twice in this statement.`);
    c.i++;
    if (w === 'ease') o.ease = parseEase(c);
    else if (w === 'margin') o.margin = parseExpr(c);
    else if (w === 'by') o.by = parseExpr(c);
    else if (w === 'fading') {
      c.eatWord('over');
      o.fading = parseQuantity(c, SECOND_UNITS);
    } else o[w] = parseQuantity(c, SECOND_UNITS);
  }
  return o;
}

// ---------------------------------------------------------------- elements

/** The query text of a `where` clause, built from script tokens, and where each token starts in it. */
export function buildQuery(toks: readonly Tok[]): { text: string; starts: number[]; subs: QuerySub[] } {
  let text = '';
  const starts: number[] = [];
  const subs: QuerySub[] = [];
  let valuePos = false;
  let betweenPending = false;
  let prevIn = false;
  const parens: boolean[] = [];
  let prev = '';
  for (const t of toks) {
    let piece = t.text;
    let pendingSub = '';
    const wasIn = prevIn;
    prevIn = false;
    if (t.type === 'word') {
      const up = t.text.toUpperCase();
      if (QUERY_KEYWORDS.has(up)) {
        piece = up;
        if (up === 'LIKE') valuePos = true;
        else if (up === 'BETWEEN') {
          valuePos = true;
          betweenPending = true;
        } else if (up === 'AND' && betweenPending) {
          valuePos = true;
          betweenPending = false;
        } else if (up === 'IN') {
          prevIn = true;
          valuePos = false;
        } else if (up === 'TRUE' || up === 'FALSE' || up === 'NULL') valuePos = false;
        else valuePos = false;
      } else {
        piece = valuePos ? `'${t.text.replace(/'/g, "''")}'` : t.text;
        if (valuePos) pendingSub = t.text;
        valuePos = false;
      }
    } else if (t.type === 'string') {
      piece = valuePos ? `'${t.text.replace(/'/g, "''")}'` : `"${t.text.replace(/"/g, '""')}"`;
      valuePos = false;
    } else if (t.type === 'number') {
      valuePos = false;
    } else if (t.text === '(') {
      parens.push(wasIn);
      valuePos = wasIn;
    } else if (t.text === ')') {
      parens.pop();
      valuePos = false;
    } else if (t.text === ',') {
      valuePos = parens[parens.length - 1] === true;
    } else if (t.text === '-') {
      /* a minus before a number keeps the value position */
    } else {
      valuePos = ['=', '==', '!=', '<>', '<', '<=', '>', '>='].includes(t.text);
    }
    const glue = text.length === 0 || prev === '(' || piece === ')' || piece === ',' || (prev === '-' && t.type === 'number');
    starts.push(text.length + (glue ? 0 : 1));
    if (pendingSub) subs.push({ at: text.length + (glue ? 0 : 1), len: piece.length, name: pendingSub });
    text += (glue ? '' : ' ') + piece;
    prev = piece;
  }
  return { text, starts, subs };
}

const isColourTok = (t: Tok | undefined): boolean => !!t && (t.type === 'colour' || (t.type === 'word' && (t.text.toLowerCase() in COLOUR_NAMES || TINT_OFF.includes(t.text.toLowerCase()))));

function parseWhere(c: Cursor, kw: Tok, endColour = false): Elements {
  const toks: Tok[] = [];
  let depth = 0;
  while (!c.atEnd) {
    const t = c.peek()!;
    if (endColour && depth <= 0 && toks.length > 0 && isColourTok(t)) {
      // `tint where class = IfcWall red`: the colour is the last word (or comes before `fading`), unless a value is due
      const prev = toks[toks.length - 1]!;
      const n = c.peek(1);
      const valueDue = (prev.type === 'punct' && ['=', '==', '!=', '<>', '<', '<=', '>', '>=', '(', ','].includes(prev.text)) || (prev.type === 'word' && ['like', 'between', 'and', 'or', 'not', 'in', 'is'].includes(prev.text.toLowerCase()));
      if (!valueDue && (!n || lowerWord(n) === 'fading')) break;
    }
    if (t.type === 'punct' && t.text === '(') depth++;
    else if (t.type === 'punct' && t.text === ')') depth--;
    else if (depth <= 0 && t.type === 'word' && STOP_WORDS.has(t.text.toLowerCase())) break;
    else if (t.type === 'punct' && (t.text === '+' || t.text === '*' || t.text === '/' || t.text === '&')) {
      throw c.fail(`\`${t.text}\` cannot be used in a criteria query.`);
    }
    toks.push(t);
    c.i++;
  }
  if (toks.length === 0) {
    throw c.fail('Expected a condition after `where`.', 'For example: where class = IfcPump and storey = "Level 2".', kw);
  }
  const { text, starts, subs } = buildQuery(toks);
  try {
    parseQuery(text);
  } catch (e) {
    if (e instanceof QueryError) {
      let k = 0;
      for (let j = 0; j < starts.length; j++) if (starts[j]! <= e.pos) k = j;
      const bad = toks[k]!;
      const hint = /expected AND, OR/i.test(e.bare) ? 'Put text values with spaces in double quotes, like storey = "Level 2".' : undefined;
      throw new ScriptError(`In the criteria: ${e.bare}.`, bad.line, bad.col, bad.end, hint);
    }
    throw e;
  }
  return { k: 'query', query: text, ...(subs.length ? { subs } : {}), ...span(tspan(kw), tspan(toks[toks.length - 1]!)) };
}

const ELEMENT_HELP = 'Write `where <criteria>`, `class IfcPump`, `set "Name"`, `the selection`, `everything`, `it`, `elements "id", "id"`, or `active`, `completed`, `critical`.';
const ELEMENT_WORDS = ['where', 'class', 'set', 'the', 'selection', 'everything', 'it', 'elements', 'active', 'completed', 'critical'];

function parseElements(c: Cursor, endColour = false): Elements {
  const t = c.peek();
  if (!t) throw c.failEnd('Expected which elements.', ELEMENT_HELP);
  const w = lowerWord(t);
  if (t.type === 'word') {
    switch (w) {
      case 'where':
        c.i++;
        return parseWhere(c, t, endColour);
      case 'active':
      case 'completed':
      case 'critical':
        c.i++;
        return { k: 'schedule', set: w, ...tspan(t) };
      case 'class':
      case 'classes': {
        c.i++;
        const names: Tok[] = [];
        for (;;) {
          const n = c.peek();
          if (!n || (n.type !== 'word' && n.type !== 'string')) throw c.fail(`Expected a class name after \`${t.text}\`, found ${describe(n)}.`, 'For example: class IfcPump, or class IfcPump, IfcPipeSegment.');
          c.i++;
          names.push(n);
          if (!c.eatPunct(',')) break;
        }
        const q = (n: Tok): string => `'${n.text.replace(/'/g, "''")}'`;
        const query = names.length === 1 ? `class = ${q(names[0]!)}` : `class IN (${names.map(q).join(', ')})`;
        // bare class names may be variables (`show class kind`): where each quoted name sits in the query
        const subs: QuerySub[] = [];
        let from = 0;
        for (const n of names) {
          const piece = q(n);
          const at = query.indexOf(piece, from);
          from = at + piece.length;
          if (n.type === 'word') subs.push({ at, len: piece.length, name: n.text });
        }
        return { k: 'query', query, ...(subs.length ? { subs } : {}), ...span(tspan(t), tspan(names[names.length - 1]!)) };
      }
      case 'set': {
        c.i++;
        const n = c.peek();
        if (!n || n.type !== 'string') throw c.fail(`Expected the name of a selection set in double quotes after \`set\`, found ${describe(n)}.`, 'For example: set "Pumps".');
        c.i++;
        return { k: 'set', name: n.text, ...span(tspan(t), tspan(n)) };
      }
      case 'the':
        if (c.word(1) === 'selection') {
          c.i += 2;
          return { k: 'selection', ...span(tspan(t), tspan(c.last())) };
        }
        break;
      case 'selection':
        c.i++;
        return { k: 'selection', ...tspan(t) };
      case 'everything':
        c.i++;
        return { k: 'everything', ...tspan(t) };
      case 'it':
        c.i++;
        return { k: 'it', ...tspan(t) };
      case 'elements': {
        c.i++;
        const ids: string[] = [];
        let endTok = t;
        for (;;) {
          const n = c.peek();
          if (!n || n.type !== 'string') throw c.fail(`Expected a GlobalId in double quotes, found ${describe(n)}.`, 'For example: elements "2O2Fr$t4X7Zf8NOew3FLOH", "0Ib9fvY1X9u8wNBF1eRZkH".');
          c.i++;
          ids.push(n.text);
          endTok = n;
          if (!c.eatPunct(',')) break;
        }
        return { k: 'gids', ids, ...span(tspan(t), tspan(endTok)) };
      }
      default:
        break;
    }
  }
  const dym = t.type === 'word' ? didYouMean(t.text, ELEMENT_WORDS) : '';
  throw c.fail(`Expected which elements, found ${describe(t)}.`, `${dym ? `${dym} ` : ''}${ELEMENT_HELP}`);
}

// ---------------------------------------------------------------- statements

function endOfStatement(c: Cursor, hintWords: string[], usage: string): void {
  if (c.atEnd) return;
  const t = c.peek()!;
  const dym = t.type === 'word' ? didYouMean(t.text, hintWords) : '';
  throw c.fail(`I did not expect ${describe(t)} here.`, `${dym ? `${dym} ` : ''}${usage}`);
}

function parseValue(c: Cursor): Value {
  const t = c.peek();
  if (!t) throw c.failEnd('Expected a value after `to`.', 'A number, on or off, or text in double quotes.');
  if (t.type === 'string') {
    c.i++;
    return { k: 'str', v: t.text, ...tspan(t) };
  }
  if (t.type === 'word') {
    const w = t.text.toLowerCase();
    const n = c.peek(1);
    const alone = !n || (n.type === 'word' && (STOP_WORDS.has(n.text.toLowerCase()) || n.text.toLowerCase() === 'over'));
    if (BOOL_WORDS.has(w) && alone) {
      c.i++;
      return { k: 'bool', v: BOOL_WORDS.get(w)!, ...tspan(t) };
    }
    if (alone) {
      c.i++;
      return { k: 'word', text: t.text, ...tspan(t) };
    }
  }
  const items: Num[] = [parseExpr(c)];
  while (c.eatPunct(',')) items.push(parseExpr(c));
  return { k: 'list', items, ...span(items[0]!, items[items.length - 1]!) };
}

/** What closes the block being read: the word after `end`, and how messages call the block. */
interface Closer {
  /** The word `end` must be followed by. */
  word: string;
  /** What the block is called in messages: `if`, `repeat`, `on showFloor`. */
  kind: string;
  /** `if` blocks: an `else` was already read, so another one is a mistake. */
  afterElse?: boolean;
}
const blk = (kind: 'together' | 'repeat' | 'if'): Closer => ({ word: kind, kind });
const article = (kind: string): string => (/^[aeiou]/.test(kind) ? 'an' : 'a');

class Parser {
  readonly errors: ScriptError[] = [];
  private idx = 0;
  /** Set by parseBlock when an `else` line ended an `if` branch (the line is kept, the block goes on with the next branch). */
  private elseLine: SourceLine | null = null;
  /** Inside the body of a `function` or an `on` handler. */
  private defKind: 'function' | 'on' | null = null;
  /** The handlers and functions the script defines (their lines are read first, so a call may come before the definition). */
  private readonly defNames = new Set<string>();
  constructor(private readonly lines: SourceLine[]) {
    for (const sl of lines) {
      const f = lowerWord(sl.tokens[0]);
      const n = sl.tokens[1];
      if ((f === 'on' || f === 'function') && n && n.type === 'word') this.defNames.add(n.text.toLowerCase());
    }
  }

  parseProgram(): Program {
    const body = this.parseBlock(null, 0, 0);
    return { body };
  }

  /** Statements until the `end` of the block (or the end of the script). Returns at the line after `end`. */
  private parseBlock(closer: Closer | null, openLine: number, depth: number): Stmt[] {
    const body: Stmt[] = [];
    while (this.idx < this.lines.length) {
      const sl = this.lines[this.idx]!;
      const c = new Cursor(sl.tokens, sl.line);
      const first = c.word();
      if (first === 'else') {
        this.idx++;
        if (closer && closer.word === 'if' && !closer.afterElse) {
          this.elseLine = sl;
          return body;
        }
        const t = c.peek()!;
        let msg: string;
        let hint: string;
        if (!closer) {
          msg = '`else` has no `if` before it.';
          hint = '`else` goes between the branches of an `if ... end if`.';
        } else if (closer.word === 'if') {
          msg = `\`else\` comes after the \`else\` of the \`if\` on line ${openLine}; an \`if\` has one \`else\`, last.`;
          hint = 'Use `else if <condition> then` for another branch before it.';
        } else {
          msg = `\`else\` is inside ${article(closer.kind)} \`${closer.kind}\` (line ${openLine}), not directly in an \`if\`.`;
          hint = `Close the \`${closer.kind}\` with \`end ${closer.word}\` before \`else\`.`;
        }
        this.errors.push(new ScriptError(msg, t.line, t.col, t.end, hint));
        continue;
      }
      if (first === 'end') {
        this.idx++;
        const what = c.word(1);
        const endTok = c.peek(1);
        if (closer === null) {
          this.errors.push(c.fail(`\`end${what ? ` ${what}` : ''}\` has no block to close.`, 'Every `end` closes a block above it: `end together`, `end repeat`, `end if`, or `end <name>` for a handler or a function.', c.peek()));
          continue;
        }
        if (!endTok || what !== closer.word) {
          this.errors.push(
            c.fail(
              endTok ? `\`end ${endTok.text}\` does not match: the open block (line ${openLine}) is ${article(closer.kind)} \`${closer.kind}\`.` : `\`end\` needs the block name: \`end ${closer.word}\`.`,
              `Write \`end ${closer.word}\` to close the \`${closer.kind}\` of line ${openLine}.`,
              endTok ?? c.peek(),
            ),
          );
          return body;
        }
        if (c.peek(2)) this.errors.push(c.fail(`I did not expect ${describe(c.peek(2))} after \`end ${closer.word}\`.`, undefined, c.peek(2)));
        return body;
      }
      this.idx++;
      try {
        const stmt = this.parseStatement(c, sl, depth);
        if (stmt) body.push(stmt);
      } catch (e) {
        if (e instanceof ScriptError) this.errors.push(e);
        else throw e;
      }
    }
    if (closer !== null) {
      const l = this.lines.find((x) => x.line === openLine);
      const t = l?.tokens[0];
      this.errors.push(new ScriptError(`The \`${closer.kind}\` on line ${openLine} has no \`end ${closer.word}\`.`, openLine, t?.col ?? 1, t?.end ?? 2, `Add a line \`end ${closer.word}\` after its last statement.`));
    }
    return body;
  }

  /** A statement, checked against where it stands: a function only computes. */
  private parseStatement(c: Cursor, sl: SourceLine, depth: number): Stmt | null {
    const stmt = this.parseStatement1(c, sl, depth);
    if (stmt && this.defKind === 'function' && !FUNCTION_KINDS.has(stmt.kind)) {
      throw new ScriptError(`A function cannot do this: it only computes a value.`, stmt.line, stmt.col, stmt.end, 'Use `put`, `if`, `repeat` and `return` in a function; a handler (`on name ... end name`) can move the camera, show and hide, and wait.');
    }
    return stmt;
  }

  private parseStatement1(c: Cursor, sl: SourceLine, depth: number): Stmt | null {
    const t0 = c.peek()!;
    const first = lowerWord(t0);
    const lineSpan = (): Span => span(tspan(t0), tspan(sl.tokens[sl.tokens.length - 1]!));
    if (t0.type !== 'word') throw c.fail(`A statement starts with a word, not ${describe(t0)}.`, `Statements: ${STATEMENT_WORDS.filter((w) => w !== 'end').join(', ')}.`);
    c.i++;
    switch (first) {
      case 'fly': {
        if (!c.eatWord('to')) throw c.fail(`Expected \`to\` after \`fly\`, found ${describe(c.peek())}.`, 'For example: fly to class IfcPump over 3 seconds.');
        if (c.word() === 'view' && c.peek(1)?.type === 'string') {
          c.i++;
          const name = c.next();
          const o = parseOptions(c, ['over', 'ease']);
          return { kind: 'flyView', name: name.text, ...o, ...lineSpan() } as Stmt;
        }
        const target = parseElements(c);
        const o = parseOptions(c, ['over', 'ease', 'margin']);
        return { kind: 'flyTo', target, ...o, ...lineSpan() } as Stmt;
      }
      case 'orbit': {
        const degrees = parseQuantity(c, DEGREE_UNITS);
        let about: Elements | undefined;
        if (c.eatWord('about')) about = parseElements(c);
        const o = parseOptions(c, ['over', 'ease']);
        return { kind: 'orbit', degrees, ...(about ? { about } : {}), ...o, ...lineSpan() };
      }
      case 'set': {
        const p = c.peek();
        if (!p || p.type !== 'word') throw c.fail(`Expected the setting to change, found ${describe(p)}.`, 'For example: set xray.alphaMax to 0.3 over 2 seconds.');
        c.i++;
        if (!c.eatWord('to')) throw c.fail(`Expected \`to\` after the setting \`${p.text}\`, found ${describe(c.peek())}.`, `For example: set ${p.text} to 0.5.`);
        const value = parseValue(c);
        const o = parseOptions(c, ['over', 'ease']);
        return { kind: 'set', path: p.text, pathSpan: tspan(p), value, ...o, ...lineSpan() } as Stmt;
      }
      case 'mode': {
        const m = c.peek();
        if (!m || m.type !== 'word') throw c.fail(`Expected a mode name, found ${describe(m)}.`, `The modes are ${MODE_WORDS.join(', ')}.`);
        c.i++;
        endOfStatement(c, [], 'A mode statement is just `mode <name>`.');
        return { kind: 'mode', mode: m.text, modeSpan: tspan(m), ...lineSpan() };
      }
      case 'apply': {
        if (!c.eatWord('preset')) throw c.fail(`Expected \`preset\` after \`apply\`, found ${describe(c.peek())}.`, 'For example: apply preset "Peelback".');
        const n = c.peek();
        if (!n || n.type !== 'string') throw c.fail(`Expected the preset id or name in double quotes, found ${describe(n)}.`, 'For example: apply preset "Peelback".');
        c.i++;
        endOfStatement(c, [], 'An apply statement is just `apply preset "name"`.');
        return { kind: 'preset', name: n.text, nameSpan: tspan(n), ...lineSpan() };
      }
      case 'show':
      case 'hide':
      case 'isolate': {
        if (first !== 'isolate' && ['issues', 'drawings'].includes(c.word())) {
          const o: { issues?: boolean; drawings?: boolean } = {};
          for (;;) {
            const w = c.word();
            if (w !== 'issues' && w !== 'drawings') throw c.fail(`Expected \`issues\` or \`drawings\`, found ${describe(c.peek())}.`, `For example: ${first} issues, or ${first} issues and drawings.`);
            if (o[w] !== undefined) throw c.fail(`\`${w}\` is given twice in this statement.`);
            c.i++;
            o[w] = first === 'show';
            if (!c.eatPunct(',') && !c.eatWord('and')) break;
          }
          endOfStatement(c, [], `Write ${first} issues, ${first} drawings, or ${first} issues and drawings.`);
          return { kind: 'overlays', ...o, ...lineSpan() };
        }
        const target = parseElements(c);
        const o = parseOptions(c, ['fading']);
        return { kind: 'visibility', op: first, target, ...(o.fading ? { fading: o.fading } : {}), ...lineSpan() };
      }
      case 'select': {
        if (c.word() === 'nothing' || c.word() === 'none') {
          c.i++;
          endOfStatement(c, [], '`select nothing` takes nothing after it.');
          return { kind: 'select', target: null, ...lineSpan() };
        }
        const target = parseElements(c);
        endOfStatement(c, [], 'A select statement is `select <elements>` or `select nothing`.');
        return { kind: 'select', target, ...lineSpan() };
      }
      case 'caption': {
        const title = parseStr(c, 'the caption text');
        let text: Str | undefined;
        const n = c.peek();
        // `over` and `ease` belong to moves; a caption only lasts `for N`. Say so instead of reading them as caption text.
        if (n && n.type === 'word' && ['over', 'ease', 'fading'].includes(n.text.toLowerCase())) {
          throw new ScriptError(`A caption does not take \`${n.text}\`.`, n.line, n.col, n.end, 'Write `for N seconds` to say how long the caption shows.');
        }
        if (n && (n.type === 'string' || (n.type === 'word' && n.text.toLowerCase() !== 'for'))) text = parseStr(c, 'the caption text');
        const o = parseOptions(c, ['for']);
        return { kind: 'caption', title, ...(text ? { text } : {}), ...(o.for ? { for: o.for } : {}), ...lineSpan() };
      }
      case 'label': {
        const target = parseElements(c);
        if (!c.eatWord('with')) throw c.fail(`Expected \`with\` and the fields to show, found ${describe(c.peek())}.`, 'For example: label class IfcPump with name, storey for 4 seconds.');
        const fields: string[] = [];
        for (;;) {
          const f = c.peek();
          if (!f || (f.type !== 'word' && f.type !== 'string')) throw c.fail(`Expected a field name, found ${describe(f)}.`, 'Fields: name, class, storey, or a property as "Pset_X.Prop".');
          if (f.type === 'word' && f.text.toLowerCase() === 'for') throw c.fail('Expected a field name before `for`.', 'Fields: name, class, storey, or a property as "Pset_X.Prop".');
          c.i++;
          fields.push(f.text);
          if (!c.eatPunct(',')) break;
        }
        const o = parseOptions(c, ['for']);
        return { kind: 'label', target, fields, ...(o.for ? { for: o.for } : {}), ...lineSpan() };
      }
      case 'hover': {
        const target = parseElements(c);
        const o = parseOptions(c, ['for']);
        return { kind: 'hover', target, ...(o.for ? { for: o.for } : {}), ...lineSpan() };
      }
      case 'wait': {
        const seconds = parseQuantity(c, SECOND_UNITS);
        endOfStatement(c, [], 'A wait statement is `wait N seconds`.');
        return { kind: 'wait', seconds, ...lineSpan() };
      }
      case 'put': {
        const value = parseFull(c);
        if (!c.eatWord('into')) throw c.fail(`Expected \`into\` and a name after the value, found ${describe(c.peek())}.`, 'For example: put 2 * 3 into pause, or put "Level " & 2 into name.');
        const n = c.peek();
        if (!n || n.type !== 'word') throw c.fail(`Expected a name to put the number into, found ${describe(n)}.`);
        c.i++;
        endOfStatement(c, [], 'A put statement is `put <value> into <name>`.');
        return { kind: 'put', value, name: n.text, nameSpan: tspan(n), ...lineSpan() };
      }
      case 'schedule': {
        const n = c.peek();
        if (!n || n.type !== 'string') throw c.fail(`Expected the name of a 4D plan in double quotes after \`schedule\`, found ${describe(n)}.`, 'For example: schedule "Tower A" over 90 seconds.');
        c.i++;
        const out: Extract<Stmt, { kind: 'schedule' }> = { kind: 'schedule', plan: { v: n.text, ...tspan(n) }, ...lineSpan() };
        const textOpt = (what: string): Text => {
          const v = c.peek();
          if (!v || v.type !== 'string') throw c.fail(`Expected a date in double quotes after \`${what}\`, found ${describe(v)}.`, `For example: ${what} "2027-03-01".`);
          c.i++;
          return { v: v.text, ...tspan(v) };
        };
        while (!c.atEnd) {
          const o = c.peek()!;
          const w = lowerWord(o);
          if (o.type !== 'word' || !['view', 'from', 'to', 'over', 'fade'].includes(w)) {
            const dym = o.type === 'word' ? didYouMean(o.text, ['view', 'from', 'to', 'over', 'fade']) : '';
            throw c.fail(`I did not expect ${describe(o)} here.`, `${dym ? `${dym} ` : ''}A schedule statement can end with \`view planned|actual|variance\`, \`from "date"\`, \`to "date"\`, \`over N seconds\` and \`fade N seconds\`.`);
          }
          if ((out as unknown as Record<string, unknown>)[w] !== undefined) throw c.fail(`\`${w}\` is given twice in this statement.`);
          c.i++;
          if (w === 'view') {
            const v = c.peek();
            const vw = lowerWord(v);
            if (!v || v.type !== 'word' || !(SCHEDULE_VIEWS as readonly string[]).includes(vw)) throw c.fail(`Expected \`planned\`, \`actual\` or \`variance\` after \`view\`, found ${describe(v)}.`, v?.type === 'word' ? didYouMean(v.text, SCHEDULE_VIEWS) : undefined);
            c.i++;
            out.view = vw as 'planned' | 'actual' | 'variance';
          } else if (w === 'from') out.from = textOpt('from');
          else if (w === 'to') out.to = textOpt('to');
          else if (w === 'fade') out.fade = parseQuantity(c, SECOND_UNITS);
          else out.over = parseQuantity(c, SECOND_UNITS);
        }
        return out;
      }
      case 'at': {
        const k = c.peek();
        const kw = lowerWord(k);
        if (!k || (kw !== 'date' && kw !== 'milestone')) throw c.fail(`Expected \`date\` or \`milestone\` after \`at\`, found ${describe(k)}.`, k?.type === 'word' ? didYouMean(k.text, ['date', 'milestone']) || 'For example: at date "2027-03-01", or at milestone "Roof complete".' : 'For example: at date "2027-03-01", or at milestone "Roof complete".');
        c.i++;
        const v = c.peek();
        if (!v || v.type !== 'string') throw c.fail(`Expected the ${kw} in double quotes, found ${describe(v)}.`, kw === 'date' ? 'Write the date in double quotes, like at date "2027-03-01".' : 'Write the milestone name in double quotes, like at milestone "Roof complete".');
        c.i++;
        endOfStatement(c, [], `An \`at ${kw}\` line holds only the ${kw}; the statements that start then follow below it.`);
        return { kind: 'at', what: kw, value: { v: v.text, ...tspan(v) }, ...lineSpan() };
      }
      case 'tint': {
        const target = parseElements(c, true);
        const col = c.peek();
        let colour: Text | null;
        if (col && col.type === 'colour') {
          c.i++;
          colour = { v: col.text, ...tspan(col) };
        } else if (col && col.type === 'string') {
          c.i++;
          colour = { v: col.text, ...tspan(col) };
        } else if (col && col.type === 'word' && TINT_OFF.includes(col.text.toLowerCase())) {
          c.i++;
          colour = null;
        } else if (col && col.type === 'word') {
          c.i++;
          colour = { v: col.text, ...tspan(col) };
        } else throw c.fail(`Expected a colour after the elements, found ${describe(col)}.`, `A colour is #rrggbb or a name (${Object.keys(COLOUR_NAMES).slice(0, 6).join(', ')}, ...); \`off\` takes the tint away.`);
        const o = parseOptions(c, ['fading']);
        return { kind: 'tint', target, colour, ...(o.fading ? { fading: o.fading } : {}), ...lineSpan() };
      }
      case 'explode': {
        const m = c.peek();
        const mw = lowerWord(m);
        if (!m || (mw !== 'storeys' && mw !== 'radial')) throw c.fail(`Expected \`storeys\` or \`radial\` after \`explode\`, found ${describe(m)}.`, m?.type === 'word' ? didYouMean(m.text, ['storeys', 'radial']) || 'For example: explode storeys by 1.5 over 2 seconds.' : 'For example: explode storeys by 1.5 over 2 seconds.');
        c.i++;
        const o = parseOptions(c, ['by', 'over']);
        return { kind: 'explode', mode: mw, ...(o.by ? { by: o.by } : {}), ...(o.over ? { over: o.over } : {}), ...lineSpan() };
      }
      case 'collapse': {
        const o = parseOptions(c, ['over']);
        return { kind: 'collapse', ...(o.over ? { over: o.over } : {}), ...lineSpan() };
      }
      case 'focus': {
        if (c.word() === 'nothing' || c.word() === 'none') {
          c.i++;
          endOfStatement(c, [], '`focus nothing` takes nothing after it.');
          return { kind: 'focus', target: null, ...lineSpan() };
        }
        const target = parseElements(c);
        endOfStatement(c, [], 'A focus statement is `focus <elements>` or `focus nothing`.');
        return { kind: 'focus', target, ...lineSpan() };
      }
      case 'section': {
        if (!c.eatWord('box')) throw c.fail(`Expected \`box\` after \`section\`, found ${describe(c.peek())}.`, 'For example: section box around storey "Level 3" over 1.5 seconds, or section box off.');
        if (c.eatWord('off')) {
          const o = parseOptions(c, ['over']);
          return { kind: 'section', around: null, ...(o.over ? { over: o.over } : {}), ...lineSpan() };
        }
        if (!c.eatWord('around')) throw c.fail(`Expected \`around\` or \`off\` after \`section box\`, found ${describe(c.peek())}.`, 'For example: section box around active, or section box off.');
        let around: Elements | { storey: Text };
        if (c.word() === 'storey' && c.peek(1)?.type === 'string') {
          c.i++;
          const n = c.next();
          around = { storey: { v: n.text, ...tspan(n) } };
        } else around = parseElements(c);
        const o = parseOptions(c, ['over']);
        return { kind: 'section', around, ...(o.over ? { over: o.over } : {}), ...lineSpan() };
      }
      case 'fade': {
        if (!(c.eatWord('new') && c.eatWord('elements'))) throw c.fail(`Expected \`new elements\` after \`fade\`, found ${describe(c.peek())}.`, 'For example: fade new elements over 1.5 seconds, or fade new elements instantly.');
        if (c.eatWord('instantly', 'instant')) {
          endOfStatement(c, [], 'Nothing follows `instantly`.');
          return { kind: 'fadeDefault', ...lineSpan() };
        }
        if (!c.eatWord('over')) throw c.fail(`Expected \`over N seconds\` or \`instantly\`, found ${describe(c.peek())}.`, 'For example: fade new elements over 1.5 seconds.');
        const seconds = parseQuantity(c, SECOND_UNITS);
        endOfStatement(c, [], 'A fade statement is `fade new elements over N seconds` or `fade new elements instantly`.');
        return { kind: 'fadeDefault', seconds, ...lineSpan() };
      }
      case 'return': {
        if (!this.defKind) throw new ScriptError('`return` is outside a function or a handler.', t0.line, t0.col, t0.end, '`return <value>` gives back the value of a `function`; `return` alone ends an `on` handler early.');
        if (this.defKind === 'function') {
          if (c.atEnd) throw c.failEnd('A function returns a value: `return` needs one.', 'For example: return n * 2.');
          const value = parseFull(c);
          endOfStatement(c, [], 'A return statement is `return <value>`.');
          return { kind: 'return', value, ...lineSpan() };
        }
        if (!c.atEnd) throw c.fail('A handler does not return a value.', 'Write just `return` to end the handler early, or use a `function` to give a value back.');
        return { kind: 'return', ...lineSpan() };
      }
      case 'if':
        return this.parseIf(c, sl, t0, depth);
      case 'on':
      case 'function':
        return this.parseDef(c, sl, t0, first, depth);
      case 'together': {
        endOfStatement(c, [], '`together` stands alone on its line; the statements follow below it.');
        if (depth >= MAX_NESTING) throw new ScriptError(`Blocks are nested more than ${MAX_NESTING} deep.`, sl.line, t0.col, t0.end, 'Flatten the script.');
        const body = this.parseBlock(blk('together'), sl.line, depth + 1);
        return { kind: 'together', body, ...lineSpan() };
      }
      case 'repeat': {
        if (depth >= MAX_NESTING) throw new ScriptError(`Blocks are nested more than ${MAX_NESTING} deep.`, sl.line, t0.col, t0.end, 'Flatten the script.');
        if (c.eatWord('for')) {
          if (!c.eatWord('each')) throw c.fail(`Expected \`each\` after \`repeat for\`, found ${describe(c.peek())}.`, 'For example: repeat for each element in class IfcPump.');
          const kind = c.peek();
          const kw = lowerWord(kind);
          if (kw === 'element' || kw === 'elements') {
            c.i++;
            if (!c.eatWord('in')) throw c.fail(`Expected \`in\` and the elements, found ${describe(c.peek())}.`, 'For example: repeat for each element in class IfcPump.');
            const target = parseElements(c);
            endOfStatement(c, [], 'Nothing follows the elements on a `repeat for each` line.');
            const body = this.parseBlock(blk('repeat'), sl.line, depth + 1);
            return { kind: 'forEach', each: 'element', target, body, ...lineSpan() };
          }
          if (kw === 'set' || kw === 'sets') {
            c.i++;
            if (!c.eatWord('in') || !c.eatWord('sets')) throw c.fail('Expected `in sets` after `repeat for each set`.', 'Write: repeat for each set in sets.', c.peek() ?? c.last());
            endOfStatement(c, [], 'Nothing follows `in sets`.');
            const body = this.parseBlock(blk('repeat'), sl.line, depth + 1);
            return { kind: 'forEach', each: 'set', body, ...lineSpan() };
          }
          throw c.fail(`Expected \`element\` or \`set\` after \`repeat for each\`, found ${describe(kind)}.`, kind?.type === 'word' ? didYouMean(kind.text, ['element', 'set']) : undefined);
        }
        if (c.eatWord('with')) {
          const n = c.peek();
          if (!n || n.type !== 'word') throw c.fail(`Expected a name for the counter after \`repeat with\`, found ${describe(n)}.`, 'For example: repeat with i from 1 to 5.');
          c.i++;
          if (!c.eatWord('from')) throw c.fail(`Expected \`from\` after \`repeat with ${n.text}\`, found ${describe(c.peek())}.`, `For example: repeat with ${n.text} from 1 to 5.`);
          const from = parseExpr(c);
          const down = !!c.eatWord('down');
          if (!c.eatWord('to')) throw c.fail(`Expected \`${down ? 'down to' : 'to'}\` and the last value, found ${describe(c.peek())}.`, `For example: repeat with ${n.text} from 5 down to 1.`);
          const to = parseExpr(c);
          let by: Num | undefined;
          if (c.eatWord('by')) by = parseExpr(c);
          endOfStatement(c, ['by'], 'A counting loop is `repeat with i from A to B [by S]`.');
          const body = this.parseBlock(blk('repeat'), sl.line, depth + 1);
          return { kind: 'repeatWith', name: n.text, nameSpan: tspan(n), from, to, down, ...(by ? { by } : {}), body, ...lineSpan() };
        }
        if (c.word() === 'while' || c.word() === 'until') {
          const until = c.word() === 'until';
          c.i++;
          const cond = this.header(() => parseFull(c), c);
          const body = this.parseBlock(blk('repeat'), sl.line, depth + 1);
          return { kind: 'while', until, cond, body, ...lineSpan() };
        }
        const times = parseExpr(c);
        if (!c.eatWord('times', 'time')) throw c.fail(`Expected \`times\` after the count, found ${describe(c.peek())}.`, 'For example: repeat 3 times, repeat while n < 5, or repeat with i from 1 to 5.');
        endOfStatement(c, [], 'Nothing follows `times`.');
        const body = this.parseBlock(blk('repeat'), sl.line, depth + 1);
        return { kind: 'repeat', times, body, ...lineSpan() };
      }
      default: {
        if (this.defNames.has(first)) {
          const args: Num[] = [];
          if (!c.atEnd) {
            for (;;) {
              args.push(parseFull(c));
              if (!c.eatPunct(',')) break;
            }
            endOfStatement(c, [], `Give the values of the call separated by commas: ${t0.text} 1, 2.`);
          }
          return { kind: 'call', name: t0.text, nameSpan: tspan(t0), args, ...lineSpan() };
        }
        const dym = didYouMean(t0.text, [...STATEMENT_WORDS, ...this.defNames]);
        throw c.fail(`I do not know the statement \`${t0.text}\`.`, `${dym ? `${dym} ` : ''}Statements start with ${STATEMENT_WORDS.filter((w) => w !== 'end').join(', ')}${this.defNames.size ? `, or the name of a handler (${[...this.defNames].join(', ')})` : ''}.`, t0);
      }
    }
  }

  /** Parse a block header (a condition): on an error, record it and carry on with a condition that is never true, so the lines of
   *  the block are not read as statements of the outer level. */
  private header(f: () => Num, c: Cursor): Num {
    try {
      return f();
    } catch (e) {
      if (!(e instanceof ScriptError)) throw e;
      this.errors.push(e);
      c.i = c.toks.length;
      return { k: 'bool', v: false, line: c.lineNo, col: 1, end: 2 };
    }
  }

  private parseIf(c: Cursor, sl: SourceLine, t0: Tok, depth: number): Stmt | null {
    if (depth >= MAX_NESTING) throw new ScriptError(`Blocks are nested more than ${MAX_NESTING} deep.`, sl.line, t0.col, t0.end, 'Flatten the script.');
    const lineSpan = (): Span => span(tspan(t0), tspan(sl.tokens[sl.tokens.length - 1]!));
    const thenAt = (cc: Cursor): number => cc.toks.findIndex((t, j) => j >= cc.i && t.type === 'word' && t.text.toLowerCase() === 'then');
    let cond: Num;
    let oneLine = false;
    try {
      cond = parseFull(c);
      if (!c.eatWord('then')) throw c.fail(`Expected \`then\` after the condition, found ${describe(c.peek())}.`, 'Write: if <condition> then. For example: if there are class IfcPump then.');
      oneLine = !c.atEnd;
    } catch (e) {
      if (!(e instanceof ScriptError)) throw e;
      this.errors.push(e);
      cond = { k: 'bool', v: false, line: sl.line, col: 1, end: 2 };
      const k = thenAt(new Cursor(sl.tokens, sl.line));
      if (k >= 0 && k < sl.tokens.length - 1) return null; // a one-line `if` with a broken condition: nothing to build on
      c.i = c.toks.length;
    }
    if (oneLine) {
      const rest = sl.tokens.slice(c.i);
      const w = lowerWord(rest[0]);
      if (BLOCK_WORDS.has(w)) throw new ScriptError(`A one-line \`if\` holds one plain statement, not \`${rest[0]!.text}\`.`, rest[0]!.line, rest[0]!.col, rest[0]!.end, 'Put the statement on its own lines: end the `if` line with `then` and close with `end if`.');
      const rc = new Cursor(rest, sl.line);
      const stmt = this.parseStatement(rc, { ...sl, tokens: rest }, depth);
      if (!stmt) return null;
      return { kind: 'if', branches: [{ cond, body: [stmt], ...lineSpan() }], ...lineSpan() };
    }
    const branches: Array<{ cond: Num; body: Stmt[] } & Span> = [];
    let otherwise: Stmt[] | undefined;
    let cur: { cond: Num; body: Stmt[] } & Span = { cond, body: [], ...lineSpan() };
    branches.push(cur);
    let afterElse = false;
    let openLine = sl.line;
    for (;;) {
      this.elseLine = null;
      const body = this.parseBlock({ word: 'if', kind: 'if', afterElse }, openLine, depth + 1);
      if (afterElse) otherwise = body;
      else cur.body = body;
      const el = this.elseLine as SourceLine | null;
      if (!el) break;
      openLine = el.line;
      const ec = new Cursor(el.tokens, el.line);
      ec.i = 1;
      if (ec.eatWord('if')) {
        let c2: Num;
        try {
          c2 = parseFull(ec);
          if (!ec.eatWord('then')) throw ec.fail(`Expected \`then\` after the condition, found ${describe(ec.peek())}.`, 'Write: else if <condition> then.');
          if (!ec.atEnd) throw ec.fail('Put the statements of an `else if` on the lines below it.', 'A one-line form exists only for a plain `if`.');
        } catch (e) {
          if (!(e instanceof ScriptError)) throw e;
          this.errors.push(e);
          c2 = { k: 'bool', v: false, line: el.line, col: 1, end: 2 };
        }
        cur = { cond: c2, body: [], line: el.line, col: el.tokens[0]!.col, end: el.tokens[el.tokens.length - 1]!.end };
        branches.push(cur);
      } else {
        if (!ec.atEnd) this.errors.push(ec.fail('Put the statements of an `else` on the lines below it.', 'Write `else` alone on its line; for another test use `else if <condition> then`.'));
        afterElse = true;
      }
    }
    return { kind: 'if', branches, ...(otherwise ? { otherwise } : {}), ...lineSpan() };
  }

  private parseDef(c: Cursor, sl: SourceLine, t0: Tok, form: string, depth: number): Stmt | null {
    const f = form as 'on' | 'function';
    const lineSpan = (): Span => span(tspan(t0), tspan(sl.tokens[sl.tokens.length - 1]!));
    if (depth > 0 || this.defKind) throw new ScriptError(`\`${f}\` defines a ${f === 'on' ? 'handler' : 'function'} and goes at the top level of the script, not inside another block.`, t0.line, t0.col, t0.end, `Move the \`${f}\` ... \`end\` lines out of the block; they may stand anywhere at the top level, before or after the lines that use them.`);
    const nameTok = c.peek();
    let name = '';
    let nameSpan: Span = tspan(t0);
    const params: Array<{ name: string; span: Span }> = [];
    let headerOk = true;
    try {
      if (!nameTok || nameTok.type !== 'word') throw c.fail(`Expected the name of the ${f === 'on' ? 'handler' : 'function'} after \`${f}\`, found ${describe(nameTok)}.`, `For example: ${f === 'on' ? 'on showFloor name' : 'function double x'}.`);
      c.i++;
      name = nameTok.text;
      nameSpan = tspan(nameTok);
      if (!c.atEnd) {
        for (;;) {
          const p = c.peek();
          if (!p || p.type !== 'word') throw c.fail(`Expected a parameter name, found ${describe(p)}.`, 'Parameters are names separated by commas: on showFloor name, seconds.');
          c.i++;
          params.push({ name: p.text, span: tspan(p) });
          if (!c.eatPunct(',')) break;
        }
        endOfStatement(c, [], 'Separate the parameters with commas.');
      }
    } catch (e) {
      if (!(e instanceof ScriptError)) throw e;
      this.errors.push(e);
      headerOk = false;
    }
    const was = this.defKind;
    this.defKind = f;
    let body: Stmt[];
    try {
      body = this.parseBlock({ word: name.toLowerCase() || f, kind: name ? `${f} ${name}` : f }, sl.line, depth + 1);
    } finally {
      this.defKind = was;
    }
    if (!headerOk) return null;
    return { kind: 'def', form: f, name, nameSpan, params, body, ...lineSpan() };
  }
}

export interface ParseResult {
  program: Program;
  errors: ScriptDiagnostic[];
}

/** Parse a script text. Never throws. */
export function parseScript(source: string): ParseResult {
  const lex = lexScript(source);
  const p = new Parser(lex.lines);
  const program = p.parseProgram();
  const errors = [...lex.errors, ...p.errors].map((e) => e.toDiagnostic());
  errors.sort((a, b) => a.line - b.line || a.col - b.col);
  return { program, errors };
}
