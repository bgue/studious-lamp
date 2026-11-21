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
//   put <number expression> into <name>
//
//   <elements> := where <criteria> | class A[, B] | set "Name" | the selection | everything | it | elements "gid", "gid"
//   <criteria> := the criteria query language of src/query; text values may be bare words or double quoted
//
// parseScript never throws: it returns the tree of the lines that are fine and the errors of the others.

import { QueryError } from '../../query/lexer';
import { parseQuery } from '../../query/parser';
import { ScriptError, didYouMean } from './diagnostics';
import type { ScriptDiagnostic } from './diagnostics';
import { lexScript, lowerWord } from './lexer';
import type { SourceLine, Tok } from './lexer';
import type { Ease, Elements, Num, Program, Span, Stmt, Str, StrPart, Value } from './ast';

export * from './ast';

/** The statement words, in the order of the reference. */
export const STATEMENT_WORDS = ['fly', 'orbit', 'set', 'mode', 'apply', 'show', 'hide', 'isolate', 'select', 'caption', 'label', 'hover', 'wait', 'together', 'repeat', 'put', 'end'] as const;
export const MODE_WORDS = ['ghost', 'solid', 'radiograph', 'glow', 'cutaway'] as const;
export const MAX_NESTING = 8;

/** Words that end a `where` clause (the start of an option) and cannot be a bare column or value there. */
const STOP_WORDS = new Set(['over', 'ease', 'margin', 'fading', 'for', 'with', 'about']);
const SECOND_UNITS = new Set(['s', 'sec', 'secs', 'second', 'seconds']);
const DEGREE_UNITS = new Set(['degree', 'degrees', 'deg']);
const QUERY_KEYWORDS = new Set(['AND', 'OR', 'NOT', 'LIKE', 'IN', 'BETWEEN', 'IS', 'NULL', 'TRUE', 'FALSE']);
const BOOL_WORDS: Record<string, boolean> = { true: true, on: true, yes: true, false: false, off: false, no: false };

const span = (a: Span, b: Span = a): Span => ({ line: a.line, col: a.col, end: b.end });
const tspan = (t: Tok): Span => ({ line: t.line, col: t.col, end: t.end });

/** Reads the tokens of one line. */
class Cursor {
  i = 0;
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
  if (t.type === 'word') {
    c.i++;
    return { k: 'var', name: t.text, ...tspan(t) };
  }
  if (t.type === 'punct' && t.text === '(') {
    c.i++;
    const e = parseExpr(c);
    const close = c.eatPunct(')');
    if (!close) throw c.fail(`Expected \`)\` to close the \`(\` at column ${t.col}, found ${describe(c.peek())}.`);
    return { ...e, line: t.line, col: t.col, end: close.end };
  }
  throw c.fail(`Expected a number, found ${describe(t)}.`, t.type === 'string' ? 'Numbers are written without quotes.' : undefined);
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

type OptionKey = 'over' | 'ease' | 'margin' | 'fading' | 'for';
interface Options {
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
    else if (w === 'fading') {
      c.eatWord('over');
      o.fading = parseQuantity(c, SECOND_UNITS);
    } else o[w] = parseQuantity(c, SECOND_UNITS);
  }
  return o;
}

// ---------------------------------------------------------------- elements

/** The query text of a `where` clause, built from script tokens, and where each token starts in it. */
export function buildQuery(toks: readonly Tok[]): { text: string; starts: number[] } {
  let text = '';
  const starts: number[] = [];
  let valuePos = false;
  let betweenPending = false;
  let prevIn = false;
  const parens: boolean[] = [];
  let prev = '';
  for (const t of toks) {
    let piece = t.text;
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
    text += (glue ? '' : ' ') + piece;
    prev = piece;
  }
  return { text, starts };
}

