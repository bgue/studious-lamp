// Classify plugin: labels each element with a discipline, a sub-discipline and (for building elements) a CSI MasterFormat
// division, with rules first, then a signature cache, then a decision model (Jev over HTTP, or a tiny WebLLM model in the
// browser). The core is src/classify/ (no DOM). This file adds the drawer, the params section, the actions and
//
//   window.__xrayClassify = { classify, classifyInputs, buildInput, questions, schema, setSchema, results, override, clear,
//                             export, abort, stats, ... }
//
// The API key is never in the params section (see classify/keyStore.ts).

import type { AppPlugin, ViewerApp } from '../app';
import { registerAction } from '../input/actions';
import { buildInput } from '../classify/build';
import { disciplineRgb, rgbCss } from '../classify/palette';
import { detectWebGpu, describeModel, customModelCheck, WEBLLM_EMBED_MODELS, WEBLLM_MODELS, WEBLLM_MODES, webllmModelInfo } from '../classify/providers/webllm';
import { DECISION_DEVICES, DECISION_DTYPES, DECISION_MODELS, DEFAULT_HYPOTHESES, HYPOTHESIS_KEYS, decisionModelInfo, describeDecisionModel } from '../classify/providers/decision';
import type { DecisionStats, ModelCacheInfo } from '../classify/providers/decision';
import type { WebLlmStats } from '../classify/providers/webllm';
import type { ApiKeyStore } from '../classify/keyStore';
import { topTwo, overallConfidence } from '../classify/review';
import { browserKeyStorages } from '../classify/keyStore';
import { ClassifyService } from '../classify/service';
import type { ModelTest, RunOptions, Target } from '../classify/service';
import { PROVIDERS } from '../classify/settings';
import type { ProviderId } from '../classify/settings';
import { JEV_DEFAULTS } from '../classify/settings';
import { propertyNames } from '../classify/schema';
import type { ManualPartial } from '../classify/results';
import type { ClassifyInput, ClassifyResult, ClassifyStats } from '../classify/types';
import { downloadText } from '../tools/csv';
import { ICONS } from '../tools/icons';
import { registerTool } from '../tools/registry';
import { button, check, note, row, section, statusLine, chips } from '../tools/ui';
import type { Widget } from '../tools/ui';
import { el } from '../ui/dom';
import { registerParamSection } from '../ui/params';
import { quoteIdent } from '../query';
import { openCriteriaSetEditor } from './sidebar';

declare global {
  interface Window {
    __xrayClassify?: ClassifyApi;
  }
}

export interface ClassifyApi {
  classify(target: Target, opts?: RunOptions): Promise<ClassifyResult[]>;
  classifyInputs(inputs: ClassifyInput[], opts?: RunOptions): Promise<ClassifyResult[]>;
  buildInput(id: number | string): ClassifyInput | null;
  /** The exact Jev requests for an element: the first request and an example of the second. */
  questions(input: ClassifyInput | number | string, discipline?: string): unknown;
  schema(): unknown;
  /** Replace the schema (an object or JSON text). Returns the problems; an empty list means accepted. */
  setSchema(json: unknown): string[];
  results(): ClassifyResult[];
  override(id: string | number, partial: ManualPartial): ClassifyResult;
  clear(): void;
  export(kind: 'json' | 'csv' | 'throughline'): string;
  abort(): void;
  stats(): ClassifyStats;
  /** Extras for scripts. */
  estimate(target: Target, opts?: RunOptions): unknown;
  configure(patch: Record<string, unknown>): { errors: string[]; warnings: string[] };
  settings(): unknown;
  setKey(key: string, remember?: boolean): void;
  keyState(): { set: boolean; remembered: boolean; mask: string };
  testConnection(): Promise<unknown>;
  /** Decision model: load it, run one tiny choice, report the load time, the device, the data type and the size. */
  testModel(): Promise<ModelTest>;
  setHfToken(token: string, remember?: boolean): void;
  hfTokenState(): { set: boolean; remembered: boolean; mask: string };
  /** Size of the downloaded models in the browser cache. */
  modelCache(): Promise<ModelCacheInfo>;
  clearModelCache(): Promise<boolean>;
  /** Pairs and forward passes of the decision model since the provider was created (null for other providers). */
  decisionStats(): DecisionStats | null;
  webllmStats(): WebLlmStats | null;
  /** Use a Throughline `Discipline` code list (JSON of CodeValue entries) as the schema. Returns the problems; empty means accepted. */
  importThroughline(json: unknown): { errors: string[]; warnings: string[] };
  selectNeedsReview(): number;
  colourByDiscipline(on?: boolean): boolean;
  state(): { running: boolean; provider: string; model: string; schemaTitle: string; placeholder: boolean; hash: string };
}

const STYLE_ID = 'xray-classify-style';
const CSS = `
.xc-body>*{flex:0 0 auto}
.xc-group[hidden],.xc-editor[hidden]{display:none}
.xc-text{background:#0e1218;color:inherit;border:1px solid var(--sb-line,#262d3a);border-radius:3px;height:24px;padding:0 6px;font:inherit;min-width:0;width:100%}
.xc-text:focus-visible,.xt-select select:focus-visible{outline:1px solid var(--sb-accent,#3b9cff)}
.xc-warn{color:#e0b252}
.xc-err{color:#ff8f8f}
.xc-legend{display:flex;flex-wrap:wrap;gap:4px 10px;font-size:11px;color:#b9c4d2}
.xc-top2{color:var(--sb-dim,#8d99a8)}
.xc-review{color:#e0b252}
.xc-edit{background:transparent;border:1px solid transparent;color:var(--sb-dim,#8d99a8);cursor:pointer;padding:0 4px;border-radius:3px}
.xc-edit:hover{color:#fff;border-color:#3a4a66}
.xc-editor{display:flex;flex-direction:column;gap:6px;padding:8px;border:1px solid #2d6aa8;border-radius:4px;background:#10141b}
.xc-adv summary{cursor:pointer;color:var(--sb-dim,#8d99a8);font-size:11px}
.xc-prog{height:6px;background:#10141b;border:1px solid var(--sb-line,#262d3a);border-radius:3px;overflow:hidden}
.xc-prog>i{display:block;height:100%;background:#2d6aa8;width:0}
`;

