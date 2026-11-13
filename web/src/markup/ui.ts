// The Markup drawer: sets with thumbnails, the drawing toolbar (tools, colours, weight, fill, undo and redo), the list of
// markups with status, assignee, due date and comments, export and import. DOM only; logic lives in controller.ts.

import { el } from '../ui/dom';
import { button, check, note, row, section, select, statusLine } from '../tools/ui';
import { COLOURS, COLOUR_KEYS, KIND_LABEL, setCounts } from './model';
import type { ColourKey, Markup, Weight } from './model';
import { PDF_RESOLUTIONS, TOOLS, toolInfo } from './controller';
import type { PdfResolution } from './controller';
import type { MarkupController, ToolId } from './controller';
import type { MarkupView } from './view';
import { buildAttachChip } from './attachUi';
import type { PageSize } from './report';

const STYLE_ID = 'markup-styles';
const CSS = `
.mk-root { --mk-fg: var(--sb-fg, #dfe6ee); --mk-dim: var(--sb-dim, #8d99a8); --mk-line: var(--sb-line, #262d3a); --mk-hover: var(--sb-hover, #1c2230); --mk-sel: var(--sb-sel, #1f4a7a); --mk-accent: var(--sb-accent, #3b9cff);
  color: var(--mk-fg); font: 12px/1.4 system-ui, sans-serif; display: flex; flex-direction: column; gap: 8px; box-sizing: border-box; padding: 8px; position: relative; min-height: 100%; }
.mk-root * { box-sizing: border-box; }
.mk-root.mk-drop::after { content: 'Drop a markup PDF or JSON file to open'; position: absolute; inset: 0; background: rgba(31,74,122,0.85); display: flex; align-items: center; justify-content: center; font-size: 14px; border: 2px dashed var(--mk-accent); z-index: 5; text-align: center; padding: 12px; }
.mk-sets { display: grid; grid-template-columns: repeat(auto-fill, minmax(112px, 1fr)); gap: 6px; }
.mk-set { border: 1px solid var(--mk-line); border-radius: 5px; padding: 4px; cursor: pointer; display: flex; flex-direction: column; gap: 3px; background: transparent; color: inherit; font: inherit; text-align: left; }
.mk-set:hover { background: var(--mk-hover); }
.mk-set.sel { border-color: var(--mk-accent); background: var(--mk-sel); }
.mk-set img, .mk-set .mk-nothumb { width: 100%; aspect-ratio: 16 / 10; object-fit: cover; border-radius: 3px; background: #0e1218; display: block; }
.mk-set .mk-nothumb { display: flex; align-items: center; justify-content: center; color: var(--mk-dim); font-size: 10px; }
.mk-set-t { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mk-set-c { color: var(--mk-dim); font-size: 10.5px; }
.mk-in { background: #0e1218; color: var(--mk-fg); border: 1px solid var(--mk-line); border-radius: 4px; padding: 4px 6px; font: inherit; min-width: 0; width: 100%; }
.mk-in:focus { outline: 1px solid var(--mk-accent); }
.mk-tools { display: grid; grid-template-columns: repeat(auto-fill, minmax(58px, 1fr)); gap: 4px; }
.mk-tool { display: flex; flex-direction: column; align-items: center; gap: 2px; padding: 5px 2px 3px; border: 1px solid var(--mk-line); border-radius: 5px; background: transparent; color: var(--mk-fg); font: 10px/1.2 system-ui, sans-serif; cursor: pointer; min-height: 44px; }
.mk-tool:hover { background: var(--mk-hover); }
.mk-tool[aria-pressed=true] { background: var(--mk-sel); border-color: var(--mk-accent); }
.mk-tool svg { width: 20px; height: 20px; }
.mk-group { color: var(--mk-dim); font-size: 10px; text-transform: uppercase; letter-spacing: 0.04em; margin: 2px 0 -2px; }
.mk-swatches { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.mk-sw { width: 26px; height: 26px; border-radius: 50%; border: 2px solid transparent; cursor: pointer; padding: 0; outline: 1px solid var(--mk-line); }
.mk-sw[aria-pressed=true] { border-color: #fff; outline: 2px solid var(--mk-accent); }
.mk-weights { display: inline-flex; gap: 3px; }
.mk-w { width: 30px; height: 26px; border: 1px solid var(--mk-line); border-radius: 4px; background: transparent; color: var(--mk-fg); cursor: pointer; display: flex; align-items: center; justify-content: center; padding: 0; }
.mk-w[aria-pressed=true] { background: var(--mk-sel); border-color: var(--mk-accent); }
.mk-w i { display: block; width: 16px; background: currentColor; border-radius: 2px; }
.mk-list { display: flex; flex-direction: column; border: 1px solid var(--mk-line); border-radius: 4px; }
.mk-item { padding: 5px 6px; border-bottom: 1px solid var(--mk-line); display: flex; flex-direction: column; gap: 4px; cursor: pointer; }
.mk-item:last-child { border-bottom: 0; }
.mk-item:hover { background: var(--mk-hover); }
.mk-item.sel { background: var(--mk-sel); }
.mk-item.done .mk-it { opacity: 0.6; }
.mk-head { display: flex; gap: 6px; align-items: center; }
.mk-num { min-width: 22px; height: 22px; border-radius: 11px; display: inline-flex; align-items: center; justify-content: center; font-weight: 700; font-size: 11px; color: #fff; padding: 0 4px; flex: none; }
.mk-kind { color: var(--mk-dim); font-size: 11px; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mk-chip { font-size: 10.5px; padding: 0 7px; border-radius: 9px; line-height: 18px; border: 1px solid var(--mk-line); background: transparent; color: var(--mk-fg); cursor: pointer; white-space: nowrap; }
.mk-chip.open { background: #4a3a12; color: #ffd37a; border-color: transparent; }
.mk-chip.resolved { background: #16401f; color: #8fe0a0; border-color: transparent; }
.mk-x { border: 0; background: transparent; color: var(--mk-dim); cursor: pointer; font-size: 16px; line-height: 1; padding: 0 4px; }
.mk-x:hover { color: #ff8a8a; }
.mk-detail { display: flex; flex-direction: column; gap: 5px; cursor: default; }
.mk-two { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.mk-comment { border-left: 2px solid var(--mk-line); padding: 1px 0 1px 7px; }
.mk-comment .who { color: var(--mk-dim); font-size: 10.5px; }
.mk-empty { color: var(--mk-dim); padding: 10px; text-align: center; }
.mk-lbl { color: var(--mk-dim); font-size: 10.5px; display: flex; flex-direction: column; gap: 2px; }
.mk-small { font-size: 11px; color: var(--mk-dim); }
`;

