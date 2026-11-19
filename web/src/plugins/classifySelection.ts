// The "selected element" card at the top of the Classification tab: the result and the decision for the one selected element,
// with quick Accept, Change and Unsure controls. They record pending changes through the review service (the same path as the
// review walk: classify/reviewService.ts), and "Commit" writes them to the review log. Nothing here talks to a model.
// Docs: docs-features/classify.md, "The selected element".

import type { ViewerApp } from '../app';
import { divisionTitle, findDiscipline } from '../classify/schema';
import type { ClassifyService } from '../classify/service';
import type { ClassifyResult } from '../classify/types';
import { el } from '../ui/dom';

const pct = (x: number): string => `${Math.round(x * 100)}%`;
const when = (iso: string): string => (iso.length >= 16 ? `${iso.slice(0, 10)} ${iso.slice(11, 16)}` : iso);

/** Where a result came from, as a short phrase. */
export function sourceText(r: ClassifyResult): string {
  switch (r.source) {
    case 'model': return `model ${r.model ?? ''}`.trim();
    case 'cache': return `model ${r.model ?? ''} (cached)`.replace('  ', ' ');
    case 'rules': return 'rule';
    case 'manual': return 'manual';
    default: return `${r.source}${r.unsure ? ' (unsure)' : ''} by ${r.confirmedBy ?? '?'}${r.confirmedAt ? `, ${when(r.confirmedAt)}` : ''}`;
  }
}

export interface SelectionCard {
  root: HTMLElement;
  update(): void;
}

