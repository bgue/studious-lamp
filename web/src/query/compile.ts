// Compiles a query AST to a predicate over the rows of a table. Pure module, no DOM.
//
// Semantics (documented in docs-features/sets-query.md):
// - A missing property, an empty name or material and "no storey" are NULL. Comparisons with NULL are UNKNOWN, and
//   the three-valued logic of SQL applies: NOT UNKNOWN is UNKNOWN, a row matches only when the whole query is TRUE.
//   So `"Pset_WallCommon.IsExternal" != TRUE` skips elements without the property; add `OR ... IS NULL` for them.
// - Two numbers compare as numbers. A number and a numeric string compare as numbers ('0.24' = 0.24). Booleans
//   compare as 0 and 1 with numbers and as 'true'/'false' (also 'yes'/'no') with strings.
// - Strings compare without regard to case ('ifcwall' = 'IfcWall'). LIKE also ignores case; % is any run of
//   characters, _ is one character, and a backslash makes the next % or _ literal.

import { QueryError } from './lexer';
import type { CmpOp, Expr, Operand, Value } from './parser';

/** Row access by row index. A table resolves column names to accessors. */
export type Accessor = (row: number) => Value;

export interface QueryTable {
  readonly size: number;
  /** Accessor for a column (name as written in the query), or null when no row has that column. */
  accessor(name: string): Accessor | null;
}

type Tri = boolean | null;
type Eval = (row: number) => Tri;
type Get = (row: number) => Value;

