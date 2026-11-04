// BCF drawer (topic list, detail, comments), the new-topic dialog and file handling. DOM only; logic lives in controller.ts.

import { el } from '../ui/dom';
import type { BcfController } from './controller';
import { DEFAULT_PRIORITIES, DEFAULT_STATUSES, DEFAULT_TYPES } from './controller';
import type { BcfTopic } from './model';

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

  form.append(field('Title', title), field('Description', desc));
  const r1 = el('div', 'bcf-row');
  for (const f of [field('Type', type), field('Status', status), field('Priority', priority)]) {
    f.style.flex = '1 1 90px';
    r1.appendChild(f);
  }
  form.append(r1, field('Labels', labels), field('Assigned to', assigned), field('Author', author), snapLabel);
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
      onDone?.(t);
    } catch (e) {
      msg.textContent = e instanceof Error ? e.message : String(e);
    }
  };
}

// ---------------------------------------------------------------- drawer

export function buildDrawer(container: HTMLElement, c: BcfController): () => void {
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
  bar.append(bOpen, bNew, b21, b30, bClear);

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
  };
  search.oninput = () => {
    query = search.value.trim().toLowerCase();
    renderList();
  };
  search.addEventListener('keydown', (e) => e.stopPropagation());

  const matches = (t: BcfTopic): boolean => {
    if (filterStatus !== 'all' && t.topicStatus !== filterStatus) return false;
    if (!query) return true;
    const hay = [t.title, t.description ?? '', t.assignedTo ?? '', t.labels.join(' '), ...t.comments.map((x) => x.text)].join('\n').toLowerCase();
    return hay.includes(query);
  };

  const chip = (text: string, cls: string): HTMLSpanElement => el('span', `bcf-chip ${cls}`, undefined, text);

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

  const render = (): void => {
    status.textContent = c.status;
    renderList();
    renderDetail();
  };
  // Re-render on controller changes, but keep a half typed comment when only the status line changed.
  let lastKey = '';
  const off = c.onChange(() => {
    const key = `${c.selectedTopic}|${c.project.topics.length}|${c.project.topics.map((t) => `${t.topicStatus}${t.comments.length}${t.viewpoints.length}`).join(',')}|${c.applied?.viewpoint ?? ''}`;
    status.textContent = c.status;
    if (key !== lastKey) {
      lastKey = key;
      renderList();
      renderDetail();
    }
  });
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
    root.remove();
    for (const u of urls.values()) URL.revokeObjectURL(u);
    urls.clear();
  };
}

