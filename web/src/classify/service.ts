// The classifier as one object, for the viewer: settings, the schema in use, the key store, results, the signature cache and
// writing the results into the model as properties. No DOM (the drawer and window.__xrayClassify live in plugins/classify.ts),
// so tests drive it with a stub fetch and the mock provider.

import { resetModelTable } from '../query/table';
import type { SceneModel } from '../types';
import { buildInput, buildInputs } from './build';
import { StorageCache, cacheKey } from './cache';
import type { KeyValueStorage, SignatureCache } from './cache';
import { buildRequest, JEV_DEFAULT_MODEL } from './jevAdapter';
import type { JevRequest } from './jevAdapter';
import { ApiKeyStore, HF_TOKEN_STORAGE_NAME } from './keyStore';
import type { KeyStorages } from './keyStore';
import { classifyInputs, estimateCalls, SUB_STRATEGIES } from './pipeline';
import type { CallEstimate, SubDisciplineStrategy } from './pipeline';
import { createProvider, providerId, testConnection } from './providers';
import type { ConnectionTest } from './providers';
import { clearModelCache, decisionModelInfo, inspectModel, modelCacheInfo, probeGpu, runtimeText } from './providers/decision';
import type { CacheStorageLike, DecisionProgress, DecisionProvider, DecisionStats, GpuProbe, LoadReport, ModelCacheInfo, ModelInspection } from './providers/decision';
import type { WebLlmStats } from './providers/webllm';
import { importDisciplineList, exportThroughlineJson } from './throughline';
import type { ImportOptions } from './throughline';
import { classByRules, resolveRule } from './rules';
import { mainQuestions, subQuestions } from './questions';
import { exportCsv, exportJson, makeManual, manualKey, ResultStore } from './results';
import type { ManualPartial } from './results';
import { overallConfidence } from './review';
import { defaultSchema, parseSchema, propertyNames, schemaHash } from './schema';
import { effectiveMinConfidence, defaultDraft, toDraft, toSettings, validateSettings } from './settings';
import type { ClassifyDraft, ClassifySettings, SettingsCheck } from './settings';
import { DEFAULT_MAX_STATE_BYTES } from './state';
import { buildState } from './state';
import type { ClassificationSchema, ClassifyInput, ClassifyResult, ClassifyStats, DecisionModel, ProgressInfo } from './types';

export const SCHEMA_STORAGE_KEY = 'xray.classify.schema.v1';

export interface ServiceEnv {
  /** For the persisted state (cache, manual overrides, schema). null: memory only. */
  storage: KeyValueStorage | null;
  keyStorages: KeyStorages;
  fetchImpl?: typeof fetch;
  /** Current selection as element indexes. */
  selection?: () => number[];
  onWebLlmProgress?: (text: string, progress: number) => void;
  /** Progress of the model download (decision provider). */
  onDecisionProgress?: (p: DecisionProgress) => void;
  /** The Cache API (tests inject a fake). Default: the browser's `caches`. */
  cacheStorage?: CacheStorageLike | null;
  /** Replace the library loaders and the GPU probe (tests). */
  decisionLoad?: Parameters<typeof createProvider>[1]['decisionLoad'];
  decisionGpu?: () => Promise<GpuProbe>;
  webllmLoad?: Parameters<typeof createProvider>[1]['webllmLoad'];
}

/** The result of "Test model". */
export interface ModelTest {
  ok: boolean;
  message: string;
  model?: string;
  device?: string;
  dtype?: string;
  /** Library and model load, ms. */
  loadMs?: number;
  /** Size of the files that the loader reported, MB. */
  sizeMB?: number;
  /** One tiny choice: the option it chose and its probability. */
  choice?: { code: string; probability: number; ms: number };
  note?: string;
}

export type Target = readonly (string | number)[] | 'selection' | 'all';
export interface RunOptions {
  /** false: skip the rules (every element goes to the cache and the model). */
  rules?: boolean;
  subDiscipline?: keyof typeof SUB_STRATEGIES | SubDisciplineStrategy;
}