function ensureStyle(): void {
  if (document.getElementById(STYLE_ID)) return;
  const st = document.createElement('style');
  st.id = STYLE_ID;
  st.textContent = CSS;
  document.head.appendChild(st);
}

function localStore(): Storage | null {
  try {
    const s = window.localStorage;
    s.getItem('xray.probe');
    return s;
  } catch {
    return null;
  }
}

const fmt2 = (n: number): string => (Math.round(n * 100) / 100).toFixed(2);

// ---------------------------------------------------------------- colour by discipline

class Tint {
  private saved: Map<number, [number, number, number]> | null = null;
  on = false;
  constructor(private readonly app: ViewerApp, private readonly svc: ClassifyService) {}

  apply(): void {
    this.restore(false);
    if (!this.on) return;
    const m = this.svc.model;
    if (!m) return;
    const color = this.app.renderer.state.color;
    const saved = new Map<number, [number, number, number]>();
    for (const r of this.svc.results()) {
      const id = m.byGlobalId.get(r.id);
      if (id === undefined) continue;
      const o = id * 3;
      saved.set(id, [color[o]!, color[o + 1]!, color[o + 2]!]);
      const c = disciplineRgb(r.discipline.code);
      color[o] = c[0];
      color[o + 1] = c[1];
      color[o + 2] = c[2];
    }
    this.saved = saved;
    this.app.renderer.markDirty();
  }

  restore(mark = true): void {
    const s = this.saved;
    if (!s) return;
    this.saved = null;
    const color = this.app.renderer.state.color;
    for (const [id, c] of s) {
      color[id * 3] = c[0];
      color[id * 3 + 1] = c[1];
      color[id * 3 + 2] = c[2];
    }
    if (mark) this.app.renderer.markDirty();
  }

  set(on: boolean): void {
    this.on = on;
    if (on) this.apply();
    else this.restore();
  }

  /** The renderer state was replaced (a new model). */
  forget(): void {
    this.saved = null;
  }
}

// ---------------------------------------------------------------- widgets

function textField(label: string, get: () => string, set: (v: string) => void, opts: { type?: string; placeholder?: string; autocomplete?: string } = {}): Widget & { input: HTMLInputElement } {
  const root = el('label', 'xt-select');
  const input = el('input', 'xc-text', { type: opts.type ?? 'text', spellcheck: 'false', autocomplete: opts.autocomplete ?? 'off' });
  if (opts.placeholder) input.placeholder = opts.placeholder;
  root.append(el('span', 'xt-lbl', undefined, label), input);
  input.addEventListener('change', () => set(input.value));
  return { root, input, update: () => { if (document.activeElement !== input) input.value = get(); } };
}

function numField(label: string, min: number, max: number, step: number, get: () => number, set: (v: number) => void): Widget {
  const root = el('label', 'xt-select');
  const input = el('input', 'xt-num', { type: 'number', min: String(min), max: String(max), step: String(step) });
  root.append(el('span', 'xt-lbl', undefined, label), input);
  input.addEventListener('change', () => set(Number(input.value)));
  return { root, update: () => { if (document.activeElement !== input) input.value = String(get()); } };
}

function pick<T extends string>(label: string, options: ReadonlyArray<{ value: T; text: string }>, get: () => T, set: (v: T) => void): Widget & { sel: HTMLSelectElement } {
  const root = el('label', 'xt-select');
  const sel = el('select');
  for (const o of options) sel.appendChild(el('option', undefined, { value: o.value }, o.text));
  root.append(el('span', 'xt-lbl', undefined, label), sel);
  sel.addEventListener('change', () => set(sel.value as T));
  return { root, sel, update: () => { sel.value = get(); } };
}

const PROVIDER_LABEL: Record<ProviderId, string> = {
  off: 'Off (rules and cache only)',
  decision: 'Decision model (in browser, WebGPU)',
  webllm: 'Browser chat model (WebLLM)',
  jev: 'Jev (HTTP)',
  mock: 'Mock (tests)',
};

const fmtMB = (b: number): string => (b >= 1e9 ? `${(b / 1e9).toFixed(2)} GB` : `${Math.round(b / 1e5) / 10} MB`);

/** A password box for a secret, with Save and Forget and a "remember" switch. The secret is never shown again. */
function secretField(
  add: <W extends Widget>(w: W) => W,
  o: { label: string; aria: string; name: string; store: ApiKeyStore; status: string; remember: string; save: string; forget: string; saveTitle: string; forgetTitle: string },
): { nodes: HTMLElement[]; paint(): void } {
  const box = el('label', 'xt-select');
  const input = el('input', 'xc-text', { type: 'password', autocomplete: 'off', spellcheck: 'false', 'aria-label': o.aria, placeholder: 'not shown after saving', name: o.name });
  box.append(el('span', 'xt-lbl', undefined, o.label), input);
  const status = statusLine('');
  const remember = add(check(o.remember, () => o.store.remembered(), (v) => {
    const k = input.value.trim() || o.store.get();
    if (k) o.store.set(k, v);
    paint();
  }));
  const save = (): void => {
    if (input.value.trim()) o.store.set(input.value, (remember.root.querySelector('input') as HTMLInputElement).checked);
    input.value = '';
    paint();
  };
  input.addEventListener('change', save);
  const paint = (): void => {
    status.set(`${o.status}: ${o.store.mask()}${o.store.remembered() ? ', kept on this device' : o.store.get() ? ', kept for this tab only' : ''}`);
    remember.update();
  };
  return {
    nodes: [
      box, remember.root, status,
      row(
        button(o.save, save, { title: o.saveTitle }),
        button(o.forget, () => { o.store.clear(); input.value = ''; paint(); }, { title: o.forgetTitle }),
      ),
    ],
    paint,
  };
}

