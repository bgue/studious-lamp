// The `presets` tool drawer: preset cards grouped by group, the save form, export / import. DOM only; all state
// comes from the PanelHost the plugin passes in.

import { el } from '../ui/dom';
import { button, note, row, section, statusLine } from '../tools/ui';
import { GROUPS, USER_GROUP, keyOf } from './model';
import type { Preset } from './model';
import type { ApplyResult } from './engine';

export interface PanelHost {
  list(): Preset[];
  activeId(): string | null;
  lastResult(): ApplyResult | null;
  apply(id: string): void;
  /** Sections that can be captured now, and which of them are ticked by default. */
  captureSections(): { all: string[]; defaults: string[] };
  save(name: string, sections: string[], description: string): { id: string; missing: string[] } | null;
  update(id: string, patch: { name?: string; description?: string }): void;
  duplicate(id: string): void;
  remove(id: string): void;
  share(id: string): void;
  exportFile(): void;
  importFile(): void;
  /** Subscribe to list / active / result changes. */
  subscribe(cb: () => void): () => void;
  /** True once when the parameter panel asked the drawer to show the save form. */
  takeSaveRequest(): boolean;
}

const CSS = `
.xp-card{border:1px solid var(--sb-line,#262d3a);border-radius:5px;padding:7px 9px;display:flex;flex-direction:column;gap:5px;background:#10141b}
.xp-card.on{border-color:#2d6aa8;background:#14233a}
.xp-head{display:flex;align-items:center;gap:6px}
.xp-name{font-weight:600;flex:1 1 auto;min-width:0}
.xp-key{font:11px ui-monospace,Menlo,Consolas,monospace;border:1px solid #3a4a66;border-radius:3px;padding:0 5px;color:#b9c4d2}
.xp-badge{font-size:10px;text-transform:uppercase;letter-spacing:.05em;background:#1f4a7a;color:#fff;border-radius:8px;padding:0 7px}
.xp-desc{color:#b9c4d2}
.xp-skip{color:#e0b36a;font-size:11px;word-break:break-word}
.xp-form{border:1px solid var(--sb-line,#262d3a);border-radius:5px;padding:8px;display:flex;flex-direction:column;gap:6px;background:#10141b}
.xp-form input[type=text]{background:#0e1218;color:inherit;border:1px solid var(--sb-line,#262d3a);border-radius:3px;height:24px;padding:0 6px;font:inherit;min-width:0;width:100%}
.xp-ticks{display:flex;flex-wrap:wrap;gap:4px 12px}
`;

function ensureStyle(): void {
  if (document.getElementById('xp-style')) return;
  const s = document.createElement('style');
  s.id = 'xp-style';
  s.textContent = CSS;
  document.head.appendChild(s);
}

