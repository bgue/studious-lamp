// The Sheets segment of the Issues panel: the open PDFs, their pages with thumbnails, and the sketches drawn on each page. DOM only;
// logic is in controller.ts. Built into the panel by src/plugins/sheets.ts (IssuesController.sheetsPane).

import { el } from '../ui/dom';
import { button, row } from '../tools/ui';
import { KIND_LABEL } from '../markup/model';
import type { MarkupSet } from '../markup/model';
import type { IssuesController } from '../issues/controller';
import { buildViewSwitch } from '../issues/viewSwitchUi';
import type { SheetsController } from './controller';
import type { Sheet, SheetDoc } from './model';
import { isPlan, placementStatus } from './placement';

const STYLE_ID = 'sheets-pane-styles';
const CSS = `
.sh-doc { border: 1px solid var(--is-line, #262d3a); border-radius: 6px; padding: 6px; display: flex; flex-direction: column; gap: 6px; }
.sh-doc-h { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.sh-doc-h .sh-name { flex: 1 1 120px; min-width: 0; font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sh-pages { display: grid; grid-template-columns: repeat(auto-fill, minmax(104px, 1fr)); gap: 6px; }
.sh-page { border: 1px solid var(--is-line, #262d3a); border-radius: 5px; padding: 4px; cursor: pointer; display: flex; flex-direction: column; gap: 3px; background: transparent; color: inherit; font: inherit; text-align: left; }
.sh-page:hover { background: var(--is-hover, #1c2230); }
.sh-page.sel { border-color: var(--is-accent, #3b9cff); background: var(--is-sel, #1f4a7a); }
.sh-page img, .sh-page .sh-nothumb { width: 100%; aspect-ratio: 4 / 3; object-fit: contain; background: #fff; border-radius: 3px; display: flex; align-items: center; justify-content: center; color: #777; font-size: 10px; }
.sh-sketches { display: flex; flex-direction: column; border: 1px solid var(--is-line, #262d3a); border-radius: 4px; }
.sh-sketch { padding: 5px 6px; border-bottom: 1px solid var(--is-line, #262d3a); display: flex; flex-direction: column; gap: 4px; }
.sh-sketch:last-child { border-bottom: 0; }
.sh-sketch.active { background: var(--is-sel, #1f4a7a); }
.sh-sketch-h { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.sh-sketch-h .is-t { flex: 1 1 100px; }
.sh-place { display: flex; flex-direction: column; gap: 4px; border: 1px solid var(--is-line, #262d3a); border-radius: 4px; padding: 5px 6px; }
.sh-place.placed { border-color: #3b6c9c; }
.sh-place-h { display: flex; align-items: baseline; gap: 6px; flex-wrap: wrap; }
.sh-place-h .is-t { flex: 1 1 100px; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sh-status { font-weight: 700; }
.sh-status.placed { color: #7dd87d; }
.sh-status.not { color: var(--is-dim, #8d99a8); }
.sh-geo-note { color: #ffd27a; font-size: 11px; }
.sh-place select, .sh-opac input { max-width: 100%; min-width: 0; }
.sh-opac { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; font-size: 11px; color: var(--is-dim, #8d99a8); }
.sh-notes { display: flex; flex-direction: column; gap: 2px; color: var(--is-dim, #8d99a8); font-size: 11px; }
`;

function ensureStyles(): void {
  if (document.getElementById(STYLE_ID)) return;
  const s = document.createElement('style');
  s.id = STYLE_ID;
  s.textContent = CSS;
  document.head.appendChild(s);
}

const count = (n: number, one: string, many = `${one}s`): string => `${n} ${n === 1 ? one : many}`;
const tag = (text: string, cls = ''): HTMLSpanElement => el('span', `is-tag ${cls}`.trim(), undefined, text);

