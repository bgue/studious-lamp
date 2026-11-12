// Results of a classification run, manual overrides (which win over everything else and are kept per model), and export.

import type { KeyValueStorage } from './cache';
import { computeNeedsReview, overallConfidence, topTwo } from './review';
import { RULE_FINAL } from './rules';
import { divisionTitle, findDiscipline, findSub } from './schema';
import { csvCell } from '../tools/csv';
import type { ClassificationSchema, ClassifyResult, ClassifyStats } from './types';

export const MANUAL_PREFIX = 'xray.classify.manual.v1.';
export const manualKey = (modelName: string, schemaHash: string): string => `${MANUAL_PREFIX}${modelName}|${schemaHash}`;

/** A change that a person makes by hand: codes only. `null` clears the sub-discipline or the division. */
export interface ManualPartial {
  discipline?: string;
  subDiscipline?: string | null;
  masterformat?: string | null;
}

/** Build a manual result from codes. Throws an Error with a plain message for a code that is not in the schema. */
export function makeManual(schema: ClassificationSchema, id: string, p: ManualPartial, prior?: ClassifyResult): ClassifyResult {
  const d = findDiscipline(schema, p.discipline ?? prior?.discipline.code ?? '');
  if (!d) throw new Error(`The discipline "${p.discipline ?? prior?.discipline.code ?? ''}" is not in the schema. Use one of: ${schema.disciplines.map((x) => x.code).join(', ')}.`);
  let sub = null as ClassifyResult['subDiscipline'];
  const wantSub = p.subDiscipline !== undefined ? p.subDiscipline : prior && prior.discipline.code === d.code ? prior.subDiscipline?.code ?? null : null;
  if (wantSub) {
    const s = findSub(d, wantSub);
    if (!s) throw new Error(`The sub-discipline "${wantSub}" is not in the schema for ${d.code}. Use one of: ${d.subDisciplines.map((x) => x.code).join(', ') || 'none'}.`);
    sub = { code: s.code, label: s.label, confidence: 1, probabilities: { [s.code]: 1 } };
  }
  let mf = null as ClassifyResult['masterformat'];
  const wantMf = p.masterformat !== undefined ? p.masterformat : prior?.masterformat?.division ?? null;
  if (wantMf) {
    const title = divisionTitle(schema, wantMf);
    if (!title) throw new Error(`The division "${wantMf}" is not in the schema.`);
    mf = { division: wantMf, title, confidence: 1, probabilities: { [wantMf]: 1 } };
  }
  return {
    id,
    discipline: { code: d.code, label: d.label, confidence: 1, probabilities: { [d.code]: 1 } },
    subDiscipline: sub,
    masterformat: mf,
    buildingElement: mf ? 1 : prior?.buildingElement ?? 1,
    source: 'manual',
    needsReview: false,
    rationale: 'set by hand',
  };
}

/** Do two results carry the same discipline, sub-discipline and division? */
export function sameCodes(a: ClassifyResult, b: ClassifyResult): boolean {
  return a.discipline.code === b.discipline.code && (a.subDiscipline?.code ?? '') === (b.subDiscipline?.code ?? '') && (a.masterformat?.division ?? '') === (b.masterformat?.division ?? '');
}

/** The results of the model on screen, by element id (GlobalId), with the manual overrides kept in storage. */
export class ResultStore {
  private readonly map = new Map<string, ClassifyResult>();
  private readonly manualMap = new Map<string, ClassifyResult>();
  /** Results that a person committed in the review walk (source confirmed or corrected). They win over every computed result and over a manual one. */
  private committedMap = new Map<string, ClassifyResult>();
  /** For a committed element: the result of the latest run when it differs from the committed codes ("the model now disagrees"). */
  private readonly disagreeMap = new Map<string, ClassifyResult>();
  /** The latest computed result of a committed element: it comes back when the commit is reverted. */
  private readonly shadowMap = new Map<string, ClassifyResult>();

  constructor(private readonly storage: KeyValueStorage | null = null, private readonly key = '') {
    try {
      const t = storage?.getItem(key);
      if (t) for (const r of JSON.parse(t) as ClassifyResult[]) if (r && r.source === 'manual') this.manualMap.set(r.id, r);
    } catch {
      /* ignore a broken entry */
    }
    for (const [id, r] of this.manualMap) this.map.set(id, r);
  }

