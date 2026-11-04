// BCF drawer (topic list, detail, comments), the new-topic dialog and file handling. DOM only; logic lives in controller.ts.

import { el } from '../ui/dom';
import type { BcfController } from './controller';
import { DEFAULT_PRIORITIES, DEFAULT_STATUSES, DEFAULT_TYPES } from './controller';
import type { BcfAnnotation, BcfTopic, BcfViewpointRef } from './model';
import type { BcfMarkupView, PlaceKind } from './pins';
import { hasMarkup } from './sidecar';
import { formatLength } from '../measure/maths';

const STYLE_ID = 'bcf-styles';
const CSS = `
.bcf-root { --bcf-bg: var(--sb-bg, #141820); --bcf-fg: var(--sb-fg, #dfe6ee); --bcf-dim: var(--sb-dim, #8d99a8); --bcf-line: var(--sb-line, #262d3a);
  --bcf-hover: var(--sb-hover, #1c2230); --bcf-sel: var(--sb-sel, #1f4a7a); --bcf-accent: var(--sb-accent, #3b9cff);
  color: var(--bcf-fg); font: 12px/1.4 system-ui, sans-serif; display: flex; flex-direction: column; gap: 8px; box-sizing: border-box; padding: 8px; min-height: 100%; position: relative; }
.bcf-root * { box-sizing: border-box; }
.bcf-root.bcf-drop::after { content: 'Drop .bcf / .bcfzip to open'; position: absolute; inset: 0; background: rgba(31,74,122,0.85); display: flex; align-items: center; justify-content: center; font-size: 14px; border: 2px dashed var(--bcf-accent); z-index: 5; }
.bcf-row { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
.bcf-btn { background: var(--bcf-hover); color: var(--bcf-fg); border: 1px solid var(--bcf-line); border-radius: 4px; padding: 4px 8px; font: inherit; cursor: pointer; }
.bcf-btn:hover { border-color: var(--bcf-accent); }
.bcf-btn.primary { background: var(--bcf-sel); border-color: var(--bcf-accent); }
.bcf-btn:disabled { opacity: 0.45; cursor: default; }
.bcf-status { color: var(--bcf-dim); font-size: 11px; min-height: 1.4em; word-break: break-word; }
.bcf-in { background: #0e1218; color: var(--bcf-fg); border: 1px solid var(--bcf-line); border-radius: 4px; padding: 4px 6px; font: inherit; min-width: 0; }
.bcf-in:focus { outline: 1px solid var(--bcf-accent); }
.bcf-list { display: flex; flex-direction: column; border: 1px solid var(--bcf-line); border-radius: 4px; max-height: 220px; overflow: auto; }
.bcf-item { padding: 6px 8px; border-bottom: 1px solid var(--bcf-line); cursor: pointer; display: flex; flex-direction: column; gap: 3px; }
.bcf-item:last-child { border-bottom: 0; }
.bcf-item:hover { background: var(--bcf-hover); }
.bcf-item.sel { background: var(--bcf-sel); }
.bcf-title { font-weight: 600; word-break: break-word; }
.bcf-chip { display: inline-block; padding: 0 6px; border-radius: 9px; font-size: 10.5px; line-height: 16px; border: 1px solid transparent; white-space: nowrap; }
.bcf-chip.st-open { background: #4a3a12; color: #ffd37a; } .bcf-chip.st-progress { background: #14365c; color: #8cc4ff; }
.bcf-chip.st-done { background: #16401f; color: #8fe0a0; } .bcf-chip.st-other { background: #2a303c; color: #c3ccd8; }
.bcf-chip.pr-high { background: #5a1f1f; color: #ffa5a5; } .bcf-chip.pr-normal { background: #2a303c; color: #c3ccd8; } .bcf-chip.pr-low { background: #1d2a33; color: #9fb4c4; }
.bcf-chip.lbl { border-color: var(--bcf-line); color: var(--bcf-dim); }
.bcf-detail { border: 1px solid var(--bcf-line); border-radius: 4px; padding: 8px; display: flex; flex-direction: column; gap: 8px; }
.bcf-snap { width: 100%; max-height: 180px; object-fit: contain; background: #0e1218; border: 1px solid var(--bcf-line); border-radius: 3px; }
.bcf-meta { color: var(--bcf-dim); font-size: 11px; }
.bcf-desc { white-space: pre-wrap; word-break: break-word; }
.bcf-vps { display: flex; flex-direction: column; gap: 4px; }
.bcf-comment { border-left: 2px solid var(--bcf-line); padding: 2px 0 2px 8px; }
.bcf-comment .who { color: var(--bcf-dim); font-size: 11px; }
.bcf-h { font-weight: 600; color: var(--bcf-dim); text-transform: uppercase; font-size: 10.5px; letter-spacing: 0.04em; }
.bcf-empty { color: var(--bcf-dim); padding: 10px; text-align: center; }
.bcf-modal { position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 1000; display: flex; align-items: center; justify-content: center; }
.bcf-form { background: #141820; color: #dfe6ee; border: 1px solid #262d3a; border-radius: 6px; padding: 14px; width: min(420px, 94vw); max-height: 92vh; overflow: auto; display: flex; flex-direction: column; gap: 8px; font: 12px/1.4 system-ui, sans-serif; box-sizing: border-box; }
.bcf-form label { display: flex; flex-direction: column; gap: 3px; color: #8d99a8; font-size: 11px; }
.bcf-form .bcf-in { width: 100%; color: #dfe6ee; }
.bcf-form h3 { margin: 0 0 2px; font-size: 14px; }
.bcf-btn[aria-pressed=true] { background: var(--bcf-sel); border-color: var(--bcf-accent); }
.bcf-btn.placing { outline: 2px solid #ff7a2f; }
.bcf-ann-in { background: #0e1218; color: var(--bcf-fg); border: 1px solid var(--bcf-line); border-radius: 4px; padding: 3px 6px; font: inherit; min-width: 0; flex: 1 1 120px; }
.bcf-ann-in:focus { outline: 1px solid var(--bcf-accent); }
.bcf-anns { display: flex; flex-direction: column; gap: 4px; }
.bcf-ann { border: 1px solid var(--bcf-line); border-radius: 4px; padding: 4px 6px; display: flex; flex-direction: column; gap: 3px; cursor: pointer; }
.bcf-ann:hover { background: var(--bcf-hover); }
.bcf-ann.sel { border-color: var(--bcf-accent); }
.bcf-ann .bcf-row { flex-wrap: nowrap; }
.bcf-ann-t { font-size: 10.5px; padding: 0 6px; border-radius: 9px; line-height: 16px; white-space: nowrap; }
.bcf-ann-t.callout { background: #4a2a12; color: #ffb27a; } .bcf-ann-t.note { background: #4a4212; color: #ffe97a; } .bcf-ann-t.arrow { background: #4a1426; color: #ff8fab; }
.bcf-mlist { display: flex; flex-direction: column; border: 1px solid var(--bcf-line); border-radius: 4px; max-height: 140px; overflow: auto; }
.bcf-mrow { padding: 4px 8px; border-bottom: 1px solid var(--bcf-line); cursor: pointer; display: flex; gap: 8px; }
.bcf-mrow:last-child { border-bottom: 0; }
.bcf-mrow:hover { background: var(--bcf-hover); }
`;