export function buildSelectionCard(app: ViewerApp, svc: ClassifyService, classifySelection: () => void): SelectionCard {
  const root = el('section', 'xcs', { 'aria-label': 'Selected element', 'data-testid': 'classify-selection' });
  const head = el('div', 'xcs-head');
  const title = el('div', 'xcs-title', { 'data-role': 'title' });
  head.append(el('span', 'xcs-h', undefined, 'Selected element'), title);
  const body = el('div', 'xcs-body');
  const acts = el('div', 'xcs-acts');
  const msg = el('div', 'xcs-msg', { role: 'status' });
  root.append(head, body, acts, msg);
  let editing: { disc: string; sub: string; div: string } | null = null;
  let message = '';
  let lastKey = '';

  const btn = (label: string, act: string, onClick: () => void, o: { primary?: boolean; title?: string; disabled?: boolean } = {}): HTMLButtonElement => {
    const b = el('button', `xcs-btn${o.primary ? ' primary' : ''}`, { type: 'button', 'data-act': act }, label);
    if (o.title) b.title = o.title;
    b.disabled = o.disabled === true;
    b.addEventListener('click', onClick);
    return b;
  };
  const select = (label: string, role: string, value: string, options: Array<[string, string]>, set: (v: string) => void): HTMLElement => {
    const l = el('label', 'xcs-sel');
    const s = el('select', undefined, { 'data-role': role, 'aria-label': label });
    for (const [v, t] of options) s.appendChild(el('option', undefined, { value: v }, t));
    s.value = value;
    s.addEventListener('change', () => set(s.value));
    l.append(el('span', undefined, undefined, label), s);
    return l;
  };

  const propose = (gid: string, action: 'confirm' | 'correct', unsure: boolean, codes?: { discipline?: string; subDiscipline?: string; division?: string }): void => {
    try {
      svc.review.propose([gid], { action, item: 'selection', ...(unsure ? { unsure: true } : {}), ...(codes ? { codes } : {}) });
      message = '';
    } catch (e) {
      message = e instanceof Error ? e.message : String(e);
    }
    editing = null;
    update(true);
  };

  const commit = (): void => {
    const input = root.querySelector<HTMLInputElement>('input[data-role=reviewer]');
    if (input && input.value.trim()) svc.review.setReviewer(input.value);
    try {
      const c = svc.review.commit('');
      message = `Committed ${c.changes.length} change${c.changes.length === 1 ? '' : 's'} as ${c.id}.`;
    } catch (e) {
      message = e instanceof Error ? e.message : String(e);
    }
    update(true);
  };

  function update(force = false): void {
    const sel = app.selection;
    const idx = sel[0];
    const model = svc.model;
    const e = idx === undefined || !model ? undefined : model.elements[idx];
    const r = e ? svc.store.get(e.globalId) : undefined;
    const pend = e ? svc.review.pendingFor(e.globalId) : undefined;
    const key = [e?.globalId ?? '', sel.length, r ? `${r.discipline.code}|${r.subDiscipline?.code ?? ''}|${r.masterformat?.division ?? ''}|${r.source}|${r.unsure ? 1 : 0}|${r.confirmedAt ?? ''}` : '-', pend ? `${pend.after.discipline}|${pend.after.subDiscipline}|${pend.after.division}|${pend.unsure ? 1 : 0}` : '-', svc.review.pending().length, svc.review.reviewer(), editing ? JSON.stringify(editing) : '', message].join('~');
    if (!force && key === lastKey) return;
    // A select that has focus is being used: leave it alone until the user is done.
    const a = document.activeElement;
    if (!force && editing && a && root.contains(a) && (a.tagName === 'SELECT' || a.tagName === 'INPUT')) return;
    lastKey = key;
    body.replaceChildren();
    acts.replaceChildren();
    msg.textContent = message;
    if (!e) {
      title.textContent = '';
      body.append(el('div', 'xcs-dim', { 'data-role': 'empty' }, model ? 'Select one element to see its classification here.' : 'Open a model to classify it.'));
      return;
    }
    title.textContent = `${e.ifcClass}${e.name ? `, ${e.name}` : ''}`;
    title.title = e.globalId;
    if (sel.length > 1) body.append(el('div', 'xcs-dim', { 'data-role': 'multi' }, `${sel.length} elements are selected: this is the first one.`));
    if (!r) {
      body.append(el('div', 'xcs-dim', { 'data-role': 'unclassified' }, 'Not classified yet.'));
      acts.append(btn('Classify this element', 'classify-one', classifySelection, { primary: true, title: 'Run the classifier on the selection' }));
      return;
    }
    const schema = svc.schema;
    const grid = el('dl', 'xcs-grid');
    const row = (k: string, v: string, role: string): void => {
      grid.append(el('dt', undefined, undefined, k), el('dd', undefined, { 'data-role': role }, v));
    };
    row('Discipline', `${r.discipline.code} ${r.discipline.label}  ${pct(r.discipline.confidence)}`, 'discipline');
    row('Sub-discipline', r.subDiscipline ? `${r.subDiscipline.code} ${r.subDiscipline.label}  ${pct(r.subDiscipline.confidence)}` : '-', 'sub');
    row('Division', r.masterformat ? `${r.masterformat.division} ${divisionTitle(schema, r.masterformat.division) ?? ''}`.trim() : '-', 'division');
    row('Source', sourceText(r), 'source');
    body.append(grid);
    if (r.rationale) body.append(el('div', 'xcs-dim', { 'data-role': 'rationale' }, `Why: ${r.rationale}`));
    if (r.needsReview) body.append(el('div', 'xcs-warn', { 'data-role': 'needs-review' }, 'Needs review.'));
    const decision = svc.review.decision(e.globalId);
    const state = pend
      ? `Pending: ${pend.after.source === 'corrected' ? `corrected to ${pend.after.discipline}${pend.after.subDiscipline ? `/${pend.after.subDiscipline}` : ''}${pend.after.division ? `/${pend.after.division}` : ''}` : 'confirmed'}${pend.unsure ? ' (unsure)' : ''}. Written when you commit.`
      : decision
        ? `Decision: ${decision}${r.unsure ? ' as unsure' : ''}${r.confirmedBy ? ` by ${r.confirmedBy}` : ''}.`
        : 'No decision yet.';
    body.append(el('div', pend ? 'xcs-ok' : 'xcs-dim', { 'data-role': 'decision' }, state));

    if (editing) {
      const ed = editing;
      const d = findDiscipline(schema, ed.disc);
      const fill = (): void => {
        const box = el('div', 'xcs-edit');
        const d2 = findDiscipline(schema, ed.disc);
        box.append(
          select('Discipline', 'edit-discipline', ed.disc, schema.disciplines.map((x): [string, string] => [x.code, `${x.code} ${x.label}`]), (v) => { ed.disc = v; ed.sub = ''; update(true); }),
          select('Sub-discipline', 'edit-sub', ed.sub, [['', '(none)'], ...(d2?.subDisciplines ?? []).map((s): [string, string] => [s.code, `${s.code} ${s.label}`])], (v) => { ed.sub = v; }),
          select('Division', 'edit-division', ed.div, [['', '(none)'], ...schema.masterformat.divisions.map((x): [string, string] => [x.division, `${x.division} ${x.title}`])], (v) => { ed.div = v; }),
        );
        body.append(box);
      };
      void d;
      fill();
      acts.append(
        btn('Apply change', 'apply-change', () => propose(e.globalId, 'correct', false, { discipline: ed.disc, ...(ed.sub ? { subDiscipline: ed.sub } : {}), ...(ed.div ? { division: ed.div } : {}) }), { primary: true }),
        btn('Cancel', 'cancel-change', () => { editing = null; update(true); }),
      );
    } else {
      acts.append(
        btn('Accept', 'accept', () => propose(e.globalId, 'confirm', false), { primary: true, title: 'Confirm these codes as right' }),
        btn('Change…', 'change', () => { editing = { disc: r.discipline.code, sub: r.subDiscipline?.code ?? '', div: r.masterformat?.division ?? '' }; update(true); }, { title: 'Pick other codes by hand' }),
        btn('Unsure', 'unsure', () => propose(e.globalId, 'confirm', true), { title: 'Confirm as a guess: still needs review, left out of Calibrate on confirmed' }),
      );
    }
    const n = svc.review.pending().length;
    if (n > 0 && !editing) {
      const foot = el('div', 'xcs-commit');
      if (!svc.review.reviewer()) foot.append(el('input', 'xcs-name', { type: 'text', 'data-role': 'reviewer', placeholder: 'Your name or initials', 'aria-label': 'Reviewer name', maxlength: '80' }));
      foot.append(btn(`Commit ${n} pending`, 'commit', commit, { title: 'Write the pending changes to the review log as one commit' }));
      acts.append(foot);
    }
  }

  return { root, update: () => update(false) };
}

