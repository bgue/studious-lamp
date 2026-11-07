// Criteria queries over the elements of a model: a small SQL WHERE subset (see parser.ts for the grammar and
// compile.ts for the semantics). Used by criteria selection sets and the property context menu.

import type { ElementId, SceneModel } from '../types';
import { compile } from './compile';
import type { QueryTable } from './compile';
import { KEYWORDS, QueryError } from './lexer';
import { parseQuery } from './parser';
import type { Expr, Operand, Value } from './parser';
import { ModelTable, modelTable } from './table';
import type { ColumnKind } from './table';

export { QueryError, tokenize } from './lexer';
export { parseQuery, columnsOf } from './parser';
export type { Expr, Operand, Value, CmpOp } from './parser';
export { compile, compareValues, likeToRegExp } from './compile';
export type { Compiled, QueryTable, Accessor } from './compile';
export { ModelTable, modelTable, CORE_COLUMNS, coreColumn } from './table';
export type { ColumnInfo, ColumnKind } from './table';

/** Row indices of a table that match the query. Throws QueryError on a syntax error. */
export function filterRows(text: string, table: QueryTable): number[] {
  const c = compile(parseQuery(text), table);
  const out: number[] = [];
  for (let r = 0; r < table.size; r++) if (c.test(r)) out.push(r);
  return out;
}

export interface QueryResult {
  ids: ElementId[];
  /** Columns that no element has (they read as NULL). */
  unknown: string[];
  error: QueryError | null;
}

/** Element ids of the model that match the query. Never throws: a syntax error comes back in `error`. */
export function runQuery(model: SceneModel, text: string): QueryResult {
  const table = modelTable(model);
  try {
    const c = compile(parseQuery(text), table);
    const ids: ElementId[] = [];
    for (let r = 0; r < table.size; r++) if (c.test(r)) ids.push(table.idOf(r));
    return { ids, unknown: c.unknown, error: null };
  } catch (e) {
    if (e instanceof QueryError) return { ids: [], unknown: [], error: e };
    throw e;
  }
}

// ---------------------------------------------------------------- writing queries

const SIMPLE_IDENT = /^[A-Za-z_À-￿][A-Za-z0-9_À-￿]*(?:\.[A-Za-z0-9_À-￿]+)*$/;

/** A column name as query text: bare for core columns, double quoted for property keys and anything unusual. */
export function quoteIdent(name: string): string {
  if (SIMPLE_IDENT.test(name) && !name.includes('.') && !KEYWORDS.has(name.toUpperCase())) return name;
  return `"${name.replace(/"/g, '""')}"`;
}

/** A value as a query literal: 'text', 12.5, TRUE, FALSE or NULL. */
export function literal(v: Value): string {
  if (v === null) return 'NULL';
  if (typeof v === 'boolean') return v ? 'TRUE' : 'FALSE';
  if (typeof v === 'number') return Number.isFinite(v) ? String(v) : 'NULL';
  return `'${v.replace(/'/g, "''")}'`;
}

/** `col = value`, or `col IS NULL` for a NULL value. */
export function equalsQuery(column: string, v: Value): string {
  return v === null ? `${quoteIdent(column)} IS NULL` : `${quoteIdent(column)} = ${literal(v)}`;
}

// ---------------------------------------------------------------- row builder <-> query text

export const BUILDER_OPS = ['=', '!=', '<', '<=', '>', '>=', 'LIKE', 'NOT LIKE', 'IN', 'NOT IN', 'IS NULL', 'IS NOT NULL'] as const;
export type BuilderOp = (typeof BUILDER_OPS)[number];
export const NO_VALUE_OPS: ReadonlySet<BuilderOp> = new Set(['IS NULL', 'IS NOT NULL']);

export interface Condition {
  column: string;
  op: BuilderOp;
  /** The value as the person types it: no quotes; IN lists are comma separated. */
  value: string;
}

export interface ConditionList {
  join: 'AND' | 'OR';
  conditions: Condition[];
}

const NUM_TEXT = /^\s*-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?\s*$/;

/** Turn a typed value into a literal, using the kind of the column: numbers and TRUE/FALSE stay unquoted. */
export function typedLiteral(text: string, kind: ColumnKind): string {
  const t = text.trim();
  if (/^'.*'$/s.test(t) && t.length >= 2) return t; // already a literal
  const up = t.toUpperCase();
  if ((kind === 'boolean' || kind === 'mixed') && (up === 'TRUE' || up === 'FALSE')) return up;
  if (kind === 'boolean' && (up === 'YES' || up === 'NO')) return up === 'YES' ? 'TRUE' : 'FALSE';
  if (kind !== 'string' && NUM_TEXT.test(t)) return String(Number(t));
  return literal(t);
}