function ensureStyles(): void {
  if (document.getElementById(STYLE_ID)) return;
  const s = document.createElement('style');
  s.id = STYLE_ID;
  s.textContent = CSS;
  document.head.appendChild(s);
}

export function isBcfName(n: string): boolean {
  return /\.(bcf|bcfzip)$/i.test(n);
}

function statusClass(s: string): string {
  const t = s.toLowerCase();
  if (/open|new|active|todo/.test(t)) return 'st-open';
  if (/progress|assigned|review/.test(t)) return 'st-progress';
  if (/resolv|clos|done|fixed/.test(t)) return 'st-done';
  return 'st-other';
}
function priorityClass(p: string): string {
  const t = p.toLowerCase();
  if (/crit|high|urgent|major/.test(t)) return 'pr-high';
  if (/low|minor/.test(t)) return 'pr-low';
  return 'pr-normal';
}
function when(s: string | undefined): string {
  if (!s) return '';
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? s : d.toLocaleString();
}

let fileInput: HTMLInputElement | null = null;

/** The shared hidden file input (drawer button, lil-gui button and palette action all use it). */
export function bcfFileInput(c: BcfController): HTMLInputElement {
  if (fileInput && document.body.contains(fileInput)) return fileInput;
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '.bcf,.bcfzip';
  input.multiple = true;
  input.style.display = 'none';
  input.setAttribute('data-bcf', 'open');
  input.addEventListener('change', () => {
    const files = Array.from(input.files ?? []);
    input.value = '';
    void openFiles(c, files);
  });
  document.body.appendChild(input);
  fileInput = input;
  return input;
}

export function pickBcfFile(c: BcfController): void {
  bcfFileInput(c).click();
}

export async function openFiles(c: BcfController, files: File[]): Promise<void> {
  const ok = files.filter((f) => isBcfName(f.name));
  if (!ok.length) {
    c.setStatus(`Not a BCF file: ${files.map((f) => f.name).join(', ')}`);
    return;
  }
  try {
    let merge = c.dirty;
    for (const f of ok) {
      await c.load(f, { merge });
      merge = true; // several files at once are combined
    }
  } catch (e) {
    c.app.showMessage(`Could not open BCF: ${e instanceof Error ? e.message : String(e)}`);
    setTimeout(() => c.app.showMessage(null), 4000);
  }
}

