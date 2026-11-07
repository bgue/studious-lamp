// Query mode of the search bar: a WHERE expression typed into the box runs through the criteria query engine
// (src/query) and shows the match count live. Pure, no DOM.

import { QueryError, runQuery } from '../query';
import type { ElementId, SceneModel } from '../types';

export type QueryDetect = { mode: 'text' } | { mode: 'query'; expr: string; forced: boolean };

// A column (bare or "quoted") followed by a comparison operator.
const COMPARE = /(?:^|[\s(])(?:"[^"]+"|[A-Za-z_][\w.]*)\s*(?:=|!=|<>|<=|>=|<|>)/;
const KEYWORD_FORMS = [
  /(?:^|[\s(])(?:"[^"]+"|[A-Za-z_][\w.]*)\s+(?:not\s+)?like\b/i,
  /(?:^|[\s(])(?:"[^"]+"|[A-Za-z_][\w.]*)\s+(?:not\s+)?in\s*\(/i,
  /(?:^|[\s(])(?:"[^"]+"|[A-Za-z_][\w.]*)\s+is\s+(?:not\s+)?null\b/i,
  /(?:^|[\s(])(?:"[^"]+"|[A-Za-z_][\w.]*)\s+(?:not\s+)?between\b/i,
];

/**
 * Decide whether the input is a query. `where <expr>` and `? <expr>` always are (`forced`). Other input is a query when
 * it looks like a condition: a column and a comparison operator, or LIKE, IN, IS NULL or BETWEEN after a column.
 */
export function detectQuery(input: string): QueryDetect {
  const text = input.trim();
  const w = /^where(?:\s+|$)/i.exec(text);
  if (w) return { mode: 'query', expr: text.slice(w[0].length), forced: true };
  if (text.startsWith('?')) return { mode: 'query', expr: text.slice(1).trim(), forced: true };
  if (COMPARE.test(text) || KEYWORD_FORMS.some((r) => r.test(text))) return { mode: 'query', expr: text, forced: false };
  return { mode: 'text' };
}

export interface LiveQuery {
  ids: ElementId[];
  count: number;
  /** Plain-language error, or null. */
  error: string | null;
  /** Character offset of the error in the expression, or -1. */
  errorPos: number;
  /** Names that no element has as a column. */
  unknown: string[];
  ms: number;
}

/** Plain-language form of an engine error: the engine's own text, with the position as a hint. */
export function plainError(e: QueryError): string {
  const msg = e.bare.replace(/\s+/g, ' ').trim();
  return `${msg}. Check the text around character ${e.pos + 1}.`;
}

/** Run an expression against the model. Never throws. An empty expression gives an explanatory error-free result. */
export function runLive(model: SceneModel, expr: string): LiveQuery {
  const t0 = performance.now();
  if (expr.trim() === '') return { ids: [], count: 0, error: null, errorPos: -1, unknown: [], ms: 0 };
  const r = runQuery(model, expr);
  const ms = performance.now() - t0;
  if (r.error) return { ids: [], count: 0, error: plainError(r.error), errorPos: r.error.pos, unknown: [], ms };
  return { ids: r.ids, count: r.ids.length, error: null, errorPos: -1, unknown: r.unknown, ms };
}
