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
import { D3_NO_WEBGPU, chooseD3Runtime } from '../classify/providers/d3';
import { D3_BACKENDS, D3_DEVICES, IMAGE_MARGIN_MAX, IMAGE_MARGIN_MIN, IMAGE_MODES, IMAGE_SIZE_MAX, IMAGE_SIZE_MIN, IMAGE_SIZE_STEP, IMAGE_STYLES } from '../classify/providers/d3Config';
import { TEMPERATURE_KEYS } from '../classify/calibrate';
import type { QuestionReport, TemperatureKey } from '../classify/calibrate';
import type { CalibrationReport } from '../classify/calibrateRules';
import { renderThumbs, thumbKey, disposeThumbRenderer } from '../classify/thumbs';
import { buildGeometry, previewSvg } from '../classify/geometrySvg';
import type { GeoSource } from '../classify/geometrySvg';
import { GEOMETRY_TEXT_MODES } from '../classify/providers/d3Config';
import type { ThumbSet, ThumbSource } from '../classify/thumbs';
import type { DecisionStats, ModelCacheInfo } from '../classify/providers/decision';
import type { WebLlmStats } from '../classify/providers/webllm';
import type { ApiKeyStore } from '../classify/keyStore';
import { topTwo, overallConfidence } from '../classify/review';
import { browserKeyStorages } from '../classify/keyStore';
import { ClassifyService } from '../classify/service';
import type { CalibrationStatus } from '../classify/calibrationStatus';
import type { ModelTest, RunOptions, Target } from '../classify/service';
import { PROVIDERS, RULES_MODES } from '../classify/settings';
import type { ProviderId } from '../classify/settings';
import { D3_DEFAULTS, JEV_DEFAULTS } from '../classify/settings';
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
  /** The temperatures in use, the mode and the numbers of the last fit. */
  calibration(): CalibrationStatus;
  /** Fit one temperature per question on the elements that the rules labelled in this model (held-out numbers in the report). */
  calibrate(opts?: { maxSignatures?: number; heldOut?: number }): Promise<CalibrationReport>;
  forgetFit(): void;
  /** The API key of a d3 endpoint (its own entry; never in params, links, views or packed pages). */
  setD3Key(key: string, remember?: boolean): void;
  d3KeyState(): { set: boolean; remembered: boolean; mask: string };
  /** The person confirms the download of the d3 browser files (about 1 GB). */
  confirmD3Download(): void;
  /** The pictures that the model would see for an element (data URLs). Needs the picture settings of a provider that sends images. */
  thumbnails(id: number | string): Promise<ThumbSet>
  /** The SVG geometry the model would read for an element (needs geometryText on a provider that sends it). */
  geometry(id: number | string): import('../classify/geometrySvg').GeometrySet
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
.xc-confirm{display:flex;flex-direction:column;gap:6px;padding:8px;border:1px solid #b8862b;border-radius:4px;background:#17130a}
.xc-confirm[hidden],.xc-thumbs[hidden],.xc-cal[hidden]{display:none}
.xc-thumbs{display:flex;flex-wrap:wrap;gap:6px}
.xc-thumbs figure{margin:0;display:flex;flex-direction:column;gap:2px;font-size:11px;color:var(--sb-dim,#8d99a8)}
.xc-thumbs img{display:block;max-width:100%;height:auto;border:1px solid var(--sb-line,#262d3a);border-radius:3px;background:#eef1f5}
.xc-cal{display:flex;flex-direction:column;gap:4px;overflow-x:auto}
.xc-caltable{border-collapse:collapse;font-size:11px;white-space:nowrap}
.xc-caltable th,.xc-caltable td{padding:2px 6px;border-bottom:1px solid var(--sb-line,#262d3a);text-align:right}
.xc-caltable th:first-child,.xc-caltable td:first-child{text-align:left}
.xc-caltable tr.xc-after td{color:#9fe3b0}
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

const D3_LABEL = { browser: 'In the browser (WebGPU)', endpoint: 'Endpoint (System One server)' } as const;
const IMAGE_LABEL: Record<(typeof IMAGE_MODES)[number], string> = { off: 'Off (text only)', isolated: 'The element alone', context: 'The element in its bounding box', both: 'Both pictures' };
const STYLE_LABEL: Record<(typeof IMAGE_STYLES)[number], string> = { render: 'Render (shaded)', vector: 'Line drawing (black on white)' };
const TEMP_LABEL: Record<TemperatureKey, string> = { discipline: 'Temperature: discipline', sub_discipline: 'Temperature: sub-discipline', masterformat: 'Temperature: division', building_element: 'Temperature: building' };
const QUESTION_LABEL: Record<string, string> = { discipline: 'Discipline', sub_discipline: 'Sub-discipline', masterformat: 'Division', building_element: 'Building' };
const CAL_MODE_LABEL = { auto: 'Auto (numbers shipped for this model)', fitted: 'Fitted on this model', manual: 'Manual', off: 'Off (the model as it comes)' } as const;
const pct = (x: number): string => (Number.isFinite(x) ? `${Math.round(x * 100)}%` : '-');

const PROVIDER_LABEL: Record<ProviderId, string> = {
  off: 'Off (rules and cache only)',
  decision: 'Decision model (in browser, WebGPU)',
  d3: 'Decision 3.0 d3-edge',
  webllm: 'Browser chat model (WebLLM)',
  jev: 'Jev (HTTP)',
  mock: 'Mock (tests)',
};

const fmtMB = (b: number): string => (b >= 1e9 ? `${(b / 1e9).toFixed(2)} GB` : `${Math.round(b / 1e5) / 10} MB`);

/** A password box for a secret, with Save and Forget and a "remember" switch. The secret is never shown again. */
function secretField(
  add: <W extends Widget>(w: W) => W,
  o: { label: string; aria: string; name: string; store: ApiKeyStore | (() => ApiKeyStore); status: string; remember: string; save: string; forget: string; saveTitle: string; forgetTitle: string },
): { nodes: HTMLElement[]; paint(): void } {
  const box = el('label', 'xt-select');
  const input = el('input', 'xc-text', { type: 'password', autocomplete: 'off', spellcheck: 'false', 'aria-label': o.aria, placeholder: 'not shown after saving', name: o.name });
  box.append(el('span', 'xt-lbl', undefined, o.label), input);
  const st = (): ApiKeyStore => (typeof o.store === 'function' ? o.store() : o.store);
  const status = statusLine('');
  const remember = add(check(o.remember, () => st().remembered(), (v) => {
    const k = input.value.trim() || st().get();
    if (k) st().set(k, v);
    paint();
  }));
  const save = (): void => {
    if (input.value.trim()) st().set(input.value, (remember.root.querySelector('input') as HTMLInputElement).checked);
    input.value = '';
    paint();
  };
  input.addEventListener('change', save);
  const paint = (): void => {
    status.set(`${o.status}: ${st().mask()}${st().remembered() ? ', kept on this device' : st().get() ? ', kept for this tab only' : ''}`);
    remember.update();
  };
  return {
    nodes: [
      box, remember.root, status,
      row(
        button(o.save, save, { title: o.saveTitle }),
        button(o.forget, () => { st().clear(); input.value = ''; paint(); }, { title: o.forgetTitle }),
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

/** The before and after numbers of a fit, held out: accuracy, mean confidence, ECE, the share that clears the minimum and its accuracy. */
function calTable(qs: QuestionReport[], source: string, min: number): HTMLElement {
  const wrap = el('div');
  const t = el('table', 'xc-caltable');
  const head = el('tr');
  for (const h of ['Question', 'n', 'T', 'Right', 'Conf.', 'ECE', `Clear ${fmt2(min)}`, 'Of clear']) head.appendChild(el('th', undefined, undefined, h));
  t.appendChild(el('thead')).appendChild(head);
  const body = el('tbody');
  for (const q of qs) {
    const mk = (cls: string, label: string, T: string, m: QuestionReport['before']): HTMLElement => {
      const tr = el('tr', cls);
      for (const c of [label, `${q.nTest || q.nTrain}`, T, pct(m.accuracy), fmt2(m.meanConfidence), fmt2(m.ece), pct(m.clearShare), pct(m.clearAccuracy)]) tr.appendChild(el('td', undefined, undefined, c));
      return tr;
    };
    body.append(mk('xc-before', `${QUESTION_LABEL[q.question] ?? q.question}, before`, '1', q.before), mk('xc-after', 'after', fmt2(q.T), q.after));
  }
  t.appendChild(body);
  wrap.append(
    t,
    el('div', 'xt-note', undefined, `n is the number of signatures. Conf. is the mean confidence. Of clear is the accuracy of the answers that clear the minimum. Numbers on ${qs[0] && qs[0].nTest ? 'the held-out share' : 'the signatures used for the fit (too few to hold any out)'} of the kinds of element that the rules label${source ? ` in ${source}` : ''}. The rules are proxy labels, not the truth: a rule can be wrong. ECE is the expected calibration error: lower is better.`),
  );
  return wrap;
}

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
  dec.append(decPreset.root, decModelId.root, decDevice.root, decDtype.root, decInfo, decRuntime, decProg, decProgLine, cacheLine, advDec);
  box.appendChild(dec);

  // Decision 3.0 d3-edge: in the browser (onnxruntime-web, WebGPU) or on a System One endpoint
  const d3g = el('div', 'xc-group');
  d3g.setAttribute('data-for', 'd3');
  d3g.style.cssText = 'display:flex;flex-direction:column;gap:6px';
  const d3Backend = add(pick('Backend', D3_BACKENDS.map((v) => ({ value: v, text: D3_LABEL[v] })), () => d().d3Backend, (v) => apply({ d3Backend: v })));
  const d3Browser = el('div', 'xc-group');
  d3Browser.style.cssText = 'display:flex;flex-direction:column;gap:6px';
  const d3Info = el('div', 'xt-note');
  const d3Runtime = el('div', 'xt-note');
  d3Runtime.setAttribute('role', 'status');
  const d3Prog = el('div', 'xc-prog');
  const d3Bar = el('i');
  d3Prog.appendChild(d3Bar);
  const d3ProgLine = statusLine('');
  const d3CacheLine = statusLine('');
  const d3Confirm = el('div', 'xc-confirm');
  d3Confirm.hidden = true;
  const d3ConfirmText = el('div', 'xt-note');
  d3Confirm.append(
    d3ConfirmText,
    row(
      button('Download model', () => { d3Confirm.hidden = true; svc.confirmD3Download(); runTestModel(); }, { primary: true, title: 'Download the model files and test them' }),
      button('Cancel', () => { d3Confirm.hidden = true; conn.set('The download was cancelled.'); }, { title: 'Do not download' }),
    ),
  );
  const advD3 = details('Advanced: file address');
  advD3.append(
    add(textField('File address', () => d().d3HfEndpoint, (v) => apply({ d3HfEndpoint: v.trim() }), { type: 'url', placeholder: 'https://huggingface.co' })).root,
    note('Use another address for a mirror or your own proxy. A token goes to this address only.'),
  );
  d3Browser.append(
    add(textField('Model repository', () => d().d3Repo, (v) => apply({ d3Repo: v.trim() }), { placeholder: 'owner/name, or the web address of an export folder' })).root,
    add(textField('Revision', () => d().d3Revision, (v) => apply({ d3Revision: v.trim() }), { placeholder: 'a commit hash of 40 characters (a label for a folder)' })).root,
    add(pick('Run on', D3_DEVICES.map((v) => ({ value: v, text: v === 'auto' ? 'Auto (WebGPU with shader-f16)' : v === 'webgpu' ? 'WebGPU' : 'WASM (very slow, about 5 GB of memory)' })), () => d().d3Device, (v) => apply({ d3Device: v }))).root,
    d3Info, d3Runtime, d3Confirm, d3Prog, d3ProgLine, d3CacheLine, advD3,
  );
  d3g.append(d3Backend.root, d3Browser);
  box.appendChild(d3g);

  // One token box for the models that come from Hugging Face (the decision model and d3 in the browser)
  const tokBox = el('div', 'xc-group');
  tokBox.style.cssText = 'display:flex;flex-direction:column;gap:6px';
  tokBox.append(...hfTok.nodes);
  box.appendChild(tokBox);

  // A server that speaks the Jev wire format: Jev, or d3-edge on a System One endpoint. The same boxes edit the fields of the provider in use.
  const isD3 = (): boolean => d().provider === 'd3';
  const jev = el('div', 'xc-group');
  jev.setAttribute('data-for', 'jev');
  jev.style.cssText = 'display:flex;flex-direction:column;gap:6px';
  const srvEndpoint = add(textField('Endpoint', () => (isD3() ? d().d3Endpoint : d().endpoint), (v) => apply(isD3() ? { d3Endpoint: v.trim() } : { endpoint: v.trim() }), { type: 'url', placeholder: JEV_DEFAULTS.endpoint }));
  const srvModel = add(textField('Model id', () => (isD3() ? d().d3Model : d().model), (v) => apply(isD3() ? { d3Model: v.trim() } : { model: v.trim() }), { placeholder: JEV_DEFAULTS.model }));
  jev.append(
    srvEndpoint.root, srvModel.root,
    add(numField('Requests at once', 1, 16, 1, () => d().concurrency, (v) => apply({ concurrency: v }))).root,
    add(numField('Timeout (ms)', 1000, 300000, 1000, () => d().timeoutMs, (v) => apply({ timeoutMs: v }))).root,
  );
  // API key: Jev and d3 keep theirs in separate entries, so a Jev key never goes to a d3 server
  const jevKey = secretField(add, {
    label: 'API key', aria: 'API key', name: 'xray-classify-key', store: () => (isD3() ? svc.d3Key : svc.keys), status: 'API key', remember: 'Remember on this device',
    save: 'Save key', forget: 'Forget key', saveTitle: 'Keep the key typed above', forgetTitle: 'Remove the key from this browser',
  });
  const srvNote = note('A key in a page can be read by anyone who uses this browser. For a shared viewer, use a same-origin proxy as the endpoint and leave the key empty.');
  const d3Hint = note('Start the server with vllm-sr serve -e vllm-sr/d3-edge. Leave the key box empty when the server needs no key. The key is kept apart from the Jev key.');
  const jevImages = add(check('Send images to Jev', () => d().jevImages, (v) => apply({ jevImages: v })));
  const jevImagesNote = note('Untested: Jev is not known to read images. Turn it on only for a server that does. The pictures follow the settings in the Pictures section.');
  jev.append(...jevKey.nodes, srvNote, d3Hint, jevImages.root, jevImagesNote);
  const paintKey = jevKey.paint;
  box.appendChild(jev);
  // The cap of the state that goes into a request: Jev and d3 (both backends)
  const capBox = el('div', 'xc-group');
  capBox.style.cssText = 'display:flex;flex-direction:column;gap:6px';
  capBox.append(add(numField('State size cap (bytes)', 500, 64000, 500, () => (isD3() ? d().d3MaxStateBytes : d().maxStateBytes), (v) => apply(isD3() ? { d3MaxStateBytes: v } : { maxStateBytes: v }))).root);
  box.appendChild(capBox);

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
  const runTestModel = (): void => {
    conn.set('Loading the model...');
    conn.classList.remove('xc-err');
    void svc.testModel().then((r) => {
      conn.set(r.message);
      conn.classList.toggle('xc-err', !r.ok);
      void paintCache();
    });
  };
  // d3 in the browser downloads about 1 GB: ask first, with the size from the manifest.
  const askD3 = async (): Promise<void> => {
    // A device that cannot run the model gets the reason now, before any question about 1 GB.
    const gpu = await svc.probeGpu();
    try { chooseD3Runtime(d().d3Device, gpu); } catch (e) { conn.set(e instanceof Error ? e.message : String(e)); conn.classList.add('xc-err'); return; }
    const [ins, c] = await Promise.all([svc.inspectD3(), svc.d3CacheInfo()]);
    if (!ins.ok) { conn.set(ins.message); conn.classList.add('xc-err'); return; }
    if (svc.d3Confirmed || c.files >= 3) { runTestModel(); return; }
    d3ConfirmText.textContent = `The d3-edge model is not on this device. Testing it downloads ${fmtMB(ins.totalBytes)} from ${/^https?:\/\//i.test(d().d3Repo) ? d().d3Repo : d().d3HfEndpoint} (revision ${d().d3Revision.slice(0, 8)}) and keeps the files in the browser cache. `
      + 'The viewer checks every file against the size in the manifest, and the small files against their sha256.';
    d3Confirm.hidden = false;
  };
  const testModelBtn = button('Test model', () => {
    if (d().provider === 'd3' && d().d3Backend === 'browser') void askD3();
    else runTestModel();
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

  // ---- pictures (d3 endpoint, and Jev when its switch is on)
  const picSec = el('div', 'xc-group');
  picSec.style.cssText = 'display:flex;flex-direction:column;gap:6px';
  const picMode = add(pick('Images', IMAGE_MODES.map((v) => ({ value: v, text: IMAGE_LABEL[v] })), () => d().images, (v) => apply({ images: v })));
  const picStyle = add(pick('Picture style', IMAGE_STYLES.map((v) => ({ value: v, text: STYLE_LABEL[v] })), () => d().imageStyle, (v) => apply({ imageStyle: v })));
  const picPlan = add(check('Add a plan view', () => d().imagePlan, (v) => apply({ imagePlan: v })));
  const picMargin = add(numField('Box margin (%)', IMAGE_MARGIN_MIN, IMAGE_MARGIN_MAX, 5, () => d().imageMargin, (v) => apply({ imageMargin: v })));
  const picSize = add(numField('Image size', IMAGE_SIZE_MIN, IMAGE_SIZE_MAX, IMAGE_SIZE_STEP, () => d().imageSize, (v) => apply({ imageSize: v })));
  const picNote = el('div', 'xt-note');
  const thumbBox = el('div', 'xc-thumbs xc-pics');
  thumbBox.hidden = true;
  const thumbLine = statusLine('');
  picSec.append(picMode.root, picStyle.root, picPlan.root, picMargin.root, picSize.root, picNote, thumbLine, thumbBox);
  box.append(section('Pictures'), picSec);
  let thumbFor = '';
  const paintThumbs = (): void => {
    const st = svc.imageSettings();
    thumbBox.hidden = !st;
    thumbLine.hidden = !st;
    if (!st) { thumbFor = ''; thumbBox.replaceChildren(); return; }
    const sel = app.selection[0];
    const key = `${sel ?? ''}|${svc.modelName}|${thumbKey(st)}`;
    if (key === thumbFor) return;
    thumbFor = key;
    if (sel === undefined) { thumbBox.replaceChildren(); thumbLine.set('Select an element to see the pictures that the model gets.'); return; }
    thumbLine.set('Drawing the pictures...');
    thumbLine.classList.remove('xc-err');
    void svc.thumbnails(sel, st).then(
      (set) => {
        if (thumbFor !== key) return;
        thumbBox.replaceChildren(...set.thumbs.map((t) => {
          const fig = el('figure');
          const img = el('img', undefined, { alt: `Picture of the selected element: ${t.label}`, src: t.dataUrl, width: String(t.width), height: String(t.height) });
          fig.append(img, el('figcaption', undefined, undefined, `${t.label}, bar ${t.scaleBarM >= 1 ? `${t.scaleBarM} m` : `${Math.round(t.scaleBarM * 100)} cm`}`));
          return fig;
        }));
        thumbLine.set(`The model gets ${set.thumbs.length} picture${set.thumbs.length === 1 ? '' : 's'}${set.neighbours.length ? `, with ${set.neighbours.length} nearby element${set.neighbours.length === 1 ? '' : 's'} in the box` : ''}, and this note in the state: "${set.note}" The pictures are not saved anywhere.`);
      },
      (e: unknown) => { if (thumbFor === key) { thumbBox.replaceChildren(); thumbLine.set(e instanceof Error ? e.message : String(e)); thumbLine.classList.add('xc-err'); } },
    );
  };

  // ---- geometry as SVG text (jev, d3): what the model reads, rendered and as text
  const geoSec = el('div', 'xc-group');
  geoSec.style.cssText = 'display:flex;flex-direction:column;gap:6px';
  const geoMode = add(pick('Geometry as text', GEOMETRY_TEXT_MODES.map((v) => ({ value: v, text: v === 'off' ? 'Off' : 'SVG in the state' })), () => d().geometryText, (v) => apply({ geometryText: v })));
  const geoCtx = add(check('Add the element in its bounding box', () => d().geometryContext, (v) => apply({ geometryContext: v })));
  const geoNote = el('div', 'xt-note');
  const geoLine = statusLine('');
  const geoViews = el('div', 'xc-thumbs xc-geo');
  const geoText = el('pre');
  geoText.style.cssText = 'max-height:180px;overflow:auto;white-space:pre-wrap;word-break:break-all;font-size:10px;margin:0';
  geoViews.hidden = true;
  geoText.hidden = true;
  geoSec.append(geoMode.root, geoCtx.root, geoNote, geoLine, geoViews, geoText);
  box.append(section('Geometry'), geoSec);
  let geoFor = '';
  const paintGeometry = (): void => {
    const gs = svc.geometrySettings();
    geoViews.hidden = !gs;
    geoText.hidden = !gs;
    geoLine.hidden = !gs;
    if (!gs) { geoFor = ''; geoViews.replaceChildren(); geoText.textContent = ''; return; }
    const sel = app.selection[0];
    const key = `${sel ?? ''}|${svc.modelName}|${gs.context}|${gs.margin}`;
    if (key === geoFor) return;
    geoFor = key;
    if (sel === undefined) { geoViews.replaceChildren(); geoText.textContent = ''; geoLine.set('Select an element to see the geometry that the model reads.'); return; }
    try {
      const set = svc.geometryOf(sel, gs);
      geoViews.replaceChildren(...set.views.map((v) => {
        const fig = el('figure');
        const img = el('img', undefined, { alt: `Geometry of the selected element: ${v.name}`, src: `data:image/svg+xml;utf8,${encodeURIComponent(previewSvg(v.svg))}`, width: '180', height: '180' });
        img.style.cssText = 'background:#fff;object-fit:contain';
        fig.append(img, el('figcaption', undefined, undefined, v.name));
        return fig;
      }));
      geoText.textContent = `${set.legend}\n${set.svg}`;
      geoLine.set(`The model reads about ${set.tokens} tokens of geometry (${set.neighbours} nearby element${set.neighbours === 1 ? '' : 's'}), once for every question. The text below is exactly what goes into the state. It is not saved anywhere.`);
      geoLine.classList.remove('xc-err');
    } catch (e) { geoViews.replaceChildren(); geoText.textContent = ''; geoLine.set(e instanceof Error ? e.message : String(e)); geoLine.classList.add('xc-err'); }
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

  // ---- calibration (logit scaling)
  const calSec = el('div', 'xc-group');
  calSec.style.cssText = 'display:flex;flex-direction:column;gap:6px';
  const calMode = add(pick('Calibration', (['auto', 'fitted', 'manual', 'off'] as const).map((v) => ({ value: v, text: CAL_MODE_LABEL[v] })), () => d().calibration, (v) => apply({ calibration: v })));
  const calManual = el('div', 'xc-group');
  calManual.style.cssText = 'display:flex;flex-direction:column;gap:6px';
  for (const k of TEMPERATURE_KEYS) {
    calManual.appendChild(add(numField(TEMP_LABEL[k], 0.05, 50, 0.05, () => d().temperatures[k] ?? 1, (v) => {
      const t = { ...d().temperatures };
      if (Number.isFinite(v)) t[k] = v;
      else delete t[k];
      apply({ temperatures: t });
    })).root);
  }
  const calLine = statusLine('');
  calLine.style.whiteSpace = 'pre-line';
  const calReport = el('div', 'xc-cal');
  calReport.hidden = true;
  const calMsg = statusLine('');
  let calMsgText: string | null = null;
  let calBusy = false;
  const calBtn = button('Calibrate on rules', () => {
    calBusy = true;
    calMsgText = 'Fitting: the model runs for the kinds of element that the rules label...';
    calMsg.classList.remove('xc-err');
    svc.notify();
    void api.calibrate().then(
      (r) => { calBusy = false; calMsgText = `Done. The temperatures were fitted on ${r.scored} kinds of element that the rules label in ${r.source}.`; svc.notify(); },
      (e: unknown) => { calBusy = false; calMsgText = e instanceof Error ? e.message : String(e); calMsg.classList.add('xc-err'); svc.notify(); },
    );
  }, { title: 'Fit one temperature per question on the elements that the rules label in this model, and show the numbers before and after' });
  const calForget = button('Forget fit', () => { svc.forgetFit(); calMsgText = null; }, { title: 'Delete the fitted temperatures of this model' });
  calSec.append(calMode.root, calManual, calLine, row(calBtn, calForget), calMsg, calReport);
  box.append(section('Calibration'), calSec);
  const paintCal = (): void => {
    const st = svc.calibrationStatus();
    const p = d().provider;
    const on = p !== 'off' && p !== 'mock';
    calSec.hidden = !on;
    calSec.style.display = on ? 'flex' : 'none';
    calManual.style.display = d().calibration === 'manual' ? 'flex' : 'none';
    const tempsText = TEMPERATURE_KEYS.filter((k) => st.temperatures[k] !== undefined).map((k) => `${QUESTION_LABEL[k]} ${fmt2(st.temperatures[k]!)}`).join(', ');
    calLine.set(`In use: ${st.label}${tempsText ? `. Temperatures: ${tempsText}` : ''}.${st.note ? `\n${st.note}` : ''}\nA temperature below 1 sharpens the confidence, above 1 flattens it. The choice of the model never changes.`);
    calBtn.setDisabled(calBusy ? 'Fitting is in progress' : svc.running ? 'A run is in progress' : !svc.model ? 'Load a model first' : false);
    calForget.setDisabled(st.fitted ? false : 'No fit is stored for this model');
    calMsg.set(calMsgText ?? '');
    calMsg.hidden = !calMsgText;
    const qs = st.questions;
    calReport.hidden = qs.length === 0;
    if (qs.length === 0) { calReport.replaceChildren(); return; }
    calReport.replaceChildren(calTable(qs, st.source, svc.minConfidence()));
  };

  // ---- run
  box.appendChild(section('Run'));
  const estimateEl = statusLine('');
  estimateEl.style.whiteSpace = 'pre-line';
  const useRules = add(pick('Rules and model', RULES_MODES.map((v) => ({ value: v, text: v === 'final' ? 'Rules where certain, else the model' : 'The model for everything' })), () => d().rulesMode, (v) => { apply({ rulesMode: v }); scheduleEstimate(); }));
  const prog = el('div', 'xc-prog');
  const bar = el('i');
  prog.appendChild(bar);
  const progLine = statusLine('');
  let runMsg: string | null = null;
  let infoMsg: string | null = null;
  const run = (target: Target): void => {
    const opts: RunOptions = {};
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
    const o: RunOptions = {};
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
    const d3b = p === 'd3' && d().d3Backend === 'browser';
    show(jev, p === 'jev' || (p === 'd3' && !d3b));
    show(capBox, p === 'jev' || p === 'd3');
    show(web, p === 'webllm');
    show(dec, p === 'decision');
    show(d3g, p === 'd3');
    show(d3Browser, d3b);
    show(tokBox, p === 'decision' || d3b);
    srvNote.style.display = p === 'jev' ? '' : 'none';
    d3Hint.style.display = p === 'd3' ? '' : 'none';
    jevImages.root.style.display = p === 'jev' ? '' : 'none';
    jevImagesNote.style.display = p === 'jev' ? '' : 'none';
    srvEndpoint.input.placeholder = p === 'd3' ? D3_DEFAULTS.d3Endpoint : JEV_DEFAULTS.endpoint;
    srvModel.input.placeholder = p === 'd3' ? D3_DEFAULTS.d3Model : JEV_DEFAULTS.model;
    const local = p === 'decision' || d3b;
    showIssues(svc.issues.errors, svc.issues.warnings);
    testBtn.style.display = local ? 'none' : '';
    testModelBtn.style.display = local ? '' : 'none';
    clearCacheBtn.style.display = local ? '' : 'none';
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
    } else if (d3b) {
      if (!svc.gpu) void svc.probeGpu().then(() => svc.notify());
      void svc.inspectD3().then((ins) => {
        d3Info.textContent = ins.ok
          ? `Download ${fmtMB(ins.totalBytes)} (the model graph is ${fmtMB(ins.torsoBytes)}). This is an export of vllm-sr/d3-edge that ${ins.vision ? 'reads text and pictures' : 'reads text only'}${d().d3Repo === 'warsang/d3-edge-web' ? ' and comes from a third party' : ''}. It runs on WebGPU with 16-bit floats.`
          : ins.message;
        d3Info.classList.toggle('xc-err', !ins.ok);
      });
      d3Runtime.textContent = svc.gpu && !(svc.gpu.present && svc.gpu.adapter && svc.gpu.f16) && d().d3Device !== 'wasm' ? D3_NO_WEBGPU : svc.gpu ? 'WebGPU with 16-bit floats is available.' : '';
      d3Runtime.classList.toggle('xc-warn', !!svc.gpu && !(svc.gpu.present && svc.gpu.adapter && svc.gpu.f16));
      const pr = svc.decisionProgress;
      d3Bar.style.width = pr ? `${Math.round(pr.progress * 100)}%` : '0';
      d3ProgLine.set(pr ? pr.text : '');
      if (cacheFor !== 'd3' || loadSeen !== svc.lastLoad) { cacheFor = 'd3'; loadSeen = svc.lastLoad; void paintCache(); }
    } else cacheFor = null;
    // pictures
    const imgCapable = p === 'd3' || p === 'jev';
    picSec.style.display = imgCapable ? 'flex' : 'none';
    picSec.hidden = !imgCapable;
    const imgBlocked = d3b && !svc.visionNow() ? 'The d3 export in use reads text only. Use the endpoint backend, or an export with a vision graph.' : p === 'jev' && !d().jevImages ? 'Images are not sent to Jev. Turn on Send images to Jev first.' : '';
    for (const w of [picMode, picStyle, picPlan, picMargin, picSize]) for (const i of Array.from(w.root.querySelectorAll('input,select'))) (i as HTMLInputElement).disabled = imgBlocked !== '';
    const mode = d().images;
    const iso = mode === 'isolated' || mode === 'both';
    const ctxPic = mode === 'context' || mode === 'both';
    const nPics = (iso ? 1 : 0) + (iso && d().imagePlan ? 1 : 0) + (ctxPic ? 1 : 0);
    picNote.textContent = imgBlocked || (mode === 'off' ? 'Pictures are off: the model reads text only.' : `The model gets ${nPics} picture${nPics === 1 ? '' : 's'} of ${d().imageSize} pixels${iso ? `: the element alone${d().imagePlan ? ', then the same from above' : ''}` : ''}${ctxPic ? `${iso ? ', then' : ':'} the element in its bounding box with nearby elements in grey` : ''}.`);
    picNote.classList.toggle('xc-warn', imgBlocked !== '');
    picStyle.root.style.display = mode === 'off' ? 'none' : '';
    picPlan.root.style.display = mode === 'isolated' || mode === 'both' ? '' : 'none';
    picMargin.root.style.display = mode === 'context' || mode === 'both' ? '' : 'none';
    picSize.root.style.display = mode === 'off' ? 'none' : '';
    {
      const geoOk = p === 'jev' || p === 'd3';
      geoSec.style.display = geoOk ? 'flex' : 'none';
      geoSec.hidden = !geoOk;
      geoNote.textContent = geoOk ? (d().geometryText === 'off' ? 'Geometry text is off: the model gets no shape as text.' : 'The shape goes into the state as SVG markup in metres: plan and elevation of the element, and its bounding box with the elements around it.') : '';
      geoCtx.root.style.display = d().geometryText === 'off' ? 'none' : '';
      if (geoOk) paintGeometry();
    }
    paintThumbs();
    paintCal();
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
  const onSel = (): void => { scheduleEstimate(); paintThumbs(); paintGeometry(); };
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

// ---------------------------------------------------------------- pictures: the geometry of the loaded model

let thumbIds: { model: unknown; ids: number[] } | null = null;
function thumbSource(app: ViewerApp): ThumbSource {
  return {
    bounds: (id) => {
      const b = app.geometry?.bounds(id);
      return !b || b.isEmpty() ? null : [b.min.x, b.min.y, b.min.z, b.max.x, b.max.y, b.max.z];
    },
    mesh: (id) => app.geometry?.elementMesh(id) ?? null,
    ids: () => {
      const m = app.controller.model;
      if (thumbIds?.model !== m) thumbIds = { model: m, ids: m.elements.map((e) => e.id) };
      return thumbIds.ids;
    },
  };
}

/** The meshes and the class and tag of the elements for the SVG geometry (positions are copied out; the geometry is freed at once). */
function geoSource(app: ViewerApp): GeoSource {
  const t = thumbSource(app);
  return {
    bounds: t.bounds,
    ids: t.ids,
    mesh: (id) => {
      const g = t.mesh(id);
      if (!g) return null;
      const pos = g.getAttribute('position');
      const out = { position: Float32Array.from(pos.array as ArrayLike<number>), index: g.index ? Uint32Array.from(g.index.array as ArrayLike<number>) : null };
      g.dispose();
      return out;
    },
    info: (id) => {
      const e = app.controller.model.elements[id];
      const props = (e?.props ?? {}) as Record<string, unknown>;
      const str = (k: string): string | undefined => (typeof props[k] === 'string' && props[k] ? (props[k] as string) : undefined);
      const tag = str('Attr.Tag');
      const predefined = str('Attr.PredefinedType');
      return { ifcClass: e?.ifcClass ?? 'IfcProduct', ...(tag ? { tag } : {}), ...(predefined ? { predefined } : {}) };
    },
  };
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
      // Pictures of an element for a model that reads images: drawn off screen from the geometry of the loaded model.
      thumbnails: (id, ts) => renderThumbs(thumbSource(app), id, ts),
      geometry: (id, gs) => buildGeometry(geoSource(app), id, gs),
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
      calibration: () => service.calibrationStatus(),
      calibrate: (opts) => service.calibrateOnRules(opts),
      forgetFit: () => service.forgetFit(),
      setD3Key: (key, remember) => service.d3Key.set(key, remember === true),
      d3KeyState: () => ({ set: !!service.d3Key.get(), remembered: service.d3Key.remembered(), mask: service.d3Key.mask() }),
      confirmD3Download: () => service.confirmD3Download(),
      geometry: (id) => {
        const gs = service.geometrySettings();
        if (!gs) throw new Error('This provider sends no geometry with the current settings.');
        return service.geometryOf(id, gs);
      },
      thumbnails: (id) => {
        const st = service.imageSettings();
        if (!st) throw new Error('This provider sends no pictures with the current settings.');
        return service.thumbnails(id, st);
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
    disposeThumbRenderer();
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