/** Window level drop of .bcf / .bcfzip anywhere in the page. Returns the remover. */
export function installDrop(c: BcfController): () => void {
  const onDrop = (e: DragEvent): void => {
    const files = Array.from(e.dataTransfer?.files ?? []);
    if (!files.length || !files.every((f) => isBcfName(f.name))) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    void openFiles(c, files);
  };
  window.addEventListener('drop', onDrop, true);
  return () => window.removeEventListener('drop', onDrop, true);
}

// ---------------------------------------------------------------- new topic dialog

export function openTopicDialog(c: BcfController, onDone?: (t: BcfTopic) => void): void {
  ensureStyles();
  if (document.getElementById('bcf-form')) return;
  const modal = el('div', 'bcf-modal');
  const form = el('div', 'bcf-form');
  form.id = 'bcf-form';
  form.appendChild(el('h3', undefined, undefined, 'Create topic from view'));

  const field = (label: string, input: HTMLElement): HTMLLabelElement => {
    const l = el('label', undefined, undefined, label);
    l.appendChild(input);
    return l;
  };
  const text = (id: string, value = '', list?: string[]): HTMLInputElement => {
    const i = el('input', 'bcf-in');
    i.id = `bcf-f-${id}`;
    i.value = value;
    if (list) {
      const dl = el('datalist');
      dl.id = `bcf-dl-${id}`;
      for (const v of list) dl.appendChild(el('option', undefined, { value: v }));
      form.appendChild(dl);
      i.setAttribute('list', dl.id);
    }
    return i;
  };
  const ext = c.project.extensions;
  const uniq = (a: string[], b: string[]): string[] => [...new Set([...a, ...b])];
  const title = text('title');
  const desc = el('textarea', 'bcf-in');
  desc.id = 'bcf-f-description';
  desc.rows = 3;
  const type = text('type', 'Issue', uniq(DEFAULT_TYPES, [...ext.topicTypes, ...c.topics.map((t) => t.topicType)]));
  const status = text('status', 'Open', uniq(DEFAULT_STATUSES, [...ext.topicStatuses, ...c.topics.map((t) => t.topicStatus)]));
  const priority = text('priority', 'Normal', uniq(DEFAULT_PRIORITIES, [...ext.priorities, ...c.topics.flatMap((t) => (t.priority ? [t.priority] : []))]));
  const labels = text('labels');
  labels.placeholder = 'comma separated';
  const assigned = text('assigned', '', uniq(ext.users, c.topics.flatMap((t) => (t.assignedTo ? [t.assignedTo] : []))));
  const author = text('author', c.author);
  author.placeholder = 'name or email (remembered)';
  const snap = el('input');
  snap.type = 'checkbox';
  snap.checked = true;
  snap.id = 'bcf-f-snapshot';
  const snapLabel = el('label');
  snapLabel.style.cssText = 'flex-direction:row;align-items:center;gap:6px';
  snapLabel.append(snap, document.createTextNode('Attach a snapshot of the current view'));
  const pinPick = el('input');
  pinPick.type = 'checkbox';
  pinPick.id = 'bcf-f-pinpick';
  const pinLabel = el('label');
  pinLabel.style.cssText = 'flex-direction:row;align-items:center;gap:6px';
  pinLabel.append(pinPick, document.createTextNode('Click the model to place the pin (else: middle of the selection)'));

  form.append(field('Title', title), field('Description', desc));
  const r1 = el('div', 'bcf-row');
  for (const f of [field('Type', type), field('Status', status), field('Priority', priority)]) {
    f.style.flex = '1 1 90px';
    r1.appendChild(f);
  }
  form.append(r1, field('Labels', labels), field('Assigned to', assigned), field('Author', author), snapLabel, pinLabel);
  const msg = el('div', 'bcf-status');
  const row = el('div', 'bcf-row');
  row.style.justifyContent = 'flex-end';
  const cancel = el('button', 'bcf-btn', undefined, 'Cancel');
  const ok = el('button', 'bcf-btn primary', undefined, 'Create topic');
  ok.id = 'bcf-f-create';
  row.append(cancel, ok);
  form.append(msg, row);
  modal.appendChild(form);
  document.body.appendChild(modal);
  title.focus();

  const close = (): void => {
    modal.remove();
    window.removeEventListener('keydown', onKey, true);
  };
  const onKey = (e: KeyboardEvent): void => {
    if (e.key === 'Escape') {
      e.stopPropagation();
      close();
    }
  };
  window.addEventListener('keydown', onKey, true);
  // Keys typed in the form must not reach the viewer's shortcuts.
  modal.addEventListener('keydown', (e) => e.stopPropagation());
  modal.addEventListener('mousedown', (e) => {
    if (e.target === modal) close();
  });
  cancel.onclick = close;
  ok.onclick = () => {
    if (!title.value.trim()) {
      msg.textContent = 'A title is required';
      title.focus();
      return;
    }
    try {
      const t = c.createTopic({
        title: title.value,
        description: desc.value,
        type: type.value,
        status: status.value,
        priority: priority.value,
        labels: labels.value.split(',').map((s) => s.trim()).filter(Boolean),
        assignedTo: assigned.value,
        author: author.value,
        snapshot: snap.checked,
      });
      close();
      if (pinPick.checked) c.markup?.start('pin', t.guid);
      onDone?.(t);
    } catch (e) {
      msg.textContent = e instanceof Error ? e.message : String(e);
    }
  };
}