function ensureStyles(): void {
  if (document.getElementById(STYLE_ID)) return;
  const s = document.createElement('style');
  s.id = STYLE_ID;
  s.textContent = CSS;
  document.head.appendChild(s);
}

const SVG = (body: string): string =>
  `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round" aria-hidden="true">${body}</svg>`;

export const TOOL_ICONS: Record<ToolId, string> = {
  select: SVG('<path d="M5 3l10 6.5-4.6 1.2L8.2 15.5z"/>'),
  cloud: SVG('<path d="M5.5 14.5a2.4 2.4 0 0 1-.4-4.6 3 3 0 0 1 3.2-3.2 3 3 0 0 1 5.4.6 2.6 2.6 0 0 1 1.4 5 2.6 2.6 0 0 1-3.3 2.2 3 3 0 0 1-3.1.6 2.6 2.6 0 0 1-3.2-.6z"/>'),
  cloudFree: SVG('<path d="M4 13.5a2.2 2.2 0 0 1-.2-4.2 2.8 2.8 0 0 1 3-2.8 2.8 2.8 0 0 1 4.8.4 2.4 2.4 0 0 1 1.2 4.4"/><path d="M11 17l5-5 1.5 1.5-5 5H11z"/>'),
  callout: SVG('<path d="M3 3.5h10v5.5H3z"/><path d="M9 9l5 6"/><circle cx="15" cy="16" r="1.4"/>'),
  text: SVG('<path d="M4 5.5V4h12v1.5M10 4v12M8 16h4"/>'),
  pointer: SVG('<path d="M4 16L15 5M15 5H8.6M15 5v6.4"/><circle cx="4.5" cy="15.5" r="1.2"/>'),
  highlight: SVG('<path d="M4 16h3.5l8-8-3.5-3.5-8 8z"/><path d="M11 6l3.5 3.5M3 18h6" stroke-width="1.2"/>'),
  highlightBox: SVG('<rect x="3.5" y="6" width="13" height="8" fill="currentColor" fill-opacity="0.35"/>'),
  rect: SVG('<rect x="3.5" y="5" width="13" height="10" rx="1"/>'),
  ellipse: SVG('<ellipse cx="10" cy="10" rx="7" ry="5"/>'),
  line: SVG('<path d="M4 16L16 4"/>'),
  arrow: SVG('<path d="M4 16L16 4M16 4H9.5M16 4v6.5"/>'),
  polyline: SVG('<path d="M3.5 15l4-8 4 5 5-7"/>'),
  polygon: SVG('<path d="M4 14.5l3-8.5 9 2.5-2 8z"/>'),
  pen: SVG('<path d="M3.5 15c3-9 5 3 8-4 1.5-3.5 3-3 5-5"/>'),
};