function details(summary: string): HTMLDetailsElement {
  const d = el('details', 'xc-adv') as HTMLDetailsElement;
  d.appendChild(el('summary', undefined, undefined, summary));
  d.style.cssText = 'display:flex;flex-direction:column;gap:6px';
  return d;
}

// ---------------------------------------------------------------- drawer

const MAX_ROWS = 200;

function panel(box: HTMLElement, app: ViewerApp, svc: ClassifyService, tint: Tint, api: ClassifyApi): () => void {
  ensureStyle();
  box.classList.add('xc-body');
  const widgets: Widget[] = [];
  const add = <W extends Widget>(w: W): W => {
    widgets.push(w);
    return w;
  };
  const d = (): typeof svc.draft => svc.draft;
  const apply = (p: Partial<typeof svc.draft>): void => {
    svc.patch(p); // the messages show on the refresh that follows
  };

  // ---- provider
  box.appendChild(section('Provider'));
  const prov = add(pick('Provider', PROVIDERS.map((p) => ({ value: p, text: PROVIDER_LABEL[p] })), () => d().provider, (v) => apply({ provider: v })));
  box.appendChild(prov.root);
  const issues = el('div', 'xt-note xc-warn');
  issues.setAttribute('role', 'status');
  const showIssues = (errors: string[], warnings: string[]): void => {
    issues.textContent = [...errors, ...warnings].join(' ');
    issues.classList.toggle('xc-err', errors.length > 0);
    issues.hidden = errors.length + warnings.length === 0;
  };

  // Decision model (a small NLI model with transformers.js): the recommended local provider
  const dec = el('div', 'xc-group');
  dec.setAttribute('data-for', 'decision');
  dec.style.cssText = 'display:flex;flex-direction:column;gap:6px';
  const CUSTOM = '__custom';
  const decPreset = add(pick('Decision model', [...DECISION_MODELS.map((m) => ({ value: m.id, text: m.label })), { value: CUSTOM, text: 'Another model from Hugging Face...' }],
    () => (decisionModelInfo(d().hfModel) ? d().hfModel : CUSTOM), (v) => { if (v !== CUSTOM) apply({ hfModel: v }); else decModelId.input.focus(); }));
  const decModelId = add(textField('Hugging Face model id', () => d().hfModel, (v) => apply({ hfModel: v.trim() }), { placeholder: 'owner/name, for example MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33' }));
  const decDevice = add(pick('Device', DECISION_DEVICES.map((v) => ({ value: v, text: v === 'auto' ? 'Auto (WebGPU when present)' : v === 'webgpu' ? 'WebGPU' : 'WASM (CPU, slower)' })), () => d().device, (v) => apply({ device: v })));
  const decDtype = add(pick('Data type', DECISION_DTYPES.map((v) => ({ value: v, text: v === 'auto' ? 'Auto (q8 on WASM, fp16 on WebGPU)' : v })), () => d().dtype, (v) => apply({ dtype: v })));
  const decInfo = el('div', 'xt-note');
  const decRuntime = el('div', 'xt-note');
  decRuntime.setAttribute('role', 'status');
  const hfTok = secretField(add, {
    label: 'Hugging Face token', aria: 'Hugging Face token', name: 'xray-classify-hf-token', store: svc.hfToken, status: 'Hugging Face token', remember: 'Remember token on this device',
    save: 'Save token', forget: 'Forget token', saveTitle: 'Keep the token typed above', forgetTitle: 'Remove the token from this browser',
  });
  const decProg = el('div', 'xc-prog');
  const decBar = el('i');
  decProg.appendChild(decBar);
  const decProgLine = statusLine('');
  const cacheLine = statusLine('');
  const advDec = details('Advanced: endpoint and hypotheses');
  advDec.append(
    add(textField('Hugging Face endpoint', () => d().hfEndpoint, (v) => apply({ hfEndpoint: v.trim() }), { type: 'url', placeholder: 'https://huggingface.co' })).root,
    note('Use another address for a mirror or your own proxy. A token goes to this address only.'),
  );
  const HYP_LABEL: Record<(typeof HYPOTHESIS_KEYS)[number], string> = { discipline: 'Discipline hypothesis', sub_discipline: 'Sub-discipline hypothesis', masterformat: 'Division hypothesis', building_element: 'Building hypothesis' };
  for (const k of HYPOTHESIS_KEYS) advDec.append(add(textField(HYP_LABEL[k], () => d().hypothesis[k], (v) => apply({ hypothesis: { ...d().hypothesis, [k]: v.trim() } }))).root);
  advDec.append(row(button('Reset hypotheses', () => apply({ hypothesis: { ...DEFAULT_HYPOTHESES } }), { title: 'Use the default hypothesis sentences' })));
  dec.append(decPreset.root, decModelId.root, decDevice.root, decDtype.root, decInfo, decRuntime, ...hfTok.nodes, decProg, decProgLine, cacheLine, advDec);
  box.appendChild(dec);

  // Jev
  const jev = el('div', 'xc-group');
  jev.setAttribute('data-for', 'jev');
  jev.style.cssText = 'display:flex;flex-direction:column;gap:6px';
  jev.append(
    add(textField('Endpoint', () => d().endpoint, (v) => apply({ endpoint: v.trim() }), { type: 'url', placeholder: JEV_DEFAULTS.endpoint })).root,
    add(textField('Model id', () => d().model, (v) => apply({ model: v.trim() }), { placeholder: JEV_DEFAULTS.model })).root,
    add(numField('Requests at once', 1, 16, 1, () => d().concurrency, (v) => apply({ concurrency: v }))).root,
    add(numField('State size cap (bytes)', 500, 64000, 500, () => d().maxStateBytes, (v) => apply({ maxStateBytes: v }))).root,
    add(numField('Timeout (ms)', 1000, 300000, 1000, () => d().timeoutMs, (v) => apply({ timeoutMs: v }))).root,
  );
  // API key
  const jevKey = secretField(add, {
    label: 'API key', aria: 'API key', name: 'xray-classify-key', store: svc.keys, status: 'API key', remember: 'Remember on this device',
    save: 'Save key', forget: 'Forget key', saveTitle: 'Keep the key typed above', forgetTitle: 'Remove the key from this browser',
  });
  jev.append(...jevKey.nodes, note('A key in a page can be read by anyone who uses this browser. For a shared viewer, use a same-origin proxy as the endpoint and leave the key empty.'));
  const paintKey = jevKey.paint;
  box.appendChild(jev);

  // WebLLM
  const web = el('div', 'xc-group');
  web.setAttribute('data-for', 'webllm');
  web.style.cssText = 'display:flex;flex-direction:column;gap:6px';
  const webMode = add(pick('Mode', WEBLLM_MODES.map((m) => ({ value: m, text: m === 'chat' ? 'Chat (one letter per question)' : m === 'embed' ? 'Embed (similarity, every option scored)' : 'Hybrid (embed, chat for close calls)' })), () => d().webllmMode, (v) => apply({ webllmMode: v })));
  const webModel = add(pick('Browser model', WEBLLM_MODELS.map((m) => ({ value: m.id, text: m.label })), () => d().webllmModel, (v) => apply({ webllmModel: v })));
  const webEmbed = add(pick('Embedding model', WEBLLM_EMBED_MODELS.map((m) => ({ value: m.id, text: m.label })), () => d().webllmEmbedModel, (v) => apply({ webllmEmbedModel: v })));
  const webTemp = add(numField('Embedding temperature', 0.005, 1, 0.005, () => d().embedTemperature, (v) => apply({ embedTemperature: v })));
  const webMargin = add(numField('Hybrid margin', 0, 1, 0.05, () => d().hybridMargin, (v) => apply({ hybridMargin: v })));
  const webInfo = el('div', 'xt-note');
  const gpuNote = el('div', 'xt-note');
  gpuNote.setAttribute('role', 'status');
  const webCustomNote = el('div', 'xt-note xc-warn');
  const advWeb = details('Advanced: a custom model from Hugging Face');
  advWeb.append(
    add(textField('Custom model URL', () => d().webllmCustomModel, (v) => apply({ webllmCustomModel: v.trim() }), { type: 'url', placeholder: 'https://huggingface.co/owner/name-q4f16_1-MLC' })).root,
    add(textField('Custom library URL', () => d().webllmCustomLib, (v) => apply({ webllmCustomLib: v.trim() }), { type: 'url', placeholder: 'https://.../model-webgpu.wasm' })).root,
    webCustomNote,
  );
  web.append(webMode.root, webModel.root, webEmbed.root, webTemp.root, webMargin.root, webInfo, gpuNote, advWeb);
  box.appendChild(web);

  box.appendChild(issues);
  issues.hidden = true;

  const conn = statusLine('');
  const testBtn = button('Test connection', () => {
    conn.set('Testing...');
    conn.classList.remove('xc-err');
    void svc.testConnection().then((r) => {
      conn.set(r.message);
      conn.classList.toggle('xc-err', !r.ok);
    });
  }, { title: 'Send one small yes or no question to the provider' });
  const testModelBtn = button('Test model', () => {
    conn.set('Loading the model...');
    conn.classList.remove('xc-err');
    void svc.testModel().then((r) => {
      conn.set(r.message);
      conn.classList.toggle('xc-err', !r.ok);
      void paintCache();
    });
  }, { title: 'Load the model, run one small question and report the time, the device and the size' });
  const clearCacheBtn = button('Clear model cache', () => {
    void svc.clearModelCache().then((ok) => { conn.set(ok ? 'The downloaded models were deleted from the browser cache.' : 'The browser cache holds no models.'); conn.classList.remove('xc-err'); void paintCache(); });
  }, { title: 'Delete the downloaded model files from the browser cache' });
  box.append(row(testBtn, testModelBtn, clearCacheBtn), conn);
  let cacheBusy = false;
  const paintCache = async (): Promise<void> => {
    if (cacheBusy) return;
    cacheBusy = true;
    try {
      const c = await svc.modelCacheInfo();
      cacheLine.set(!c.available ? 'Model cache: not available in this browser.' : c.files === 0 ? 'Model cache: empty. The model downloads on first use.' : `Model cache: ${fmtMB(c.bytes)} in ${c.files} file${c.files === 1 ? '' : 's'}.`);
      clearCacheBtn.setDisabled(c.available && c.files > 0 ? false : 'Nothing is cached');
    } finally {
      cacheBusy = false;
    }
  };

  // ---- schema
  box.appendChild(section('Schema'));
  const schemaLine = statusLine('');
  const schemaIssues = el('div', 'xt-note xc-err');
  schemaIssues.hidden = true;
  const file = el('input', undefined, { type: 'file', accept: '.json,application/json', hidden: '' });
  file.addEventListener('change', async () => {
    const f = file.files?.[0];
    if (!f) return;
    const errs = svc.setSchema(await f.text());
    schemaIssues.hidden = errs.length === 0;
    schemaIssues.textContent = errs.join(' ');
    file.value = '';
  });
  const tlFile = el('input', undefined, { type: 'file', accept: '.json,application/json', hidden: '' });
  const schemaNotes = el('div', 'xt-note xc-warn');
  schemaNotes.hidden = true;
  tlFile.addEventListener('change', async () => {
    const f = tlFile.files?.[0];
    if (!f) return;
    const errs = svc.importThroughline(await f.text());
    schemaIssues.hidden = errs.length === 0;
    schemaIssues.textContent = errs.join(' ');
    tlFile.value = '';
  });
  box.append(
    schemaLine,
    row(
      button('Load schema file', () => file.click(), { title: 'Use your own xray-classification-schema/1 file' }),
      button('Import Throughline list', () => tlFile.click(), { title: 'Use a Throughline Discipline code list (a JSON export of its entries) as the schema' }),
      button('Use built-in schema', () => { svc.useDefaultSchema(); schemaIssues.hidden = true; }, { title: 'Go back to the Throughline-aligned default schema' }),
    ),
    file,
    tlFile,
    schemaIssues,
    schemaNotes,
    add(numField('Minimum confidence', 0, 1, 0.05, () => svc.minConfidence(), (v) => apply({ minConfidence: Number.isFinite(v) ? Math.min(1, Math.max(0, v)) : null }))).root,
    add(check('Write properties to the model', () => d().writePset, (v) => apply({ writePset: v }))).root,
  );

  // ---- run
  box.appendChild(section('Run'));
  const estimateEl = statusLine('');
  estimateEl.style.whiteSpace = 'pre-line';
  const useRules = add(check('Use rules first', () => useRulesOn, (v) => { useRulesOn = v; scheduleEstimate(); }));
  let useRulesOn = true;
  const prog = el('div', 'xc-prog');
  const bar = el('i');
  prog.appendChild(bar);
  const progLine = statusLine('');
  let runMsg: string | null = null;
  let infoMsg: string | null = null;
  const run = (target: Target): void => {
    const opts: RunOptions = useRulesOn ? {} : { rules: false };
    runMsg = null;
    infoMsg = null;
    if (target === 'selection' && app.selection.length === 0) {
      runMsg = 'Select elements in the model first, or click Classify all.';
      refresh();
      return;
    }
    void api.classify(target, opts).then(
      () => { runMsg = null; },
      (e: unknown) => { runMsg = e instanceof Error ? e.message : String(e); svc.notify(); },
    );
  };
  const bSel = button('Classify selection', () => run('selection'), { primary: true, title: 'Classify the selected elements' });
  const bAll = button('Classify all', () => run('all'), { title: 'Classify every element of the model' });
  const bStop = button('Stop', () => svc.abort(), { title: 'Stop after the requests in flight' });
  box.append(estimateEl, useRules.root, row(bSel, bAll, bStop), prog, progLine);

  // ---- results
  box.appendChild(section('Results'));
  const filter = new Set<string>();
  const filterChips = chips([{ value: 'low', label: 'Low confidence', title: 'Confidence below the minimum' }, { value: 'review', label: 'Needs review', title: 'Marked for review' }], filter, () => renderTable());
  const countLine = statusLine('');
  const wrap = el('div', 'xt-table-wrap');
  const table = el('table', 'xt-table');
  const thead = el('thead');
  const hr = el('tr');
  for (const h of ['Element', 'Disc.', 'Sub', 'Div.', 'Conf.', 'Top 2', 'Source', '']) hr.appendChild(el('th', undefined, undefined, h));
  thead.appendChild(hr);
  const tbody = el('tbody');
  table.append(thead, tbody);
  wrap.appendChild(table);
  const editor = el('div', 'xc-editor');
  editor.hidden = true;
  box.append(filterChips, countLine, wrap, editor);

  let editId: string | null = null;
  const closeEditor = (): void => { editId = null; editor.hidden = true; editor.replaceChildren(); };
  const openEditor = (r: ClassifyResult): void => {
    editId = r.id;
    editor.hidden = false;
    editor.replaceChildren();
    const name = svc.model?.elements[svc.model.byGlobalId.get(r.id) ?? -1]?.name || r.id;
    const draftOverride: { disc: string; sub: string; div: string } = { disc: r.discipline.code, sub: r.subDiscipline?.code ?? '', div: r.masterformat?.division ?? '' };
    const mk = (label: string, opts: Array<[string, string]>, get: () => string, set: (v: string) => void): HTMLElement => {
      const w = pick(label, opts.map(([value, text]) => ({ value, text })), get, set);
      w.update();
      return w.root;
    };
    const subOpts = (): Array<[string, string]> => [['', '(none)'], ...(svc.schema.disciplines.find((x) => x.code === draftOverride.disc)?.subDisciplines ?? []).map((s): [string, string] => [s.code, `${s.code} ${s.label}`])];
    const holder = el('div', 'xt-list');
    const fill = (): void => {
      holder.replaceChildren(
        mk('Override discipline', svc.schema.disciplines.map((x): [string, string] => [x.code, `${x.code} ${x.label}`]), () => draftOverride.disc, (v) => { draftOverride.disc = v; draftOverride.sub = ''; fill(); }),
        mk('Override sub-discipline', subOpts(), () => draftOverride.sub, (v) => { draftOverride.sub = v; }),
        mk('Override division', [['', '(none)'], ...svc.schema.masterformat.divisions.map((x): [string, string] => [x.division, `${x.division} ${x.title}`])], () => draftOverride.div, (v) => { draftOverride.div = v; }),
      );
    };
    fill();
    const msg = el('div', 'xt-note xc-err');
    msg.hidden = true;
    editor.append(
      el('div', 'xt-note', undefined, `Set by hand: ${name}`),
      holder,
      msg,
      row(
        button('Apply override', () => {
          try {
            svc.override(r.id, { discipline: draftOverride.disc, subDiscipline: draftOverride.sub || null, masterformat: draftOverride.div || null });
            closeEditor();
          } catch (e) {
            msg.hidden = false;
            msg.textContent = e instanceof Error ? e.message : String(e);
          }
        }, { primary: true, title: 'Keep these codes for this element. A manual result wins over every other source.' }),
        button('Remove override', () => { svc.removeOverride(r.id); closeEditor(); }, { title: 'Delete the manual result of this element' }),
        button('Cancel', closeEditor),
      ),
    );
  };

  const renderTable = (): void => {
    const min = svc.minConfidence();
    let list = svc.results();
    const total = list.length;
    if (filter.has('low')) list = list.filter((r) => overallConfidence(r) < min);
    if (filter.has('review')) list = list.filter((r) => r.needsReview);
    list = [...list].sort((a, b) => Number(b.needsReview) - Number(a.needsReview) || overallConfidence(a) - overallConfidence(b));
    countLine.set(total === 0 ? 'No results yet' : `${list.length} of ${total} shown${list.length > MAX_ROWS ? `, first ${MAX_ROWS}` : ''}. ${svc.stats().needsReview} need review.`);
    tbody.replaceChildren();
    const m = svc.model;
    for (const r of list.slice(0, MAX_ROWS)) {
      const id = m?.byGlobalId.get(r.id);
      const tr = el('tr');
      tr.dataset['gid'] = r.id;
      const cell = (t: string, cls?: string, title?: string): HTMLTableCellElement => {
        const td = el('td', cls, undefined, t);
        if (title) td.title = title;
        return td;
      };
      const rec = id === undefined ? undefined : m?.elements[id];
      tr.append(
        cell(rec?.name || r.id, undefined, `${rec?.ifcClass ?? ''} ${r.id}`),
        cell(r.discipline.code, undefined, r.discipline.label),
        cell(r.subDiscipline?.code ?? '', undefined, r.subDiscipline?.label),
        cell(r.masterformat?.division ?? '', undefined, r.masterformat?.title),
        cell(fmt2(overallConfidence(r)), r.needsReview ? 'xc-review' : undefined, r.needsReview ? 'Needs review' : ''),
        cell(topTwo(r.discipline.probabilities).map(([k, v]) => `${k} ${fmt2(v)}`).join(' '), 'xc-top2', r.rationale ?? ''),
        cell(r.source, undefined, r.model ? `Model: ${r.model}` : r.rationale ?? ''),
      );
      const tdEdit = el('td');
      const eb = el('button', 'xc-edit', { type: 'button', 'aria-label': `Edit ${rec?.name || r.id}`, title: 'Set the codes by hand' }, '✎');
      eb.addEventListener('click', (ev) => { ev.stopPropagation(); openEditor(r); });
      tdEdit.appendChild(eb);
      tr.appendChild(tdEdit);
      tr.addEventListener('click', () => { if (id !== undefined) app.selectIds([id]); });
      tbody.appendChild(tr);
    }
    if (editId && !svc.results().some((r) => r.id === editId)) closeEditor();
  };

  // ---- output
  box.appendChild(section('Output'));
  const legend = el('div', 'xc-legend');
  const colour = add(check('Colour by discipline', () => tint.on, (v) => { tint.set(v); renderLegend(); }));
  const renderLegend = (): void => {
    legend.replaceChildren();
    if (!tint.on) return;
    const seen = new Set(svc.results().map((r) => r.discipline.code));
    for (const dsc of svc.schema.disciplines) {
      if (!seen.has(dsc.code)) continue;
      const s = el('span');
      const dot = el('span', 'xt-dot');
      dot.style.background = rgbCss(disciplineRgb(dsc.code));
      s.append(dot, document.createTextNode(`${dsc.code} ${dsc.label}`));
      legend.appendChild(s);
    }
  };
  box.append(
    colour.root,
    legend,
    row(
      button('Select needs review', () => { const n = api.selectNeedsReview(); infoMsg = `${n} element${n === 1 ? '' : 's'} need review and ${n === 1 ? 'is' : 'are'} selected.`; svc.notify(); }, { title: 'Select every element that needs review' }),
      button('Save needs-review set', () => {
        const n = propertyNames(svc.schema);
        openCriteriaSetEditor(`${quoteIdent(`${svc.schema.psetName}.${n.needsReview}`)} = TRUE`, 'Needs review');
      }, { title: 'Save a criteria set of the elements that need review' }),
    ),
    row(
      button('Export CSV', () => downloadText(`classification-${app.modelName}.csv`, svc.export('csv')), { title: 'Save the results as a CSV file' }),
      button('Export JSON', () => downloadText(`classification-${app.modelName}.json`, svc.export('json'), 'application/json'), { title: 'Save the results as a JSON file' }),
    ),
    row(
      button('Export Throughline JSON', () => downloadText(`classification-${app.modelName}.throughline.json`, svc.export('throughline'), 'application/json'), { title: 'Save the results in the shape of a Throughline Discipline code list' }),
    ),
    row(
      button('Clear results', () => { svc.clear(); tint.apply(); }, { title: 'Remove the results and the written properties. Manual overrides stay.' }),
      button('Clear cache', () => svc.clearCache(), { title: 'Forget the stored decisions of this model' }),
    ),
  );

  // ---- refresh
  let estTimer: ReturnType<typeof setTimeout> | null = null;
  const estimateNow = (): void => {
    estTimer = null;
    const m = svc.model;
    if (!m) { estimateEl.set('No model loaded'); return; }
    const o: RunOptions = useRulesOn ? {} : { rules: false };
    const line = (label: string, e: ReturnType<typeof svc.estimate>): string =>
      `${label}: ${e.elements} elements, ${e.byRules} by rules, ${e.cached} cached, ${e.manual} manual. ${e.signatures} signature${e.signatures === 1 ? '' : 's'}, ${e.signatures === 0 ? '0' : `${e.callsMin} to ${e.calls}`} request${e.calls === 1 ? '' : 's'}.`;
    const s = svc.estimate('selection', o);
    const lines = [line('Selection', s)];
    lines.push(m.elements.length <= 30000 ? line('All', svc.estimate('all', o)) : `All: ${m.elements.length} elements (the estimate is skipped above 30000).`);
    svc.lastEstimate = s;
    estimateEl.set(d().provider === 'off' ? `${lines.join('\n')}\nProvider is off: elements without a final rule stay unclassified.` : lines.join('\n'));
  };
  const scheduleEstimate = (): void => {
    if (estTimer) clearTimeout(estTimer);
    estTimer = setTimeout(estimateNow, 120);
  };

  let cacheFor: string | null = null;
  let loadSeen: unknown = null;
  const show = (e: HTMLElement, on: boolean): void => { e.hidden = !on; e.style.display = on ? 'flex' : 'none'; };
  const refresh = (): void => {
    for (const w of widgets) w.update();
    const p = d().provider;
    show(jev, p === 'jev');
    show(web, p === 'webllm');
    show(dec, p === 'decision');
    showIssues(svc.issues.errors, svc.issues.warnings);
    testBtn.style.display = p === 'decision' ? 'none' : '';
    testModelBtn.style.display = p === 'decision' ? '' : 'none';
    clearCacheBtn.style.display = p === 'decision' ? '' : 'none';
    testBtn.setDisabled(p === 'off' ? 'Choose a provider first' : false);
    // decision model
    if (p === 'decision') {
      decInfo.textContent = `${describeDecisionModel(d().hfModel, d().dtype)}${decisionModelInfo(d().hfModel) ? '' : ' A model that is not in the list is checked before it downloads: it must be a zero-shot or NLI model.'}`;
      if (!svc.gpu) void svc.probeGpu().then(() => svc.notify());
      decRuntime.textContent = svc.runtimeNote();
      const pr = svc.decisionProgress;
      decBar.style.width = pr ? `${Math.round(pr.progress * 100)}%` : '0';
      decProgLine.set(pr ? pr.text : '');
      if (cacheFor !== 'decision' || loadSeen !== svc.lastLoad) { cacheFor = 'decision'; loadSeen = svc.lastLoad; void paintCache(); }
    } else cacheFor = null;
    // browser chat model
    webInfo.textContent = `${d().webllmMode === 'chat' || d().webllmMode === 'hybrid' ? describeModel(d().webllmModel) : ''}${d().webllmMode !== 'chat' ? ` ${describeModel(d().webllmEmbedModel)}.` : ''} The browser loads the library and the models on first use and keeps them in its cache.${webllmModelInfo(d().webllmModel) ? '' : ' This model id is not in the tested list.'}`.trim();
    webModel.root.style.display = d().webllmMode === 'embed' ? 'none' : '';
    webEmbed.root.style.display = d().webllmMode === 'chat' ? 'none' : '';
    webTemp.root.style.display = d().webllmMode === 'chat' ? 'none' : '';
    webMargin.root.style.display = d().webllmMode === 'hybrid' ? '' : 'none';
    const cm = customModelCheck(d().webllmCustomModel, d().webllmCustomLib);
    webCustomNote.textContent = [...cm.errors, ...cm.warnings].join(' ');
    webCustomNote.hidden = webCustomNote.textContent === '';
    if (p === 'webllm') void detectWebGpu().then((g) => { gpuNote.textContent = g.ok ? 'WebGPU is available.' : g.reason; gpuNote.classList.toggle('xc-err', !g.ok); });
    else gpuNote.textContent = '';
    const s = svc.schema;
    schemaLine.set(`${s.title}${svc.customSchema ? '' : ' (built in)'}${s.placeholder ? ' - PLACEHOLDER, replace it with your own schema' : ''}. ${s.disciplines.length} disciplines, ${s.masterformat.divisions.length} divisions. Property set ${s.psetName}.${svc.customSchema ? '' : ' Load the Discipline code list of your company standards to replace it.'}`);
    schemaLine.classList.toggle('xc-warn', s.placeholder === true);
    schemaNotes.textContent = svc.importNotes.join(' ');
    schemaNotes.hidden = svc.importNotes.length === 0;
    paintKey();
    hfTok.paint();
    const running = svc.running;
    bSel.setDisabled(running ? 'A run is in progress' : false);
    bAll.setDisabled(running ? 'A run is in progress' : false);
    bStop.setDisabled(running ? false : 'Nothing is running');
    const pr = svc.progress;
    if (running && pr) {
      bar.style.width = `${pr.total ? Math.round((pr.done / pr.total) * 100) : 0}%`;
      progLine.set(`Classifying: ${pr.done} of ${pr.total}. Rules ${pr.bySource.rules}, cache ${pr.bySource.cache}, model ${pr.bySource.model}. Requests ${pr.calls} of about ${pr.callsPlanned * 2}.`);
    } else if (!running) {
      bar.style.width = svc.lastStats ? '100%' : '0';
      const st = svc.lastStats;
      const ds = svc.decisionStats();
      const decText = ds && ds.requests ? ` Decision model: ${ds.pairs} text pairs in ${ds.passes} passes${ds.cachedPairs ? `, ${ds.cachedPairs} from the pair cache` : ''}.` : '';
      progLine.set(runMsg ?? infoMsg ?? (st ? `${summaryText(st, svc.results().length)}${decText}${st.errors[0] ? ` ${st.errors[0]}` : ''}` : ''));
      progLine.classList.toggle('xc-err', !!runMsg || (!!st && st.failed > 0));
    }
    renderTable();
    renderLegend();
    scheduleEstimate();
  };

  let raf = 0;
  const off = svc.onChange(() => {
    if (raf) return;
    raf = requestAnimationFrame(() => { raf = 0; refresh(); });
  });
  const onSel = (): void => scheduleEstimate();
  document.addEventListener('xray-selection', onSel);
  refresh();
  return () => {
    off();
    if (raf) cancelAnimationFrame(raf);
    if (estTimer) clearTimeout(estTimer);
    document.removeEventListener('xray-selection', onSel);
  };
}

