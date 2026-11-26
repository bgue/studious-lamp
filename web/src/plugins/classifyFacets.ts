// The "Facets" folder of the Classification tab: a switch per facet and the facet values of the selected element, each with its
// confidence and source and a picker to set it by hand (source `manual`). Core: classify/facets/*; docs-features/classify.md, "Facets".

import type { ViewerApp } from '../app';
import { FACET_IDS } from '../classify/facets/defs';
import type { FacetId } from '../classify/facets/defs';
import type { ClassifyService } from '../classify/service';
import { CONCRETE_FACET_IDS, METHOD_CODES, REINFORCEMENT_CODES, ROLE_CODES } from '../classify/concrete/defs';
import type { ConcreteCode, ConcreteFacetId } from '../classify/concrete/defs';
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
  const widgets: Array<{ update(): void }> = FACET_IDS.map((f) => {
    const w = check(`${f}${f === 'ClassRepair' ? ' (suggestions only)' : ''}`, () => svc.facetOn[f], (v) => svc.setFacetEnabled(f, v));
    w.root.title = HINT[f];
    w.root.dataset['facet'] = f;
    switches.appendChild(w.root);
    return w;
  });
  const cw = check('Concrete', () => svc.concreteOn, (v) => svc.setConcreteEnabled(v));
  cw.root.title = 'The XR_Concrete* sets of concrete elements: role, method, spec, reinforcement, measured geometry';
  cw.root.dataset['facet'] = 'Concrete';
  switches.appendChild(cw.root);
  widgets.push(cw);
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
    paintConcrete(id);
  };

  const PICK: Partial<Record<ConcreteFacetId, readonly ConcreteCode[]>> = { ConcreteElement: ROLE_CODES, ConcreteMethod: METHOD_CODES, ConcreteReinforcement: REINFORCEMENT_CODES };
  const SHOW: Record<ConcreteFacetId, readonly string[]> = {
    ConcreteGeometry: ['Volume', 'FormworkArea', 'Thickness', 'SectionShape'], ConcreteElement: ['Mark', 'HostGroup'], ConcreteMethod: [],
    ConcreteSpec: ['ExposureClass', 'CoverNominal'], ConcreteReinforcement: ['Scheme', 'RatioEstimate'],
  };
  const paintConcrete = (id: number): void => {
    if (!svc.concreteOn) return;
    const set = svc.concreteOf(id);
    for (const f of CONCRETE_FACET_IDS) {
      const r = set[f];
      if (!r) continue;
      const line = el('div', 'xc-facet-row', { 'data-facet': f });
      line.appendChild(el('span', 'xc-facet-name', undefined, f.replace('Concrete', 'Concrete ')));
      const extra = SHOW[f].filter((k) => r.fields[k] !== undefined).map((k) => `${k} ${r.fields[k]}`).join(', ');
      line.appendChild(el('span', `xc-facet-val${r.needsReview ? ' xc-review' : ''}`, { 'data-role': 'value' }, `${r.code}${extra ? ` (${extra})` : ''}`));
      line.appendChild(el('span', 'xt-note', { 'data-role': 'meta' }, `${Math.round(r.confidence * 100)}% ${r.source}${r.model ? ` ${r.model}` : ''}${r.needsReview ? ', review' : ''}`));
      const list = PICK[f];
      if (list) {
        const s = el('select', undefined, { 'aria-label': `Set ${f} by hand`, 'data-role': 'override' }) as HTMLSelectElement;
        s.appendChild(el('option', undefined, { value: '' }, 'Set by hand...'));
        for (const c of list) s.appendChild(el('option', undefined, { value: c.code }, `${c.code} ${c.label}`));
        s.addEventListener('change', () => {
          if (!s.value) return;
          void svc.overrideConcrete(id, f as 'ConcreteElement' | 'ConcreteMethod' | 'ConcreteReinforcement', s.value).then(() => { msg.textContent = ''; }, (e: unknown) => { msg.textContent = e instanceof Error ? e.message : String(e); });
        });
        line.appendChild(s);
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