function parseWhere(c: Cursor, kw: Tok): Elements {
  const toks: Tok[] = [];
  let depth = 0;
  while (!c.atEnd) {
    const t = c.peek()!;
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
  const { text, starts } = buildQuery(toks);
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
  return { k: 'query', query: text, ...span(tspan(kw), tspan(toks[toks.length - 1]!)) };
}

const ELEMENT_HELP = 'Write `where <criteria>`, `class IfcPump`, `set "Name"`, `the selection`, `everything`, `it` or `elements "id", "id"`.';
const ELEMENT_WORDS = ['where', 'class', 'set', 'the', 'selection', 'everything', 'it', 'elements'];

function parseElements(c: Cursor): Elements {
  const t = c.peek();
  if (!t) throw c.failEnd('Expected which elements.', ELEMENT_HELP);
  const w = lowerWord(t);
  if (t.type === 'word') {
    switch (w) {
      case 'where':
        c.i++;
        return parseWhere(c, t);
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
        return { k: 'query', query, ...span(tspan(t), tspan(names[names.length - 1]!)) };
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
    if (w in BOOL_WORDS && alone) {
      c.i++;
      return { k: 'bool', v: BOOL_WORDS[w]!, ...tspan(t) };
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

class Parser {
  readonly errors: ScriptError[] = [];
  private idx = 0;
  constructor(private readonly lines: SourceLine[]) {}

  parseProgram(): Program {
    const body = this.parseBlock(null, 0, 0);
    return { body };
  }

  /** Statements until the `end` of the block (or the end of the script). Returns at the line after `end`. */
  private parseBlock(closer: 'together' | 'repeat' | null, openLine: number, depth: number): Stmt[] {
    const body: Stmt[] = [];
    while (this.idx < this.lines.length) {
      const sl = this.lines[this.idx]!;
      const c = new Cursor(sl.tokens, sl.line);
      const first = c.word();
      if (first === 'end') {
        this.idx++;
        const what = c.word(1);
        const endTok = c.peek(1);
        if (closer === null) {
          this.errors.push(c.fail(`\`end${what ? ` ${what}` : ''}\` has no block to close.`, 'Every `end` closes a `together` or a `repeat` above it.', c.peek()));
          continue;
        }
        if (!endTok || what !== closer) {
          this.errors.push(
            c.fail(
              endTok ? `\`end ${endTok.text}\` does not match: the open block (line ${openLine}) is a \`${closer}\`.` : `\`end\` needs the block name: \`end ${closer}\`.`,
              `Write \`end ${closer}\` to close the \`${closer}\` of line ${openLine}.`,
              endTok ?? c.peek(),
            ),
          );
          return body;
        }
        if (c.peek(2)) this.errors.push(c.fail(`I did not expect ${describe(c.peek(2))} after \`end ${closer}\`.`, undefined, c.peek(2)));
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
      this.errors.push(new ScriptError(`The \`${closer}\` on line ${openLine} has no \`end ${closer}\`.`, openLine, t?.col ?? 1, t?.end ?? 2, `Add a line \`end ${closer}\` after its last statement.`));
    }
    return body;
  }

  private parseStatement(c: Cursor, sl: SourceLine, depth: number): Stmt | null {
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
        const value = parseExpr(c);
        if (!c.eatWord('into')) throw c.fail(`Expected \`into\` and a name after the number, found ${describe(c.peek())}.`, 'For example: put 2 * 3 into pause.');
        const n = c.peek();
        if (!n || n.type !== 'word') throw c.fail(`Expected a name to put the number into, found ${describe(n)}.`);
        c.i++;
        endOfStatement(c, [], 'A put statement is `put <number> into <name>`.');
        return { kind: 'put', value, name: n.text, nameSpan: tspan(n), ...lineSpan() };
      }
      case 'together': {
        endOfStatement(c, [], '`together` stands alone on its line; the statements follow below it.');
        if (depth >= MAX_NESTING) throw new ScriptError(`Blocks are nested more than ${MAX_NESTING} deep.`, sl.line, t0.col, t0.end, 'Flatten the script.');
        const body = this.parseBlock('together', sl.line, depth + 1);
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
            const body = this.parseBlock('repeat', sl.line, depth + 1);
            return { kind: 'forEach', each: 'element', target, body, ...lineSpan() };
          }
          if (kw === 'set' || kw === 'sets') {
            c.i++;
            if (!c.eatWord('in') || !c.eatWord('sets')) throw c.fail('Expected `in sets` after `repeat for each set`.', 'Write: repeat for each set in sets.', c.peek() ?? c.last());
            endOfStatement(c, [], 'Nothing follows `in sets`.');
            const body = this.parseBlock('repeat', sl.line, depth + 1);
            return { kind: 'forEach', each: 'set', body, ...lineSpan() };
          }
          throw c.fail(`Expected \`element\` or \`set\` after \`repeat for each\`, found ${describe(kind)}.`, kind?.type === 'word' ? didYouMean(kind.text, ['element', 'set']) : undefined);
        }
        const times = parseExpr(c);
        if (!c.eatWord('times', 'time')) throw c.fail(`Expected \`times\` after the count, found ${describe(c.peek())}.`, 'For example: repeat 3 times.');
        endOfStatement(c, [], 'Nothing follows `times`.');
        const body = this.parseBlock('repeat', sl.line, depth + 1);
        return { kind: 'repeat', times, body, ...lineSpan() };
      }
      default: {
        const dym = didYouMean(t0.text, STATEMENT_WORDS);
        throw c.fail(`I do not know the statement \`${t0.text}\`.`, `${dym ? `${dym} ` : ''}Statements start with ${STATEMENT_WORDS.filter((w) => w !== 'end').join(', ')}.`, t0);
      }
    }
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
