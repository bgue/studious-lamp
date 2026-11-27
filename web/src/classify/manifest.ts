// The classification manifest: a high-level record of what was classified and reviewed, for a report or an audit. No DOM, no API keys.
//
//   format  xray-classification-manifest/1 (JSON), and a short Markdown summary of the same numbers
//   holds   model identity, schema, provider and model ids, thresholds, counts by source / code / confidence band, needs review,
//           the review actions, the from-to matrix of corrections, first and last decision time
//   option  `perElement`: a list of the corrections that people made (one row per element and changed part)
//   option  `reviewerNames`: the commit authors in the rows and a list of reviewers. Off by default; the numbers never carry a name.
//
// Never in it: API keys, tokens, endpoints, the reviewer's name unless asked for, or a picture of an element.

import { overallConfidence } from './review';
import type { FacetLike } from './facetWalk';
import type { ReviewCommit, ReviewFacetChange, ReviewChange, ReviewState } from './reviewLog';
import type { ClassifySettings } from './settings';
import type { ClassifyResult } from './types';

export const MANIFEST_SCHEMA = 'xray-classification-manifest/1';
export const MANIFEST_TOP_N = 10;
export const MANIFEST_MATRIX_LIMIT = 100;

/** The three kinds of origin that the manifest counts: a rule or a measurement, the decision model, a person. */
export type SourceFamily = 'rule' | 'model' | 'human';
export const SOURCE_FAMILIES: readonly SourceFamily[] = ['rule', 'model', 'human'];

/** The family of a result source (classification: rules, cache, model, manual, confirmed, corrected; facets: rule, model, geometry, ifc, manual, human, batch-learned). */
export function sourceFamily(source: string): SourceFamily {
  switch (source) {
    case 'model': case 'cache': case 'batch-learned': return 'model';
    case 'manual': case 'confirmed': case 'corrected': case 'human': return 'human';
    default: return 'rule'; // rules, rule, geometry, ifc
  }
}

export const CONFIDENCE_BANDS = ['<0.50', '0.50-0.74', '0.75-0.89', '>=0.90'] as const;
export type ConfidenceBand = (typeof CONFIDENCE_BANDS)[number];
export const bandOf = (c: number): ConfidenceBand => (c < 0.5 ? '<0.50' : c < 0.75 ? '0.50-0.74' : c < 0.9 ? '0.75-0.89' : '>=0.90');

export interface Tally {
  total: number;
  bySource: Record<SourceFamily, number>;
  /** The sources as they are in the results (rules, cache, model, manual, confirmed, corrected; or the facet sources). */
  bySourceDetail: Record<string, number>;
  /** The most frequent codes. */
  byCode: Array<{ code: string; count: number }>;
  byConfidenceBand: Array<{ band: ConfidenceBand; count: number }>;
  needsReview: number;
}

export interface ManifestActions {
  /** Decisions that stand: in commits that are not reversals and were not reverted. */
  confirmed: number;
  corrected: number;
  /** Corrections picked with key 2 (runner-up) or keys 3 to 9 (another numbered candidate). */
  runnerUp: number;
  candidate: number;
  unsure: number;
  /** Of the decisions above, the ones on facets. */
  facetConfirmed: number;
  facetCorrected: number;
  /** Commits that were reverted (a reversal commit is in the log). */
  commitsReverted: number;
  /** Skipped elements and undone pending items of the session that made the export: the log does not keep them. */
  skippedThisSession: number;
  undoneThisSession: number;
}

export interface MatrixCell {
  from: string;
  to: string;
  count: number;
}

export interface CorrectionRow {
  globalId: string;
  ifcClass: string;
  name: string;
  /** `classification` or `facet`. */
  kind: 'classification' | 'facet';
  /** `discipline`, `subDiscipline` or `division` for a classification; the facet id for a facet. */
  part: string;
  before: { code: string; confidence: number; source: string };
  after: { code: string };
  action: 'correct';
  via?: 'runner-up' | 'candidate';
  note?: string;
  time: string;
  /** Only with the reviewer-names option. */
  reviewer?: string;
}

