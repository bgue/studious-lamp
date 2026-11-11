// Classification of BIM elements by discipline, sub-discipline and CSI MasterFormat division with a decision model.
// Node-usable: no DOM. Typical use in Node:
//
//   import { classifyInputs, defaultSchema, createJevProvider } from './classify';
//   const { results, stats } = await classifyInputs(inputs, { schema: defaultSchema(), provider: createJevProvider({ ... }) });

export { classifyInputs, decodeAnswers, estimateCalls, subOfTop, subOfTop2WhenUnsure, SUB_STRATEGIES } from './pipeline';
export type { CallEstimate, ClassifyRun, ClassifyRunOptions, SubDisciplineStrategy } from './pipeline';
export { buildInput, buildInputs, splitProps } from './build';
export { buildState, signatureOf, nameStem, DEFAULT_MAX_STATE_BYTES } from './state';
export { mainQuestions, subQuestions } from './questions';
export { classByRules, isBuildingContext, isProcessContext, isProcessModel, processEvidenceOf, resolveRule, RULE_FINAL } from './rules';
export { defaultSchema, parseSchema, propertyNames, schemaHash, DEFAULT_MIN_CONFIDENCE, SCHEMA_ID } from './schema';
export { MemoryCache, StorageCache, cacheKey } from './cache';
export type { CachedDecision, KeyValueStorage, SignatureCache } from './cache';
export { computeNeedsReview, overallConfidence, topMargin, topTwo, DEFAULT_MIN_MARGIN } from './review';
export { ResultStore, makeManual, exportCsv, exportJson, CSV_HEADER } from './results';
export { createJevProvider, redact } from './providers/jev';
export { createMockProvider } from './providers/mock';
export { createWebLlmProvider, detectWebGpu, WEBLLM_MODELS, WEBLLM_EMBED_MODELS, WEBLLM_MODES, WEBLLM_VERSION } from './providers/webllm';
export {
  createDecisionProvider, checkNliConfig, inspectModel, chooseRuntime, buildPremise, hfModelProblem, DECISION_MODELS, DEFAULT_HYPOTHESES, TRANSFORMERS_CDN_URL, TRANSFORMERS_VERSION,
} from './providers/decision';
export type { DecisionProvider, DecisionStats, TransformersModule } from './providers/decision';
export { importDisciplineList, exportThroughline, exportThroughlineJson, schemaToCodeValues, THROUGHLINE_EXPORT_SCHEMA } from './throughline';
export type { ThroughlineCodeValue, ThroughlineExport } from './throughline';
export { createProvider, providerId, testConnection } from './providers';
export { buildRequest, parseResponse, JEV_DEFAULT_ENDPOINT, JEV_DEFAULT_MODEL, JEV_LATEST_ALIAS } from './jevAdapter';
export { validateSettings, defaultDraft, toSettings, toDraft, JEV_DEFAULTS, PROVIDERS, RULES_MODES } from './settings';
export type { RulesMode } from './settings';
export { ApiKeyStore, HF_TOKEN_STORAGE_NAME, KEY_STORAGE_NAME } from './keyStore';
export { withBackoff } from './retry';

export { ReviewLog, parseReviewLog, modelFingerprint, createReviewPersistence, REVIEW_LOG_SCHEMA } from './reviewLog';
export type { ReviewCommit, ReviewChange, ReviewState, ReviewPersistence } from './reviewLog';
export { buildWalk, walkElementsOf, walkProgress, chainOrder, sweepOrder, runnerUp, WALK_ORDERS } from './reviewWalk';
export type { WalkElement, WalkItem, WalkOrder } from './reviewWalk';
export { ClassifyService, SCHEMA_STORAGE_KEY } from './service';
export type { RunOptions, ServiceEnv, Target } from './service';
export * from './types';