/** Query text of one builder row. */
export function conditionText(c: Condition, kind: ColumnKind): string {
  const col = quoteIdent(c.column);
  if (c.op === 'IS NULL' || c.op === 'IS NOT NULL') return `${col} ${c.op}`;
  if (c.op === 'IN' || c.op === 'NOT IN') {
    const items = c.value.split(',').map((s) => s.trim()).filter((s) => s.length > 0);
    return `${col} ${c.op} (${(items.length ? items : ['']).map((s) => typedLiteral(s, kind)).join(', ')})`;
  }
  if (c.op === 'LIKE' || c.op === 'NOT LIKE') return `${col} ${c.op} ${literal(c.value.trim())}`;
  return `${col} ${c.op} ${typedLiteral(c.value, kind)}`;
}

/** Query text of a builder row list. */
export function conditionsText(list: ConditionList, kindOf: (column: string) => ColumnKind): string {
  return list.conditions
    .filter((c) => c.column.trim().length > 0)
    .map((c) => conditionText(c, kindOf(c.column)))
    .join(` ${list.join} `);
}

const valueText = (v: Value): string => (v === null ? '' : typeof v === 'boolean' ? (v ? 'TRUE' : 'FALSE') : String(v));

function rowOf(e: Expr): Condition | null {
  const colOf = (o: Operand): string | null => (o.kind === 'col' ? o.name : null);
  const litOf = (o: Operand): Value | undefined => (o.kind === 'lit' ? o.value : undefined);
  switch (e.kind) {
    case 'cmp': {
      const col = colOf(e.left);
      const v = litOf(e.right);
      if (col === null || v === undefined || v === null) return null;
      return { column: col, op: e.op, value: valueText(v) };
    }
    case 'like': {
      const col = colOf(e.left);
      const v = litOf(e.pattern);
      if (col === null || typeof v !== 'string') return null;
      return { column: col, op: e.neg ? 'NOT LIKE' : 'LIKE', value: v };
    }
    case 'in': {
      const col = colOf(e.left);
      const vs = e.list.map(litOf);
      if (col === null || vs.some((v) => v === undefined || v === null || (typeof v === 'string' && v.includes(',')))) return null;
      return { column: col, op: e.neg ? 'NOT IN' : 'IN', value: vs.map((v) => valueText(v!)).join(', ') };
    }
    case 'isnull': {
      const col = colOf(e.left);
      return col === null ? null : { column: col, op: e.neg ? 'IS NOT NULL' : 'IS NULL', value: '' };
    }
    case 'truthy': {
      const col = colOf(e.operand);
      return col === null ? null : { column: col, op: '=', value: 'TRUE' };
    }
    default:
      return null;
  }
}

/**
 * Builder rows for a query, when the query is a flat AND or OR of simple conditions (column, operator, literal).
 * Null when the builder cannot show it (nested groups, NOT, BETWEEN, column-to-column comparisons, syntax errors).
 */
export function toConditions(text: string): ConditionList | null {
  let ast: Expr;
  try {
    ast = parseQuery(text);
  } catch {
    return null;
  }
  const items = ast.kind === 'and' || ast.kind === 'or' ? ast.items : [ast];
  const conditions: Condition[] = [];
  for (const it of items) {
    const c = rowOf(it);
    if (!c) return null;
    conditions.push(c);
  }
  return { join: ast.kind === 'or' ? 'OR' : 'AND', conditions };
}

/** Build a ModelTable without the cache (tests and benchmarks). */
export function freshTable(model: SceneModel): ModelTable {
  return new ModelTable(model);
}

export { parseAggregate, looksLikeAggregate, isExplicitAggregate, resolveQuantity, aggregate, runAggregate, summaryLines, formatNumber, formatValue, classNoun, toNumber, unitFor } from './aggregate';
export type { AggQuery, AggSpec, AggFn, AggResult, GroupResult, QuantitySummary, QtyPlan, GeoEstimator, AggOptions, SkippedRow } from './aggregate';
export { makeGeoEstimator, meshMeasure } from './geoEstimate';