export interface ClassificationManifest {
  schema: typeof MANIFEST_SCHEMA;
  exportedAt: string;
  model: { name: string; reviewFingerprint: string };
  classifier: {
    schema: { id: string; title: string; version: string | null; edition: string | null };
    provider: string;
    modelIds: string[];
    decisionMode: string | null;
    rulesMode: string;
    minConfidence: number;
    calibration: string;
    facetsOn: string[];
    concreteOn: boolean;
  };
  classification: Tally;
  facets: Tally & { byFacet: Record<string, Tally> };
  review: {
    commits: number;
    reviewers: number;
    firstDecision: string | null;
    lastDecision: string | null;
    actions: ManifestActions;
    matrix: { classification: MatrixCell[]; facets: Array<MatrixCell & { facet: string }>; truncated: boolean };
  };
  /** Present only with the per-element option. */
  corrections?: CorrectionRow[];
  /** Present only with the reviewer-names option. */
  reviewerNames?: string[];
  options: { perElement: boolean; reviewerNames: boolean; topN: number };
}

export interface ManifestInput {
  now?: Date;
  modelName: string;
  reviewFingerprint: string;
  schema: { id: string; title: string; version?: string; edition?: string };
  settings: ClassifySettings;
  /** The confidence limit in use (the setting, else the schema's). */
  minConfidence: number;
  facetsOn: readonly string[];
  concreteOn: boolean;
  /** The results as the walk shows them (committed ones win over runs). */
  results: Iterable<ClassifyResult>;
  facetResults: Iterable<{ globalId: string; result: FacetLike }>;
  commits: readonly ReviewCommit[];
  activity?: { skipped: number; undone: number };
  /** Name and IFC class of an element, for the per-element rows. */
  elementInfo?: (globalId: string) => { ifcClass: string; name: string } | undefined;
  perElement?: boolean;
  reviewerNames?: boolean;
  topN?: number;
}

/** Provider and model ids from the settings. Only these fields are read: an endpoint or a key can never get into the manifest. */
export function classifierOf(s: ClassifySettings): { provider: string; modelIds: string[]; decisionMode: string | null } {
  const o = s as unknown as Record<string, unknown>;
  const str = (k: string): string => (typeof o[k] === 'string' ? (o[k] as string) : '');
  const ids: string[] = [];
  switch (s.provider) {
    case 'jev': ids.push(str('model')); break;
    case 'd3': ids.push(str('d3Backend') === 'endpoint' ? str('d3Model') : str('d3Repo')); break;
    case 'webllm': {
      const mode = str('webllmMode');
      if (mode !== 'embed') ids.push(str('webllmModel'));
      if (mode === 'embed' || mode === 'hybrid') ids.push(str('webllmEmbedModel'));
      break;
    }
    case 'decision': ids.push(str('decisionMode') === 'embed' ? str('embedModel') : str('hfModel')); break;
    default: break;
  }
  return { provider: s.provider, modelIds: ids.filter(Boolean), decisionMode: s.provider === 'decision' ? str('decisionMode') || null : null };
}

