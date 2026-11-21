// The 4D tab: Values, Assign, Suggest, Coverage, Import / Export. Draws the controller (controller.ts); holds no data of its own.
// Every control carries a help key `4D tab/<name>` (src/ui/helpText.ts). Phone: the tab is a bottom sheet like the others.

import type { ViewerApp } from '../app';
import { downloadBlob } from '../cinematic/flythrough';
import { el } from '../ui/dom';
import type { Assignment, AttributeKind } from '../schedule/types';
import { ATTRIBUTES, ATTRIBUTE_LABEL } from './assignments';
import type { Map4dController } from './controller';
import { buildSchedulePanel } from './schedulePanel';
import type { ScheduleController } from './scheduleController';
import type { Target } from './targets';
import { colourOf } from './values';

const STYLE_ID = 'xray-4d-style';
const CSS = `
.x4{display:flex;flex-direction:column;gap:8px;padding:8px 10px 14px;font-size:12px;color:var(--sb-fg,#dfe6ee)}
.x4 details{border:1px solid var(--sb-line,#262d3a);border-radius:5px;background:rgba(255,255,255,.02)}
.x4 summary{cursor:pointer;padding:6px 8px;font-weight:600;font-size:12px;user-select:none}
.x4 .x4-sec{display:flex;flex-direction:column;gap:6px;padding:4px 8px 8px}
.x4 .x4-row{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.x4 .x4-row>.grow{flex:1 1 120px;min-width:0}
.x4 input[type=text],.x4 input[type=number],.x4 select{background:#0e1218;color:inherit;border:1px solid var(--sb-line,#262d3a);border-radius:3px;height:26px;padding:0 6px;font:inherit;min-width:0}
.x4 input[type=color]{width:26px;height:22px;padding:0;border:1px solid var(--sb-line,#262d3a);background:none;border-radius:3px}
.x4 input[type=number]{width:62px}
.x4 button{background:#1c2430;color:inherit;border:1px solid #2d3748;border-radius:4px;height:26px;padding:0 9px;font:inherit;cursor:pointer;white-space:nowrap}
.x4 button.primary{background:#2d6aa8;border-color:#3b82c4;color:#fff}
.x4 button:disabled{opacity:.45;cursor:default}
.x4 button.x4-icon{padding:0 6px;min-width:26px}
.x4 :focus-visible{outline:1px solid var(--sb-accent,#3b9cff);outline-offset:1px}
.x4 .x4-dim{color:var(--sb-dim,#8d99a8);font-size:11px}
.x4 .x4-msg{min-height:15px;color:#9fe3b0;font-size:11px}
.x4 .x4-msg.err{color:#ff8f8f}
.x4 .x4-seg{display:flex;gap:0}
.x4 .x4-seg button{border-radius:0;border-right-width:0}
.x4 .x4-seg button:first-child{border-radius:4px 0 0 4px}
.x4 .x4-seg button:last-child{border-radius:0 4px 4px 0;border-right-width:1px}
.x4 .x4-seg button.on{background:#1f4a7a;border-color:#3b82c4;color:#fff}
.x4 .x4-list{display:flex;flex-direction:column;gap:3px;max-height:230px;overflow:auto}
.x4 .x4-item{display:flex;gap:6px;align-items:center;padding:2px 0}
.x4 .x4-item input[type=text]{flex:1 1 auto}
.x4 .x4-count{color:var(--sb-dim,#8d99a8);min-width:34px;text-align:right}
.x4 .x4-prop{display:grid;grid-template-columns:1fr auto;gap:2px 6px;padding:4px 2px;border-bottom:1px solid var(--sb-line,#262d3a);cursor:pointer}
.x4 .x4-prop:hover{background:var(--sb-hover,#1c2230)}
.x4 .x4-prop b{font-weight:600}
.x4 .x4-conf{font-variant-numeric:tabular-nums;color:#e0b252}
.x4 .x4-why{grid-column:1 / 3;color:var(--sb-dim,#8d99a8);font-size:11px;overflow-wrap:anywhere}
.x4 table{border-collapse:collapse;width:100%}
.x4 td,.x4 th{padding:2px 4px;text-align:left;border-bottom:1px solid var(--sb-line,#262d3a);font-weight:400}
.x4 td.n{text-align:right;font-variant-numeric:tabular-nums}
.x4 .x4-sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px}
@media (max-width:700px){.x4 input[type=text],.x4 input[type=number],.x4 select,.x4 button{height:32px}}
`;