/** Build the pane: `render` returns the elements for the Issues panel's Sheets segment. */
export function sheetsPane(c: SheetsController, issues: IssuesController, pick: () => void, phoneClose: () => void): { render(): HTMLElement[]; status(): string } {
  ensureStyles();
  const fail = (e: unknown): void => c.setStatus(e instanceof Error ? e.message : String(e));
  const arm = (b: HTMLButtonElement, label: string, run: () => void): void => {
    b.addEventListener('click', () => {
      if (b.dataset['arm'] === '1') run();
      else {
        b.dataset['arm'] = '1';
        b.textContent = 'Click again to confirm';
        setTimeout(() => { b.dataset['arm'] = ''; b.textContent = label; }, 2500);
      }
    });
  };
  const act = (b: HTMLButtonElement, name: string): HTMLButtonElement => { b.setAttribute('data-act', name); return b; };
  const busyBtn = (label: string, fn: () => Promise<unknown>, o: { title: string; primary?: boolean }, name: string): HTMLButtonElement => {
    const b = act(button(label, () => {
      b.disabled = true;
      Promise.resolve().then(fn).catch(fail).finally(() => { b.disabled = false; });
    }, o), name);
    return b;
  };

  function sketchRow(set: MarkupSet, sheet: Sheet): HTMLElement {
    const active = c.markup.activeId === set.id;
    const box = el('div', `sh-sketch${active ? ' active' : ''}`, { 'data-sheet-sketch': set.id, 'data-readonly': set.readonly ? '1' : '0' });
    const h = el('div', 'sh-sketch-h');
    h.appendChild(el('span', 'is-t', undefined, set.title));
    const ref = issues.issueOf(set.id);
    if (set.readonly) h.appendChild(tag('read-only', 'lbl'));
    if (ref) h.appendChild(tag(`Issue: ${ref.topic.title}`, 'link'));
    h.appendChild(el('span', 'is-meta', undefined, count(set.markups.length, 'drawing')));
    box.appendChild(h);
    const btns: Array<HTMLElement | null> = [];
    if (set.readonly) {
      btns.push(act(button('Copy to editable sketch', () => { c.copyToEditable(set.id); }, { title: 'Make an editable copy of these annotations. The original stays read-only.' }), 'copy-editable'));
      btns.push(act(button('Show', () => { c.openSet(set); }, { title: 'Open the sheet' }), 'show'));
    } else {
      btns.push(act(button('Edit drawing', () => { c.openSet(set); c.markup.setEditing(true); phoneClose(); }, { primary: true, title: 'Open the sheet and draw on this sketch' }), 'edit-drawing'));
      if (!ref) btns.push(busyBtn('Raise as issue', () => issues.raise(set.id), { title: 'Make an issue of this sketch: a snapshot of the sheet region, the PDF as a document reference, and the shapes in the side file.', primary: false }, 'raise'));
      else btns.push(act(button('Open issue', () => issues.openIssue(ref.topic.guid, { apply: false }), { title: 'Open the issue this sketch belongs to' }), 'open-issue'));
      btns.push(busyBtn('JSON', async () => { c.markup.downloadJson([set.id]); }, { title: 'The sketch as a JSON file. Drop it on the viewer with its PDF open to get it back.' }, 'export-json'));
    }
    const del = act(button('Delete', () => undefined, { title: ref ? 'Remove this sketch. It belongs to an issue, so you are asked first.' : 'Remove this sketch' }), 'delete');
    if (ref) del.addEventListener('click', () => { issues.removeSketch(set.id); });
    else arm(del, 'Delete', () => { issues.removeSketch(set.id, true); });
    btns.push(del);
    box.appendChild(row(...btns));
    if (!set.readonly && issues.views.tied(set)) box.appendChild(buildViewSwitch({ mode: () => issues.views.mode(set), apply: (m) => { if (!issues.views.apply(set.id, m)) c.setStatus('The 3D, Plan and Section views need the model this sketch is attached to'); } }, { labelled: true, helpKey: 'Issues panel/View switch' }));
    if (issues.confirmRemove === set.id && ref) {
      const conf = el('div', 'is-confirm', { 'data-confirm-remove': set.id, role: 'alertdialog' });
      conf.appendChild(el('div', undefined, undefined, `"${set.title}" is a viewpoint of the issue "${ref.topic.title}". Remove it?`));
      conf.appendChild(row(act(button('Remove sketch', () => { issues.removeSketch(set.id, true); }), 'remove-confirm'), act(button('Keep it', () => issues.cancelRemove()), 'remove-cancel')));
      box.appendChild(conf);
    }
    if (set.readonly) {
      const notes = el('div', 'sh-notes', { 'data-imported-list': set.id });
      for (const m of set.markups.slice(0, 40)) {
        const who = m.author && m.author !== 'unknown' ? m.author : 'no author';
        notes.appendChild(el('div', undefined, { 'data-imported': m.id }, `${m.number}. ${KIND_LABEL[m.kind]}, ${who}${m.text ? `: ${m.text.slice(0, 120)}` : ''}`));
      }
      if (set.markups.length > 40) notes.appendChild(el('div', undefined, undefined, `and ${set.markups.length - 40} more`));
      box.appendChild(notes);
    }
    void sheet;
    return box;
  }

  /** The placement row of a sheet: status, level, and the actions. */
  function placeRow(sh: Sheet, d: SheetDoc): HTMLElement {
    const p = sh.placement;
    const box = el('div', `sh-place${p ? ' placed' : ''}`, { 'data-sheet-place': sh.id });
    const h = el('div', 'sh-place-h');
    h.appendChild(el('span', 'is-t', { title: sh.name }, d.pageCount > 1 ? `Page ${sh.page}` : sh.name));
    h.appendChild(el('span', `sh-status ${p ? 'placed' : 'not'}`, { 'data-placement-status': sh.id }, placementStatus(p)));
    if (p) h.appendChild(el('span', 'is-meta', undefined, p.level.name ?? `${p.level.elevation} m`));
    box.appendChild(h);
    const loaded = c.place.loaded;
    const btns: HTMLElement[] = [];
    btns.push(act(button(p ? 'Place again…' : 'Place in model…', () => { c.openPlace(sh.id); phoneClose(); }, { primary: !p, title: loaded ? 'Pick two points on the sheet and the same two in the model, or use the drawing scale. A geo-referenced PDF is placed by itself when the model has the same coordinate system.' : 'Open a model first' }), 'place'));
    if (p) {
      const on3 = c.shown3d.has(sh.id);
      const b3 = act(button('Show in 3D', () => c.setShow3d(sh.id, !on3), { title: 'The sheet as a textured quad at its level in the 3D view, with its sketches drawn on it' }), 'show3d');
      b3.setAttribute('aria-pressed', String(on3));
      btns.push(b3);
      if (isPlan(p)) {
        const onO = c.overlayOn.has(sh.id);
        const bo = act(button('Model overlay', () => { c.setOverlay(sh.id, !onO); if (!onO) { c.open(sh.id); phoneClose(); } }, { title: 'Draw the model as thin outlines over the sheet (the plan cut about 1.2 m above the level)' }), 'overlay');
        bo.setAttribute('aria-pressed', String(onO));
        btns.push(bo);
      }
      const rm = act(button('Remove placement', () => undefined, { title: 'Take the sheet out of the model. Its sketches stay on the sheet and lose their attachment to the model.' }), 'remove-placement');
      arm(rm, 'Remove placement', () => c.place.remove(sh.id));
      btns.push(rm);
    }
    box.appendChild(row(...btns));
    const note = !p ? c.place.geoNotes.get(sh.id) : undefined;
    if (note) box.appendChild(el('div', 'sh-geo-note', { 'data-geo-note': sh.id }, note));
    else if (!p && sh.geo) box.appendChild(el('div', 'sh-geo-note', { 'data-geo-note': sh.id }, `Found: ${sh.geo.summary}.`));
    return box;
  }

  function docBlock(d: SheetDoc): HTMLElement {
    const box = el('div', 'sh-doc', { 'data-doc': d.id });
    const h = el('div', 'sh-doc-h');
    h.appendChild(el('div', 'sh-name', { title: d.name }, d.name));
    h.appendChild(el('span', 'is-meta', undefined, count(d.pageCount, 'page')));
    box.appendChild(h);
    const del = act(button('Remove', () => undefined, { title: 'Remove this PDF and its sketches from the session' }), 'remove-doc');
    arm(del, 'Remove', () => { void c.removeDoc(d.id).catch(fail); });
    box.appendChild(row(
      busyBtn('Export marked-up PDF', () => c.downloadMarkedUp(d.id), { title: 'Download a copy of the PDF with your sketches as annotations on the layer "X-ray markups". The page content is not changed.', primary: true }, 'export-pdf'),
      del,
    ));
    const grid = el('div', 'sh-pages', { 'data-sheet-pages': d.id });
    const sheets = c.sheetsOf(d.id);
    for (const sh of sheets) {
      const n = c.sketchesOn(sh.id).length;
      const card = el('button', `sh-page${c.openId === sh.id ? ' sel' : ''}`, { type: 'button', 'data-sheet': sh.id, title: `${sh.name}: open the sheet` });
      const th = c.store.thumbs.get(sh.id);
      if (th) card.appendChild(el('img', undefined, { src: th, alt: `Thumbnail of ${sh.name}`, draggable: 'false' }));
      else card.appendChild(el('div', 'sh-nothumb', undefined, 'no picture'));
      card.appendChild(el('div', 'is-t', undefined, d.pageCount > 1 ? `Page ${sh.page}` : sh.name));
      card.appendChild(el('div', 'is-meta', undefined, n ? count(n, 'sketch', 'sketches') : `${Math.round(sh.widthPt)} x ${Math.round(sh.heightPt)} pt`));
      card.appendChild(el('div', `is-meta sh-status ${sh.placement ? 'placed' : 'not'}`, undefined, placementStatus(sh.placement)));
      card.addEventListener('click', () => { c.open(sh.id); phoneClose(); });
      grid.appendChild(card);
    }
    box.appendChild(grid);
    for (const sh of sheets) if (d.pageCount <= 6 || sh.placement || c.openId === sh.id) box.appendChild(placeRow(sh, d));
    for (const sh of sheets) {
      const sets = c.sketchesOn(sh.id).filter((s) => c.markup.inScope(s));
      if (!sets.length) continue;
      box.appendChild(el('div', 'is-h', undefined, d.pageCount > 1 ? `Sketches, page ${sh.page}` : 'Sketches'));
      const list = el('div', 'sh-sketches', { 'data-sheet-sketches': sh.id });
      for (const s of sets) list.appendChild(sketchRow(s, sh));
      box.appendChild(list);
    }
    return box;
  }

  return {
    status: () => c.status,
    render(): HTMLElement[] {
      const out: HTMLElement[] = [];
      out.push(row(
        act(button('Open PDF', pick, { primary: true, title: 'Open a PDF drawing as sheets, one per page. You can also drop it on the page. It does not replace the model.' }), 'open-pdf'),
      ));
      const { here, other } = c.docs();
      if (here.some((d) => c.sheetsOf(d.id).some((x) => x.placement))) {
        const o = el('label', 'sh-opac', { 'data-help-key': 'Sheets/3D opacity' }, 'Sheets in 3D, opacity');
        const r = el('input', '', { type: 'range', min: '10', max: '100', step: '5', value: String(Math.round(c.quadOpacity * 100)), 'data-act': 'quad-opacity', 'aria-label': '3D sheet opacity' }) as HTMLInputElement;
        r.addEventListener('input', () => c.setQuadOpacity(Number(r.value) / 100));
        o.appendChild(r);
        out.push(o);
      }
      if (!here.length) out.push(el('div', 'is-empty', undefined, 'No sheets yet. Open a PDF drawing to view it, sketch on it and raise issues from it.'));
      for (const d of here) out.push(docBlock(d));
      const orphans = c.orphans().filter((s) => c.markup.inScope(s));
      if (orphans.length) {
        const o = el('div', 'sh-doc', { 'data-orphans': '' });
        o.appendChild(el('div', 'is-t', undefined, `Waiting for their PDF (${orphans.length})`));
        o.appendChild(el('div', 'is-meta', undefined, 'These sketches were drawn on a PDF that is not open. Open the same PDF and they find their sheet.'));
        for (const s of orphans) o.appendChild(el('div', 'is-meta', { 'data-orphan': s.id }, `${s.title}, ${count(s.markups.length, 'drawing')}`));
        out.push(o);
      }
      if (other.length) out.push(el('div', 'is-meta', { 'data-other-docs': '' }, `${count(other.length, 'PDF')} of other models hidden.`));
      return out;
    },
  };
}
