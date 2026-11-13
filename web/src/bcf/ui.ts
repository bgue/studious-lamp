// BCF file handling and the new-topic dialog (the issue list and detail are in src/issues/ui.ts). DOM only; logic lives in controller.ts.

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
.bcf-ann-t.callout { background: #4a2a12; color: #ffb27a; } .bcf-ann-t.note { background: #4a4212; color: #ffe97a; } .bcf-ann-t.arrow { background: #4a1426; color: #ff8fab; } .bcf-ann-t.rect { background: #4a1426; color: #ff8fab; } .bcf-ann-t.freehand { background: #4a3a0a; color: #ffc94d; }
.bcf-mlist { display: flex; flex-direction: column; border: 1px solid var(--bcf-line); border-radius: 4px; max-height: 140px; overflow: auto; }
.bcf-mrow { padding: 4px 8px; border-bottom: 1px solid var(--bcf-line); cursor: pointer; display: flex; gap: 8px; }
.bcf-mrow:last-child { border-bottom: 0; }
.bcf-mrow:hover { background: var(--bcf-hover); }
.bcf-other { border: 1px solid var(--bcf-line); border-radius: 5px; }
.bcf-other:empty { display: none; }
.bcf-other > summary { cursor: pointer; padding: 6px 8px; font-weight: 600; color: var(--bcf-dim); }
.bcf-other[open] > summary { border-bottom: 1px solid var(--bcf-line); }
.bcf-other-model { padding: 6px 8px; display: flex; flex-direction: column; gap: 4px; border-bottom: 1px solid var(--bcf-line); }
.bcf-other-model:last-child { border-bottom: 0; }
.bcf-other-topic { display: flex; flex-direction: column; gap: 4px; padding: 4px 0; }
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
      // Topics made on another model, or on none: say where they went (the same warning the markup file opening gives).
      if (c.lastImport?.message) {
        c.app.showMessage(`BCF opened. ${c.lastImport.message}`);
        setTimeout(() => c.app.showMessage(null), 7000);
      }
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
  const type = text('type', 'Issue', uniq(DEFAULT_TYPES, [...ext.topicTypes, ...c.currentTopics.map((t) => t.topicType)]));
  const status = text('status', 'Open', uniq(DEFAULT_STATUSES, [...ext.topicStatuses, ...c.currentTopics.map((t) => t.topicStatus)]));
  const priority = text('priority', 'Normal', uniq(DEFAULT_PRIORITIES, [...ext.priorities, ...c.currentTopics.flatMap((t) => (t.priority ? [t.priority] : []))]));
  const labels = text('labels');
  labels.placeholder = 'comma separated';
  const assigned = text('assigned', '', uniq(ext.users, c.currentTopics.flatMap((t) => (t.assignedTo ? [t.assignedTo] : []))));
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
