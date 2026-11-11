// Types of the classification API. No DOM: this folder runs in Node as well as in the browser.

export type GlobalId = string;
export type PsetValue = string | number | boolean | null;
/** Property sets as nested records: pset name -> property name -> value. */
export type PsetRecord = Record<string, Record<string, PsetValue>>;

export interface HierarchyNode {
  ifcClass: string;
  name: string;
  globalId: string;
}

export interface RelatedElement {
  ifcClass: string;
  name: string;
  psets: PsetRecord;
}

/** What the pipeline knows about one element. */
export interface ClassifyInput {
  id: GlobalId;
  ifcClass: string;
  name: string;
  /** The property sets of the element (Attr.*, Pset_*, and so on). */
  psets: PsetRecord;
  /** Quantity sets (Qto_*, BaseQuantities). Optional. */
  quantities?: PsetRecord;
  /**
   * Position in the spatial hierarchy: project, site, building, storey, space or assembly, outermost first.
   * `buildingContext` states whether the element belongs to a building (true) or to infrastructure (false).
   */
  hierarchy?: { path: HierarchyNode[]; parents?: RelatedElement[]; buildingContext?: boolean };
  /** The type object of the element. */
  type?: RelatedElement;
  /** Names of the systems (IfcSystem) the element belongs to. */
  systems?: string[];
  material?: string;
  /**
   * True when the model this element belongs to is a process facility (see `processEvidenceOf` in rules.ts): process equipment, line numbers
   * and process services. Set by buildInput for the whole model; the rules then read steam, condensate and cooling water piping as utility
   * piping (PIP/UTL) and a pump, vessel or exchanger as process equipment. Absent: the model is not known to be a process facility.
   */
  processContext?: boolean;
}

export type ResultSource = 'rules' | 'cache' | 'model' | 'manual';

export interface CodeLabel {
  code: string;
  label: string;
}

/** A decided code with its confidence and the probability of every option that the decision model returned. */
export interface ChoiceResult extends CodeLabel {
  confidence: number;
  probabilities: Record<string, number>;
}

export interface MasterformatResult {
  division: string;
  title: string;
  confidence: number;
  probabilities: Record<string, number>;
  /** A section number such as "23 31 13". Set by rules only. */
  section?: string;
}

export interface ClassifyResult {
  id: GlobalId;
  discipline: ChoiceResult;
  subDiscipline: ChoiceResult | null;
  /** Null when the element is not part of a building, or when the schema has no division for it. */
  masterformat: MasterformatResult | null;
  /** P(this element is part of a building), 0 to 1. */
  buildingElement: number;
  source: ResultSource;
  /** The model id that the decision model returned (source 'model', and 'cache' filled by a model). */
  model?: string;
  /** True when a confidence is below the limit, a top-2 margin is small, or the answer failed validation. */
  needsReview: boolean;
  /** Why, for rules only. */
  rationale?: string;
  /** The signature that the decision came from (source 'rules' has none). */
  signature?: string;
}

// ---------------------------------------------------------------- target schema

export interface SchemaSubDiscipline {
  code: string;
  label: string;
  /** Short text that becomes the criteria text of the decision model. */
  description: string;
  /** Code that the built-in rules use for this entry, when it differs from `code`. */
  rulesKey?: string;
}
export interface SchemaDiscipline {
  code: string;
  label: string;
  description: string;
  rulesKey?: string;
  /** Free text: where the code comes from ("throughline", "added", "company", "project"). */
  origin?: string;
  /** Throughline `CodeValue.crosswalk`: the company code that a project-added value maps to. */
  crosswalk?: string;
  /** Throughline `CodeValue.meaning`: an IRI that says what the value means. */
  meaning?: string;
  /** Throughline `CodeValue.sort_order`. */
  sortOrder?: number;
  subDisciplines: SchemaSubDiscipline[];
}
export interface SchemaDivision {
  division: string;
  title: string;
  description: string;
}
export interface SchemaPropertyNames {
  discipline: string;
  subDiscipline: string;
  masterformatDivision: string;
  masterformatTitle: string;
  masterformatSection: string;
  confidence: string;
  source: string;
  model: string;
  needsReview: string;
}

/** `xray-classification-schema/1`: the controlled output properties and their code lists. */
export interface ClassificationSchema {
  schema: 'xray-classification-schema/1';
  title: string;
  version?: string;
  /** True for a schema that must be replaced (shown in the UI). The shipped default is Throughline-aligned and has none. */
  placeholder?: boolean;
  /** Throughline: the code list that `disciplines` is (`Discipline`). */
  codeList?: string;
  /** Throughline: the standards edition that supplied the list, for example `co.acme.standards@1.0.0`. */
  edition?: string;
  notice?: string;
  /** Name of the property set that results are written under. */
  psetName: string;
  /** Results below this confidence need review. 0 to 1. */
  minConfidence: number;
  properties: Partial<SchemaPropertyNames>;
  /** Discipline code for elements that no rule and no model could place. Must be in `disciplines`. */
  fallbackDiscipline?: string;
  fallbackSubDiscipline?: string;
  disciplines: SchemaDiscipline[];
  masterformat: { edition?: string; note?: string; appliesTo?: 'building' | 'all'; divisions: SchemaDivision[] };
}

// ---------------------------------------------------------------- decision model contract (the Jev shape)
// The question and answer types, and every field name of the Jev wire format, live in jevAdapter.ts.

export type { Answer, Answers, ChoiceAnswer, ChoiceQuestion, JsonObject, JsonValue, NoulAnswer, NoulQuestion, Question, Questions, ScoreAnswer, ScoreQuestion } from './jevAdapter';
import type { Answers, JsonObject, Questions } from './jevAdapter';

/** What a request may carry besides the state and the questions. */
export interface DecideExtra {
  /** Base64 data URLs of pictures of the element. Only a provider that reads images uses them. */
  images?: readonly string[];
}

export interface DecisionModel {
  /** Provider id, for messages: 'jev', 'd3', 'webllm', 'mock'. */
  readonly provider: string;
  decide(state: JsonObject, questions: Questions, signal: AbortSignal, extra?: DecideExtra): Promise<Answers>;
}

/** An error from a provider. `status` is the HTTP status when there is one. */
export class ProviderError extends Error {
  constructor(message: string, readonly status?: number, readonly retryAfterMs?: number, readonly retryable = false) {
    super(message);
    this.name = 'ProviderError';
  }
}

export interface ProgressInfo {
  phase: 'rules' | 'cache' | 'model' | 'done';
  total: number;
  done: number;
  bySource: Record<ResultSource, number>;
  calls: number;
  callsPlanned: number;
}

export interface ClassifyStats {
  total: number;
  bySource: Record<ResultSource, number>;
  /** Requests to the decision model that were sent (retries after 429 and 5xx not counted). */
  calls: number;
  /** Distinct signatures that went to the decision model. */
  signatures: number;
  needsReview: number;
  /** Elements with no result (the model failed and no rule gave a guess). */
  failed: number;
  aborted: boolean;
  errors: string[];
  /** Models that answered, with the number of answers of each. */
  models: Record<string, number>;
  usage: { input_tokens: number; output_tokens: number };
}
