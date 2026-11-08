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
export { classByRules, isBuildingContext, resolveRule, RULE_FINAL } from './rules';
export { defaultSchema, parseSchema, propertyNames, schemaHash, DEFAULT_MIN_CONFIDENCE, SCHEMA_ID } from './schema';
export { MemoryCache, StorageCache, cacheKey } from './cache';
export type { CachedDecision, KeyValueStorage, SignatureCache } from './cache';
export { computeNeedsReview, overallConfidence, topMargin, topTwo, DEFAULT_MIN_MARGIN } from './review';
export { ResultStore, makeManual, exportCsv, exportJson, CSV_HEADER } from './results';
export { createJevProvider, redact } from './providers/jev';
export { createMockProvider } from './providers/mock';
export { createWebLlmProvider, detectWebGpu, WEBLLM_MODELS, WEBLLM_VERSION } from './providers/webllm';
export { createProvider, providerId, testConnection } from './providers';
export { buildRequest, parseResponse, JEV_DEFAULT_ENDPOINT, JEV_DEFAULT_MODEL, JEV_LATEST_ALIAS } from './jevAdapter';
export { validateSettings, defaultDraft, toSettings, toDraft, JEV_DEFAULTS, PROVIDERS } from './settings';
export { ApiKeyStore } from './keyStore';
export { withBackoff } from './retry';

export { ClassifyService, SCHEMA_STORAGE_KEY } from './service';
export type { RunOptions, ServiceEnv, Target } from './service';
export * from './types';
