// The "Temporary works" section of the Film step: the rules of config.temporaryWorks (scaffold, falsework, formwork), one editable row each,
// and the layer's own visibility toggle. Draws the schedule controller's configuration; every change goes through setConfig. The rules travel in
// the `.4d.json`. Help keys `4D tab/Temporary works <name>` (src/ui/helpText.ts).

import type { TempWorksKind, TempWorksRule, TempWorksSize } from '../schedule/types';
import { KIND_NAME, TEMP_DEFAULTS, TEMP_KINDS, resolveRules } from '../schedule/tempworks';
import { el } from '../ui/dom';
import { setTempWorks, tempWorksRules } from './scheduleConfig';
import type { ScheduleController } from './scheduleController';

const KEY = '4D tab/Temporary works ';
function help<T extends HTMLElement>(e: T, key: string): T { e.setAttribute('data-help-key', KEY + key); return e; }

const SIZE_FIELDS: Record<TempWorksKind, Array<{ key: keyof TempWorksSize; label: string }>> = {
  scaffold: [{ key: 'offset', label: 'Offset from the face (m)' }, { key: 'width', label: 'Width (m)' }, { key: 'lift', label: 'Lift height (m)' }, { key: 'bay', label: 'Bay length (m)' }, { key: 'above', label: 'Above the top (m)' }],
  falsework: [{ key: 'spacing', label: 'Prop spacing (m)' }],
  formwork: [{ key: 'thickness', label: 'Panel thickness (m)' }],
};

export interface TempWorksSectionHandle { render(): void }