const NUMERIC = /^\s*[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?\s*$/;

function boolFromString(s: string): boolean | null {
  const l = s.trim().toLowerCase();
  if (l === 'true' || l === 'yes') return true;
  if (l === 'false' || l === 'no') return false;
  return null;
}

/** Order of two values: negative, 0 or positive; null when either is NULL. */
export function compareValues(a: Value, b: Value): number | null {
  if (a === null || b === null) return null;
  const ta = typeof a;
  const tb = typeof b;
  if (ta === 'number' && tb === 'number') return (a as number) - (b as number);
  if (ta === 'string' && tb === 'string') {
    if (a === b) return 0;
    const la = (a as string).toLowerCase();
    const lb = (b as string).toLowerCase();
    return la < lb ? -1 : la > lb ? 1 : 0;
  }
  if (ta === 'boolean' && tb === 'boolean') return Number(a) - Number(b);
  if (ta === 'boolean' || tb === 'boolean') {
    const [bv, other, flip] = ta === 'boolean' ? [a as boolean, b, 1] : [b as boolean, a, -1];
    if (typeof other === 'number') return flip * (Number(bv) - other);
    const ob = boolFromString(other as string);
    if (ob !== null) return flip * (Number(bv) - Number(ob));
    return flip * compareValues(String(bv), other as string)!;
  }
  // number and string
  const [num, str, flip] = ta === 'number' ? [a as number, b as string, 1] : [b as number, a as string, -1];
  if (NUMERIC.test(str)) return flip * (num - Number(str));
  return flip * compareValues(String(num), str)!;
}

function cmpTest(op: CmpOp, c: number): boolean {
  switch (op) {
    case '=':
      return c === 0;
    case '!=':
      return c !== 0;
    case '<':
      return c < 0;
    case '<=':
      return c <= 0;
    case '>':
      return c > 0;
    case '>=':
      return c >= 0;
  }
}

/** Regular expression for a LIKE pattern (anchored, case-insensitive). */
export function likeToRegExp(pattern: string): RegExp {
  let re = '';
  for (let i = 0; i < pattern.length; i++) {
    const c = pattern[i]!;
    if (c === '\\' && (pattern[i + 1] === '%' || pattern[i + 1] === '_' || pattern[i + 1] === '\\')) {
      re += pattern[++i]!.replace(/[\\]/, '\\\\');
    } else if (c === '%') re += '[\\s\\S]*';
    else if (c === '_') re += '[\\s\\S]';
    else re += c.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&');
  }
  return new RegExp(`^${re}$`, 'i');
}

const asText = (v: Value): string => (typeof v === 'string' ? v : String(v));

export interface Compiled {
  /** True when the row matches (the query is TRUE for it). */
  test(row: number): boolean;
  /** Column names that no row of the table has (they read as NULL everywhere). */
  unknown: string[];
}

/** Compile an AST against a table. Never throws for unknown columns; they are NULL and listed in `unknown`. */
export function compile(ast: Expr, table: QueryTable): Compiled {
  const unknown: string[] = [];
  const operand = (o: Operand): Get => {
    if (o.kind === 'lit') {
      const v = o.value;
      return () => v;
    }
    const acc = table.accessor(o.name);
    if (acc) return acc;
    if (!unknown.includes(o.name)) unknown.push(o.name);
    return () => null;
  };

  const build = (e: Expr): Eval => {
    switch (e.kind) {
      case 'and': {
        const parts = e.items.map(build);
        return (r) => {
          let unk = false;
          for (const p of parts) {
            const v = p(r);
            if (v === false) return false;
            if (v === null) unk = true;
          }
          return unk ? null : true;
        };
      }
      case 'or': {
        const parts = e.items.map(build);
        return (r) => {
          let unk = false;
          for (const p of parts) {
            const v = p(r);
            if (v === true) return true;
            if (v === null) unk = true;
          }
          return unk ? null : false;
        };
      }
      case 'not': {
        const inner = build(e.expr);
        return (r) => {
          const v = inner(r);
          return v === null ? null : !v;
        };
      }
      case 'cmp': {
        const a = operand(e.left);
        const b = operand(e.right);
        const op = e.op;
        // Fast paths for `column <op> literal`: same-type values skip the generic comparison.
        if (e.left.kind === 'col' && e.right.kind === 'lit' && e.right.value !== null) {
          const lit = e.right.value;
          const generic = (v: Value): Tri => {
            const c = compareValues(v, lit);
            return c === null ? null : cmpTest(op, c);
          };
          if (typeof lit === 'number') {
            return (r) => {
              const v = a(r);
              return typeof v === 'number' ? cmpTest(op, v - lit) : generic(v);
            };
          }
          if (typeof lit === 'string') {
            const low = lit.toLowerCase();
            return (r) => {
              const v = a(r);
              if (typeof v !== 'string') return generic(v);
              if (v === lit) return cmpTest(op, 0);
              const lv = v.toLowerCase();
              return cmpTest(op, lv < low ? -1 : lv > low ? 1 : 0);
            };
          }
        }
        return (r) => {
          const c = compareValues(a(r), b(r));
          return c === null ? null : cmpTest(op, c);
        };
      }
      case 'like': {
        const a = operand(e.left);
        const neg = e.neg;
        let fixed: RegExp | null = null;
        if (e.pattern.kind === 'lit') {
          if (e.pattern.value === null) return () => null;
          fixed = likeToRegExp(asText(e.pattern.value));
        }
        const p = fixed ? null : operand(e.pattern);
        return (r) => {
          const v = a(r);
          if (v === null) return null;
          let re = fixed;
          if (!re) {
            const pv = p!(r);
            if (pv === null) return null;
            re = likeToRegExp(asText(pv));
          }
          return re.test(asText(v)) !== neg;
        };
      }
      case 'in': {
        const a = operand(e.left);
        const list = e.list.map(operand);
        const neg = e.neg;
        // Fast path: a list of plain string literals and a string value -> one Set lookup.
        if (e.list.every((o) => o.kind === 'lit' && typeof o.value === 'string')) {
          const set = new Set(e.list.map((o) => (o as { value: string }).value.toLowerCase()));
          const general = (v: Value): Tri => {
            for (const g of list) if (compareValues(v, g(0)) === 0) return !neg;
            return neg;
          };
          return (r) => {
            const v = a(r);
            if (v === null) return null;
            if (typeof v === 'string') return set.has(v.toLowerCase()) !== neg;
            return general(v);
          };
        }
        return (r) => {
          const v = a(r);
          if (v === null) return null;
          let unk = false;
          for (const g of list) {
            const c = compareValues(v, g(r));
            if (c === 0) return !neg;
            if (c === null) unk = true;
          }
          return unk ? null : neg;
        };
      }
      case 'between': {
        const a = operand(e.left);
        const lo = operand(e.lo);
        const hi = operand(e.hi);
        const neg = e.neg;
        return (r) => {
          const v = a(r);
          const c1 = compareValues(v, lo(r));
          const c2 = compareValues(v, hi(r));
          // v >= lo AND v <= hi, in three-valued logic
          const t1: Tri = c1 === null ? null : c1 >= 0;
          const t2: Tri = c2 === null ? null : c2 <= 0;
          const res: Tri = t1 === false || t2 === false ? false : t1 === null || t2 === null ? null : true;
          return res === null ? null : res !== neg;
        };
      }
      case 'isnull': {
        const a = operand(e.left);
        const neg = e.neg;
        return (r) => (a(r) === null) !== neg;
      }
      case 'truthy': {
        if (e.operand.kind === 'lit' && typeof e.operand.value === 'string') {
          throw new QueryError(`A text value alone is not a condition: compare it, as in name = '${e.operand.value}'`, e.operand.pos);
        }
        const a = operand(e.operand);
        return (r) => {
          const v = a(r);
          if (v === null) return null;
          if (typeof v === 'boolean') return v;
          if (typeof v === 'number') return v !== 0;
          return boolFromString(v) === true;
        };
      }
    }
  };

  const root = build(ast);
  return { test: (r) => root(r) === true, unknown };
}
