// Quantity summaries in the search bar: `count where ...`, `sum length where ...`, `... by storey`. The parsing and the
// arithmetic are in src/query/aggregate.ts; this file adds what needs the viewer: the visible set, the mesh estimates, the
// console report and the answer for scripts (`window.__xraySearch.summarize`). No DOM.

import type { ViewerApp } from '../app';
import { QueryError, formatNumber, formatValue, isExplicitAggregate, looksLikeAggregate, makeGeoEstimator, modelTable, parseAggregate, resolveQuantity, runAggregate, summaryLines } from '../query';
import type { AggResult, GeoEstimator, QuantitySummary } from '../query';
import { FLAG_HIDDEN } from '../types';
import type { SceneModel } from '../types';
import { plainError } from './queryMode';

export interface SummaryOutcome {
  summary: QuantitySummary | null;
  /** Plain-language error with the position hint, or null. */
  error: string | null;
  errorPos: number;
}

/**
 * Does the box text ask for a summary? `count where`, `... by`, a comma list and `sum <quantity>` with a quantity this model
 * has. A bare `max height` that names nothing in the model stays a text search.
 */
export function detectSummary(input: string, model: SceneModel): boolean {
  if (!looksLikeAggregate(input)) return false;
  if (isExplicitAggregate(input) || /^\s*\??\s*count\s*$/i.test(input)) return true;
  try {
    const q = parseAggregate(input);
    return q.aggs.every((a) => a.qty === null || resolveQuantity(modelTable(model), a.qty) !== null);
  } catch {
    return false;
  }
}

export class QuantitySearch {
  private geo: GeoEstimator | null = null;
  private geoFor: unknown = null;

  constructor(private readonly app: ViewerApp) {}

  private estimator(): GeoEstimator | null {
    const loaded = this.app.loaded;
    if (!loaded) return null;
    if (this.geoFor === loaded) return this.geo;
    this.geoFor = loaded;
    const g = loaded.geometry;
    const els = loaded.model.elements;
    this.geo = makeGeoEstimator({
      position: g.geometry.getAttribute('position').array,
      index: g.geometry.getIndex()!.array,
      ranges: g.ranges,
      closed: this.app.renderer.closedFlags,
      bounds: (id) => els[id]!.bounds,
    });
    return this.geo;
  }

  private visible(): (id: number) => boolean {
    const st = this.app.renderer.state as { flags?: ArrayLike<number>; alpha?: ArrayLike<number> } | undefined;
    const flags = st?.flags;
    const alpha = st?.alpha;
    if (!flags) return () => true;
    return (id) => ((flags[id] ?? 0) & FLAG_HIDDEN) === 0 && (alpha?.[id] ?? 1) >= 0;
  }

  /** Run a summary. Never throws: a syntax error or an unknown quantity comes back in `error`. */
  run(text: string): SummaryOutcome {
    const model = this.app.controller.model;
    try {
      const s = runAggregate(modelTable(model), text, { geo: this.estimator(), visible: this.visible(), lengthUnit: model.units });
      return { summary: s, error: null, errorPos: -1 };
    } catch (e) {
      if (e instanceof QueryError) return { summary: null, error: plainError(e), errorPos: e.pos };
      throw e;
    }
  }

  /** What `window.__xraySearch.summarize(text)` returns. Throws on an error, so a script cannot miss it. */
  summarize(text: string): SummaryApi {
    const o = this.run(text);
    if (!o.summary) throw new Error(o.error ?? 'The summary failed.');
    return toApi(o.summary);
  }
}

// ---------------------------------------------------------------------------------------------------- rows

export interface SummaryRow {
  id: number;
  globalId: string;
  name: string;
  class: string;
  storey: string;
  group: string | null;
  /** Value per quantity label (null: none). */
  values: Record<string, number | null>;
  /** Source per quantity label: the property key, `estimated` or `none`. */
  sources: Record<string, string>;
}

/** The per-element rows of a summary (all of them, or the first `limit`). */
export function summaryRows(s: QuantitySummary, limit = Infinity): SummaryRow[] {
  const out: SummaryRow[] = [];
  const n = Math.min(s.rows.length, limit);
  for (let i = 0; i < n; i++) {
    const el = s.table.elementAt(s.rows[i]!);
    const values: Record<string, number | null> = {};
    const sources: Record<string, string> = {};
    for (const q of s.qtys) {
      const v = q.vals[i]!;
      const c = q.src[i]!;
      values[q.plan.label] = v === v ? v : null;
      sources[q.plan.label] = c >= 0 ? q.keys[c] ?? 'property' : c === -1 ? 'estimated' : 'none';
    }
    out.push({ id: el.id, globalId: el.globalId, name: el.name ?? '', class: el.ifcClass, storey: s.table.storeyOf(s.rows[i]!) ?? '', group: s.groupBy ? s.groupKeys[s.groupOf[i]!]! : null, values, sources });
  }
  return out;
}