function tally(items: Iterable<{ code: string; source: string; confidence: number; needsReview: boolean }>, topN: number): Tally {
  const bySource: Record<SourceFamily, number> = { rule: 0, model: 0, human: 0 };
  const detail: Record<string, number> = {};
  const codes = new Map<string, number>();
  const bands = new Map<ConfidenceBand, number>(CONFIDENCE_BANDS.map((b) => [b, 0]));
  let total = 0;
  let needs = 0;
  for (const it of items) {
    total++;
    bySource[sourceFamily(it.source)]++;
    detail[it.source] = (detail[it.source] ?? 0) + 1;
    codes.set(it.code, (codes.get(it.code) ?? 0) + 1);
    const b = bandOf(it.confidence);
    bands.set(b, (bands.get(b) ?? 0) + 1);
    if (it.needsReview) needs++;
  }
  const byCode = [...codes].sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1)).slice(0, topN).map(([code, count]) => ({ code, count }));
  return { total, bySource, bySourceDetail: Object.fromEntries(Object.entries(detail).sort((a, b) => (a[0] < b[0] ? -1 : 1))), byCode, byConfidenceBand: CONFIDENCE_BANDS.map((band) => ({ band, count: bands.get(band) ?? 0 })), needsReview: needs };
}

const codeOf = (s: ReviewState): string => `${s.discipline}${s.subDiscipline ? `/${s.subDiscipline}` : ''}${s.division ? `/${s.division}` : ''}`;

const PARTS = ['discipline', 'subDiscipline', 'division'] as const;

/** The code that a classification state has for a part, or '' when it has none. */
const partCode = (s: ReviewState, part: (typeof PARTS)[number]): string => (part === 'discipline' ? s.discipline : part === 'subDiscipline' ? s.subDiscipline ?? '' : s.division ?? '');

