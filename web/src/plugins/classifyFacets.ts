// The "Facets" folder of the Classification tab: a switch per facet and the facet values of the selected element, each with its
// confidence and source and a picker to set it by hand (source `manual`). Core: classify/facets/*; docs-features/classify.md, "Facets".

import type { ViewerApp } from '../app';
import { FACET_IDS } from '../classify/facets/defs';
import type { FacetId } from '../classify/facets/defs';
import type { ClassifyService } from '../classify/service';
import { button, check, row } from '../tools/ui';
import { el } from '../ui/dom';

const HINT: Record<FacetId, string> = {
  Trade: 'Who builds it',
  Placement: 'Exterior, interior or on the envelope; load-bearing',
  Material: 'What it is made of',
  Phase: 'When in the job it is built',
  Orientation: 'Which way it points (measured)',
  ClassRepair: 'A better IFC class for generic elements (suggestions only)',
};

export interface FacetsFolder {
  root: HTMLElement;
  update(): void;
}

export function buildFacetsFolder(app: ViewerApp, svc: ClassifyService): FacetsFolder {
  const root = el('details', 'xc-facets', { 'data-testid': 'classify-facets' }) as HTMLDetailsElement;
  root.open = true;
  root.appendChild(el('summary', undefined, undefined, 'Facets'));
  const switches = el('div', 'xt-list', { 'data-role': 'facet-switches' });
  const widgets = FACET_IDS.map((f) => {
    const w = check(`${f}${f === 'ClassRepair' ? ' (suggestions only)' : ''}`, () => svc.facetOn[f], (v) => svc.setFacetEnabled(f, v));
    w.root.title = HINT[f];
    w.root.dataset['facet'] = f;
    switches.appendChild(w.root);
    return w;
  });
  const sel = el('div', 'xc-facet-sel', { 'data-role': 'facet-selected' });
  const msg = el('div', 'xt-note');
  const runRow = row(
    button('Facets: selection', () => run('selection'), { title: 'Work out the facets of the selected elements' }),
    button('Facets: all', () => run('all'), { title: 'Work out the facets of every element' }),
  );
  root.append(switches, runRow, msg, sel);

  const run = (target: 'selection' | 'all'): void => {
    msg.textContent = '';
    if (target === 'selection' && app.selection.length === 0) { msg.textContent = 'Select elements in the model first.'; return; }
    void svc.classifyFacets(target).then(
      (r) => { msg.textContent = r ? `Facets done: ${r.stats.calls} request${r.stats.calls === 1 ? '' : 's'}, ${r.stats.needsReview} need review.` : ''; svc.notify(); },
      (e: unknown) => { msg.textContent = e instanceof Error ? e.message : String(e); },
    );
  };

  const paintSelected = (): void => {
    sel.replaceChildren();
    const ids = app.selection;
    if (ids.length !== 1) { sel.appendChild(el('div', 'xt-note', undefined, ids.length === 0 ? 'Select one element to see its facets.' : 'Select a single element to see its facets.')); return; }
    const id = ids[0]!;
    const set = svc.facetsOf(id);
    const defs = svc.facetDefs();
    for (const f of FACET_IDS) {
      if (!svc.facetOn[f]) continue;
      const r = set[f];
      const line = el('div', 'xc-facet-row', { 'data-facet': f });
      line.appendChild(el('span', 'xc-facet-name', undefined, f));
      line.appendChild(el('span', `xc-facet-val${r?.needsReview ? ' xc-review' : ''}`, { 'data-role': 'value' }, r ? `${r.code} ${r.label}` : '(none)'));
      if (r) line.appendChild(el('span', 'xt-note', { 'data-role': 'meta' }, `${Math.round(r.confidence * 100)}% ${r.source}${r.model ? ` ${r.model}` : ''}${r.needsReview ? ', review' : ''}`));
      if (f !== 'Orientation') {
        const s = el('select', undefined, { 'aria-label': `Set ${f} by hand`, 'data-role': 'override' }) as HTMLSelectElement;
        s.appendChild(el('option', undefined, { value: '' }, 'Set by hand...'));
        for (const c of defs[f].codes) s.appendChild(el('option', undefined, { value: c.code }, `${c.code} ${c.label}`));
        s.addEventListener('change', () => {
          if (!s.value) return;
          try { svc.overrideFacet(id, f, { code: s.value }); msg.textContent = ''; } catch (e) { msg.textContent = e instanceof Error ? e.message : String(e); }
        });
        line.appendChild(s);
        if (r?.source === 'manual') line.appendChild(button('Reset', () => { void svc.removeFacetOverride(id, f); }, { title: 'Remove the manual choice and work the facet out again' }));
      }
      sel.appendChild(line);
    }
  };

  const update = (): void => {
    for (const w of widgets) w.update();
    paintSelected();
  };
  document.addEventListener('xray-selection', paintSelected);
  update();
  return { root, update };
}
