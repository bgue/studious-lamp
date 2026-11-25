// The schedule sections of the 4D tab: Schedule (open an .xer), Configure (what the schedule's codes mean, value table, trade queries),
// Link (coverage, unlinked elements, suggestions, report), Style (the film options) and Play (play, scrub, record, save into the IFC).
// Draws the schedule controller (scheduleController.ts); holds no data of its own. Every control carries a help key `4D tab/<name>`
// (src/ui/helpText.ts). Called by buildMapPanel (panel.ts), which owns the tab's root element and styles.

import type { ViewerApp } from '../app';
import { downloadBlob } from '../cinematic/flythrough';
import { formatDate } from '../schedule/planTime';
import type { AttributeKind, FourDStyle, SplitRule } from '../schedule/types';
import { el } from '../ui/dom';
import { ATTRIBUTES, ATTRIBUTE_LABEL } from './assignments';
import type { Map4dController } from './controller';
import { linksWithStatus, proposedLinks } from './linkReview';
import { setExisting, setSource, setSplit, setStyle, setTradeQuery, setValueMap, sourceChoices, sourceKey, sourcesOf, tradeKeys, valueRows } from './scheduleConfig';
import type { ScheduleController } from './scheduleController';

const STYLE_ID = 'xray-4d-schedule-style';
const CSS = `
.x4 .x4-grid{display:grid;grid-template-columns:auto 1fr;gap:5px 8px;align-items:center}
.x4 .x4-grid>label{color:var(--sb-dim,#8d99a8)}
.x4 .x4-grid select,.x4 .x4-grid input[type=text],.x4 .x4-grid input[type=number],.x4 .x4-grid input[type=date]{width:100%;box-sizing:border-box}
.x4 input[type=date]{background:#0e1218;color:inherit;border:1px solid var(--sb-line,#262d3a);border-radius:3px;height:26px;padding:0 6px;font:inherit;min-width:0}
.x4 input[type=range]{flex:1 1 140px;min-width:0}
.x4 .x4-sum{display:grid;grid-template-columns:auto 1fr;gap:1px 10px;padding:2px 0}
.x4 .x4-sum>span:nth-child(odd){color:var(--sb-dim,#8d99a8)}
.x4 .x4-warn{color:#e0b252;font-size:11px}
.x4 .x4-link{display:grid;grid-template-columns:1fr auto;gap:2px 6px;padding:4px 2px;border-bottom:1px solid var(--sb-line,#262d3a)}
.x4 .x4-link b{font-weight:600}
.x4 .x4-bar{height:6px;border-radius:3px;background:#262d3a;overflow:hidden}
.x4 .x4-bar>i{display:block;height:100%;background:#3b82c4}
.x4 .x4-date{font-variant-numeric:tabular-nums;min-width:88px}
.x4 .x4-check{display:flex;gap:6px;align-items:center}
.x4 .x4-table-wrap{overflow-x:auto}
.x4 .x4-film{position:sticky;top:0;z-index:5;display:flex;flex-direction:column;gap:6px;padding:6px 8px;border:1px solid var(--sb-line,#262d3a);border-radius:5px;background:var(--sb-bg,#141820);box-shadow:0 2px 6px rgba(0,0,0,.25)}
.x4 .x4-film .x4-msg{min-height:0}
.x4 .x4-film .x4-msg:empty{display:none}
.x4 .x4-film .x4-warn:empty{display:none}
.x4 .x4-film-need{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.x4 .x4-film-need>span{flex:1 1 140px}
.x4 details[data-sec]{scroll-margin-top:92px}
@media (max-width:700px){.x4 input[type=date]{height:32px}}
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
const plural = (n: number, w: string): string => `${n} ${n === 1 ? w : w.endsWith('y') ? w.slice(0, -1) + 'ies' : w + 's'}`;
const pct = (x: number): string => `${(x * 100).toFixed(x >= 0.995 || x === 0 ? 0 : 1)} %`;

export interface SchedulePanelHandle { render(): void; dispose(): void; open(section: string): void }

export function buildSchedulePanel(root: HTMLElement, app: ViewerApp, sc: ScheduleController, map: Map4dController, ctx: { visible(): boolean }): SchedulePanelHandle {
  ensureStyle();
  const sections = new Map<string, HTMLDetailsElement>();
  const section = (title: string, id: string, open: boolean, key: string): HTMLElement => {
    const d = el('details', '', { 'data-sec': id });
    if (open) d.open = true;
    const body = el('div', 'x4-sec');
    d.append(help(el('summary', '', undefined, title), 'Section ' + key), body);
    root.append(d);
    sections.set(id, d);
    return body;
  };
  const msgBox = (): { box: HTMLElement; say(t: string, err?: boolean): void } => {
    const box = el('div', 'x4-msg');
    return { box, say: (t, err = false) => { box.textContent = t; box.classList.toggle('err', err); } };
  };

  // ---------------------------------------------------------------- Schedule
  const sSec = section('Schedule', 'schedule', true, 'Schedule');
  const sMsg = msgBox();
  const xerIn = help(el('input', '', { type: 'file', accept: '.xer,.XER,text/plain', 'data-x4': 'xer-input' }), 'Open schedule');
  xerIn.style.display = 'none';
  xerIn.addEventListener('change', () => {
    const f = xerIn.files?.[0];
    xerIn.value = '';
    if (f) void sc.map.ready().then(() => loadFile(f));
  });
  const openBtn = btn('Open .xer', 'Open schedule', () => xerIn.click(), 'primary');
  const projectSel = help(el('select', 'grow', { 'aria-label': 'Project' }), 'Schedule project');
  const projectBtn = btn('Use project', 'Use project', () => { const r = sc.chooseProject(projectSel.value); sMsg.say(r.message, !r.ok); });
  const projectRow = el('div', 'x4-row');
  projectRow.append(projectSel, projectBtn);
  const openRow = el('div', 'x4-row');
  openRow.append(openBtn, xerIn);
  const summary = el('div', 'x4-sum', { 'data-x4': 'schedule-summary' });
  const sDim = el('div', 'x4-dim', undefined, 'Open a P6 export (.xer) or drop the file on the viewer.');
  sSec.append(sDim, openRow, projectRow, summary, sMsg.box);

  async function loadFile(f: File): Promise<void> {
    const r = sc.loadXer(new Uint8Array(await f.arrayBuffer()), f.name);
    sMsg.say(r.message, !r.ok);
  }

  function renderSchedule(): void {
    projectRow.style.display = sc.pendingProjects ? '' : 'none';
    if (sc.pendingProjects) projectSel.replaceChildren(...sc.pendingProjects.map((p) => el('option', '', { value: p.shortName }, `${p.shortName}${p.dataDate ? ` (data date ${p.dataDate.slice(0, 10)})` : ''}`)));
    summary.replaceChildren();
    const s = sc.summary();
    sDim.style.display = s ? 'none' : '';
    if (!s) return;
    const row = (k: string, v: string): void => { summary.append(el('span', '', undefined, k), el('span', '', undefined, v)); };
    row('Project', s.projectName ? `${s.project}, ${s.projectName}` : s.project);
    row('File', s.fileName);
    row('Data date', s.dataDate ? s.dataDate.replace('T', ' ') : 'none');
    const types = Object.entries(s.byType).map(([t, n]) => `${n} ${t}`).join(', ');
    row('Activities', `${s.tasks} (${types})`);
    row('WBS, relations', `${s.wbs} nodes, ${s.relations} relations`);
    row('Code types', s.codeTypes.length ? s.codeTypes.map((c) => `${c.name} (${c.values})`).join(', ') : 'none');
    if (s.udfs.length) row('User fields', s.udfs.join(', '));
    if (s.warnings) row('Warnings', String(s.warnings));
  }

  // ---------------------------------------------------------------- Configure
  const cSec = section('Configure', 'configure', true, 'Configure');
  const cMsg = msgBox();
  const srcSel = new Map<AttributeKind, HTMLSelectElement>();
  const srcGrid = el('div', 'x4-grid');
  for (const a of ATTRIBUTES) {
    const sel = help(el('select', '', { 'aria-label': `${ATTRIBUTE_LABEL[a]} from`, 'data-attr': a }), 'Schedule source');
    sel.addEventListener('change', () => {
      const ch = sourceChoices(sc.schedule, sourcesOf(sc.config, a)).find((c) => c.key === sel.value) ?? null;
      sc.setConfig(setSource(sc.config, a, ch));
    });
    srcSel.set(a, sel);
    srcGrid.append(el('label', '', undefined, `${ATTRIBUTE_LABEL[a]} from`), sel);
  }

  let vAttr: AttributeKind = 'location';
  const vSeg = el('div', 'x4-seg', { role: 'group', 'aria-label': 'Value table for' });
  const vBtns = new Map<AttributeKind, HTMLButtonElement>();
  for (const a of ATTRIBUTES) {
    const b = help(el('button', '', { type: 'button', 'data-vattr': a }, ATTRIBUTE_LABEL[a]), 'Value table attribute');
    b.addEventListener('click', () => { vAttr = a; renderConfigure(); });
    vBtns.set(a, b);
    vSeg.append(b);
  }
  const vHead = el('div', 'x4-row');
  vHead.append(el('span', 'x4-dim', undefined, 'Map values for'), vSeg);
  const vTable = el('div', 'x4-list', { 'data-x4': 'value-map' });
  const vList = el('datalist', '', { id: 'x4-model-values' });

  const tradeBox = el('div', 'x4-list', { 'data-x4': 'trade-queries' });
  tradeBox.style.maxHeight = '300px';
  const existingIn = help(el('input', 'grow', { type: 'text', placeholder: "Elements that exist before the job, such as storey = 'Site'", 'aria-label': 'Existing elements query', spellcheck: 'false' }), 'Existing query');
  existingIn.addEventListener('change', () => { sc.setConfig(setExisting(sc.config, existingIn.value)); });
  const existingCount = el('span', 'x4-dim');
  const existingRow = el('div', 'x4-row');
  existingRow.append(existingIn, existingCount);

  const saveCfg = btn('Save', 'Save configuration', () => { void sc.flush().then((ok) => cMsg.say(ok ? 'Configuration kept in this browser for this model.' : 'This browser keeps nothing: export the file instead.', !ok)); });
  const cfgFile = help(el('input', '', { type: 'file', accept: '.json,application/json', 'data-x4': 'config-input' }), 'Import configuration');
  cfgFile.style.display = 'none';
  cfgFile.addEventListener('change', () => {
    const f = cfgFile.files?.[0];
    cfgFile.value = '';
    if (f) void f.text().then((t) => importConfig(t));
  });
  const expCfg = btn('Export .4d.json', 'Export configuration', () => {
    const name = `${(app.modelName || 'model').replace(/\.[^.]+$/, '').replace(/[^A-Za-z0-9._-]+/g, '_')}.4d.json`;
    downloadBlob(new Blob([sc.exportConfigText()], { type: 'application/json' }), name);
    cMsg.say(`Exported ${name}.`);
  });
  const impCfg = btn('Import .4d.json', 'Import configuration', () => cfgFile.click());
  const cfgRow = el('div', 'x4-row');
  cfgRow.append(saveCfg, expCfg, impCfg, cfgFile);
  cSec.append(
    el('div', 'x4-dim', undefined, 'Pick what the schedule uses for the place, the work type and the zone of an activity.'),
    srcGrid, vHead, vTable, vList,
    el('div', 'x4-dim', undefined, 'Trade queries pick the elements of a trade when the model has no trade value.'),
    tradeBox, existingRow, cfgRow, cMsg.box,
  );

  function importConfig(text: string): void {
    const r = sc.loadConfigText(text);
    if (!r.config) { cMsg.say(r.problems[0] ?? 'Not a 4D configuration.', true); return; }
    cMsg.say(`Configuration read${r.problems.length ? `, ${plural(r.problems.length, 'problem')}: ${r.problems[0]}` : '.'}`, r.problems.length > 0);
  }

  const modelChoices = (a: AttributeKind): string[] => [...new Set([...map.valueList(a).map((v) => v.name), ...map.modelValues()[a]])].sort((x, y) => x.localeCompare(y, undefined, { numeric: true }));

  function renderConfigure(): void {
    const sched = sc.schedule;
    for (const a of ATTRIBUTES) {
      const sel = srcSel.get(a)!;
      const cur = sourcesOf(sc.config, a);
      sel.replaceChildren(el('option', '', { value: '' }, sched ? 'Not used' : 'Open a schedule first'), ...sourceChoices(sched, cur).map((c) => el('option', '', { value: c.key }, c.label)));
      sel.value = cur.length ? sourceKey(cur[0]) : '';
      sel.disabled = !sched;
    }
    for (const [a, b] of vBtns) { b.classList.toggle('on', a === vAttr); b.setAttribute('aria-pressed', String(a === vAttr)); }
    // the value table
    vTable.replaceChildren();
    const rows = valueRows(sched, sc.config, vAttr);
    const choices = modelChoices(vAttr);
    vList.replaceChildren(...choices.map((c) => el('option', '', { value: c })));
    if (!rows.length) vTable.append(el('div', 'x4-dim', undefined, sched ? `The schedule gives no ${ATTRIBUTE_LABEL[vAttr].toLowerCase()} values yet. Pick a source above.` : 'No schedule yet.'));
    for (const r of rows) {
      const line = el('div', 'x4-item', { 'data-value': r.schedule });
      const inp = help(el('input', '', { type: 'text', list: 'x4-model-values', value: r.model, placeholder: 'Same as schedule', 'aria-label': `Model value for ${r.schedule}`, autocomplete: 'off' }), 'Model value');
      inp.addEventListener('change', () => { sc.setConfig(setValueMap(sc.config, vAttr, r.schedule, inp.value)); });
      const lab = el('span', '', undefined, r.schedule);
      lab.style.minWidth = '60px';
      line.append(lab, el('span', 'x4-count', undefined, String(r.count)), inp);
      vTable.append(line);
    }
    // trade queries
    tradeBox.replaceChildren();
    const keys = sched ? tradeKeys(sched, sc.config) : Object.keys(sc.config.tradeQueries ?? {});
    for (const k of keys) {
      const q = sc.config.tradeQueries?.[k] ?? '';
      const line = el('div', 'x4-item', { 'data-trade': k });
      const inp = help(el('input', '', { type: 'text', value: q, placeholder: "class = 'IfcSlab'", 'aria-label': `Query for ${k}`, spellcheck: 'false' }), 'Trade query');
      const cnt = el('span', 'x4-count');
      const upd = (): void => {
        if (!inp.value.trim()) { cnt.textContent = ''; return; }
        const r = map.queryCount(inp.value);
        cnt.textContent = r.error ? 'error' : String(r.count);
        cnt.title = r.error ?? `${r.count} elements match`;
      };
      let timer: ReturnType<typeof setTimeout> | null = null;
      inp.addEventListener('input', () => { if (timer) clearTimeout(timer); timer = setTimeout(upd, 200); });
      inp.addEventListener('change', () => { sc.setConfig(setTradeQuery(sc.config, k, inp.value)); });
      inp.addEventListener('focus', () => { const r = map.queryCount(inp.value); if (!r.error && inp.value.trim()) map.preview(map.resolve({ query: inp.value }).ids); });
      inp.addEventListener('blur', () => map.cancelPreview());
      upd();
      const lab = el('span', '', undefined, k);
      lab.style.minWidth = '60px';
      line.append(lab, inp, cnt);
      tradeBox.append(line);
    }
    if (!keys.length) tradeBox.append(el('div', 'x4-dim', undefined, 'Pick a trade source above and the trade values appear here.'));
    if (document.activeElement !== existingIn) existingIn.value = sc.config.model.existing ?? '';
    const ex = sc.config.model.existing ? map.queryCount(sc.config.model.existing) : null;
    existingCount.textContent = ex ? (ex.error ? 'error' : `${ex.count}`) : '';
  }

  // ---------------------------------------------------------------- Link
  const lSec = section('Link', 'link', true, 'Link');
  const lMsg = msgBox();
  const linkBtn = btn('Link schedule', 'Link schedule', () => {
    const r = sc.link();
    if ('error' in r) { lMsg.say(r.error, true); return; }
    lMsg.say(`Linked ${r.elements.linked} of ${r.elements.considered} elements (${pct(r.elements.ratio)}).`);
  }, 'primary');
  const reportBtn = btn('Open report', 'Open report', () => { if (!sc.openReport()) lMsg.say('The browser blocked the new window. Allow pop-ups for this page.', true); });
  const selUnlinked = btn('Select unlinked', 'Select unlinked', () => { const n = sc.selectUnlinked(); lMsg.say(`Selected ${plural(n, 'element')} that no accepted link builds.`); });
  const lRow = el('div', 'x4-row');
  lRow.append(linkBtn, selUnlinked, reportBtn);
  const covBox = el('div', '', { 'data-x4': 'link-coverage' });
  const groupBox = el('div', 'x4-list', { 'data-x4': 'unlinked-groups' });
  const noElBox = el('div', 'x4-list', { 'data-x4': 'unlinked-activities' });
  const sugBox = el('div', 'x4-list', { 'data-x4': 'link-suggestions' });
  sugBox.style.maxHeight = '320px';
  const decidedBox = el('details');
  decidedBox.append(help(el('summary', '', undefined, 'Decided links'), 'Decided links'));
  const decidedList = el('div', 'x4-list', { 'data-x4': 'decided-links' });
  decidedBox.append(decidedList);
  const linkFile = help(el('input', '', { type: 'file', accept: '.json,application/json', 'data-x4': 'links-input' }), 'Import links');
  linkFile.style.display = 'none';
  linkFile.addEventListener('change', () => {
    const f = linkFile.files?.[0];
    linkFile.value = '';
    if (!f) return;
    void f.text().then((t) => {
      const r = sc.importLinksText(t);
      if (r.links === 0 && r.problems.length) { lMsg.say(r.problems[0]!, true); return; }
      lMsg.say(`Read ${plural(r.links, 'link')}${r.assignments ? ` and ${plural(r.assignments, 'assignment')}` : ''}${r.problems.length ? `, ${plural(r.problems.length, 'row')} left out` : ''}${r.otherSchedule ? '. The file was made for another schedule.' : '.'}`, r.otherSchedule);
    });
  });
  const expLinks = btn('Export links', 'Export links', () => {
    const t = sc.exportLinksText();
    if (!t) { lMsg.say('Link the schedule first.', true); return; }
    downloadBlob(new Blob([t], { type: 'application/json' }), `${(app.modelName || 'model').replace(/[^A-Za-z0-9._-]+/g, '_')}.4d-links.json`);
    lMsg.say('Exported the links as a LinkML dataset.');
  });
  const impLinks = btn('Import links', 'Import links', () => linkFile.click());
  const ioRow = el('div', 'x4-row');
  ioRow.append(expLinks, impLinks, linkFile);
  lSec.append(el('div', 'x4-dim', undefined, 'Link activities to elements by the values above. Suggestions wait for your decision.'), lRow, covBox, groupBox, noElBox, sugBox, decidedBox, ioRow, lMsg.box);

  function linkRow(l: { id: string; activity: string; elements: string[]; confidence?: number; reasons?: string[]; status?: string; source?: string }, withButtons: boolean): HTMLElement {
    const row = el('div', 'x4-link', { 'data-link': l.id });
    const name = sc.schedule?.tasks.find((t) => t.code === l.activity)?.name ?? '';
    const left = el('div');
    left.append(el('b', undefined, undefined, l.activity), el('span', 'x4-dim', undefined, ` ${name} · ${plural(l.elements.length, 'element')}${l.confidence !== undefined ? ` · ${l.confidence.toFixed(2)}` : ''}`));
    const right = el('div', 'x4-row');
    if (withButtons) {
      const acc = help(el('button', 'x4-icon', { type: 'button', 'aria-label': 'Accept link' }, 'Accept'), 'Accept link');
      const rej = help(el('button', 'x4-icon', { type: 'button', 'aria-label': 'Reject link' }, 'Reject'), 'Reject link');
      acc.addEventListener('click', (ev) => { ev.stopPropagation(); sc.decide(l.id, 'accepted'); });
      rej.addEventListener('click', (ev) => { ev.stopPropagation(); sc.decide(l.id, 'rejected'); });
      right.append(acc, rej);
    } else {
      const undo = help(el('button', 'x4-icon', { type: 'button', 'aria-label': 'Reopen link' }, 'Reopen'), 'Reopen link');
      undo.addEventListener('click', (ev) => { ev.stopPropagation(); sc.decide(l.id, 'proposed'); });
      right.append(el('span', 'x4-dim', undefined, l.status ?? ''), undo);
    }
    row.append(left, right, el('div', 'x4-why', undefined, (l.reasons ?? []).join('. ')));
    help(row, 'Link row');
    row.addEventListener('click', () => { sc.selectGlobalIds(l.elements); });
    return row;
  }

  function renderLink(): void {
    const sum = sc.linkSummary();
    linkBtn.disabled = !sc.schedule || !sc.hasModel;
    reportBtn.disabled = !sc.report;
    selUnlinked.disabled = !sc.links || (sc.links.unlinked_elements?.length ?? 0) === 0;
    expLinks.disabled = !sc.links;
    covBox.replaceChildren();
    groupBox.replaceChildren();
    noElBox.replaceChildren();
    sugBox.replaceChildren();
    decidedList.replaceChildren();
    if (!sum || !sc.report) { covBox.append(el('div', 'x4-dim', undefined, sc.schedule ? 'Not linked yet. Press Link schedule.' : 'Open a schedule first.')); return; }
    const t = el('table', '', { 'data-x4': 'coverage-schedule' });
    const head = el('tr');
    for (const h of ['', 'Linked', 'Of', '']) head.append(el('th', '', undefined, h));
    t.append(head);
    const bar = (x: number): HTMLElement => { const b = el('div', 'x4-bar'); const i = el('i'); i.style.width = `${Math.round(Math.min(1, x) * 100)}%`; b.append(i); return b; };
    const r1 = el('tr', '', { 'data-row': 'elements' });
    r1.append(el('td', '', undefined, 'Elements'), el('td', 'n', undefined, String(sum.elements.linked)), el('td', 'n', undefined, String(sum.elements.considered)), el('td', 'n', undefined, pct(sum.elements.ratio)));
    const r2 = el('tr', '', { 'data-row': 'activities' });
    r2.append(el('td', '', undefined, 'Activities'), el('td', 'n', undefined, String(sum.activities.linked)), el('td', 'n', undefined, String(sum.activities.total)), el('td', 'n', undefined, pct(sum.activities.ratio)));
    t.append(r1, r2);
    covBox.append(t, bar(sum.elements.ratio));
    const bits = [`${sum.ties} tied`, `${sum.activities.suggestedOnly} with a suggestion only`, `${sum.accepted} accepted, ${sum.proposed} proposed, ${sum.rejected} rejected`];
    covBox.append(el('div', 'x4-dim', undefined, bits.join('. ') + '.'));

    const groups = sc.report.unlinkedElements;
    if (groups.length) {
      groupBox.append(el('div', 'x4-dim', undefined, `${plural(sum.elements.unlinked, 'element')} without an accepted link, by class and storey.`));
      for (const g of groups.slice(0, 40)) {
        const line = el('div', 'x4-item', { 'data-group': `${g.ifcClass}|${g.storey ?? ''}` });
        line.append(el('span', 'grow', undefined, `${g.ifcClass}${g.storey ? ` · ${g.storey}` : ''}`), el('span', 'x4-count', undefined, String(g.count)),
          btn('Select', 'Select group', () => { const n = sc.selectQuery(g.query); lMsg.say(`Selected ${plural(n, 'element')}.`); }));
        groupBox.append(line);
      }
    }
    const na = sc.report.unlinkedActivities;
    if (na.length) {
      const d = el('details');
      d.append(help(el('summary', '', undefined, `${plural(na.length, 'activity')} without elements`), 'Unlinked activities'));
      const list = el('div', 'x4-list');
      for (const a of na.slice(0, 80)) list.append(el('div', 'x4-item', undefined, `${a.code} ${a.name}${a.hasSuggestion ? ' (suggestion)' : ''}`));
      d.append(list);
      noElBox.append(d);
    }
    const props = proposedLinks(sc.links);
    if (props.length) {
      sugBox.append(el('div', 'x4-dim', undefined, `${plural(props.length, 'suggestion')} to decide, best first.`));
      for (const l of props.slice(0, 60)) sugBox.append(linkRow(l, true));
    }
    const decided = [...linksWithStatus(sc.links, 'rejected'), ...linksWithStatus(sc.links, 'accepted').filter((l) => l.source === 'suggested' || l.source === 'manual')];
    for (const l of decided) decidedList.append(linkRow(l, false));
    decidedBox.style.display = decided.length ? '' : 'none';
  }

  // ---------------------------------------------------------------- Style
  const ySec = section('Style', 'style', false, 'Style');
  const yGrid = el('div', 'x4-grid');
  const field = (label: string, control: HTMLElement): void => { yGrid.append(el('label', '', undefined, label), control); };
  const select = (key: string, label: string, opts: Array<[string, string]>, onChange: (v: string) => void): HTMLSelectElement => {
    const s = help(el('select', '', { 'aria-label': label, 'data-style': key }), 'Style ' + key);
    for (const [v, t] of opts) s.append(el('option', '', { value: v }, t));
    s.addEventListener('change', () => onChange(s.value));
    return s;
  };
  const num = (key: string, label: string, min: string, max: string, step: string, onChange: (v: number) => void): HTMLInputElement => {
    const i = help(el('input', '', { type: 'number', min, max, step, 'aria-label': label, 'data-style': key }), 'Style ' + key);
    i.addEventListener('change', () => { const v = Number(i.value); if (Number.isFinite(v)) onChange(v); });
    return i;
  };
  const check = (key: string, label: string, onChange: (v: boolean) => void): { wrap: HTMLElement; input: HTMLInputElement } => {
    const wrap = el('label', 'x4-check');
    const input = help(el('input', '', { type: 'checkbox', 'data-style': key, 'aria-label': label }), 'Style ' + key);
    input.addEventListener('change', () => onChange(input.checked));
    wrap.append(input, el('span', '', undefined, 'On'));
    return { wrap, input };
  };
  const st = (): FourDStyle => sc.config.style;
  const view = select('view', 'View', [['planned', 'Planned'], ['actual', 'Actual to date, then forecast'], ['variance', 'Variance']], (v) => sc.setStyle({ view: v as FourDStyle['view'] }));
  const unbuilt = select('unbuilt', 'Unbuilt parts', [['hidden', 'Hidden'], ['ghost', 'Faint ghost']], (v) => sc.setStyle({ unbuilt: v as FourDStyle['unbuilt'] }));
  const win = select('window', 'Window', [['all', 'The whole job'], ['lookahead', 'Look ahead'], ['range', 'Date range']], (v) => {
    const dd = sc.schedule?.project.dataDate;
    if (v === 'all') sc.setStyle({ window: { kind: 'all' } });
    else if (v === 'lookahead') sc.setStyle({ window: { kind: 'lookahead', from: 'dataDate', weeks: 6 } });
    else sc.setStyle({ window: { kind: 'range', from: (dd ?? '2027-01-01').slice(0, 10), to: (dd ?? '2027-12-31').slice(0, 10) } });
  });
  const weeks = num('weeks', 'Weeks to look ahead', '1', '520', '1', (v) => { const w = st().window; if (w.kind === 'lookahead') sc.setStyle({ window: { ...w, weeks: Math.max(1, Math.round(v)) } }); });
  const rangeFrom = help(el('input', '', { type: 'date', 'aria-label': 'Range from', 'data-style': 'from' }), 'Style range from');
  const rangeTo = help(el('input', '', { type: 'date', 'aria-label': 'Range to', 'data-style': 'to' }), 'Style range to');
  const onRange = (): void => { if (rangeFrom.value && rangeTo.value) sc.setStyle({ window: { kind: 'range', from: rangeFrom.value, to: rangeTo.value } }); };
  rangeFrom.addEventListener('change', onRange);
  rangeTo.addEventListener('change', onRange);
  const winRow = el('div', 'x4-row');
  winRow.append(weeks, rangeFrom, rangeTo);
  const paceMode = select('pace mode', 'Film length by', [['length', 'Length in seconds'], ['days', 'Days per second']], (v) => {
    if (v === 'length') { const { daysPerSecond: _d, ...rest } = st(); sc.setConfig({ ...sc.config, style: { ...rest, length: 90 } }); }
    else { const { length: _l, ...rest } = st(); sc.setConfig({ ...sc.config, style: { ...rest, daysPerSecond: 7 } }); }
  });
  const paceVal = num('pace value', 'Seconds or days per second', '0.1', '3600', '0.5', (v) => { if (st().daysPerSecond !== undefined && st().length === undefined) sc.setStyle({ daysPerSecond: Math.max(0.1, v) }); else sc.setStyle({ length: Math.max(3, v) }); });
  const pace = select('pace', 'Pace', [['warp', 'Warp: busy weeks get more time'], ['fixed', 'Fixed']], (v) => sc.setStyle({ pace: v as FourDStyle['pace'] }));
  const camera = select('camera', 'Camera', [['director', 'Director'], ['fixed', 'Fixed: the current camera'], ['none', 'None']], (v) => sc.setStyle({ camera: v as FourDStyle['camera'] }));
  const explode = select('explode', 'Explode', [['auto', 'Auto'], ['off', 'Off']], (v) => sc.setStyle({ explode: v as FourDStyle['explode'] }));
  const xray = check('xray', 'X-ray the active work', (v) => sc.setStyle({ xrayFocus: v }));
  const secBox = select('section box', 'Section box', [['auto', 'Auto'], ['off', 'Off']], (v) => sc.setStyle({ sectionBox: v as FourDStyle['sectionBox'] }));
  const labels = num('labels', 'Labels', '0', '12', '1', (v) => sc.setStyle({ labels: Math.max(0, Math.min(12, Math.round(v))) }));
  const critical = num('critical', 'Critical float in hours', '0', '10000', '1', (v) => sc.setStyle({ criticalFloatHours: Math.max(0, v) }));
  const critOnly = check('critical only', 'Driving path only', (v) => sc.setStyle({ criticalFloatHours: v ? null : 0 }));
  const critRow = el('div', 'x4-row');
  critRow.append(critical, el('span', 'x4-dim', undefined, 'or driving path only'), critOnly.wrap);
  const captions = check('captions', 'Captions', (v) => sc.setStyle({ captions: v }));
  const hold = num('hold', 'Milestone hold in seconds', '0', '10', '0.5', (v) => sc.setStyle({ milestoneHold: Math.max(0, v) }));
  const splitSel = select('split', 'Split', [['', 'By trade'], ['none', 'All at once'], ['sweep_x', 'Sweep along x'], ['sweep_y', 'Sweep along y'], ['sweep_z', 'Sweep up'], ['by_storey', 'Storey by storey'], ['by_name', 'By name']], (v) => sc.setConfig(setSplit(sc.config, '*', v as SplitRule | '')));
  field('View', view); field('Unbuilt parts', unbuilt); field('Window', win); field('', winRow);
  field('Film length by', paceMode); field('Value', paceVal); field('Pace', pace); field('Camera', camera); field('Explode', explode);
  field('X-ray active work', xray.wrap); field('Section box', secBox); field('Labels', labels); field('Critical float', critRow);
  field('Captions', captions.wrap); field('Milestone hold', hold); field('Default split', splitSel);
  const colourBox = el('div', 'x4-list', { 'data-x4': 'trade-colours' });
  colourBox.style.maxHeight = '220px';
  const cameraNote = el('div', 'x4-warn', { 'data-x4': 'camera-note' });
  ySec.append(el('div', 'x4-dim', undefined, 'The film options. They are part of the configuration.'), yGrid, el('div', 'x4-dim', undefined, 'Trade colours'), colourBox, cameraNote);

  function renderStyle(): void {
    const s = st();
    view.value = s.view; unbuilt.value = s.unbuilt; win.value = s.window.kind;
    weeks.style.display = s.window.kind === 'lookahead' ? '' : 'none';
    rangeFrom.style.display = rangeTo.style.display = s.window.kind === 'range' ? '' : 'none';
    if (s.window.kind === 'lookahead') weeks.value = String(s.window.weeks);
    if (s.window.kind === 'range') { rangeFrom.value = s.window.from.slice(0, 10); rangeTo.value = s.window.to.slice(0, 10); }
    const byDays = s.daysPerSecond !== undefined && s.length === undefined;
    paceMode.value = byDays ? 'days' : 'length';
    paceVal.value = String(byDays ? s.daysPerSecond : s.length ?? 90);
    pace.value = s.pace; camera.value = s.camera; explode.value = s.explode; xray.input.checked = s.xrayFocus; secBox.value = s.sectionBox;
    labels.value = String(s.labels);
    critical.value = String(s.criticalFloatHours ?? 0); critical.disabled = s.criticalFloatHours === null; critOnly.input.checked = s.criticalFloatHours === null;
    captions.input.checked = s.captions; hold.value = String(s.milestoneHold);
    splitSel.value = sc.config.split?.['*'] ?? '';
    colourBox.replaceChildren();
    const colours = sc.tradeColours();
    for (const k of Object.keys(colours).sort()) {
      const line = el('div', 'x4-item', { 'data-trade': k });
      const col = help(el('input', '', { type: 'color', value: colours[k]!, 'aria-label': `Colour of ${k}` }), 'Style trade colour');
      col.addEventListener('change', () => sc.setStyle({ colours: { ...sc.config.style.colours, [k]: col.value } }));
      line.append(col, el('span', '', undefined, k));
      colourBox.append(line);
    }
    if (!Object.keys(colours).length) colourBox.append(el('div', 'x4-dim', undefined, 'Trade values appear here once the schedule has a trade source. Colours come from the Values section.'));
    cameraNote.textContent = s.camera === 'director' && sc.note ? sc.note : '';
  }

  // ---------------------------------------------------------------- Play: the film bar (top of the tab, sticky) and the Play section
  const pMsg = msgBox();
  const bar = el('div', 'x4-film', { role: 'group', 'aria-label': '4D film', 'data-x4': 'film-bar' });
  help(bar, 'Film bar');
  const playBtn = btn('Play', 'Play film', () => { void sc.play().then((r) => pMsg.say(r.message, !r.ok)); }, 'primary');
  const pauseBtn = btn('Pause', 'Pause film', () => sc.pause());
  const stopBtn = btn('Stop', 'Stop film', () => sc.stopPlay());
  const recBtn = btn('Record', 'Record film', () => { void sc.record().then((r) => pMsg.say(r.message, !r.ok)); });
  const scriptBtn = btn('Open as script', 'Open film as script', () => { void sc.openAsScript().then((r) => pMsg.say(r.message, !r.ok)); });
  scriptBtn.setAttribute('data-x4', 'film-script');
  const pRow = el('div', 'x4-row', { 'data-x4': 'film-controls' });
  pRow.append(playBtn, pauseBtn, stopBtn, recBtn, scriptBtn);
  const slider = help(el('input', '', { type: 'range', min: '0', max: '1000', step: '1', value: '0', 'aria-label': 'Schedule date', 'data-x4': 'scrub' }), 'Scrub date');
  const dateOut = el('span', 'x4-date', { 'data-x4': 'scrub-date' }, '');
  const sRow = el('div', 'x4-row');
  sRow.append(slider, dateOut);
  const needText = el('span', '', { 'data-x4': 'film-need' });
  const needOpen = btn('Open schedule', 'Open schedule', () => xerIn.click(), 'primary');
  const needLink = btn('Link now', 'Link schedule', () => linkBtn.click(), 'primary');
  const need = el('div', 'x4-film-need', { 'data-x4': 'film-missing' });
  need.append(needText, needOpen, needLink);
  const pNote = el('div', 'x4-warn', { 'data-x4': 'play-note' });
  const controls = el('div', '', { 'data-x4': 'film-ready' });
  controls.style.cssText = 'display:flex;flex-direction:column;gap:6px';
  controls.append(pRow, sRow);
  bar.append(need, controls, pNote, pMsg.box);
  root.prepend(bar);

  const pSec = section('Play', 'play', true, 'Play');
  let dragging = false;
  const winMs = (): { from: number; to: number } | null => (sc.plan ? sc.plan.window : null);
  slider.addEventListener('input', () => {
    const w = winMs();
    if (!w) return;
    dragging = true;
    const ms = w.from + (Number(slider.value) / 1000) * (w.to - w.from);
    dateOut.textContent = formatDate(ms);
    void sc.seekDate(ms).then(() => { dragging = false; });
  });
  const saveBtn = btn('Save IFC with 4D links', 'Save IFC with links', () => {
    const w = window.__xrayIfcSave;
    if (!w) { pMsg.say('Save IFC is not available in this build.', true); return; }
    w.open();
  });
  pSec.append(el('div', 'x4-dim', undefined, 'The film controls (Play, date bar, Record, Open as script) are in the bar at the top of this tab. Space pauses. Save IFC writes the task codes of accepted links into the model file.'), saveBtn);

  function renderPlay(): void {
    const ready = !!sc.schedule && !!sc.links && sc.acceptedLinks().length > 0;
    need.style.display = ready ? 'none' : '';
    controls.style.display = ready ? 'flex' : 'none';
    if (!ready) {
      const noSchedule = !sc.schedule;
      needText.textContent = noSchedule ? 'Open a schedule to make the film.' : 'Link the schedule first to make the film.';
      needOpen.style.display = noSchedule ? '' : 'none';
      needLink.style.display = noSchedule ? 'none' : '';
    }
    playBtn.disabled = !ready;
    recBtn.disabled = !ready;
    scriptBtn.disabled = !ready;
    pauseBtn.disabled = !sc.playing;
    pauseBtn.textContent = sc.paused ? 'Resume' : 'Pause';
    stopBtn.disabled = !sc.playing;
    slider.disabled = !ready;
    saveBtn.disabled = sc.acceptedLinks().length === 0;
    pNote.textContent = sc.note;
    const w = winMs();
    if (!w) { dateOut.textContent = ready ? 'Press Play' : ''; return; }
    if (!dragging) {
      const ms = sc.playing ? sc.currentPlanMs() : null;
      if (ms !== null) { slider.value = String(Math.round(((ms - w.from) / Math.max(1, w.to - w.from)) * 1000)); dateOut.textContent = formatDate(ms); }
      else if (!dateOut.textContent || dateOut.textContent === 'Press Play') dateOut.textContent = formatDate(w.from);
    }
  }

  // ---------------------------------------------------------------- render
  let raf = 0;
  /** Draw everything again; the control that has the focus gets it back (a list is rebuilt after each change, and a Tab moves on). */
  function render(): void {
    const a = document.activeElement;
    const keep = a instanceof HTMLInputElement || a instanceof HTMLSelectElement ? { label: a.getAttribute('aria-label'), type: a.type, at: a instanceof HTMLInputElement && a.type === 'text' ? a.selectionStart : null, in: root.contains(a) } : null;
    renderSchedule();
    renderConfigure();
    renderLink();
    renderStyle();
    renderPlay();
    if (keep?.in && keep.label && (!document.activeElement || document.activeElement === document.body)) {
      const again = Array.from(root.querySelectorAll<HTMLInputElement | HTMLSelectElement>('input, select')).find((e) => e.getAttribute('aria-label') === keep.label && e.type === keep.type);
      if (again) { again.focus(); if (keep.at !== null && again instanceof HTMLInputElement && again.type === 'text') again.setSelectionRange(keep.at, keep.at); }
    }
  }
  const schedule = (): void => { if (!ctx.visible()) return; if (raf) return; raf = requestAnimationFrame(() => { raf = 0; render(); }); };
  const off = sc.onChange(schedule);
  const offMap = map.onChange(schedule);
  const tick = setInterval(() => { if (ctx.visible() && (sc.playing || dragging)) renderPlay(); }, 250);
  render();
  return {
    render,
    open(id) {
      // the film controls are the bar at the top, so the Play section shows the tab from its top
      const d = sections.get(id);
      if (d) d.open = true;
      const pane = root.parentElement;
      if (!d || id === 'play') { if (pane) pane.scrollTop = 0; return; }
      d.scrollIntoView({ block: 'start' });
    },
    dispose() { off(); offMap(); clearInterval(tick); if (raf) cancelAnimationFrame(raf); },
  };
}