const emptyStats = (): ClassifyStats => ({ total: 0, bySource: { rules: 0, cache: 0, model: 0, manual: 0 }, calls: 0, signatures: 0, needsReview: 0, failed: 0, aborted: false, errors: [], models: {}, usage: { input_tokens: 0, output_tokens: 0 } });

export class ClassifyService {
  draft: ClassifyDraft = defaultDraft();
  /** The messages from the last settings check. */
  issues: SettingsCheck = { settings: toSettings(defaultDraft()), errors: [], warnings: [] };
  schema: ClassificationSchema = defaultSchema();
  schemaHashValue = schemaHash(this.schema);
  /** True when the schema in use is the shipped placeholder. */
  customSchema = false;
  readonly keys: ApiKeyStore;
  /** The Hugging Face token (gated or private models). Same rules as the API key: not a setting, never in params, links or views. */
  readonly hfToken: ApiKeyStore;
  /** Messages of the last schema import (warnings that did not stop it). */
  importNotes: string[] = [];
  /** The last load of the decision model, and the download progress while it loads. */
  lastLoad: LoadReport | null = null;
  decisionProgress: DecisionProgress | null = null;
  gpu: GpuProbe | null = null;
  private testCtl: AbortController | null = null;
  model: SceneModel | null = null;
  modelName = '';
  store = new ResultStore();
  cache: SignatureCache = new StorageCache(null, '');
  lastStats: ClassifyStats | null = null;
  lastEstimate: CallEstimate | null = null;
  running = false;
  progress: ProgressInfo | null = null;
  private ctl: AbortController | null = null;
  private readonly listeners = new Set<() => void>();
  /** Pset properties written to the model (keys), to remove them again. */
  private written = new Set<number>();
  private writtenPset = '';

  constructor(private readonly env: ServiceEnv) {
    this.keys = new ApiKeyStore(env.keyStorages);
    this.hfToken = new ApiKeyStore(env.keyStorages, HF_TOKEN_STORAGE_NAME);
    this.loadStoredSchema();
  }

  onChange(cb: () => void): () => void {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }
  /** Tell the listeners (the drawer) that something changed. */
  notify(): void {
    for (const l of this.listeners) l();
  }
  private emit(): void {
    this.notify();
  }

  // ------------------------------------------------------------ settings

  settings(): ClassifySettings {
    return toSettings(this.draft);
  }

  /** The value of the `classify` params section. It never holds the API key. */
  collect(): ClassifySettings {
    return this.settings();
  }

  /** Apply untrusted settings (a params document). Bad values keep their defaults; the messages are in `issues`. */
  applySettings(raw: unknown): SettingsCheck {
    const c = validateSettings(raw);
    this.issues = c;
    this.draft = toDraft(c.settings);
    this.afterSettingsChange();
    return c;
  }

  /** Change fields of the draft (the drawer), validate, and keep the valid result. */
  patch(p: Partial<ClassifyDraft>): SettingsCheck {
    const next = { ...this.draft, ...p };
    const c = validateSettings(toSettings(next));
    this.issues = c;
    // Keep what the person typed in the fields of other providers; take the checked values of the active one.
    this.draft = toDraft(c.settings, { ...next });
    this.afterSettingsChange();
    return c;
  }

  private afterSettingsChange(): void {
    this.reloadCaches();
    this.store.rereview(this.minConfidence());
    if (this.store.size) {
      if (this.draft.writePset) this.writeToModel(this.store.all());
      else this.clearWritten();
    }
    this.emit();
  }

  minConfidence(): number {
    return effectiveMinConfidence(this.draft, this.schema.minConfidence);
  }

  /** Cache identity: the provider and the model id. */
  modelId(): string {
    return providerId(this.settings());
  }

  // ------------------------------------------------------------ schema

  private loadStoredSchema(): void {
    try {
      const t = this.env.storage?.getItem(SCHEMA_STORAGE_KEY);
      if (t) {
        const p = parseSchema(t);
        if (p.schema) this.useSchema(p.schema, true);
      }
    } catch {
      /* ignore */
    }
  }

  private useSchema(s: ClassificationSchema, custom: boolean): void {
    this.schema = s;
    this.schemaHashValue = schemaHash(s);
    this.customSchema = custom;
    this.clearWritten();
    this.reloadCaches();
    this.reloadStore();
  }