export function buildManifest(i: ManifestInput): ClassificationManifest {
  const topN = Math.max(1, Math.floor(i.topN ?? MANIFEST_TOP_N));
  const withNames = i.reviewerNames === true;
  const perElement = i.perElement === true;

  const results = [...i.results];
  const classification = tally(results.map((r) => ({ code: r.discipline.code, source: r.source, confidence: overallConfidence(r), needsReview: r.needsReview })), topN);

  const facetList = [...i.facetResults];
  const facetTally = tally(facetList.map((f) => ({ code: `${f.result.facet}:${f.result.code}`, source: f.result.source, confidence: f.result.confidence, needsReview: f.result.needsReview })), topN);
  const byFacet: Record<string, Tally> = {};
  const facetIds = [...new Set(facetList.map((f) => f.result.facet))].sort();
  for (const id of facetIds) byFacet[id] = tally(facetList.filter((f) => f.result.facet === id).map((f) => ({ code: f.result.code, source: f.result.source, confidence: f.result.confidence, needsReview: f.result.needsReview })), topN);

  // decisions that stand: commits that are not reversals and were not reverted
  const revertedIds = new Set(i.commits.filter((c) => c.reverts).map((c) => c.reverts as string));
  const standing = i.commits.filter((c) => !c.reverts && !revertedIds.has(c.id));
  const actions: ManifestActions = {
    confirmed: 0, corrected: 0, runnerUp: 0, candidate: 0, unsure: 0, facetConfirmed: 0, facetCorrected: 0,
    commitsReverted: i.commits.filter((c) => c.reverts).length,
    skippedThisSession: i.activity?.skipped ?? 0, undoneThisSession: i.activity?.undone ?? 0,
  };
  const classMatrix = new Map<string, number>();
  const facetMatrix = new Map<string, number>();
  const rows: CorrectionRow[] = [];
  const count = (c: ReviewChange | ReviewFacetChange, facet: boolean): void => {
    if (c.action === 'confirm') { actions.confirmed++; if (facet) actions.facetConfirmed++; }
    else { actions.corrected++; if (facet) actions.facetCorrected++; }
    if (c.via === 'runner-up') actions.runnerUp++;
    if (c.via === 'candidate') actions.candidate++;
    if (c.unsure) actions.unsure++;
  };
  const info = (g: string): { ifcClass: string; name: string } => i.elementInfo?.(g) ?? { ifcClass: '', name: '' };
  for (const c of standing) {
    for (const ch of c.changes) {
      count(ch, false);
      if (ch.action !== 'correct') continue;
      const key = `${codeOf(ch.before)}\u0000${codeOf(ch.after)}`;
      classMatrix.set(key, (classMatrix.get(key) ?? 0) + 1);
      if (!perElement) continue;
      for (const part of PARTS) {
        const b = partCode(ch.before, part);
        const a = partCode(ch.after, part);
        if (b === a) continue;
        rows.push({
          globalId: ch.globalId, ...info(ch.globalId), kind: 'classification', part,
          before: { code: b, confidence: ch.before.confidence, source: ch.before.source }, after: { code: a }, action: 'correct',
          ...(ch.via ? { via: ch.via } : {}), ...(ch.comment ? { note: ch.comment } : {}), time: c.time, ...(withNames ? { reviewer: c.author } : {}),
        });
      }
    }
    for (const ch of c.facetChanges ?? []) {
      count(ch, true);
      if (ch.action !== 'correct') continue;
      const key = `${ch.facet}\u0000${ch.before.code}\u0000${ch.after.code}`;
      facetMatrix.set(key, (facetMatrix.get(key) ?? 0) + 1);
      if (!perElement) continue;
      rows.push({
        globalId: ch.globalId, ...info(ch.globalId), kind: 'facet', part: ch.facet,
        before: { code: ch.before.code, confidence: ch.before.confidence, source: ch.before.source }, after: { code: ch.after.code }, action: 'correct',
        ...(ch.via ? { via: ch.via } : {}), ...(ch.comment ? { note: ch.comment } : {}), time: c.time, ...(withNames ? { reviewer: c.author } : {}),
      });
    }
  }
  const sortCells = <T extends MatrixCell>(cells: T[]): T[] => cells.sort((a, b) => b.count - a.count || (a.from < b.from ? -1 : a.from > b.from ? 1 : a.to < b.to ? -1 : a.to > b.to ? 1 : 0));
  const cm = sortCells([...classMatrix].map(([k, count]) => { const [from, to] = k.split('\u0000') as [string, string]; return { from, to, count }; }));
  const fm = sortCells([...facetMatrix].map(([k, count]) => { const [facet, from, to] = k.split('\u0000') as [string, string, string]; return { facet, from, to, count }; }));
  const times = standing.map((c) => c.time).sort();
  rows.sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : a.globalId < b.globalId ? -1 : a.globalId > b.globalId ? 1 : a.kind !== b.kind ? (a.kind === 'classification' ? -1 : 1) : a.part < b.part ? -1 : 1));
  const authors = [...new Set(i.commits.map((c) => c.author).filter(Boolean))].sort();
  const c = classifierOf(i.settings);

  return {
    schema: MANIFEST_SCHEMA,
    exportedAt: (i.now ?? new Date()).toISOString(),
    model: { name: i.modelName, reviewFingerprint: i.reviewFingerprint },
    classifier: {
      schema: { id: i.schema.id, title: i.schema.title, version: i.schema.version ?? null, edition: i.schema.edition ?? null },
      provider: c.provider, modelIds: c.modelIds, decisionMode: c.decisionMode,
      rulesMode: i.settings.rulesMode, minConfidence: i.minConfidence, calibration: i.settings.calibration,
      facetsOn: [...i.facetsOn], concreteOn: i.concreteOn,
    },
    classification,
    facets: { ...facetTally, byFacet },
    review: {
      commits: i.commits.length,
      reviewers: authors.length,
      firstDecision: times[0] ?? null,
      lastDecision: times[times.length - 1] ?? null,
      actions,
      matrix: { classification: cm.slice(0, MANIFEST_MATRIX_LIMIT), facets: fm.slice(0, MANIFEST_MATRIX_LIMIT), truncated: cm.length > MANIFEST_MATRIX_LIMIT || fm.length > MANIFEST_MATRIX_LIMIT },
    },
    ...(perElement ? { corrections: rows } : {}),
    ...(withNames ? { reviewerNames: authors } : {}),
    options: { perElement, reviewerNames: withNames, topN },
  };
}