  /** The manual overrides only (the pipeline skips these; a committed element is still computed, to find out whether the model disagrees). */
  get manual(): ReadonlyMap<string, ClassifyResult> {
    return this.manualMap;
  }
  get committed(): ReadonlyMap<string, ClassifyResult> {
    return this.committedMap;
  }
  /** Committed elements where the latest run differs from the committed value: id -> what the run says. */
  get disagreements(): ReadonlyMap<string, ClassifyResult> {
    return this.disagreeMap;
  }
  /**
   * Replace the committed results (the effective state of the review log). A committed result is the element's result from now on and a
   * run never replaces it. An element that is no longer committed gets its manual result back, or no result until it is classified again.
   */
  setCommitted(next: ReadonlyMap<string, ClassifyResult>): void {
    for (const id of this.committedMap.keys()) {
      if (next.has(id)) continue;
      const back = this.manualMap.get(id) ?? this.shadowMap.get(id);
      if (back) this.map.set(id, back);
      else this.map.delete(id);
      this.disagreeMap.delete(id);
      this.shadowMap.delete(id);
    }
    this.committedMap = new Map(next);
    for (const [id, r] of next) {
      const cur = this.map.get(id);
      if (cur && cur.source !== 'manual' && cur.source !== 'confirmed' && cur.source !== 'corrected') this.shadowMap.set(id, cur);
      this.map.set(id, r);
    }
  }
  get(id: string): ClassifyResult | undefined {
    return this.map.get(id);
  }
  all(): ClassifyResult[] {
    return [...this.map.values()];
  }
  get size(): number {
    return this.map.size;
  }
  /** Add computed results. A manual result is never replaced. */
  merge(results: readonly ClassifyResult[]): void {
    for (const r of results) {
      const c = this.committedMap.get(r.id);
      if (c) {
        this.shadowMap.set(r.id, r);
        if (sameCodes(c, r)) this.disagreeMap.delete(r.id);
        else this.disagreeMap.set(r.id, r);
        continue;
      }
      if (!this.manualMap.has(r.id)) this.map.set(r.id, r);
    }
  }
  setManual(r: ClassifyResult): void {
    this.manualMap.set(r.id, r);
    if (!this.committedMap.has(r.id)) this.map.set(r.id, r);
    this.persist();
  }
  /** Drop one manual override (the computed result is gone with it: classify again). */
  removeManual(id: string): void {
    if (this.manualMap.delete(id) && !this.committedMap.has(id)) this.map.delete(id);
    this.persist();
  }
  /** Drop every computed result. Manual overrides stay unless `manual` is true. */
  clear(manual = false): void {
    this.map.clear();
    this.disagreeMap.clear();
    this.shadowMap.clear();
    if (manual) {
      this.manualMap.clear();
      this.persist();
    } else for (const [id, r] of this.manualMap) this.map.set(id, r);
    for (const [id, r] of this.committedMap) this.map.set(id, r); // a committed result stays, like a manual one
  }
  /** Recompute the review flag after the confidence limit changed. */
  rereview(minConfidence: number, minMargin?: number): void {
    for (const [id, r] of this.map) {
      if (r.source === 'manual' || r.source === 'confirmed' || r.source === 'corrected') continue;
      const guess = r.source === 'rules' && r.discipline.confidence < RULE_FINAL; // a weak rule used as a fallback
      this.map.set(id, { ...r, needsReview: guess || computeNeedsReview(r, minConfidence, minMargin) });
    }
  }
  private persist(): void {
    try {
      this.storage?.setItem(this.key, JSON.stringify([...this.manualMap.values()]));
    } catch {
      /* ignore */
    }
  }
}

// ---------------------------------------------------------------- export

const fmt = (n: number): string => (Math.round(n * 1000) / 1000).toString();
const top2Text = (p: Record<string, number>): string => topTwo(p).map(([k, v]) => `${k} ${fmt(v)}`).join('; ');

export const CSV_HEADER = [
  'GlobalId', 'Discipline', 'DisciplineLabel', 'DisciplineConfidence', 'DisciplineTop2', 'SubDiscipline', 'SubDisciplineConfidence',
  'MasterFormatDivision', 'MasterFormatTitle', 'MasterFormatConfidence', 'BuildingElement', 'Confidence', 'Source', 'Model', 'NeedsReview', 'Rationale', 'ConfirmedBy', 'ConfirmedAt', 'CommitId', 'Unsure',
] as const;

export function toCsvRows(results: readonly ClassifyResult[]): Array<Array<string | number | boolean>> {
  return results.map((r) => [
    r.id, r.discipline.code, r.discipline.label, fmt(r.discipline.confidence), top2Text(r.discipline.probabilities),
    r.subDiscipline?.code ?? '', r.subDiscipline ? fmt(r.subDiscipline.confidence) : '',
    r.masterformat?.division ?? '', r.masterformat?.title ?? '', r.masterformat ? fmt(r.masterformat.confidence) : '',
    fmt(r.buildingElement), fmt(overallConfidence(r)), r.source, r.model ?? '', r.needsReview, r.rationale ?? '', r.confirmedBy ?? '', r.confirmedAt ?? '', r.commitId ?? '', r.unsure === true,
  ]);
}

export function exportCsv(results: readonly ClassifyResult[]): string {
  return [CSV_HEADER.join(','), ...toCsvRows(results).map((row) => row.map(csvCell).join(','))].join('\r\n') + '\r\n';
}

export const EXPORT_SCHEMA = 'xray-classification/1';

export function exportJson(results: readonly ClassifyResult[], schema: ClassificationSchema, stats: ClassifyStats | null, modelName: string): string {
  return JSON.stringify(
    {
      schema: EXPORT_SCHEMA,
      classificationSchema: { title: schema.title, version: schema.version ?? null, placeholder: schema.placeholder === true },
      model: modelName,
      count: results.length,
      stats,
      results,
    },
    null,
    2,
  );
}