  /** Replace the schema with a JSON object or text. Returns the problems (empty when it was accepted). */
  setSchema(json: unknown, persist = true): string[] {
    const p = parseSchema(json);
    if (!p.schema) return p.errors;
    this.useSchema(p.schema, true);
    try {
      if (persist) this.env.storage?.setItem(SCHEMA_STORAGE_KEY, JSON.stringify(p.schema));
    } catch {
      /* ignore */
    }
    this.emit();
    return [];
  }

  useDefaultSchema(): void {
    this.importNotes = [];
    this.useSchema(defaultSchema(), false);
    try {
      this.env.storage?.removeItem(SCHEMA_STORAGE_KEY);
    } catch {
      /* ignore */
    }
    this.emit();
  }

  /** Fetch a schema file from a URL and use it. Returns the problems. */
  async loadSchemaUrl(url: string): Promise<string[]> {
    try {
      const f = this.env.fetchImpl ?? globalThis.fetch.bind(globalThis);
      const r = await f(url, { credentials: 'omit' });
      if (!r.ok) return [`The schema file answered HTTP ${r.status}.`];
      return this.setSchema(await r.text(), false);
    } catch (e) {
      return [`Could not read the schema file: ${e instanceof Error ? e.message : String(e)}`];
    }
  }

  // ------------------------------------------------------------ model, cache

  setModel(model: SceneModel, name: string): void {
    this.model = model;
    this.modelName = name;
    this.written.clear();
    this.writtenPset = '';
    this.reloadCaches();
    this.reloadStore();
    this.lastStats = null;
    this.lastEstimate = null;
    this.emit();
  }

  private reloadCaches(): void {
    this.cache = new StorageCache(this.env.storage, cacheKey(this.modelName, this.schemaHashValue, this.modelId()));
  }

  /** Results and manual overrides belong to a model and a schema. */
  private reloadStore(): void {
    this.store = new ResultStore(this.env.storage, manualKey(this.modelName, this.schemaHashValue));
  }

  clearCache(): void {
    this.cache.clear();
    this.emit();
  }

  // ------------------------------------------------------------ inputs

  idsOf(target: Target): number[] {
    const m = this.model;
    if (!m) return [];
    if (target === 'all') return m.elements.map((e) => e.id);
    if (target === 'selection') return this.env.selection?.() ?? [];
    const out: number[] = [];
    for (const t of target) {
      const id = typeof t === 'number' ? t : m.byGlobalId.get(t);
      if (id !== undefined && m.elements[id]) out.push(id);
    }
    return out;
  }

  buildInput(id: number | string): ClassifyInput | null {
    return this.model ? buildInput(this.model, id) : null;
  }

  inputsFor(target: Target): ClassifyInput[] {
    return this.model ? buildInputs(this.model, this.idsOf(target)) : [];
  }

  // ------------------------------------------------------------ provider

  /** The provider for the current settings. It is reused while the settings stay the same (a browser model keeps its engine). */
  provider(): DecisionModel | null {
    const key = JSON.stringify(this.settings());
    if (this.providerMemo?.key !== key) {
      this.providerMemo = {
        key,
        provider: createProvider(this.settings(), {
          apiKey: () => this.keys.get(),
          hfToken: () => this.hfToken.get(),
          ...(this.env.fetchImpl ? { fetchImpl: this.env.fetchImpl } : {}),
          ...(this.env.onWebLlmProgress ? { onWebLlmProgress: (p: { text: string; progress: number }) => this.env.onWebLlmProgress?.(p.text, p.progress) } : {}),
          onDecisionProgress: (p) => {
            this.decisionProgress = p;
            this.env.onDecisionProgress?.(p);
            this.emit();
          },
          ...(this.env.decisionLoad ? { decisionLoad: this.env.decisionLoad } : {}),
          ...(this.env.decisionGpu ? { decisionGpu: this.env.decisionGpu } : {}),
          ...(this.env.webllmLoad ? { webllmLoad: this.env.webllmLoad } : {}),
        }),
      };
    }
    return this.providerMemo.provider;
  }
  private providerMemo: { key: string; provider: DecisionModel | null } | null = null;

