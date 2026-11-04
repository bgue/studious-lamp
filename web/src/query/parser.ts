// Recursive-descent parser for the criteria query language. Produces the AST below. Pure module, no DOM.
//
// Grammar (keywords are case-insensitive; precedence from low to high: OR, AND, NOT, comparison):
//   query     := or EOF
//   or        := and ( OR and )*
//   and       := not ( AND not )*
//   not       := NOT not | primary
//   primary   := '(' or ')' | operand [ tail ]
//   tail      := cmpOp operand
//              | [NOT] LIKE operand
//              | [NOT] IN '(' operand ( ',' operand )* ')'
//              | [NOT] BETWEEN operand AND operand
//              | IS [NOT] NULL
//   operand   := column | 'string' | number | '-' number | TRUE | FALSE | NULL
//   column    := ident ( '.' ident )* | "quoted name"
//   cmpOp     := = | == | != | <> | < | <= | > | >=
// An operand with no tail is a test for TRUE: `"Pset_WallCommon.IsExternal"` equals `"Pset_WallCommon.IsExternal" = TRUE`.

import { QueryError, tokenize } from './lexer';
import type { Token } from './lexer';

export type Value = string | number | boolean | null;
export type CmpOp = '=' | '!=' | '<' | '<=' | '>' | '>=';

export type Operand = { kind: 'col'; name: string; quoted: boolean; pos: number } | { kind: 'lit'; value: Value; pos: number };

export type Expr =
  | { kind: 'and' | 'or'; items: Expr[] }
  | { kind: 'not'; expr: Expr }
  | { kind: 'cmp'; op: CmpOp; left: Operand; right: Operand }
  | { kind: 'like'; neg: boolean; left: Operand; pattern: Operand }
  | { kind: 'in'; neg: boolean; left: Operand; list: Operand[] }
  | { kind: 'between'; neg: boolean; left: Operand; lo: Operand; hi: Operand }
  | { kind: 'isnull'; neg: boolean; left: Operand }
  | { kind: 'truthy'; operand: Operand };

function describe(t: Token): string {
  switch (t.type) {
    case 'eof':
      return 'the end of the query';
    case 'string':
      return `'${t.value}'`;
    case 'qident':
      return `"${t.value}"`;
    default:
      return `"${t.value}"`;
  }
}

class Parser {
  private i = 0;
  constructor(private readonly toks: Token[]) {}

  private get t(): Token {
    return this.toks[this.i]!;
  }
  private next(): Token {
    return this.toks[this.i++]!;
  }
  private isKw(kw: string, k = 0): boolean {
    const t = this.toks[this.i + k];
    return !!t && t.type === 'keyword' && t.value === kw;
  }
  private eatKw(kw: string): boolean {
    if (this.isKw(kw)) {
      this.i++;
      return true;
    }
    return false;
  }
  private isPunct(p: string): boolean {
    return this.t.type === 'punct' && this.t.value === p;
  }

  parse(): Expr {
    if (this.t.type === 'eof') throw new QueryError('The query is empty', 0);
    const e = this.or();
    const t: Token = this.toks[this.i]!;
    if (t.type !== 'eof') {
      if (t.type === 'punct' && t.value === ')') throw new QueryError('Unexpected ")": there is no matching "("', t.pos);
      throw new QueryError(`Unexpected ${describe(t)}: expected AND, OR or the end of the query`, t.pos);
    }
    return e;
  }

  private or(): Expr {
    const items = [this.and()];
    while (this.eatKw('OR')) items.push(this.and());
    return items.length === 1 ? items[0]! : { kind: 'or', items };
  }

  private and(): Expr {
    const items = [this.not()];
    while (this.eatKw('AND')) items.push(this.not());
    return items.length === 1 ? items[0]! : { kind: 'and', items };
  }

  private not(): Expr {
    if (this.eatKw('NOT')) return { kind: 'not', expr: this.not() };
    return this.primary();
  }