export interface SummaryApi {
  rows: SummaryRow[];
  /** Value of the first aggregate (the count for `count`). */
  total: number | null;
  /** Every aggregate over all matched elements. */
  aggs: AggResult[];
  groups: Array<{ key: string; count: number; total: number | null; aggs: AggResult[] }> | null;
  skipped: Array<{ id: number; globalId: string; name: string; qty: string; reason: string }>;
  skippedCount: number;
  estimated: number;
  unit: string;
  matched: number;
  lines: string[];
  ms: number;
}

export function toApi(s: QuantitySummary): SummaryApi {
  return {
    rows: summaryRows(s),
    total: s.aggs[0]?.value ?? null,
    aggs: s.aggs,
    groups: s.groups ? s.groups.map((g) => ({ key: g.key, count: g.count, total: g.aggs[0]?.value ?? null, aggs: g.aggs })) : null,
    skipped: s.skipped,
    skippedCount: s.skippedCount,
    estimated: s.estimated,
    unit: s.unit,
    matched: s.matched,
    lines: summaryLines(s),
    ms: s.ms,
  };
}

// ---------------------------------------------------------------------------------------------------- console

const TABLE_CAP = 500;
const SKIP_CAP = 200;

/** The details of a summary on the browser console: one collapsed group with the table, the group subtotals and the skipped. */
export function reportToConsole(s: QuantitySummary, out: Pick<Console, 'groupCollapsed' | 'groupEnd' | 'table' | 'log' | 'info'> = console): void {
  const lines = summaryLines(s);
  out.groupCollapsed(`[X-ray] ${s.text.trim()} → ${lines[0]} (${s.ms.toFixed(1)} ms)`);
  try {
    for (const a of s.aggs) {
      if (a.fn === 'count') continue;
      out.log(`${a.fn} ${a.label}: ${formatValue(a.value, a.unit)} from ${a.n} of ${s.matched} elements, ${a.estimated} estimated, ${a.skipped} skipped`);
    }
    if (s.unknown.length > 0) out.log(`No element has a property named ${s.unknown.map((u) => `"${u}"`).join(', ')}. It reads as empty.`);
    const rows = summaryRows(s, TABLE_CAP).map((r) => {
      const row: Record<string, string | number | null> = { GlobalId: r.globalId, Name: r.name, Class: r.class, Storey: r.storey };
      if (r.group !== null) row[s.groupBy!] = r.group;
      for (const q of s.qtys) {
        row[q.plan.label] = r.values[q.plan.label] === null ? null : Number(r.values[q.plan.label]!.toPrecision(6));
        row[`${q.plan.label} source`] = r.sources[q.plan.label]!;
      }
      return row;
    });
    if (rows.length > 0) {
      out.table(rows);
      if (s.matched > rows.length) out.log(`${s.matched - rows.length} more elements not shown in the table. window.__xraySearch.summarize(text) returns all rows.`);
    }
    if (s.groups) {
      out.log(`Subtotals by ${s.groupBy}:`);
      out.table(
        s.groups.map((g) => {
          const row: Record<string, string | number | null> = { [s.groupBy!]: g.key, elements: g.count };
          for (const a of g.aggs) {
            if (a.fn === 'count') continue;
            row[`${a.fn} ${a.label}${a.unit ? ` (${a.unit})` : ''}`] = a.value === null ? null : Number(a.value.toPrecision(6));
            if (a.estimated > 0) row[`${a.fn} ${a.label} est.`] = a.estimated;
          }
          return row;
        }),
      );
    }
    if (s.skippedCount > 0) {
      out.log(`Skipped ${s.skippedCount} element${s.skippedCount === 1 ? '' : 's'}, each with the reason:`);
      out.table(s.skipped.slice(0, SKIP_CAP).map((k) => ({ GlobalId: k.globalId, Name: k.name, Quantity: k.qty, Reason: k.reason })));
      if (s.skippedCount > SKIP_CAP) out.log(`${s.skippedCount - SKIP_CAP} more skipped elements not listed.`);
    }
    out.info(`Total ${formatNumber(s.matched)} elements summarised in ${s.ms.toFixed(1)} ms.`);
  } finally {
    out.groupEnd();
  }
}