export const manifestJson = (m: ClassificationManifest): string => JSON.stringify(m, null, 2);

/** A short Markdown summary of a manifest: the same numbers as the JSON, without the per-element list. */
export function manifestMarkdown(m: ClassificationManifest): string {
  const pct = (n: number, t: number): string => (t > 0 ? ` (${Math.round((n / t) * 100)}%)` : '');
  const line = (t: Tally): string => `${t.total} results: rule ${t.bySource.rule}, model ${t.bySource.model}, human ${t.bySource.human}; ${t.needsReview} need review`;
  const a = m.review.actions;
  const out: string[] = [];
  out.push(`# Classification manifest: ${m.model.name}`, '');
  out.push(`Format \`${m.schema}\`, exported ${m.exportedAt}. Review fingerprint \`${m.model.reviewFingerprint}\`.`, '');
  out.push('## Classifier', '');
  out.push(`- Schema: ${m.classifier.schema.title}${m.classifier.schema.version ? ` ${m.classifier.schema.version}` : ''}${m.classifier.schema.edition ? `, edition ${m.classifier.schema.edition}` : ''} (${m.classifier.schema.id})`);
  out.push(`- Provider: ${m.classifier.provider}${m.classifier.modelIds.length ? `, ${m.classifier.modelIds.join(', ')}` : ''}${m.classifier.decisionMode ? `, decision mode ${m.classifier.decisionMode}` : ''}`);
  out.push(`- Rules mode ${m.classifier.rulesMode}, confidence limit ${m.classifier.minConfidence}, calibration ${m.classifier.calibration}`);
  out.push(`- Facets on: ${m.classifier.facetsOn.length ? m.classifier.facetsOn.join(', ') : 'none'}${m.classifier.concreteOn ? ', concrete' : ''}`, '');
  out.push('## Classification', '', `- ${line(m.classification)}`);
  out.push(`- Top codes: ${m.classification.byCode.map((c) => `${c.code} ${c.count}`).join(', ') || 'none'}`);
  out.push(`- Confidence: ${m.classification.byConfidenceBand.map((b) => `${b.band} ${b.count}`).join(', ')}`, '');
  out.push('## Facets', '', `- ${line(m.facets)}`);
  for (const [id, t] of Object.entries(m.facets.byFacet)) out.push(`- ${id}: ${line(t)}`);
  out.push('', '## Review', '');
  out.push(`- ${m.review.commits} commits${m.review.firstDecision ? `, first decision ${m.review.firstDecision}, last ${m.review.lastDecision}` : ', no decisions yet'}`);
  const done = a.confirmed + a.corrected;
  out.push(`- Confirmed ${a.confirmed}${pct(a.confirmed, done)}, corrected ${a.corrected}${pct(a.corrected, done)} (runner-up ${a.runnerUp}, other candidate ${a.candidate}), unsure ${a.unsure}; facets: confirmed ${a.facetConfirmed}, corrected ${a.facetCorrected}`);
  out.push(`- Commits reverted ${a.commitsReverted}; this session: skipped ${a.skippedThisSession}, undone ${a.undoneThisSession}`);
  if (m.review.matrix.classification.length) {
    out.push('', '### Corrections, from to', '', '| From | To | Count |', '| --- | --- | ---: |');
    for (const c of m.review.matrix.classification.slice(0, 20)) out.push(`| ${c.from} | ${c.to} | ${c.count} |`);
  }
  if (m.review.matrix.facets.length) {
    out.push('', '### Facet corrections, from to', '', '| Facet | From | To | Count |', '| --- | --- | --- | ---: |');
    for (const c of m.review.matrix.facets.slice(0, 20)) out.push(`| ${c.facet} | ${c.from} | ${c.to} | ${c.count} |`);
  }
  if (m.corrections) out.push('', `The JSON file also lists ${m.corrections.length} corrections element by element.`);
  out.push('');
  return out.join('\n');
}