export function buildTempWorksSection(body: HTMLElement, sc: ScheduleController, layer: { visible: boolean; setVisible(v: boolean): void }): TempWorksSectionHandle {
  const intro = el('div', 'x4-dim', undefined, 'Scaffold, falsework and formwork the film builds around the permanent work. They are not part of the IFC model.');
  const showWrap = el('label', 'x4-check');
  const show = help(el('input', '', { type: 'checkbox', 'aria-label': 'Show temporary works', 'data-tw': 'show' }), 'show');
  show.addEventListener('change', () => layer.setVisible(show.checked));
  showWrap.append(show, el('span', '', undefined, 'Show in the film'));
  const list = el('div', 'x4-list', { 'data-x4': 'temp-rules' });
  const addRow = el('div', 'x4-row');
  const addKind = help(el('select', '', { 'aria-label': 'New rule kind', 'data-tw': 'add-kind' }), 'add');
  for (const k of TEMP_KINDS) addKind.append(el('option', '', { value: k }, KIND_NAME[k]));
  const add = help(el('button', '', { type: 'button', 'data-tw': 'add' }, 'Add rule'), 'add');
  add.addEventListener('click', () => {
    const kind = addKind.value as TempWorksKind;
    const rule: TempWorksRule = { kind, for: kind === 'scaffold' ? "class = 'IfcWall' and IsExternal = TRUE" : kind === 'falsework' ? "class = 'IfcSlab'" : "class in ('IfcSlab', 'IfcWall')" };
    sc.setConfig(setTempWorks(sc.config, [...tempWorksRules(sc.config), rule]));
  });
  addRow.append(addKind, add);
  const status = el('div', 'x4-dim', { 'data-x4': 'temp-status' });
  body.append(intro, showWrap, list, addRow, status);

  const rulesNow = (): TempWorksRule[] => tempWorksRules(sc.config).map((r) => JSON.parse(JSON.stringify(r)) as TempWorksRule);
  const save = (i: number, fn: (r: TempWorksRule) => void): void => {
    const rules = rulesNow();
    const r = rules[i];
    if (!r) return;
    fn(r);
    sc.setConfig(setTempWorks(sc.config, rules));
  };
  const numberBox = (label: string, value: number | undefined, placeholder: string, onSet: (v: number | undefined) => void, key: string, step = '0.1'): HTMLInputElement => {
    const i = help(el('input', '', { type: 'number', step, min: '0', 'aria-label': label, placeholder }), key);
    if (value !== undefined) i.value = String(value);
    i.addEventListener('change', () => { const v = i.value.trim() === '' ? undefined : Number(i.value); if (v === undefined || Number.isFinite(v)) onSet(v); });
    return i;
  };
  const textBox = (label: string, value: string | undefined, placeholder: string, onSet: (v: string) => void, key: string): HTMLInputElement => {
    const i = help(el('input', '', { type: 'text', 'aria-label': label, placeholder, spellcheck: 'false' }), key);
    i.value = value ?? '';
    i.addEventListener('change', () => onSet(i.value.trim()));
    return i;
  };

  function render(): void {
    show.checked = layer.visible;
    list.replaceChildren();
    const rules = tempWorksRules(sc.config);
    const resolved = resolveRules(sc.config.temporaryWorks);
    rules.forEach((r, i) => {
      const n = i + 1;
      const row = el('div', 'x4-item', { 'data-rule': resolved[i]!.id });
      row.style.flexDirection = 'column';
      row.style.alignItems = 'stretch';
      const grid = el('div', 'x4-grid');
      const f = (label: string, c: HTMLElement): void => { grid.append(el('label', '', undefined, label), c); };
      const kind = help(el('select', '', { 'aria-label': `Rule ${n} kind` }), 'kind');
      for (const k of TEMP_KINDS) kind.append(el('option', '', { value: k }, KIND_NAME[k]));
      kind.value = r.kind;
      kind.addEventListener('change', () => save(i, (x) => { x.kind = kind.value as TempWorksKind; delete x.size; }));
      f(`Rule ${n}`, kind);
      f('Name', textBox(`Rule ${n} name`, r.name, KIND_NAME[r.kind], (v) => save(i, (x) => { if (v) x.name = v; else delete x.name; }), 'name'));
      f('Serves', textBox(`Rule ${n} for`, r.for, "class = 'IfcWall' and IsExternal = TRUE", (v) => save(i, (x) => { if (v) x.for = v; }), 'for'));
      const er = r.erect ?? {};
      f('Erect: days before', numberBox(`Rule ${n} erect days before`, er.daysBefore, 'default', (v) => save(i, (x) => setT(x, 'erect', 'daysBefore', v)), 'erect', '1'));
      f('Erect: takes (days)', numberBox(`Rule ${n} erect duration`, er.duration, 'default', (v) => save(i, (x) => setT(x, 'erect', 'duration', v)), 'erect', '1'));
      f('Erect: during activity', textBox(`Rule ${n} erect activity`, er.activity, 'activity code', (v) => save(i, (x) => setT(x, 'erect', 'activity', v || undefined)), 'erect'));
      const sk = r.strike ?? {};
      f('Strike: days after', numberBox(`Rule ${n} strike days after`, sk.daysAfter, 'default', (v) => save(i, (x) => setT(x, 'strike', 'daysAfter', v)), 'strike', '1'));
      f('Strike: takes (days)', numberBox(`Rule ${n} strike duration`, sk.duration, 'default', (v) => save(i, (x) => setT(x, 'strike', 'duration', v)), 'strike', '1'));
      f('Strike: after activity', textBox(`Rule ${n} strike after`, sk.after, 'the served work', (v) => save(i, (x) => setT(x, 'strike', 'after', v || undefined)), 'strike'));
      f('Strike: during activity', textBox(`Rule ${n} strike activity`, sk.activity, 'activity code', (v) => save(i, (x) => setT(x, 'strike', 'activity', v || undefined)), 'strike'));
      for (const sf of SIZE_FIELDS[r.kind]) {
        f(sf.label, numberBox(`Rule ${n} ${sf.label}`, r.size?.[sf.key], String(TEMP_DEFAULTS[sf.key]), (v) => save(i, (x) => { const s = { ...(x.size ?? {}) }; if (v !== undefined && v > 0) s[sf.key] = v; else delete s[sf.key]; if (Object.keys(s).length) x.size = s; else delete x.size; }), 'size'));
      }
      const del = help(el('button', '', { type: 'button', 'aria-label': `Remove rule ${n}` }, 'Remove'), 'remove');
      del.addEventListener('click', () => { const rs = rulesNow(); rs.splice(i, 1); sc.setConfig(setTempWorks(sc.config, rs)); });
      row.append(grid, del);
      list.append(row);
    });
    if (!rules.length) list.append(el('div', 'x4-dim', undefined, 'No rules. Add one to build temporary works into the film.'));
    const groups = sc.plan?.temporaryWorks?.groups.length;
    status.textContent = groups === undefined ? (rules.length ? 'Press Play to build the plan with these rules.' : '') : `${groups} temporary works ${groups === 1 ? 'group' : 'groups'} in the plan.`;
  }
  render();
  return { render };
}

function setT(r: TempWorksRule, which: 'erect' | 'strike', field: string, v: number | string | undefined): void {
  const t: Record<string, unknown> = { ...(r[which] ?? {}) };
  if (v === undefined || v === '') delete t[field];
  else t[field] = v;
  if (Object.keys(t).length) (r as unknown as Record<string, unknown>)[which] = t;
  else delete (r as unknown as Record<string, unknown>)[which];
}