  /** Counts of the decision model (pairs, passes) since the provider was created. Null for other providers. */
  decisionStats(): DecisionStats | null {
    const p = this.provider() as Partial<DecisionProvider> | null;
    return p && p.provider === 'decision' && p.stats ? p.stats() : null;
  }

  webllmStats(): WebLlmStats | null {
    const p = this.provider() as { provider?: string; stats?: () => WebLlmStats } | null;
    return p && p.provider === 'webllm' && p.stats ? p.stats() : null;
  }

  /** Look at the GPU once and keep the answer for the drawer. */
  async probeGpu(): Promise<GpuProbe> {
    this.gpu = await (this.env.decisionGpu ?? probeGpu)();
    return this.gpu;
  }

  /** Size of the downloaded models in the Cache API. */
  modelCacheInfo(): Promise<ModelCacheInfo> {
    return modelCacheInfo(this.env.cacheStorage === undefined ? undefined : this.env.cacheStorage);
  }

  /** Delete the downloaded models (the Cache API entry of transformers.js) and free the loaded one. */
  async clearModelCache(): Promise<boolean> {
    const p = this.provider() as Partial<DecisionProvider> | null;
    await p?.dispose?.();
    this.lastLoad = null;
    this.decisionProgress = null;
    const ok = await clearModelCache(this.env.cacheStorage === undefined ? undefined : this.env.cacheStorage);
    this.emit();
    return ok;
  }

  /**
   * Load the decision model, run one tiny choice and report the load time, the device, the data type and the size.
   * For other providers it is the connection test. Never throws.
   */
  async testModel(): Promise<ModelTest> {
    if (this.draft.provider !== 'decision') {
      const r = await this.testConnection();
      return { ok: r.ok, message: r.message, ...(r.model ? { model: r.model } : {}) };
    }
    const s = this.settings();
    if (s.provider !== 'decision') return { ok: false, message: 'The decision model is not selected.' };
    const provider = this.provider() as DecisionProvider;
    this.testCtl = new AbortController();
    const signal = this.testCtl.signal;
    this.decisionProgress = null;
    this.emit();
    try {
      let sizeNote = '';
      if (!decisionModelInfo(s.hfModel)) {
        const ins: ModelInspection = await inspectModel(s.hfModel, { endpoint: s.hfEndpoint, token: this.hfToken.get(), ...(this.env.fetchImpl ? { fetchImpl: this.env.fetchImpl } : {}), signal });
        if (!ins.ok) return { ok: false, message: ins.message, model: s.hfModel };
        sizeNote = ins.sizesMB ? ` Files: ${Object.entries(ins.sizesMB).map(([k, v]) => `${k} ${v} MB`).join(', ')}.` : '';
      }
      const rep = await provider.load(signal);
      this.lastLoad = rep;
      const t0 = Date.now();
      const a = await provider.decide(
        { class: 'IfcDuctSegment', name: 'Duct 300x200', building_context: true },
        {
          pick: {
            type: 'choice',
            instructions: 'Choose the discipline.',
            criteria: { MEC: 'Mechanical. Heating, ventilation and air conditioning: ducts, fans.', ARC: 'Architectural. Walls, doors, windows, finishes.', PLB: 'Plumbing. Water supply and drainage pipes.' },
          },
        },
        signal,
      );
      const ans = a.answers['pick'];
      const choice = ans && ans.type === 'choice' ? { code: ans.choice, probability: ans.probabilities[ans.choice] ?? ans.confidence, ms: Date.now() - t0 } : undefined;
      const sizeText = rep.sizeMB > 0 ? `, ${rep.sizeMB} MB of files` : '';
      return {
        ok: true,
        model: s.hfModel,
        device: rep.device,
        dtype: rep.dtype,
        loadMs: rep.loadMs,
        sizeMB: rep.sizeMB,
        ...(choice ? { choice } : {}),
        ...(rep.note ? { note: rep.note } : {}),
        message: `Ready: ${s.hfModel} on ${rep.device} (${rep.dtype}) in ${(rep.loadMs / 1000).toFixed(1)} s${sizeText}.${choice ? ` Test question: chose ${choice.code} (${choice.probability.toFixed(2)}) in ${choice.ms} ms.` : ''}${rep.note ? ` ${rep.note}` : ''}${sizeNote}`,
      };
    } catch (e) {
      if (signal.aborted) return { ok: false, message: 'Stopped.' };
      return { ok: false, message: e instanceof Error ? e.message : String(e) };
    } finally {
      this.testCtl = null;
      this.emit();
    }
  }