function ensureStyle(): void {
  if (document.getElementById(STYLE_ID)) return;
  const st = document.createElement('style');
  st.id = STYLE_ID;
  st.textContent = CSS;
  document.head.appendChild(st);
}

const KEY = '4D tab/';
function help<T extends HTMLElement>(e: T, key: string): T { e.setAttribute('data-help-key', KEY + key); return e; }
const btn = (text: string, key: string, onClick: () => void, cls = ''): HTMLButtonElement => {
  const b = help(el('button', cls, { type: 'button' }, text), key);
  b.addEventListener('click', onClick);
  return b;
};
const confText = (c: number | undefined): string => (c === undefined ? '' : c.toFixed(2));
const lower = (a: AttributeKind): string => ATTRIBUTE_LABEL[a].toLowerCase();

export interface PanelHandle { dispose(): void; render(): void; setAttribute(a: AttributeKind): void; openSection(id: string): void }

export function buildMapPanel(pane: HTMLElement, app: ViewerApp, c: Map4dController, sc: ScheduleController, ctx: { visible(): boolean; onVisible(cb: (v: boolean) => void): () => void }): PanelHandle {
  ensureStyle();
  const root = el('div', 'x4');
  pane.append(root);
  let attr: AttributeKind = 'location';
  let raf = 0;

  const status = el('div', 'x4-dim');
  const msg = el('div', 'x4-msg');
  const say = (text: string, err = false): void => { msg.textContent = text; msg.classList.toggle('err', err); };

  // ---------------------------------------------------------------- attribute switch
  const seg = el('div', 'x4-seg', { role: 'group', 'aria-label': 'Attribute' });
  const segBtns = new Map<AttributeKind, HTMLButtonElement>();
  for (const a of ATTRIBUTES) {
    const b = help(el('button', '', { type: 'button', 'data-attr': a }, ATTRIBUTE_LABEL[a]), 'Attribute');
    b.addEventListener('click', () => { setAttribute(a); });
    segBtns.set(a, b);
    seg.append(b);
  }
  const top = el('div', 'x4-row');
  top.append(el('span', 'x4-dim', undefined, 'Attribute'), seg);
  root.append(status, top);

  const section = (title: string, id: string, open: boolean, key: string = title): { box: HTMLDetailsElement; body: HTMLElement } => {
    const d = el('details', '', { 'data-sec': id });
    if (open) d.open = true;
    const s = help(el('summary', '', undefined, title), 'Section ' + key);
    const body = el('div', 'x4-sec');
    d.append(s, body);
    root.append(d);
    return { box: d, body };
  };

  // ---------------------------------------------------------------- Values
  const values = section('Values', 'values', true);
  const valueList = el('div', 'x4-list', { 'data-x4': 'value-list' });
  const newValue = help(el('input', 'grow', { type: 'text', placeholder: 'New value', 'aria-label': 'New value', maxlength: '255' }), 'New value');
  const addBtn = btn('Add', 'Add value', () => { if (c.addValue(attr, newValue.value)) { newValue.value = ''; say(''); } else say('Enter a name that is not in the list yet.', true); });
  newValue.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') addBtn.click(); });
  const seedBtn = btn('Seed from model', 'Seed from model', () => { const n = c.seed(); say(n ? `Added ${n} value${n === 1 ? '' : 's'} from the model.` : 'The model offers nothing new.'); });
  const addRow = el('div', 'x4-row');
  addRow.append(newValue, addBtn, seedBtn);
  values.body.append(el('div', 'x4-dim', undefined, 'Storey names give locations, zone groups give zones, the classifier gives trades. Edit, add or delete values.'), valueList, addRow);

  // ---------------------------------------------------------------- Assign
  const assign = section('Assign', 'assign', true);
  const valueIn = help(el('input', 'grow', { type: 'text', list: 'x4-values', placeholder: 'Value to assign', 'aria-label': 'Value to assign', maxlength: '255', autocomplete: 'off' }), 'Value to assign');
  const datalist = el('datalist', '', { id: 'x4-values' });
  const selCount = el('span', 'x4-dim');
  const selBtn = btn('Selection', 'Assign to selection', () => run({ selection: true }, 'the selection'), 'primary');
  const clearBtn = btn('Clear', 'Clear from selection', () => {
    const n = c.clearAssignment(attr, { selection: true });
    say(n ? `Removed ${lower(attr)} from ${n} element${n === 1 ? '' : 's'}.` : 'The selection has no accepted value to remove.');
  });
  const selRow = el('div', 'x4-row');
  selRow.append(el('span', 'x4-dim', undefined, 'To'), selBtn, selCount, clearBtn);

  const queryIn = help(el('input', 'grow', { type: 'text', placeholder: "Criteria, such as class = 'IfcSlab'", 'aria-label': 'Criteria query', spellcheck: 'false' }), 'Query text');
  const queryCount = el('span', 'x4-dim');
  const queryBtn = btn('Query', 'Assign to query', () => run({ query: queryIn.value }, 'the query'), 'primary');
  const queryRow = el('div', 'x4-row');
  queryRow.append(queryIn, queryCount, queryBtn);

  const storeySel = help(el('select', 'grow', { 'aria-label': 'Storey' }), 'Storey');
  const storeyBtn = btn('Storey', 'Assign to storey', () => { if (storeySel.value) run({ storey: storeySel.value }, `storey ${storeySel.value}`); }, 'primary');
  const storeyAll = btn('Every storey', 'Location from every storey', () => {
    const m = c.model;
    if (!m) return;
    let n = 0;
    for (const s of m.storeys) n += c.assign('location', s.name, { storey: s.id }).assigned;
    setAttribute('location');
    say(`Location set from the storey for ${n} element${n === 1 ? '' : 's'}.`);
  });
  const storeyRow = el('div', 'x4-row');
  storeyRow.append(storeySel, storeyBtn, storeyAll);

  const setSel = help(el('select', 'grow', { 'aria-label': 'Selection set' }), 'Selection set');
  const setBtn = btn('Set', 'Assign to set', () => { if (setSel.value) run({ set: setSel.value }, `set ${setSel.value}`); }, 'primary');
  const setRow = el('div', 'x4-row');
  setRow.append(setSel, setBtn);

  assign.body.append(el('div', 'x4-row', undefined), datalist);
  assign.body.firstElementChild!.append(valueIn);
  assign.body.append(selRow, queryRow, storeyRow, setRow, msg);

  function run(target: Target, what: string): void {
    const v = valueIn.value;
    if (!v.trim()) { say(`Enter or pick a ${lower(attr)} value first.`, true); return; }
    const r = c.assign(attr, v, target);
    if (r.error) { say(r.error, true); return; }
    say(`${ATTRIBUTE_LABEL[attr]} "${v.trim()}" set on ${r.assigned} element${r.assigned === 1 ? '' : 's'} of ${what}${r.unchanged ? `, ${r.unchanged} already had it` : ''}.`);
    c.cancelPreview();
  }

  const showPreview = (t: Target | null): void => {
    if (!t) { c.cancelPreview(); return; }
    c.preview(c.resolve(t).ids);
  };
  let queryTimer: ReturnType<typeof setTimeout> | null = null;
  const onQuery = (): void => {
    if (queryTimer) clearTimeout(queryTimer);
    queryTimer = setTimeout(() => {
      const q = queryIn.value;
      const r = c.queryCount(q);
      queryCount.textContent = !q.trim() ? '' : r.error ? 'syntax error' : `${r.count} match${r.count === 1 ? '' : 'es'}`;
      queryCount.title = r.error ?? '';
      showPreview(q.trim() && !r.error ? { query: q } : null);
    }, 200);
  };
  queryIn.addEventListener('input', onQuery);
  queryIn.addEventListener('focus', onQuery);
  storeySel.addEventListener('change', () => showPreview(storeySel.value ? { storey: storeySel.value } : null));
  setSel.addEventListener('change', () => showPreview(setSel.value ? { set: setSel.value } : null));
  for (const e of [storeySel, setSel]) e.addEventListener('blur', () => c.cancelPreview());
  queryIn.addEventListener('blur', () => c.cancelPreview());

  // ---------------------------------------------------------------- Suggest
  const sug = section('Suggest', 'suggest', false);
  const sugBtn = btn('Suggest', 'Suggest', () => {
    const r = c.suggest();
    say(`${r.proposed} proposal${r.proposed === 1 ? '' : 's'}: ${r.byAttribute.location} location, ${r.byAttribute.trade} trade, ${r.byAttribute.zone} zone.`);
    sug.box.open = true;
  }, 'primary');
  const limit = help(el('input', '', { type: 'number', min: '0', max: '1', step: '0.05', value: '0.8', 'aria-label': 'Confidence limit' }), 'Confidence limit');
  const accAbove = btn('Accept all above', 'Accept all above', () => {
    const lim = Math.max(0, Math.min(1, Number(limit.value) || 0));
    const n = c.acceptAbove(lim);
    say(`Accepted ${n} proposal${n === 1 ? '' : 's'} at ${lim.toFixed(2)} or more.`);
  });
  const sugRow = el('div', 'x4-row');
  sugRow.append(sugBtn, accAbove, limit);
  const propList = el('div', 'x4-list', { 'data-x4': 'proposals' });
  propList.style.maxHeight = '300px';
  const tableBox = el('details');
  tableBox.append(help(el('summary', '', undefined, 'Class to trade table'), 'Class trade table'));
  const tableBody = el('div', 'x4-sec');
  tableBox.append(tableBody);
  sug.body.append(el('div', 'x4-dim', undefined, 'Location from the storey, zone from its group, trade from the class table and the classifier.'), sugRow, propList, tableBox);

  let proposalLimit = 60;
  function renderProposals(): void {
    const list = c.proposals().sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0));
    propList.replaceChildren();
    if (list.length === 0) { propList.append(el('div', 'x4-dim', undefined, 'No open proposals. Press Suggest.')); return; }
    const m = c.model;
    propList.append(el('div', 'x4-dim', undefined, `${list.length} open proposal${list.length === 1 ? '' : 's'}, highest confidence first.`));
    for (const a of list.slice(0, proposalLimit)) propList.append(proposalRow(a, m?.byGlobalId.get(a.element)));
    if (list.length > proposalLimit) propList.append(btn(`Show more (${list.length - proposalLimit})`, 'Show more', () => { proposalLimit += 100; renderProposals(); }));
  }
  function proposalRow(a: Assignment, id: number | undefined): HTMLElement {
    const m = c.model;
    const e = id !== undefined ? m?.elements[id] : undefined;
    const row = help(el('div', 'x4-prop', { 'data-id': a.id }), 'Proposal');
    const left = el('div');
    left.append(el('b', undefined, undefined, `${ATTRIBUTE_LABEL[a.attribute]}: ${a.value}`), el('span', 'x4-dim', undefined, ` ${e ? `${e.ifcClass} ${e.name ?? ''}` : a.element}`));
    const right = el('div', 'x4-row');
    right.append(el('span', 'x4-conf', undefined, confText(a.confidence)),
      help(el('button', 'x4-icon', { type: 'button', title: 'Accept', 'aria-label': 'Accept' }, 'Accept'), 'Accept proposal'),
      help(el('button', 'x4-icon', { type: 'button', title: 'Reject', 'aria-label': 'Reject' }, 'Reject'), 'Reject proposal'));
    (right.children[1] as HTMLElement).addEventListener('click', (ev) => { ev.stopPropagation(); c.accept([a.id]); });
    (right.children[2] as HTMLElement).addEventListener('click', (ev) => { ev.stopPropagation(); c.reject([a.id]); });
    row.append(left, right, el('div', 'x4-why', undefined, (a.reasons ?? []).join('. ')));
    row.addEventListener('click', () => { if (id !== undefined) app.selectIds([id]); });
    return row;
  }

  function renderTable(): void {
    tableBody.replaceChildren();
    const trades = c.valueList('trade').map((v) => v.name);
    const rows = Object.entries(c.classTrade).sort((a, b) => a[0].localeCompare(b[0]));
    for (const [cls, trade] of rows) {
      const r = el('div', 'x4-item');
      const name = help(el('input', '', { type: 'text', value: cls, 'aria-label': 'Class' }), 'Class name');
      const sel = help(el('select', '', { 'aria-label': 'Trade for the class' }), 'Class trade');
      for (const t of [...new Set([...trades, trade])]) { const o = el('option', '', { value: t }, t); if (t === trade) o.selected = true; sel.append(o); }
      sel.addEventListener('change', () => { c.setClassTrade({ ...c.classTrade, [cls]: sel.value }); });
      name.addEventListener('change', () => { const t = { ...c.classTrade }; delete t[cls]; const n = name.value.trim(); if (n) t[n] = trade; c.setClassTrade(t); });
      const del = help(el('button', 'x4-icon', { type: 'button', 'aria-label': 'Delete row' }, 'Delete'), 'Delete class row');
      del.addEventListener('click', () => { const t = { ...c.classTrade }; delete t[cls]; c.setClassTrade(t); });
      r.append(name, sel, del);
      tableBody.append(r);
    }
    const addCls = help(el('input', 'grow', { type: 'text', placeholder: 'IfcClass or IfcClass:material', 'aria-label': 'New class' }), 'New class');
    const addB = btn('Add', 'Add class row', () => { const n = addCls.value.trim(); if (n && trades[0]) c.setClassTrade({ ...c.classTrade, [n]: trades[0] }); });
    const r = el('div', 'x4-row');
    r.append(addCls, addB);
    tableBody.append(r);
  }

  // ---------------------------------------------------------------- Coverage
  const cov = section('Coverage', 'coverage', false);
  const covBox = el('div');
  const colourSel = help(el('select', '', { 'aria-label': 'Colour the model by' }), 'Colour by');
  for (const [v, t] of [['', 'Normal colours'], ...ATTRIBUTES.map((a) => [a, `By ${lower(a)}`] as const)] as const) colourSel.append(el('option', '', { value: v }, t));
  colourSel.addEventListener('change', () => { c.setColourBy((colourSel.value || null) as AttributeKind | null); });
  const legend = el('div', 'x4-dim');
  const colourRow = el('div', 'x4-row');
  colourRow.append(el('span', 'x4-dim', undefined, 'Colour'), colourSel);
  cov.body.append(covBox, colourRow, legend);

  function renderCoverage(): void {
    const cv = c.coverage();
    covBox.replaceChildren();
    const t = el('table', '', { 'data-x4': 'coverage' });
    const head = el('tr');
    for (const h of ['', 'With', 'Without', 'Proposed', '']) head.append(el('th', '', undefined, h));
    t.append(head);
    for (const a of ATTRIBUTES) {
      const r = el('tr', '', { 'data-attr': a });
      const x = cv.attributes[a];
      r.append(el('td', '', undefined, ATTRIBUTE_LABEL[a]), el('td', 'n', undefined, String(x.assigned)), el('td', 'n', undefined, String(x.unassigned)), el('td', 'n', undefined, String(x.proposed)));
      const td = el('td');
      const b = help(el('button', '', { type: 'button', 'data-attr': a }, 'Select without'), 'Select unassigned');
      b.disabled = x.unassigned === 0;
      b.addEventListener('click', () => { const n = c.selectUnassigned(a); say(`Selected ${n} element${n === 1 ? '' : 's'} without ${lower(a)}.`); });
      td.append(b);
      r.append(td);
      t.append(r);
    }
    covBox.append(el('div', 'x4-dim', undefined, `${cv.total} elements.`), t);
    colourSel.value = c.colourBy ?? '';
    legend.replaceChildren();
    if (c.colourBy) {
      const a = c.colourBy;
      const parts = cv.attributes[a].values;
      for (const p of parts.slice(0, 40)) {
        const s = el('span');
        const sw = el('span', 'x4-sw');
        sw.style.background = colourOf(c.values, a, p.value);
        s.append(sw, `${p.value} ${p.count}  `);
        legend.append(s);
      }
      const sw = el('span', 'x4-sw');
      sw.style.background = '#5c616b';
      legend.append(sw, `Without ${cv.attributes[a].unassigned}`);
    }
  }

  // ---------------------------------------------------------------- the schedule workflow (Schedule, Configure, Link, Style, Play)
  const sched = buildSchedulePanel(root, app, sc, c, ctx);

  // ---------------------------------------------------------------- Import / Export
  const io = section('Import / Export', 'io', false, 'Import and Export');
  const exportBtn = btn('Export JSON', 'Export assignments', () => {
    const r = c.exportJson();
    const name = `${(app.modelName || 'model').replace(/\.[^.]+$/, '').replace(/[^A-Za-z0-9._-]+/g, '_')}.4d-assignments.json`;
    downloadBlob(new Blob([r.json], { type: 'application/json' }), name);
    say(`Exported ${r.assignments} assignment${r.assignments === 1 ? '' : 's'} for ${r.elements} element${r.elements === 1 ? '' : 's'}${r.skipped ? `, ${r.skipped} skipped (no GlobalId)` : ''}. The schedule is a placeholder.`);
  });
  const file = el('input', '', { type: 'file', accept: '.json,application/json' });
  file.style.display = 'none';
  help(file, 'Import assignments');
  file.addEventListener('change', () => {
    const f = file.files?.[0];
    file.value = '';
    if (!f) return;
    void f.text().then((text) => {
      const r = c.importJson(text);
      if (r.read === 0 && r.problems.length) { say(r.problems[0]!, true); return; }
      say(`Read ${r.read} assignment${r.read === 1 ? '' : 's'}: ${r.added} new, ${r.updated} updated, ${r.superseded} superseded${r.problems.length ? `, ${r.problems.length} rows left out` : ''}${r.otherModel ? '. The file names another model.' : '.'}`, r.otherModel);
    });
  });
  const importBtn = btn('Import JSON', 'Import assignments', () => file.click());
  const resetBtn = btn('Reset', 'Reset assignments', () => {
    if (!window.confirm('Remove all 4D assignments and values of this model from this browser?')) return;
    c.reset();
    say('All assignments were removed.');
  });
  const ioRow = el('div', 'x4-row');
  ioRow.append(exportBtn, importBtn, resetBtn, file);
  io.body.append(el('div', 'x4-dim', undefined, 'The file is a LinkML LinkDataset with model, elements and assignments. Save IFC writes the accepted values into the model file.'), ioRow);

  // ---------------------------------------------------------------- render
  function renderValues(): void {
    const list = c.valueList(attr);
    const use = c.usage(attr);
    valueList.replaceChildren();
    if (list.length === 0) valueList.append(el('div', 'x4-dim', undefined, `No ${lower(attr)} values yet. Add one or seed from the model.`));
    for (const v of list) {
      const r = el('div', 'x4-item', { 'data-value': v.name });
      const col = help(el('input', '', { type: 'color', value: colourOf(c.values, attr, v.name), 'aria-label': 'Colour' }), 'Value colour');
      col.addEventListener('change', () => c.setColour(attr, v.name, col.value));
      const name = help(el('input', '', { type: 'text', value: v.name, 'aria-label': 'Value name', maxlength: '255' }), 'Value name');
      name.addEventListener('change', () => { if (!c.renameValue(attr, v.name, name.value)) { name.value = v.name; say('That name is empty or already in the list.', true); } else say(''); });
      const n = use.get(v.name) ?? 0;
      const count = el('span', 'x4-count', undefined, String(n));
      const del = help(el('button', 'x4-icon', { type: 'button', 'aria-label': 'Delete value', title: n ? 'In use: remove it from the elements first' : 'Delete' }, 'Delete'), 'Delete value');
      del.disabled = n > 0;
      del.addEventListener('click', () => { c.deleteValue(attr, v.name); });
      const use_ = help(el('button', 'x4-icon', { type: 'button', 'aria-label': 'Use this value' }, 'Use'), 'Use value');
      use_.addEventListener('click', () => { valueIn.value = v.name; });
      r.append(col, name, count, use_, del);
      valueList.append(r);
    }
  }

  function renderAssign(): void {
    const m = c.model;
    datalist.replaceChildren(...c.valueList(attr).map((v) => el('option', '', { value: v.name })));
    valueIn.setAttribute('placeholder', `${ATTRIBUTE_LABEL[attr]} to assign`);
    const keepS = storeySel.value;
    storeySel.replaceChildren(el('option', '', { value: '' }, 'Pick a storey'), ...(m?.storeys ?? []).map((s) => el('option', '', { value: s.name }, s.name)));
    storeySel.value = keepS;
    const keepT = setSel.value;
    setSel.replaceChildren(el('option', '', { value: '' }, 'Pick a selection set'), ...c.sets().map((s) => el('option', '', { value: s.name }, `${s.name} (${s.globalIds.length})`)));
    setSel.value = keepT;
    storeyAll.disabled = !m || m.storeys.length === 0;
    updateSel();
  }
  const updateSel = (): void => {
    const n = app.selection.length;
    selCount.textContent = `${n} selected`;
    selBtn.disabled = n === 0;
    clearBtn.disabled = n === 0;
  };

  function renderStatus(): void {
    const a = c.assignments.filter((x) => x.status === 'accepted').length;
    const p = c.assignments.filter((x) => x.status === 'proposed').length;
    status.textContent = c.model ? `${a} accepted, ${p} proposed. ${c.persistent ? 'Kept in this browser per model.' : 'Not kept after this session (no browser storage).'}` : 'Open a model to map it.';
  }

  function render(): void {
    for (const [a, b] of segBtns) { b.classList.toggle('on', a === attr); b.setAttribute('aria-pressed', String(a === attr)); }
    renderStatus();
    renderValues();
    renderAssign();
    renderProposals();
    renderTable();
    renderCoverage();
  }
  const schedule = (): void => { if (!ctx.visible()) return; if (raf) return; raf = requestAnimationFrame(() => { raf = 0; render(); }); };

  function setAttribute(a: AttributeKind): void {
    attr = a;
    render();
  }

  const off = c.onChange(schedule);
  const offVis = ctx.onVisible((v) => {
    if (v) { c.resume(); render(); } else { c.release(); }
  });
  const onSel = (): void => { if (ctx.visible()) updateSel(); };
  document.addEventListener('xray-selection', onSel);
  render();
  return {
    render: () => { render(); sched.render(); },
    setAttribute,
    openSection(id) { sched.open(id); },
    dispose() { sched.dispose(); off(); offVis(); document.removeEventListener('xray-selection', onSel); if (raf) cancelAnimationFrame(raf); root.remove(); },
  };
}