function when(s: string | undefined): string {
  if (!s) return '';
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? s : d.toLocaleString();
}

export function isMarkupFile(n: string): boolean {
  return /\.pdf$/i.test(n) || /\.json$/i.test(n);
}

let fileInput: HTMLInputElement | null = null;

/** The shared hidden file input (drawer button, panel button and palette action all use it). */
export function markupFileInput(c: MarkupController): HTMLInputElement {
  if (fileInput && document.body.contains(fileInput)) return fileInput;
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '.pdf,.json,application/pdf,application/json';
  input.style.display = 'none';
  input.setAttribute('data-markup', 'open');
  input.addEventListener('change', () => {
    const f = input.files?.[0];
    input.value = '';
    if (f) void openFile(c, f);
  });
  document.body.appendChild(input);
  fileInput = input;
  return input;
}

export function pickMarkupFile(c: MarkupController): void {
  markupFileInput(c).click();
}

export async function openFile(c: MarkupController, f: File): Promise<void> {
  try {
    const r = await c.importFile(f);
    if (r.warnings.length || !r.ok) {
      c.app.showMessage(r.ok ? `Markup opened. ${r.warnings[0]}` : (r.error ?? 'Could not open the markup file'));
      setTimeout(() => c.app.showMessage(null), 7000);
    }
  } catch (e) {
    c.setStatus(`Could not open the markup file: ${e instanceof Error ? e.message : String(e)}`);
  }
}

/** Window level drop of a PDF or JSON file that is not a model: anywhere on the page. Returns the remover. */
export function installDrop(c: MarkupController): () => void {
  const onDrop = (e: DragEvent): void => {
    const files = Array.from(e.dataTransfer?.files ?? []);
    // A lone .pdf or .json is never a model (models are .ifc or .glb, a .json goes with a .glb), so it is a markup file.
    if (files.length !== 1 || !isMarkupFile(files[0]!.name)) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    void openFile(c, files[0]!);
  };
  window.addEventListener('drop', onDrop, true);
  return () => window.removeEventListener('drop', onDrop, true);
}