export const SELECTION_CSS = `
.xcs{flex:0 0 auto;border:1px solid var(--sb-line,#262d3a);border-radius:5px;background:#10141b;padding:7px 8px;display:flex;flex-direction:column;gap:6px}
.xcs-head{display:flex;align-items:baseline;gap:8px;min-width:0}
.xcs-h{font-size:10px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--sb-dim,#8d99a8);flex:0 0 auto}
.xcs-title{font-weight:600;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.xcs-body{display:flex;flex-direction:column;gap:4px}
.xcs-grid{display:grid;grid-template-columns:92px 1fr;gap:1px 8px;margin:0}
.xcs-grid dt{color:var(--sb-dim,#8d99a8)}
.xcs-grid dd{margin:0;overflow-wrap:anywhere}
.xcs-dim{color:var(--sb-dim,#8d99a8);overflow-wrap:anywhere}
.xcs-warn{color:#e0b252}
.xcs-ok{color:#9fe3b0}
.xcs-acts{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.xcs-btn{background:#1b2230;color:inherit;border:1px solid #2d3748;border-radius:4px;padding:3px 10px;cursor:pointer;font:inherit;min-height:24px}
.xcs-btn:hover:not(:disabled){background:#243049;border-color:#3a4a66}
.xcs-btn:disabled{opacity:.45;cursor:default}
.xcs-btn.primary{background:#1f4a7a;border-color:#2d6aa8;color:#fff}
.xcs-edit{display:flex;flex-direction:column;gap:4px;margin-top:2px}
.xcs-sel{display:grid;grid-template-columns:92px 1fr;gap:6px;align-items:center;color:var(--sb-dim,#8d99a8)}
.xcs-sel select,.xcs-name{background:#0e1218;color:var(--sb-fg,#dfe6ee);border:1px solid var(--sb-line,#262d3a);border-radius:3px;height:24px;padding:0 5px;font:inherit;min-width:0}
.xcs-commit{display:flex;gap:6px;align-items:center;flex:1 1 100%}
.xcs-name{flex:1 1 120px}
.xcs-msg{color:var(--sb-dim,#8d99a8);min-height:0}
.xcs-msg:empty{display:none}
@media (max-width:700px){.xcs-btn{min-height:32px;padding:5px 12px}.xcs-sel select,.xcs-name{height:32px;font-size:14px}}
`;