  private primary(): Expr {
    if (this.isPunct('(')) {
      const open = this.next();
      const e = this.or();
      if (!this.isPunct(')')) throw new QueryError(`Expected ")" to close the "(" at character ${open.pos + 1}, found ${describe(this.t)}`, this.t.pos);
      this.next();
      return e;
    }
    const left = this.operand('a condition');
    const t = this.t;
    if (t.type === 'op') {
      this.next();
      return { kind: 'cmp', op: t.value as CmpOp, left, right: this.operand(`"${t.value}"`) };
    }
    if (this.isKw('IS')) {
      this.next();
      const neg = this.eatKw('NOT');
      if (!this.eatKw('NULL')) throw new QueryError(`Expected NULL after IS${neg ? ' NOT' : ''}, found ${describe(this.t)}`, this.t.pos);
      return { kind: 'isnull', neg, left };
    }
    let neg = false;
    if (this.isKw('NOT')) {
      this.next();
      neg = true;
      if (!this.isKw('LIKE') && !this.isKw('IN') && !this.isKw('BETWEEN')) {
        throw new QueryError(`Expected LIKE, IN or BETWEEN after NOT, found ${describe(this.t)}`, this.t.pos);
      }
    }
    if (this.eatKw('LIKE')) return { kind: 'like', neg, left, pattern: this.operand('LIKE') };
    if (this.isKw('IN')) {
      this.next();
      if (!this.isPunct('(')) throw new QueryError(`Expected "(" after IN, found ${describe(this.t)}`, this.t.pos);
      this.next();
      const list: Operand[] = [];
      if (this.isPunct(')')) throw new QueryError('The IN list is empty', this.t.pos);
      for (;;) {
        list.push(this.operand('IN ( or ","'));
        if (this.isPunct(',')) {
          this.next();
          continue;
        }
        if (this.isPunct(')')) {
          this.next();
          break;
        }
        throw new QueryError(`Expected "," or ")" in the IN list, found ${describe(this.t)}`, this.t.pos);
      }
      return { kind: 'in', neg, left, list };
    }
    if (this.eatKw('BETWEEN')) {
      const lo = this.operand('BETWEEN');
      if (!this.eatKw('AND')) throw new QueryError(`Expected AND in BETWEEN ... AND ..., found ${describe(this.t)}`, this.t.pos);
      const hi = this.operand('BETWEEN ... AND');
      return { kind: 'between', neg, left, lo, hi };
    }
    return { kind: 'truthy', operand: left };
  }

  private operand(after: string): Operand {
    const t = this.t;
    switch (t.type) {
      case 'ident':
      case 'qident':
        this.next();
        return { kind: 'col', name: t.value, quoted: t.type === 'qident', pos: t.pos };
      case 'string':
        this.next();
        return { kind: 'lit', value: t.value, pos: t.pos };
      case 'number':
        this.next();
        return { kind: 'lit', value: t.num!, pos: t.pos };
      case 'keyword':
        if (t.value === 'TRUE' || t.value === 'FALSE' || t.value === 'NULL') {
          this.next();
          return { kind: 'lit', value: t.value === 'NULL' ? null : t.value === 'TRUE', pos: t.pos };
        }
        break;
      case 'punct':
        if (t.value === '-' && this.toks[this.i + 1]?.type === 'number') {
          this.next();
          const n = this.next();
          return { kind: 'lit', value: -n.num!, pos: t.pos };
        }
        break;
      default:
        break;
    }
    const what = after === 'a condition' ? 'a column name or a value' : `a value after ${after}`;
    const hint = t.type === 'keyword' ? ` (${t.value} is a keyword: write "${t.value.toLowerCase()}" in double quotes to use it as a column)` : '';
    throw new QueryError(`Expected ${what}, found ${describe(t)}${hint}`, t.pos);
  }
}

/** Parse a query into an AST. Throws QueryError with the character position on a syntax error. */
export function parseQuery(src: string): Expr {
  return new Parser(tokenize(src)).parse();
}

/** Every column referenced in the AST, in order of first appearance. */
export function columnsOf(e: Expr): Array<{ name: string; pos: number }> {
  const out: Array<{ name: string; pos: number }> = [];
  const seen = new Set<string>();
  const op = (o: Operand): void => {
    if (o.kind === 'col' && !seen.has(o.name)) {
      seen.add(o.name);
      out.push({ name: o.name, pos: o.pos });
    }
  };
  const walk = (x: Expr): void => {
    switch (x.kind) {
      case 'and':
      case 'or':
        x.items.forEach(walk);
        break;
      case 'not':
        walk(x.expr);
        break;
      case 'cmp':
        op(x.left);
        op(x.right);
        break;
      case 'like':
        op(x.left);
        op(x.pattern);
        break;
      case 'in':
        op(x.left);
        x.list.forEach(op);
        break;
      case 'between':
        op(x.left);
        op(x.lo);
        op(x.hi);
        break;
      case 'isnull':
        op(x.left);
        break;
      case 'truthy':
        op(x.operand);
        break;
    }
  };
  walk(e);
  return out;
}