// ---------------------------------------------------------------- drawer

export function buildDrawer(container: HTMLElement, c: BcfController, view: BcfMarkupView | null = c.markup): () => void {
  ensureStyles();
  const root = el('div', 'bcf-root');
  root.id = 'bcf-drawer';
  container.appendChild(root);

  const bar = el('div', 'bcf-row');
  const mk = (label: string, fn: () => void, cls = ''): HTMLButtonElement => {
    const b = el('button', `bcf-btn ${cls}`.trim(), undefined, label);
    b.onclick = fn;
    return b;
  };
  const bOpen = mk('Open BCF', () => pickBcfFile(c));
  bOpen.setAttribute('data-act', 'open');
  const bNew = mk('New topic', () => openTopicDialog(c), 'primary');
  bNew.setAttribute('data-act', 'new');
  const b21 = mk('Export 2.1', () => void c.download('2.1'));
  b21.setAttribute('data-act', 'export-2.1');
  const b30 = mk('Export 3.0', () => void c.download('3.0'));
  b30.setAttribute('data-act', 'export-3.0');
  const bClear = mk('Clear viewpoint', () => void c.clearViewpoint());
  bClear.setAttribute('data-act', 'clear');
  const bPins = mk('Show pins', () => c.setPinsVisible(!c.pinsVisible));
  bPins.setAttribute('data-act', 'pins');
  bar.append(bOpen, bNew, b21, b30, bClear, bPins);

  const status = el('div', 'bcf-status');
  status.setAttribute('data-bcf-status', '');

  const filters = el('div', 'bcf-row');
  const statusSel = el('select', 'bcf-in');
  const search = el('input', 'bcf-in');
  search.placeholder = 'Search title, description, comments';
  search.style.flex = '1 1 120px';
  filters.append(statusSel, search);

  const list = el('div', 'bcf-list');
  list.setAttribute('data-bcf-list', '');
  const detail = el('div', 'bcf-detail');
  detail.setAttribute('data-bcf-detail', '');
  root.append(bar, status, filters, list, detail);

  const urls = new Map<string, string>();
  const urlFor = (guid: string, bytes: Uint8Array, mime: string): string => {
    let u = urls.get(guid);
    if (!u) {
      u = URL.createObjectURL(new Blob([bytes as Uint8Array<ArrayBuffer>], { type: mime }));
      urls.set(guid, u);
    }
    return u;
  };

  let filterStatus = 'all';
  let query = '';
  statusSel.onchange = () => {
    filterStatus = statusSel.value;
    renderList();
    view?.invalidate();
  };
  search.oninput = () => {
    query = search.value.trim().toLowerCase();
    renderList();
    view?.invalidate();
  };
  search.addEventListener('keydown', (e) => e.stopPropagation());

  const matches = (t: BcfTopic): boolean => {
    if (filterStatus !== 'all' && t.topicStatus !== filterStatus) return false;
    if (!query) return true;
    const hay = [t.title, t.description ?? '', t.assignedTo ?? '', t.labels.join(' '), ...t.comments.map((x) => x.text)].join('\n').toLowerCase();
    return hay.includes(query);
  };

  const chip = (text: string, cls: string): HTMLSpanElement => el('span', `bcf-chip ${cls}`, undefined, text);
  // Pins show, and follow the list filter, while the drawer is open.
  c.pinFilter = matches;
  c.setDrawerOpen(true);
  let measureOpen = false;
  let annText = '';

  function renderList(): void {
    const statuses = [...new Set(c.topics.map((t) => t.topicStatus).filter(Boolean))];
    statusSel.textContent = '';
    statusSel.appendChild(el('option', undefined, { value: 'all' }, 'All statuses'));
    for (const s of statuses) statusSel.appendChild(el('option', undefined, { value: s }, s));
    if (filterStatus !== 'all' && !statuses.includes(filterStatus)) filterStatus = 'all';
    statusSel.value = filterStatus;

    list.textContent = '';
    const shown = [...c.topics].filter(matches).sort((a, b) => (b.creationDate || '').localeCompare(a.creationDate || ''));
    if (!shown.length) {
      list.appendChild(el('div', 'bcf-empty', undefined, c.topics.length ? 'No topic matches the filter' : 'No topics. Open a BCF file or create a topic from the view.'));
    }
    for (const t of shown) {
      const row = el('div', `bcf-item${t.guid === c.selectedTopic ? ' sel' : ''}`);
      row.setAttribute('data-topic', t.guid);
      row.appendChild(el('div', 'bcf-title', undefined, t.title));
      const chips = el('div', 'bcf-row');
      chips.style.gap = '4px';
      if (t.topicStatus) chips.appendChild(chip(t.topicStatus, statusClass(t.topicStatus)));
      if (t.priority) chips.appendChild(chip(t.priority, priorityClass(t.priority)));
      if (t.pin) chips.appendChild(chip(`pin ${c.pinNumber(t)}`, 'lbl'));
      if (t.viewpoints.length) chips.appendChild(chip(`${t.viewpoints.length} view${t.viewpoints.length === 1 ? '' : 's'}`, 'lbl'));
      if (t.comments.length) chips.appendChild(chip(`${t.comments.length} comment${t.comments.length === 1 ? '' : 's'}`, 'lbl'));
      row.appendChild(chips);
      row.onclick = () => c.select(t.guid);
      list.appendChild(row);
    }
  }

  function renderDetail(): void {
    detail.textContent = '';
    const t = c.selectedTopic ? c.topic(c.selectedTopic) : undefined;
    if (!t) {
      detail.style.display = 'none';
      return;
    }
    detail.style.display = '';
    const first = t.viewpoints.find((v) => v.snapshot);
    if (first?.snapshot) {
      const img = el('img', 'bcf-snap');
      img.src = urlFor(first.guid, first.snapshot, first.snapshotMime ?? 'image/png');
      img.alt = 'Snapshot';
      detail.appendChild(img);
      if (hasMarkup(t)) void markedSnapshot(t, first, img);
    }
    detail.appendChild(el('div', 'bcf-title', undefined, t.title));
    const chips = el('div', 'bcf-row');
    chips.style.gap = '4px';
    const stSel = el('select', 'bcf-in');
    const statuses = [...new Set([...DEFAULT_STATUSES, ...c.project.extensions.topicStatuses, ...c.topics.map((x) => x.topicStatus), t.topicStatus].filter(Boolean))];
    for (const s of statuses) stSel.appendChild(el('option', undefined, { value: s }, s));
    stSel.value = t.topicStatus;
    stSel.onchange = () => c.setTopicStatus(t.guid, stSel.value);
    chips.appendChild(stSel);
    if (t.priority) chips.appendChild(chip(t.priority, priorityClass(t.priority)));
    if (t.topicType) chips.appendChild(chip(t.topicType, 'lbl'));
    for (const l of t.labels) chips.appendChild(chip(l, 'lbl'));
    detail.appendChild(chips);
    const meta = [`${t.creationAuthor || 'unknown'} · ${when(t.creationDate)}`];
    if (t.assignedTo) meta.push(`Assigned to ${t.assignedTo}`);
    if (t.dueDate) meta.push(`Due ${when(t.dueDate)}`);
    if (t.stage) meta.push(`Stage ${t.stage}`);
    detail.appendChild(el('div', 'bcf-meta', undefined, meta.join(' · ')));
    if (t.description) detail.appendChild(el('div', 'bcf-desc', undefined, t.description));

    if (t.viewpoints.length) {
      detail.appendChild(el('div', 'bcf-h', undefined, 'Viewpoints'));
      const vps = el('div', 'bcf-vps');
      t.viewpoints.forEach((v, i) => {
        const r = el('div', 'bcf-row');
        const applied = c.applied?.viewpoint === v.guid;
        const b = el('button', `bcf-btn${applied ? ' primary' : ''}`, undefined, `Apply${t.viewpoints.length > 1 ? ` ${i + 1}` : ''}`);
        b.setAttribute('data-act', 'apply');
        b.disabled = !v.data;
        b.title = v.problem ?? (v.data ? 'Apply this viewpoint' : 'No viewpoint data');
        b.onclick = () => void c.applyViewpoint(t.guid, v.guid);
        const clr = el('button', 'bcf-btn', undefined, 'Clear');
        clr.setAttribute('data-act', 'clear');
        clr.disabled = !applied;
        clr.onclick = () => void c.clearViewpoint();
        r.append(b, clr);
        if (v.data) {
          const bits = [v.data.camera ? (v.data.camera.kind === 'orthogonal' ? 'orthogonal camera' : 'camera') : '', v.data.selection.length ? `${v.data.selection.length} selected` : '', v.data.visibility ? 'visibility' : '', v.data.coloring.length ? 'colours' : '', v.data.clipping.length ? `${v.data.clipping.length} clip` : ''].filter(Boolean);
          r.appendChild(el('span', 'bcf-meta', undefined, bits.join(', ')));
        } else if (v.problem) r.appendChild(el('span', 'bcf-meta', undefined, v.problem));
        vps.appendChild(r);
      });
      detail.appendChild(vps);
    }

    renderMarkup(t);

    detail.appendChild(el('div', 'bcf-h', undefined, `Comments (${t.comments.length})`));
    for (const cm of t.comments) {
      const box = el('div', 'bcf-comment');
      box.appendChild(el('div', 'who', undefined, `${cm.author || 'unknown'} · ${when(cm.date)}${cm.viewpointGuid ? ' · with viewpoint' : ''}`));
      box.appendChild(el('div', 'bcf-desc', undefined, cm.text));
      detail.appendChild(box);
    }
    const ta = el('textarea', 'bcf-in');
    ta.rows = 2;
    ta.placeholder = 'Add a comment';
    ta.setAttribute('data-bcf-comment', '');
    ta.addEventListener('keydown', (e) => e.stopPropagation());
    const withView = el('input');
    withView.type = 'checkbox';
    const wl = el('label', 'bcf-meta');
    wl.style.cssText = 'display:flex;gap:4px;align-items:center';
    wl.append(withView, document.createTextNode('attach current view'));
    const add = el('button', 'bcf-btn', undefined, 'Add comment');
    add.setAttribute('data-act', 'comment');
    add.onclick = () => {
      if (!ta.value.trim() && !withView.checked) return;
      c.addComment(t.guid, ta.value, { viewpoint: withView.checked });
    };
    const ar = el('div', 'bcf-row');
    ar.append(add, wl);
    detail.append(ta, ar);
  }

  // ---------------------------------------------------------------- markup: pins and annotations

  const marked = new Map<string, { sig: string; url: string }>();
  /** Show the snapshot with the markup burned in, as the export writes it (cached per markup state). */
  async function markedSnapshot(t: BcfTopic, ref: BcfViewpointRef, img: HTMLImageElement): Promise<void> {
    const sig = JSON.stringify([t.pin, ref.annotations, c.pinNumber(t)]);
    const have = marked.get(ref.guid);
    if (have?.sig === sig) {
      img.src = have.url;
      return;
    }
    const bytes = await c.composeSnapshot(t, ref);
    if (!bytes || !img.isConnected) return;
    if (have) URL.revokeObjectURL(have.url);
    const url = URL.createObjectURL(new Blob([bytes as Uint8Array<ArrayBuffer>], { type: ref.snapshotMime ?? 'image/png' }));
    marked.set(ref.guid, { sig, url });
    img.src = url;
  }

  const kindLabel: Record<string, string> = { callout: 'Add callout', note: 'Add note', arrow: 'Add arrow' };

  /** Apply the viewpoint that annotations go to, so new annotations show at once. */
  function ensureApplied(t: BcfTopic): BcfViewpointRef | null {
    const ref = c.annotationViewpoint(t.guid);
    if (!ref) {
      c.setStatus('This topic has no viewpoint to annotate');
      return null;
    }
    if (c.applied?.viewpoint !== ref.guid) c.applyViewpoint(t.guid, ref.guid);
    return ref;
  }

  function describe(a: BcfAnnotation): string {
    const an = a.anchor;
    if (an.kind === 'measurement' && an.measurement) {
      const m = an.measurement;
      const names = (m.elementGuids ?? []).map(elementName);
      return `measurement ${m.label || formatLength(m.distance, 'm')}${names.length ? `: ${names.join(' to ')}` : ''}`;
    }
    if (an.kind === 'element' && an.elementGuid) return `element ${elementName(an.elementGuid)}`;
    return 'free point';
  }
  function elementName(gid: string): string {
    const model = c.app.loaded ? c.app.controller.model : null;
    const id = model?.byGlobalId.get(gid);
    const e = id !== undefined ? model!.elements[id] : undefined;
    if (!e) return `${gid} (not in model)`;
    const n = e.name && e.name.trim() ? e.name : e.ifcClass.replace(/^Ifc/, '');
    return `${n} (${e.ifcClass.replace(/^Ifc/, '')})`;
  }

  function renderMarkup(t: BcfTopic): void {
    detail.appendChild(el('div', 'bcf-h', undefined, 'Markup'));
    const placing = view?.placing?.topic === t.guid ? view.placing.kind : null;
    const pinRow = el('div', 'bcf-row');
    const place = (kind: PlaceKind): void => {
      if (!view) return;
      if (view.placing?.kind === kind && view.placing.topic === t.guid) {
        view.cancel();
        return;
      }
      if (kind !== 'pin' && !ensureApplied(t)) return;
      // The typed text goes to this annotation only; the box clears for the next one.
      if (view.start(kind, t.guid, annText.trim()) && kind !== 'pin') annText = '';
    };
    const bPin = el('button', `bcf-btn${placing === 'pin' ? ' placing' : ''}`, undefined, 'Place pin');
    bPin.setAttribute('data-act', 'place-pin');
    bPin.disabled = !view || !c.app.loaded;
    bPin.onclick = () => place('pin');
    pinRow.appendChild(bPin);
    if (t.pin) {
      const bRm = el('button', 'bcf-btn', undefined, 'Remove pin');
      bRm.setAttribute('data-act', 'remove-pin');
      bRm.onclick = () => c.setPin(t.guid, null);
      pinRow.appendChild(bRm);
      const where = t.pin.elementGuid ? ` on ${elementName(t.pin.elementGuid)}` : '';
      pinRow.appendChild(el('span', 'bcf-meta', undefined, `Pin ${c.pinNumber(t)}${where}`));
    } else pinRow.appendChild(el('span', 'bcf-meta', undefined, 'No pin'));
    detail.appendChild(pinRow);

    const ref = c.annotationViewpoint(t.guid);
    const can = !!view && !!ref && !!c.app.loaded;
    const txtRow = el('div', 'bcf-row');
    const txt = el('input', 'bcf-ann-in');
    txt.placeholder = 'Text for the next callout, note or arrow';
    txt.value = annText;
    txt.setAttribute('data-bcf-anntext', '');
    txt.oninput = () => { annText = txt.value; };
    txt.addEventListener('keydown', (e) => e.stopPropagation());
    txtRow.appendChild(txt);
    detail.appendChild(txtRow);
    const addRow = el('div', 'bcf-row');
    for (const kind of ['callout', 'note', 'arrow'] as const) {
      const b = el('button', `bcf-btn${placing === kind ? ' placing' : ''}`, undefined, kindLabel[kind]);
      b.setAttribute('data-act', `add-${kind}`);
      b.disabled = !can;
      b.title = ref ? '' : 'The topic has no viewpoint';
      b.onclick = () => place(kind);
      addRow.appendChild(b);
    }
    const bLink = el('button', 'bcf-btn', undefined, 'Link measurement');
    bLink.setAttribute('data-act', 'link-measurement');
    bLink.setAttribute('aria-pressed', String(measureOpen));
    bLink.disabled = !can;
    bLink.onclick = () => {
      measureOpen = !measureOpen;
      lastKey = '';
      renderDetail();
    };
    addRow.appendChild(bLink);
    detail.appendChild(addRow);

    if (measureOpen && can) {
      const ms = view!.measurements();
      const ml = el('div', 'bcf-mlist');
      ml.setAttribute('data-bcf-measures', '');
      if (!ms.length) ml.appendChild(el('div', 'bcf-empty', undefined, 'No measurements. Measure with the Measure tool first; the dimensions stay on the model.'));
      const linked = new Set((ref!.annotations ?? []).map((a) => a.anchor.measurement?.sourceId).filter((x) => x !== undefined));
      for (const m of ms) {
        const r = el('div', 'bcf-mrow');
        r.setAttribute('data-measure-id', String(m.id));
        const names = [m.elementA, m.elementB].filter((x): x is number => x !== undefined).map((id) => c.app.controller.model.elements[id]?.name || `#${id}`);
        r.append(el('span', undefined, undefined, `#${m.id}`), el('strong', undefined, undefined, formatLength(m.distance, 'm')),
          el('span', 'bcf-meta', undefined, `${m.kind === 'point' ? 'point to point' : names.join(' to ')}${linked.has(m.id) ? ' (linked)' : ''}`));
        r.onclick = () => {
          if (!ensureApplied(t)) return;
          view!.linkMeasurement(t.guid, m, annText.trim() || undefined);
          annText = '';
          measureOpen = false;
        };
        ml.appendChild(r);
      }
      detail.appendChild(ml);
    }

    // Annotation list, per viewpoint.
    const withAnn = t.viewpoints.filter((v) => v.annotations?.length);
    if (!withAnn.length) {
      detail.appendChild(el('div', 'bcf-meta', undefined, ref ? 'No annotations. Add one: the viewpoint applies and the next click on the model anchors it.' : 'The topic has no viewpoint to annotate.'));
      return;
    }
    const list = el('div', 'bcf-anns');
    list.setAttribute('data-bcf-anns', '');
    for (const v of withAnn) {
      const vi = t.viewpoints.indexOf(v);
      if (t.viewpoints.length > 1) list.appendChild(el('div', 'bcf-meta', undefined, `Viewpoint ${vi + 1}${c.applied?.viewpoint === v.guid ? ' (applied)' : ''}`));
      for (const a of v.annotations!) {
        const row = el('div', `bcf-ann${view?.selected === a.guid ? ' sel' : ''}`);
        row.setAttribute('data-ann', a.guid);
        const top = el('div', 'bcf-row');
        top.appendChild(el('span', `bcf-ann-t ${a.type}`, undefined, a.type));
        const inp = el('input', 'bcf-ann-in');
        inp.value = a.text;
        inp.placeholder = a.type === 'arrow' ? '(no text)' : 'Text';
        inp.setAttribute('data-ann', a.guid);
        inp.addEventListener('keydown', (e) => e.stopPropagation());
        inp.addEventListener('click', (e) => e.stopPropagation());
        inp.oninput = () => c.updateAnnotation(a.guid, { text: inp.value }, true);
        inp.onchange = () => c.updateAnnotation(a.guid, { text: inp.value });
        const del = el('button', 'bcf-btn', undefined, 'Delete');
        del.setAttribute('data-act', 'delete-annotation');
        del.onclick = (e) => {
          e.stopPropagation();
          c.removeAnnotation(a.guid);
        };
        top.append(inp, del);
        row.append(top, el('div', 'bcf-meta', undefined, describe(a)));
        row.onclick = () => {
          view?.focus(a.guid);
          lastKey = '';
          renderDetail();
        };
        list.appendChild(row);
      }
    }
    detail.appendChild(list);
  }

  if (view) {
    view.onEdit = (guid) => {
      const inp = root.querySelector<HTMLInputElement>(`input.bcf-ann-in[data-ann="${guid}"]`);
      if (!inp) return false;
      inp.focus();
      inp.select();
      return true;
    };
  }

  const render = (): void => {
    status.textContent = c.status;
    bPins.setAttribute('aria-pressed', String(c.pinsVisible));
    renderList();
    renderDetail();
  };
  // Re-render on controller changes, but keep a half typed comment when only the status line changed.
  let lastKey = '';
  const refresh = (): void => {
    const key = `${c.selectedTopic}|${c.project.topics.length}|${c.project.topics.map((t) => `${t.topicStatus}${t.comments.length}${t.viewpoints.length}`).join(',')}|${c.applied?.viewpoint ?? ''}|${c.markupRev}|${view?.placing?.kind ?? ''}|${view?.selected ?? ''}`;
    status.textContent = c.status;
    bPins.setAttribute('aria-pressed', String(c.pinsVisible));
    // Typing in an annotation box or dragging a text box only redraws the overlay; the drawer catches up afterwards.
    const typing = document.activeElement instanceof HTMLElement && root.contains(document.activeElement) && document.activeElement.matches('.bcf-ann-in');
    if (key !== lastKey && !typing && !view?.dragging) {
      lastKey = key;
      renderList();
      renderDetail();
    }
  };
  const off = c.onChange(refresh);
  const offView = view?.onChange(refresh);
  root.addEventListener('focusout', () => setTimeout(refresh, 0));
  render();

  // Drop onto the drawer.
  let depth = 0;
  root.addEventListener('dragenter', (e) => {
    e.preventDefault();
    depth++;
    root.classList.add('bcf-drop');
  });
  root.addEventListener('dragleave', () => {
    depth = Math.max(0, depth - 1);
    if (!depth) root.classList.remove('bcf-drop');
  });
  root.addEventListener('dragover', (e) => e.preventDefault());
  root.addEventListener('drop', (e) => {
    e.preventDefault();
    e.stopPropagation();
    depth = 0;
    root.classList.remove('bcf-drop');
    void openFiles(c, Array.from(e.dataTransfer?.files ?? []));
  });

  return () => {
    off();
    offView?.();
    view?.cancel(true);
    if (view) view.onEdit = null;
    if (c.pinFilter === matches) c.pinFilter = null;
    c.setDrawerOpen(false);
    view?.invalidate();
    root.remove();
    for (const u of urls.values()) URL.revokeObjectURL(u);
    urls.clear();
    for (const m of marked.values()) URL.revokeObjectURL(m.url);
    marked.clear();
  };
}