  /** Text for the drawer: where the decision model runs, and what that costs. */
  runtimeNote(): string {
    return runtimeText(this.lastLoad, this.gpu);
  }

  async testConnection(): Promise<ConnectionTest> {
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), (this.draft.provider === 'jev' ? this.draft.timeoutMs : 60_000) + 1000);
    try {
      return await testConnection(this.provider(), ctl.signal);
    } finally {
      clearTimeout(t);
    }
  }

  // ------------------------------------------------------------ estimate

  estimate(target: Target, o: RunOptions = {}): CallEstimate {
    const e = estimateCalls(this.inputsFor(target), { schema: this.schema, cache: this.cache, manual: this.store.manual, ...(o.rules === false ? { rules: false } : {}) });
    this.lastEstimate = e;
    return e;
  }

  /** The exact requests the viewer would send for an element: the first (discipline, building_element, masterformat) and an example of the second. */
  questions(input: ClassifyInput, discipline?: string): { model: string; stateBytes: number; main: JevRequest; sub: JevRequest | null; subFor: string } {
    const model = this.draft.provider === 'jev' ? this.draft.model : JEV_DEFAULT_MODEL;
    const maxBytes = this.draft.provider === 'jev' ? this.draft.maxStateBytes : DEFAULT_MAX_STATE_BYTES;
    const state = buildState(input, maxBytes);
    const guess = classByRules(input);
    const resolved = guess ? resolveRule(guess, this.schema, true) : null;
    const subFor = discipline ?? resolved?.discipline ?? this.schema.disciplines[0]!.code;
    const sq = subQuestions(this.schema, [subFor]);
    return { model, stateBytes: new TextEncoder().encode(JSON.stringify(state)).length, main: buildRequest(model, state, mainQuestions(this.schema)), sub: sq ? buildRequest(model, state, sq) : null, subFor };
  }

  // ------------------------------------------------------------ run

  async classify(target: Target, o: RunOptions = {}): Promise<ClassifyResult[]> {
    return this.classifyInputs(this.inputsFor(target), o);
  }

  async classifyInputs(inputs: readonly ClassifyInput[], o: RunOptions = {}): Promise<ClassifyResult[]> {
    if (this.running) throw new Error('A classification is already running. Stop it first.');
    this.running = true;
    this.ctl = new AbortController();
    this.progress = null;
    this.emit();
    const s = this.settings();
    try {
      const sub = typeof o.subDiscipline === 'function' ? o.subDiscipline : SUB_STRATEGIES[o.subDiscipline ?? 'top2-when-unsure'];
      const run = await classifyInputs(inputs, {
        schema: this.schema,
        provider: this.provider(),
        minConfidence: this.minConfidence(),
        cache: this.cache,
        manual: this.store.manual,
        concurrency: s.provider === 'jev' ? s.concurrency : 1,
        maxStateBytes: s.provider === 'jev' ? s.maxStateBytes : DEFAULT_MAX_STATE_BYTES,
        subDiscipline: sub,
        signal: this.ctl.signal,
        ...(o.rules === false ? { rules: false } : {}),
        onProgress: (p) => {
          this.progress = p;
          this.emit();
        },
      });
      this.store.merge(run.results);
      this.lastStats = run.stats;
      if (s.writePset) this.writeToModel(run.results);
      return run.results;
    } finally {
      this.running = false;
      this.ctl = null;
      this.emit();
    }
  }

  abort(): void {
    this.ctl?.abort();
    this.testCtl?.abort();
  }

  // ------------------------------------------------------------ results

  results(): ClassifyResult[] {
    return this.store.all();
  }

  stats(): ClassifyStats {
    const bySource = { rules: 0, cache: 0, model: 0, manual: 0 };
    let nr = 0;
    for (const r of this.store.all()) {
      bySource[r.source]++;
      if (r.needsReview) nr++;
    }
    return { ...(this.lastStats ?? emptyStats()), total: this.store.size, bySource, needsReview: nr };
  }

  /** Set the discipline, sub-discipline or division of one element by hand. Source `manual`; it wins over everything and is kept. */
  override(id: string | number, partial: ManualPartial): ClassifyResult {
    const m = this.model;
    const gid = typeof id === 'number' ? m?.elements[id]?.globalId : id;
    if (!gid) throw new Error(`No element "${String(id)}" in the model.`);
    const r = makeManual(this.schema, gid, partial, this.store.get(gid));
    this.store.setManual(r);
    if (this.draft.writePset) this.writeToModel([r]);
    this.emit();
    return r;
  }

  /** Remove a manual override. The element has no result until it is classified again. */
  removeOverride(id: string): void {
    this.store.removeManual(id);
    this.clearWritten([id]);
    this.emit();
  }

  clear(): void {
    this.clearWritten();
    this.store.clear(false);
    this.lastStats = null;
    this.progress = null;
    this.emit();
  }

  /** Needs-review elements, as element indexes. */
  needsReviewIds(): number[] {
    const m = this.model;
    if (!m) return [];
    return this.store.all().filter((r) => r.needsReview).map((r) => m.byGlobalId.get(r.id)).filter((x): x is number => x !== undefined);
  }

  export(kind: 'json' | 'csv' | 'throughline'): string {
    const all = this.store.all();
    if (kind === 'throughline') return exportThroughlineJson(all, this.schema, this.modelName);
    return kind === 'csv' ? exportCsv(all) : exportJson(all, this.schema, this.stats(), this.modelName);
  }

  /**
   * Use a Throughline `Discipline` code list (JSON of CodeValue entries) as the schema. Returns the problems (empty: accepted).
   * Warnings that did not stop the import are in `importNotes`.
   */
  importThroughline(json: unknown, o: ImportOptions = {}): string[] {
    const r = importDisciplineList(json, o);
    this.importNotes = r.warnings;
    if (!r.schema) return r.errors;
    return this.setSchema(r.schema);
  }

  // ------------------------------------------------------------ properties in the model

  /** Write results as `<psetName>.<Property>` into the element properties, so the query engine and the search bar see them. */
  writeToModel(results: readonly ClassifyResult[]): void {
    const m = this.model;
    if (!m) return;
    const pset = this.schema.psetName;
    if (this.writtenPset && this.writtenPset !== pset) this.clearWritten();
    this.writtenPset = pset;
    const n = propertyNames(this.schema);
    for (const r of results) {
      const id = m.byGlobalId.get(r.id);
      const e = id === undefined ? undefined : m.elements[id];
      if (!e) continue;
      const props = (e.props ??= {});
      const put = (k: string, v: string | number | boolean | undefined): void => {
        const key = `${pset}.${k}`;
        if (v === undefined || v === '') delete props[key];
        else props[key] = v;
      };
      put(n.discipline, r.discipline.code);
      put(n.subDiscipline, r.subDiscipline?.code);
      put(n.masterformatDivision, r.masterformat?.division);
      put(n.masterformatTitle, r.masterformat?.title);
      put(n.masterformatSection, r.masterformat?.section);
      put(n.confidence, overallConfidence(r));
      put(n.source, r.source);
      put(n.model, r.model);
      put(n.needsReview, r.needsReview);
      this.written.add(e.id);
    }
    resetModelTable(m);
  }

  /** Remove the written properties (all, or of the given GlobalIds). */
  clearWritten(only?: readonly string[]): void {
    const m = this.model;
    if (!m || !this.writtenPset) return;
    const prefix = `${this.writtenPset}.`;
    const ids = only ? only.map((g) => m.byGlobalId.get(g)).filter((x): x is number => x !== undefined) : [...this.written];
    for (const id of ids) {
      const props = m.elements[id]?.props;
      if (!props) continue;
      for (const k of Object.keys(props)) if (k.startsWith(prefix)) delete props[k];
      this.written.delete(id);
    }
    resetModelTable(m);
  }
}