function summaryText(st: ClassifyStats | null, n: number): string {
  if (!st) return `${n} results.`;
  const b = st.bySource;
  return `${n} classified: rules ${b.rules}, cache ${b.cache}, model ${b.model}, manual ${b.manual}. ${st.calls} request${st.calls === 1 ? '' : 's'} for ${st.signatures} signature${st.signatures === 1 ? '' : 's'}. ${st.needsReview} need review.${st.aborted ? ' Stopped.' : ''}`;
}

// ---------------------------------------------------------------- plugin

let svc: ClassifyService | null = null;
let tint: Tint | null = null;
let lastSelKey = '';

export const classifyPlugin: AppPlugin = {
  name: 'classify',
  install(app) {
    const service = new ClassifyService({
      storage: localStore(),
      keyStorages: browserKeyStorages(),
      selection: () => app.selection,
    });
    svc = service;
    tint = new Tint(app, service);
    const t = tint;

    const sectionApi = {
      collect: () => service.collect(),
      apply(value: unknown, bad: string[], path: string): void {
        const c = service.applySettings(value);
        for (const e of c.errors) bad.push(`${path} (${e})`);
        const url = service.settings().schemaUrl;
        if (url) void service.loadSchemaUrl(url).then((errs) => { for (const e of errs) app.showMessage(`Classify schema: ${e}`); });
      },
    };
    registerParamSection('classify', sectionApi);

    const api: ClassifyApi = {
      classify: (target, opts) => service.classify(target, opts),
      classifyInputs: (inputs, opts) => service.classifyInputs(inputs, opts),
      buildInput: (id) => service.buildInput(id),
      questions: (input, discipline) => {
        const i = typeof input === 'object' ? input : service.buildInput(input);
        if (!i) throw new Error('No such element.');
        return service.questions(i, discipline);
      },
      schema: () => service.schema,
      setSchema: (json) => service.setSchema(json, false),
      results: () => service.results(),
      override: (id, partial) => service.override(id, partial),
      clear: () => { service.clear(); t.apply(); },
      export: (kind) => service.export(kind),
      abort: () => service.abort(),
      stats: () => service.stats(),
      estimate: (target, opts) => service.estimate(target, opts),
      configure: (patch) => {
        const c = service.patch(patch as never);
        return { errors: c.errors, warnings: c.warnings };
      },
      settings: () => service.settings(),
      setKey: (key, remember) => service.keys.set(key, remember === true),
      keyState: () => ({ set: !!service.keys.get(), remembered: service.keys.remembered(), mask: service.keys.mask() }),
      testConnection: () => service.testConnection(),
      testModel: () => service.testModel(),
      setHfToken: (token, remember) => service.hfToken.set(token, remember === true),
      hfTokenState: () => ({ set: !!service.hfToken.get(), remembered: service.hfToken.remembered(), mask: service.hfToken.mask() }),
      modelCache: () => service.modelCacheInfo(),
      clearModelCache: () => service.clearModelCache(),
      decisionStats: () => service.decisionStats(),
      webllmStats: () => service.webllmStats(),
      importThroughline: (json) => {
        const errors = service.importThroughline(json);
        return { errors, warnings: [...service.importNotes] };
      },
      selectNeedsReview: () => {
        const ids = service.needsReviewIds();
        app.selectIds(ids);
        return ids.length;
      },
      colourByDiscipline: (on) => {
        if (on !== undefined) { t.set(on); service.notify(); }
        return t.on;
      },
      state: () => ({ running: service.running, provider: service.draft.provider, model: service.modelId(), schemaTitle: service.schema.title, placeholder: service.schema.placeholder === true, hash: service.schemaHashValue }),
    };
    window.__xrayClassify = api;

    service.onChange(() => { if (t.on && !service.running) t.apply(); });

    registerTool({
      id: 'classify', label: 'Classify', title: 'Label elements by discipline, sub-discipline and MasterFormat division', icon: ICONS.classify, order: 115, drawerWidth: 480,
      panel: (box, a) => panel(box, a, service, t, api),
    });
    registerAction({ id: 'classify.selection', label: 'Classify: selection', group: 'Tools', keys: [], run: () => void api.classify('selection') });
    registerAction({ id: 'classify.all', label: 'Classify: all elements', group: 'Tools', keys: [], run: () => void api.classify('all') });
    registerAction({ id: 'classify.review', label: 'Classify: select elements that need review', group: 'Tools', keys: [], run: () => void api.selectNeedsReview() });
    registerAction({ id: 'classify.stop', label: 'Classify: stop', group: 'Tools', keys: [], run: () => api.abort() });
    registerAction({ id: 'classify.colour', label: 'Classify: colour by discipline', group: 'Tools', keys: [], run: () => api.colourByDiscipline(!t.on) });
  },
  onModel(app) {
    const service = svc;
    if (!service || !app.loaded) return;
    tint?.forget();
    if (tint) tint.on = false;
    service.setModel(app.controller.model, app.modelName); // notifies the drawer
    lastSelKey = '';
    const url = service.settings().schemaUrl;
    if (url && !service.customSchema) void service.loadSchemaUrl(url);
  },
  onStatic(app) {
    // The drawer listens for this event to refresh its estimate when the selection changed.
    const key = [...app.controller.selection].join(',');
    if (key !== lastSelKey) {
      lastSelKey = key;
      document.dispatchEvent(new Event('xray-selection'));
    }
  },
};