/** Build the drawer. Returns the cleanup. */
export function buildDrawer(container: HTMLElement, c: MarkupController, view: MarkupView): () => void {
  ensureStyles();
  const root = el('div', 'mk-root');
  root.id = 'markup-drawer';
  container.appendChild(root);
  view.setActive(true);
  const status = statusLine(c.status);
  status.classList.add('mk-status');
  let recorded: string | null = null; // the markup whose text edit already has a history entry

  const render = (): void => {
    const focus = document.activeElement as HTMLElement | null;
    const keep = focus && root.contains(focus) ? focus.getAttribute('data-keep') : null;
    root.textContent = '';
    const set = c.active;

    // ---- sets
    root.appendChild(section('Sets'));
    root.appendChild(note('A set is one saved view and its markups. Select a set to bring its view back.'));
    const bar = row(
      button('New set from view', () => { try { c.newSet(); } catch (e) { c.setStatus(e instanceof Error ? e.message : String(e)); } }, { primary: true, title: 'Save the current view as a new markup set' }),
      button('Open file', () => pickMarkupFile(c), { title: 'Open a markup PDF or JSON file. You can also drop it on the page.' }),
    );
    root.appendChild(bar);
    if (c.sets.length) {
      const grid = el('div', 'mk-sets');
      for (const s of c.sets) {
        const card = el('button', `mk-set${s.id === c.activeId ? ' sel' : ''}`, { type: 'button', 'data-set': s.id, title: `${s.title}: restore the view` });
        if (s.thumb) card.appendChild(el('img', undefined, { src: s.thumb, alt: '', draggable: 'false' }));
        else card.appendChild(el('div', 'mk-nothumb', undefined, 'no picture'));
        card.appendChild(el('div', 'mk-set-t', undefined, s.title));
        const cn = setCounts(s);
        card.appendChild(el('div', 'mk-set-c', undefined, `${cn.total} markup${cn.total === 1 ? '' : 's'}${cn.total ? `, ${cn.open} open` : ''}`));
        card.addEventListener('click', () => void c.select(s.id));
        grid.appendChild(card);
      }
      root.appendChild(grid);
    } else root.appendChild(el('div', 'mk-empty', undefined, 'No markup set yet. Frame the view you want to mark up, then press New set from view.'));

    // ---- the active set
    if (set) {
      const title = el('input', 'mk-in', { type: 'text', 'aria-label': 'Set title', 'data-keep': 'title' });
      title.value = set.title;
      title.addEventListener('change', () => c.renameSet(set.id, title.value));
      root.appendChild(title);
      const pageSel = select<PageSize>('Page size', ['A4', 'Letter'], () => c.page, (v) => { c.page = v; });
      pageSel.update();
      const resLabel = (r: PdfResolution): string => (r === 'screen' ? 'screen' : `${r} dpi`);
      const resSel = select<string>('Picture quality', PDF_RESOLUTIONS.map(resLabel), () => resLabel(c.pdfResolution), (v) => { c.pdfResolution = PDF_RESOLUTIONS.find((r) => resLabel(r) === v) ?? 200; });
      resSel.update();
      const fileBtn = (label: string, fn: () => Promise<unknown> | unknown, o: { title: string; primary?: boolean }): HTMLButtonElement => {
        const b = button(label, () => {
          b.disabled = true;
          Promise.resolve()
            .then(fn)
            .catch((e) => c.setStatus(e instanceof Error ? e.message : String(e)))
            .finally(() => { b.disabled = false; });
        }, o);
        return b;
      };
      root.appendChild(row(
        button('Restore view', () => c.restore(set.id, true), { title: 'Bring back the camera, section, hidden elements and look of this set' }),
        fileBtn('Export PDF', () => c.downloadPdf({ ids: [set.id] }), { title: 'A PDF with the clean view, the marked view and the comment table. The JSON is attached.', primary: true }),
        fileBtn('Export JSON', () => c.downloadJson([set.id]), { title: 'The markup as a JSON file. Drop it on the viewer to restore the view and the markups.' }),
      ));
      root.appendChild(row(
        ...(c.sets.length > 1 ? [fileBtn('PDF of all sets', () => c.downloadPdf(), { title: 'One PDF with every set' })] : []),
        pageSel.root,
        resSel.root,
      ));
      const bcf = button('Convert to BCF topic', () => { void c.toBcf(set.id).catch((e) => c.setStatus(e instanceof Error ? e.message : String(e))); }, { title: 'Create a BCF topic with the viewpoint, the annotations and the comments' });
      bcf.setDisabled(c.bcfAvailable ? false : 'The BCF tool is not available in this build');
      const del = button('Delete set', () => {
        if (del.dataset['arm'] === '1') c.deleteSet(set.id);
        else { del.dataset['arm'] = '1'; del.textContent = 'Click again to delete'; setTimeout(() => { del.dataset['arm'] = ''; del.textContent = 'Delete set'; }, 2500); }
      }, { title: 'Remove this set and its markups from the session' });
      root.appendChild(row(bcf, del));
      const keepSel = select<string>('Shapes stay', ['on the model', 'on the screen'], () => (c.updateKeep === 'model' ? 'on the model' : 'on the screen'), (v) => { c.updateKeep = v === 'on the model' ? 'model' : 'screen'; });
      keepSel.update();
      root.appendChild(row(
        button('Update view', () => { try { c.updateView(set.id); } catch (e) { c.setStatus(e instanceof Error ? e.message : String(e)); } }, { title: 'Capture the view of this set again from the current camera. You can undo it.' }),
        keepSel.root,
      ));
      const vis = check('Show markups on the model', () => c.visible, (v) => { c.visible = v; c.emit(true); });
      vis.update();
      root.appendChild(vis.root);

      // ---- tools
      root.appendChild(section('Tools'));
      let group = '';
      let grid: HTMLElement | null = null;
      for (const t of TOOLS) {
        if (t.group !== group) {
          group = t.group;
          root.appendChild(el('div', 'mk-group', undefined, group));
          grid = el('div', 'mk-tools');
          root.appendChild(grid);
        }
        const b = el('button', 'mk-tool', { type: 'button', 'aria-pressed': String(c.tool === t.id), 'aria-label': t.label, title: `${t.label}: ${t.hint}`, 'data-tool-id': t.id });
        b.innerHTML = TOOL_ICONS[t.id];
        b.appendChild(el('span', undefined, undefined, t.label));
        b.addEventListener('click', () => {
          c.setTool(t.id === c.tool && t.id !== 'select' ? 'select' : t.id);
          // On a phone the drawer covers the view: close it to draw; the floating bar brings the tools back.
          if (c.tool !== 'select' && window.innerWidth < 760) window.__xrayToolbar?.close();
        });
        grid!.appendChild(b);
      }
      root.appendChild(el('div', 'mk-small', undefined, toolInfo(c.tool).hint));
      if (view.polyPoints > 0) root.appendChild(row(button('Finish', () => view.finishPoly(), { primary: true, title: 'Finish the polyline or polygon' }), button('Cancel drawing', () => view.cancel(), { title: 'Drop the corners so far' })));

      // colour, weight, fill
      const sw = el('div', 'mk-swatches');
      for (const k of COLOUR_KEYS) {
        const b = el('button', 'mk-sw', { type: 'button', 'aria-pressed': String(c.colour() === k), 'aria-label': k, title: k, 'data-colour': k });
        b.style.background = COLOURS[k as ColourKey];
        b.addEventListener('click', () => c.setColour(k));
        sw.appendChild(b);
      }
      root.appendChild(sw);
      const wts = el('div', 'mk-weights');
      ([1, 2, 3, 4] as Weight[]).forEach((w) => {
        const b = el('button', 'mk-w', { type: 'button', 'aria-pressed': String(c.weight === w), 'aria-label': `Line weight ${w}`, title: `Line weight ${w}`, 'data-weight': String(w) });
        const i = el('i');
        i.style.height = `${[1.5, 2.5, 4, 6][w - 1]}px`;
        b.appendChild(i);
        b.addEventListener('click', () => c.setWeight(w));
        wts.appendChild(b);
      });
      const fill = check('Fill', () => c.fill, (v) => c.setFill(v));
      fill.update();
      root.appendChild(row(wts, fill.root));
      const text = el('input', 'mk-in', { type: 'text', placeholder: 'Text for the next callout, text box or pointer', 'aria-label': 'Text for the next markup', 'data-keep': 'text' });
      text.value = c.text;
      text.addEventListener('input', () => { c.text = text.value; });
      root.appendChild(text);
      const undo = button('Undo', () => c.undo(), { title: 'Undo the last change (Ctrl+Z)' });
      const redo = button('Redo', () => c.redo(), { title: 'Redo (Ctrl+Shift+Z)' });
      undo.setDisabled(c.canUndo ? false : 'Nothing to undo');
      redo.setDisabled(c.canRedo ? false : 'Nothing to redo');
      const meas = c.measurements();
      root.appendChild(row(undo, redo));
      if (meas.length) {
        const sel = el('select', 'mk-in', { 'aria-label': 'Link a measurement', 'data-keep': 'meas' });
        sel.appendChild(el('option', undefined, { value: '' }, 'Link a measurement...'));
        for (const m of meas) sel.appendChild(el('option', undefined, { value: String(m.id) }, `Measurement ${m.id}: ${m.distance.toFixed(3)} m`));
        sel.addEventListener('change', () => { if (sel.value) c.linkMeasurement(Number(sel.value), c.text); });
        root.appendChild(sel);
      }

      // ---- markups
      root.appendChild(section('Markups'));
      if (!set.markups.length) root.appendChild(el('div', 'mk-empty', undefined, 'Pick a tool and draw on the view.'));
      else {
        const list = el('div', 'mk-list');
        for (const m of set.markups) list.appendChild(renderItem(m));
        root.appendChild(list);
      }
    }

    // ---- author and status
    const au = el('input', 'mk-in', { type: 'text', placeholder: 'Your name (author of markups and comments)', 'aria-label': 'Author', 'data-keep': 'author' });
    au.value = c.author;
    au.addEventListener('change', () => c.setAuthor(au.value));
    root.appendChild(au);
    status.set(c.status);
    root.appendChild(status);
    if (keep) root.querySelector<HTMLElement>(`[data-keep="${keep}"]`)?.focus();
  };

  const renderItem = (m: Markup): HTMLElement => {
    const sel = c.selected === m.id;
    const item = el('div', `mk-item${sel ? ' sel' : ''}${m.status === 'resolved' ? ' done' : ''}`, { 'data-mk-item': m.id });
    const head = el('div', 'mk-head');
    const num = el('span', 'mk-num', undefined, String(m.number));
    num.style.background = COLOURS[m.colour];
    if (m.colour === 'yellow') num.style.color = '#111';
    head.append(num, el('span', 'mk-kind', undefined, KIND_LABEL[m.kind]));
    const st = el('button', `mk-chip ${m.status}`, { type: 'button', title: m.status === 'open' ? 'Mark as resolved' : 'Reopen', 'data-act': 'status' }, m.status === 'open' ? 'Open' : 'Resolved');
    st.addEventListener('click', (e) => { e.stopPropagation(); c.patch(m.id, { status: m.status === 'open' ? 'resolved' : 'open' }); });
    const x = el('button', 'mk-x', { type: 'button', 'aria-label': `Delete markup ${m.number}`, title: 'Delete', 'data-act': 'delete' }, '×');
    x.addEventListener('click', (e) => { e.stopPropagation(); c.remove(m.id); });
    head.append(st, x);
    item.appendChild(head);
    if (c.detached(m)) item.appendChild(el('div', 'mk-small', { 'data-detached': '1' }, 'Detached: an element it was attached to is not in this model. Shown view-locked.'));
    const text = el('input', 'mk-in mk-it', { type: 'text', placeholder: 'Text', 'aria-label': `Text of markup ${m.number}`, 'data-keep': `t-${m.id}`, 'data-field': 'text' });
    text.value = m.text;
    text.addEventListener('click', (e) => e.stopPropagation());
    text.addEventListener('focus', () => { recorded = null; });
    text.addEventListener('input', () => {
      const f = c.markup(m.id);
      if (f && recorded !== m.id) { c.record(f.set); recorded = m.id; }
      c.patch(m.id, { text: text.value }, { quiet: true });
    });
    item.appendChild(text);
    if (sel) {
      const d = el('div', 'mk-detail');
      d.addEventListener('click', (e) => e.stopPropagation());
      const asg = el('input', 'mk-in', { type: 'text', 'aria-label': 'Assignee', placeholder: 'Assigned to', 'data-keep': `a-${m.id}`, 'data-field': 'assignee' });
      asg.value = m.assignee ?? '';
      asg.addEventListener('change', () => c.patch(m.id, { assignee: asg.value }));
      const due = el('input', 'mk-in', { type: 'date', 'aria-label': 'Due date', 'data-keep': `d-${m.id}`, 'data-field': 'due' });
      due.value = m.due ?? '';
      due.addEventListener('change', () => c.patch(m.id, { due: due.value }));
      const two = el('div', 'mk-two');
      two.append(asg, due);
      d.appendChild(two);
      d.appendChild(buildAttachChip(c, m, 'panel'));
      d.appendChild(el('div', 'mk-small', undefined, `${m.author}, ${when(m.created)}`));
      for (const cm of m.comments) {
        const box = el('div', 'mk-comment');
        box.appendChild(el('div', 'who', undefined, `${cm.author}, ${when(cm.date)}`));
        box.appendChild(el('div', undefined, undefined, cm.text));
        d.appendChild(box);
      }
      const ta = el('textarea', 'mk-in', { rows: '2', placeholder: 'Add a comment', 'aria-label': 'Comment', 'data-keep': `c-${m.id}`, 'data-field': 'comment' });
      d.appendChild(ta);
      const add = button('Add comment', () => { if (ta.value.trim()) c.comment(m.id, ta.value); }, { title: 'Add the comment to this markup, as the author named below' });
      const toBcf = button('Convert to BCF topic', () => {
        const s = c.active;
        if (s) void c.toBcf(s.id, m.id).catch((e) => c.setStatus(e instanceof Error ? e.message : String(e)));
      }, { title: 'Create a BCF topic for this markup only' });
      toBcf.setDisabled(c.bcfAvailable ? false : 'The BCF tool is not available in this build');
      d.appendChild(row(add, toBcf));
      item.appendChild(d);
    }
    item.addEventListener('click', () => c.selectMarkup(sel ? null : m.id));
    return item;
  };

  render();
  const off = c.onChange((quiet) => {
    if (quiet) {
      status.set(c.status);
      return;
    }
    render();
  });
  // Drop highlight on the drawer itself (the page-level drop handler does the work).
  const dragOn = (e: DragEvent): void => { if (e.dataTransfer?.types.includes('Files')) root.classList.add('mk-drop'); };
  const dragOff = (): void => root.classList.remove('mk-drop');
  root.addEventListener('dragover', dragOn);
  root.addEventListener('dragleave', dragOff);
  root.addEventListener('drop', dragOff);
  return () => {
    off();
    view.setActive(false);
    root.remove();
  };
}