export function presetsPanel(box: HTMLElement, host: PanelHost): () => void {
  ensureStyle();
  let formOpen = host.takeSaveRequest();
  let editing: string | null = null;
  const ticked = new Set<string>(host.captureSections().defaults.filter((s) => host.captureSections().all.includes(s)));
  const formState = { name: '', description: '' };
  const status = statusLine('');

  const buildForm = (): HTMLElement => {
    const f = el('div', 'xp-form');
    const { all } = host.captureSections();
    f.appendChild(section('Save current as preset'));
    const name = el('input', undefined, { type: 'text', placeholder: 'Name', 'aria-label': 'Preset name' }) as HTMLInputElement;
    name.value = formState.name;
    name.addEventListener('input', () => { formState.name = name.value; });
    const desc = el('input', undefined, { type: 'text', placeholder: 'Description (one sentence)', 'aria-label': 'Preset description' }) as HTMLInputElement;
    desc.value = formState.description;
    desc.addEventListener('input', () => { formState.description = desc.value; });
    f.append(name, desc, note('Sections to store:'));
    const ticks = el('div', 'xp-ticks');
    for (const s of all) {
      const l = el('label', 'xt-check');
      const cb = el('input', undefined, { type: 'checkbox' }) as HTMLInputElement;
      cb.checked = ticked.has(s);
      cb.addEventListener('change', () => { if (cb.checked) ticked.add(s); else ticked.delete(s); });
      l.append(cb, el('span', undefined, undefined, s));
      ticks.appendChild(l);
    }
    f.appendChild(ticks);
    const msg = el('div', 'xt-note');
    f.append(row(
      button('Save', () => {
        if (!formState.name.trim()) { msg.textContent = 'Give the preset a name.'; name.focus(); return; }
        if (ticked.size === 0) { msg.textContent = 'Tick at least one section.'; return; }
        const r = host.save(formState.name, [...ticked].filter((s) => all.includes(s)), formState.description);
        if (r) {
          formState.name = '';
          formState.description = '';
          formOpen = false;
          render();
          status.set(`Saved "${host.list().find((p) => p.id === r.id)?.name ?? r.id}".`);
        }
      }, { primary: true }),
      button('Cancel', () => { formOpen = false; render(); }),
    ), msg);
    setTimeout(() => name.focus(), 0);
    return f;
  };

  const card = (p: Preset, index: number): HTMLElement => {
    const active = host.activeId() === p.id;
    const c = el('div', `xp-card${active ? ' on' : ''}`, { 'data-preset': p.id });
    if (editing === p.id) {
      const name = el('input', undefined, { type: 'text', 'aria-label': 'Preset name' }) as HTMLInputElement;
      name.value = p.name;
      const desc = el('input', undefined, { type: 'text', 'aria-label': 'Preset description' }) as HTMLInputElement;
      desc.value = p.description;
      const form = el('div', 'xp-form');
      form.append(name, desc, row(
        button('Save', () => { host.update(p.id, { name: name.value, description: desc.value }); editing = null; render(); }, { primary: true }),
        button('Cancel', () => { editing = null; render(); }),
      ));
      c.appendChild(form);
      return c;
    }
    const head = el('div', 'xp-head');
    head.appendChild(el('span', 'xp-name', undefined, p.name));
    const k = keyOf(index);
    if (k) head.appendChild(el('span', 'xp-key', { title: `Press ${k} to apply` }, k));
    if (active) head.appendChild(el('span', 'xp-badge', undefined, 'active'));
    c.appendChild(head);
    c.appendChild(el('div', 'xp-desc', undefined, p.description));
    const res = host.lastResult();
    if (res && res.id === p.id && res.partial) {
      c.appendChild(el('div', 'xp-skip', undefined, `Partly applied. Skipped: ${res.skipped.slice(0, 8).join(', ')}${res.skipped.length > 8 ? ', ...' : ''}`));
    }
    const btns = [button('Apply', () => host.apply(p.id), { primary: true, title: k ? `Apply (key ${k})` : 'Apply' })];
    if (!p.builtIn) {
      btns.push(button('Edit', () => { editing = p.id; render(); }, { title: 'Rename or change the description' }));
      btns.push(button('Delete', () => host.remove(p.id)));
      btns.push(button('Share', () => host.share(p.id), { title: 'Copy a link that applies this preset' }));
    }
    btns.push(button('Duplicate', () => host.duplicate(p.id)));
    c.appendChild(row(...btns));
    return c;
  };

  const render = (): void => {
    box.textContent = '';
    box.appendChild(row(
      button('Save current as preset', () => { formOpen = !formOpen; render(); }, { primary: true }),
      button('Export', () => host.exportFile(), { title: 'Download your presets as JSON' }),
      button('Import', () => host.importFile(), { title: 'Add presets from a JSON file' }),
    ));
    if (formOpen) box.appendChild(buildForm());
    box.appendChild(status);
    const list = host.list();
    const groups = [...GROUPS, ...new Set(list.map((p) => p.group).filter((g) => !(GROUPS as readonly string[]).includes(g) && g !== USER_GROUP)), USER_GROUP];
    for (const g of groups) {
      const items = list.map((p, i) => ({ p, i })).filter((x) => x.p.group === g);
      if (items.length === 0) continue;
      box.appendChild(section(g));
      for (const { p, i } of items) box.appendChild(card(p, i));
    }
    if (!list.some((p) => !p.builtIn)) box.appendChild(note('Presets you save appear under "My presets". Keys 1 to 9 apply the first nine presets.'));
  };

  render();
  const off = host.subscribe(() => { if (host.takeSaveRequest()) formOpen = true; render(); });
  return off;
}
