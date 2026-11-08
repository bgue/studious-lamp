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
import { detectWebGpu, describeModel, WEBLLM_MODELS, webllmModelInfo } from '../classify/providers/webllm';
import { topTwo, overallConfidence } from '../classify/review';
import { browserKeyStorages } from '../classify/keyStore';
import { ClassifyService } from '../classify/service';
import type { RunOptions, Target } from '../classify/service';
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
  export(kind: 'json' | 'csv'): string;
  abort(): void;
  stats(): ClassifyStats;
  /** Extras for scripts. */
  estimate(target: Target, opts?: RunOptions): unknown;
  configure(patch: Record<string, unknown>): { errors: string[]; warnings: string[] };
  settings(): unknown;
  setKey(key: string, remember?: boolean): void;
  keyState(): { set: boolean; remembered: boolean; mask: string };
  testConnection(): Promise<unknown>;
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

const PROVIDER_LABEL: Record<ProviderId, string> = { off: 'Off (rules and cache only)', jev: 'Jev (HTTP)', webllm: 'Browser model (WebLLM)', mock: 'Mock (tests)' };

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
  const keyBox = el('label', 'xt-select');
  const keyInput = el('input', 'xc-text', { type: 'password', autocomplete: 'off', spellcheck: 'false', 'aria-label': 'API key', placeholder: 'not shown after saving', name: 'xray-classify-key' });
  keyBox.append(el('span', 'xt-lbl', undefined, 'API key'), keyInput);
  const keyStatus = statusLine('');
  const remember = add(check('Remember on this device', () => svc.keys.remembered(), (v) => {
    const k = keyInput.value.trim() || svc.keys.get();
    if (k) svc.keys.set(k, v);
    paintKey();
  }));
  const saveKey = (): void => {
    if (keyInput.value.trim()) svc.keys.set(keyInput.value, (remember.root.querySelector('input') as HTMLInputElement).checked);
    keyInput.value = '';
    paintKey();
  };
  keyInput.addEventListener('change', saveKey);
  const paintKey = (): void => {
    keyStatus.set(`API key: ${svc.keys.mask()}${svc.keys.remembered() ? ', kept on this device' : svc.keys.get() ? ', kept for this tab only' : ''}`);
    remember.update();
  };
  jev.append(
    keyBox,
    remember.root,
    keyStatus,
    row(
      button('Save key', saveKey, { title: 'Keep the key typed above' }),
      button('Forget key', () => { svc.keys.clear(); keyInput.value = ''; paintKey(); }, { title: 'Remove the key from this browser' }),
    ),
    note('A key in a page can be read by anyone who uses this browser. For a shared viewer, use a same-origin proxy as the endpoint and leave the key empty.'),
  );
  box.appendChild(jev);

  // WebLLM
  const web = el('div', 'xc-group');
  web.setAttribute('data-for', 'webllm');
  web.style.cssText = 'display:flex;flex-direction:column;gap:6px';
  const webModel = add(pick('Browser model', WEBLLM_MODELS.map((m) => ({ value: m.id, text: m.label })), () => d().webllmModel, (v) => apply({ webllmModel: v })));
  const webInfo = el('div', 'xt-note');
  const gpuNote = el('div', 'xt-note');
  gpuNote.setAttribute('role', 'status');
  web.append(webModel.root, webInfo, gpuNote);
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
  box.append(row(testBtn), conn);

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
  box.append(
    schemaLine,
    row(
      button('Load schema file', () => file.click(), { title: 'Use your own xray-classification-schema/1 file' }),
      button('Use built-in schema', () => { svc.useDefaultSchema(); schemaIssues.hidden = true; }, { title: 'Go back to the shipped placeholder schema' }),
    ),
    file,
    schemaIssues,
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

  const refresh = (): void => {
    for (const w of widgets) w.update();
    const p = d().provider;
    jev.hidden = p !== 'jev';
    web.hidden = p !== 'webllm';
    jev.style.display = p === 'jev' ? 'flex' : 'none';
    web.style.display = p === 'webllm' ? 'flex' : 'none';
    showIssues(svc.issues.errors, svc.issues.warnings);
    testBtn.setDisabled(p === 'off' ? 'Choose a provider first' : false);
    webInfo.textContent = `${describeModel(d().webllmModel)}. The browser loads the library and the model on first use and keeps them in its cache.${webllmModelInfo(d().webllmModel) ? '' : ' This model id is not in the tested list.'}`;
    if (p === 'webllm') void detectWebGpu().then((g) => { gpuNote.textContent = g.ok ? 'WebGPU is available.' : g.reason; gpuNote.classList.toggle('xc-err', !g.ok); });
    else gpuNote.textContent = '';
    const s = svc.schema;
    schemaLine.set(`${s.title}${svc.customSchema ? '' : ' (built in)'}${s.placeholder ? ' - PLACEHOLDER, replace it with your own schema' : ''}. ${s.disciplines.length} disciplines, ${s.masterformat.divisions.length} divisions. Property set ${s.psetName}.`);
    schemaLine.classList.toggle('xc-warn', s.placeholder === true);
    paintKey();
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
      progLine.set(runMsg ?? infoMsg ?? (st ? `${summaryText(st, svc.results().length)}${st.errors[0] ? ` ${st.errors[0]}` : ''}` : ''));
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
