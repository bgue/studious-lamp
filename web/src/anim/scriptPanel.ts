// The Script tab: an editor for animation scripts (src/anim/script) with line numbers, light syntax colouring, a live list of
// problems, Run / Pause / Stop through the score player, the line being played, examples, a statement reference, named scripts
// saved per model and .xrayanim export and import. Plain DOM: a transparent textarea over a coloured copy of its text.
// Phone: the right sidebar is a bottom sheet there, so the panel has one column, 16 px text and large buttons.

import { el } from '../ui/dom';
import { openMenu } from '../ui/popupMenu';
import type { ScorePlayerApi } from './score';
import { compileScript } from './script/compiler';
import type { CompileOptions, CompileResult } from './script/compiler';
import { formatDiagnostic } from './script/diagnostics';
import type { ScriptDiagnostic } from './script/diagnostics';
import { EXAMPLES } from './script/examples';
import { getPlan, registerPlan } from './fourd/plans';
import type { FourDPlan } from '../schedule/types';
import { highlightLine, markPieces } from './script/highlight';
import { runScript } from './script/runner';
import type { RunResult } from './script/runner';
import { ELEMENT_HELP, STATEMENT_HELP, TIMING_NOTES } from './script/scriptHelp';
import { cleanName, emptyDoc, exportFileName, exportText, findScript, importText, loadDoc, removeScript, saveDoc, uniqueScriptName, upsertScript } from './scriptStore';
import type { ScriptDoc, ScriptStorage } from './scriptStore';

export interface ScriptPanelDeps {
  /** Fresh options for each compile (the model, the sets and the settings may have changed). */
  compileOptions(): CompileOptions;
  player(): ScorePlayerApi | null;
  /** The identity key of the loaded model (scripts are kept per model). */
  modelKey(): string;
  storage: ScriptStorage | null;
  /** The mark on the tab button: the number of problems. */
  setBadge?(text: string): void;
  toast?(text: string, ms?: number): void;
  /** Give a text file to the person (a download). */
  download?(fileName: string, text: string): void;
  /** Open the video export (options dialog) for the compiled script. */
  record?(text: string, name: string): void;
}

export interface ScriptPanelState {
  name: string;
  dirty: boolean;
  errors: number;
  warnings: number;
  cues: number | null;
  duration: number | null;
  playingLine: number | null;
  status: string;
  running: boolean;
  paused: boolean;
}

const STYLE_ID = 'xray-script-style';
const LINE_H = 20;
const COMPILE_MS = 120;
const DRAFT_MS = 600;

const CSS = `
.as-root { --as-fs: 13px; display: flex; flex-direction: column; gap: 8px; padding: 8px 10px 14px; min-width: 0; color: var(--sb-fg, #dfe6ee); font: 12px/1.4 system-ui, -apple-system, 'Segoe UI', sans-serif; }
.as-row { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; min-width: 0; }
.as-btn { background: #1f2735; color: inherit; border: 1px solid #344055; border-radius: 4px; padding: 4px 9px; font: inherit; cursor: pointer; min-height: 26px; }
.as-btn:hover:not(:disabled) { background: #28344a; }
.as-btn:focus-visible, .as-name:focus-visible, .as-saved:focus-visible { outline: 2px solid var(--sb-accent, #3b9cff); outline-offset: 1px; }
.as-btn:disabled { opacity: 0.45; cursor: default; }
.as-btn.primary { background: #1d4f86; border-color: #3b9cff; color: #fff; }
.as-btn.primary:hover:not(:disabled) { background: #2461a3; }
.as-btn.armed { background: #5a2a2a; color: #fff; }
.as-name { flex: 1 1 120px; min-width: 0; background: #11161f; color: inherit; border: 1px solid #344055; border-radius: 4px; padding: 4px 7px; font: inherit; min-height: 26px; }
.as-saved { flex: 0 1 150px; min-width: 0; background: #11161f; color: inherit; border: 1px solid #344055; border-radius: 4px; padding: 3px 4px; font: inherit; min-height: 26px; }
.as-grow { flex: 1 1 auto; }
.as-msg { flex: 1 1 140px; min-width: 0; color: var(--sb-dim, #8d99a8); overflow-wrap: anywhere; }
.as-msg.bad { color: #ff9a8f; }
.as-msg.good { color: #8fd69a; }
.as-editor { position: relative; display: flex; height: 300px; min-height: 160px; resize: vertical; overflow: hidden; background: #0e131b; border: 1px solid #2d3748; border-radius: 4px;
  font: var(--as-fs)/${LINE_H}px ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace; tab-size: 2; }
.as-editor:focus-within { border-color: var(--sb-accent, #3b9cff); }
.as-gutter { position: relative; flex: 0 0 auto; width: 3.6ch; overflow: hidden; background: #121823; border-right: 1px solid #232c3b; color: #5d6b7e; text-align: right; user-select: none; }
.as-gutter-in { position: absolute; left: 0; right: 0; top: 0; padding: 6px 6px 6px 0; will-change: transform; }
.as-gn { height: ${LINE_H}px; line-height: ${LINE_H}px; cursor: pointer; padding-right: 2px; border-right: 3px solid transparent; }
.as-gn.error { color: #ff8a80; border-right-color: #ff5b4d; }
.as-gn.warning { color: #e0b252; border-right-color: #e0b252; }
.as-gn.play { color: #fff; background: #1d4f86; }
.as-code { position: relative; flex: 1 1 auto; min-width: 0; overflow: hidden; }
.as-hl { position: absolute; left: 0; top: 0; min-width: 100%; margin: 0; padding: 6px 8px; white-space: pre; pointer-events: none; will-change: transform; font: inherit; color: #d6dee9; }
.as-hl .as-l { height: ${LINE_H}px; }
.as-hl .as-l.play { background: rgba(59, 156, 255, 0.22); box-shadow: inset 3px 0 0 #3b9cff; }
.as-ta { position: absolute; inset: 0; width: 100%; height: 100%; margin: 0; padding: 6px 8px; resize: none; border: 0; outline: 0; background: transparent; color: transparent; caret-color: #fff;
  white-space: pre; overflow: auto; font: inherit; tab-size: 2; -webkit-text-fill-color: transparent; }
.as-ta::selection { background: rgba(59, 156, 255, 0.4); }
.as-ta::placeholder { color: #5d6b7e; -webkit-text-fill-color: #5d6b7e; }
.as-kw { color: #7cc0ff; font-weight: 600; } .as-opt { color: #c4a5ff; } .as-str { color: #9fdc8f; } .as-num { color: #f0b27a; }
.as-com { color: #6b7a8e; font-style: italic; } .as-op { color: #9aa7b8; } .as-el { color: #6fd6d0; }
.as-mark-error { text-decoration: underline wavy #ff5b4d; text-underline-offset: 3px; } .as-mark-warning { text-decoration: underline wavy #e0b252; text-underline-offset: 3px; }
.as-errors { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 3px; max-height: 170px; overflow-y: auto; }
.as-err { display: block; width: 100%; text-align: left; background: #161d29; color: inherit; border: 1px solid #2a3344; border-left: 3px solid #ff5b4d; border-radius: 3px; padding: 4px 7px; font: inherit; cursor: pointer; }
.as-err.warning { border-left-color: #e0b252; }
.as-err:hover { background: #1d2636; } .as-err:focus-visible { outline: 2px solid var(--sb-accent, #3b9cff); outline-offset: 1px; }
.as-err b { color: #fff; font-weight: 600; } .as-err .as-hint { display: block; color: var(--sb-dim, #8d99a8); margin-top: 1px; }
.as-ref { border: 1px solid #2a3344; border-radius: 4px; padding: 4px 8px; background: #11161f; }
.as-ref summary { cursor: pointer; font-weight: 600; padding: 3px 0; }
.as-ref h4 { margin: 10px 0 4px; font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--sb-dim, #8d99a8); }
.as-ref .as-item { padding: 5px 0; border-top: 1px solid #1e2634; }
.as-ref code, .as-ref pre { font: 12px/1.4 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; color: #bcd6f2; }
.as-ref pre { margin: 3px 0; padding: 4px 6px; background: #0b1017; border-radius: 3px; overflow-x: auto; white-space: pre; }
.as-ref p { margin: 2px 0; } .as-ref ul { margin: 4px 0 0; padding-left: 16px; }
@media (max-width: 700px) {
  .as-root { --as-fs: 16px; padding: 8px 8px 16px; }
  .as-btn, .as-name, .as-saved { min-height: 40px; font-size: 14px; padding: 6px 10px; }
  .as-editor { height: 240px; }
  .as-err { padding: 8px 9px; }
}
`;

function ensureStyle(): void {
  if (document.getElementById(STYLE_ID)) return;
  const st = document.createElement('style');
  st.id = STYLE_ID;
  st.textContent = CSS;
  document.head.appendChild(st);
}

const HELP = (name: string): Record<string, string> => ({ 'data-help-key': `Script tab/${name}`, 'data-help-title': name });

export class ScriptPanel {
  private root!: HTMLElement;
  private ta!: HTMLTextAreaElement;
  private hl!: HTMLElement;
  private gutterIn!: HTMLElement;
  private gutter!: HTMLElement;
  private errList!: HTMLElement;
  private msg!: HTMLElement;
  private nameIn!: HTMLInputElement;
  private savedSel!: HTMLSelectElement;
  private runBtn!: HTMLButtonElement;
  private pauseBtn!: HTMLButtonElement;
  private stopBtn!: HTMLButtonElement;
  private recBtn!: HTMLButtonElement;
  private delBtn!: HTMLButtonElement;
  private fileIn!: HTMLInputElement;
  private examplesBtn!: HTMLButtonElement;

  private doc: ScriptDoc = emptyDoc();
  private docKey = '';
  private diags: ScriptDiagnostic[] = [];
  private last: CompileResult | null = null;
  private playingLine: number | null = null;
  private running = false;
  private status = '';
  private statusKind: '' | 'bad' | 'good' = '';
  private savedText: string | null = null;
  private visible = true;
  private compileTimer: ReturnType<typeof setTimeout> | null = null;
  private draftTimer: ReturnType<typeof setTimeout> | null = null;
  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private delTimer: ReturnType<typeof setTimeout> | null = null;
  private mounted = false;

  constructor(private readonly deps: ScriptPanelDeps) {}

  // ---------------------------------------------------------------- build

  mount(pane: HTMLElement): () => void {
    ensureStyle();
    this.mounted = true;
    const root = el('div', 'as-root', { 'data-script-panel': '1' });
    this.root = root;

    // run row
    this.runBtn = el('button', 'as-btn primary', { type: 'button', ...HELP('Run'), 'data-act': 'run' }, 'Run') as HTMLButtonElement;
    this.pauseBtn = el('button', 'as-btn', { type: 'button', ...HELP('Pause'), 'data-act': 'pause' }, 'Pause') as HTMLButtonElement;
    this.stopBtn = el('button', 'as-btn', { type: 'button', ...HELP('Stop'), 'data-act': 'stop' }, 'Stop') as HTMLButtonElement;
    this.recBtn = el('button', 'as-btn', { type: 'button', title: 'Record the script as a video', ...HELP('Record'), 'data-act': 'record' }, 'Record') as HTMLButtonElement;
    this.msg = el('div', 'as-msg', { role: 'status', 'aria-live': 'polite', 'data-script-status': '1' });
    const runRow = el('div', 'as-row');
    runRow.append(this.runBtn, this.pauseBtn, this.stopBtn);
    if (this.deps.record) runRow.append(this.recBtn);
    runRow.append(this.msg);

    // file row
    this.nameIn = el('input', 'as-name', { type: 'text', 'aria-label': 'Script name', placeholder: 'Script name', maxlength: '60', spellcheck: 'false', autocomplete: 'off', ...HELP('Name') }) as HTMLInputElement;
    const saveBtn = el('button', 'as-btn', { type: 'button', ...HELP('Save'), 'data-act': 'save' }, 'Save');
    this.delBtn = el('button', 'as-btn', { type: 'button', ...HELP('Delete'), 'data-act': 'delete' }, 'Delete') as HTMLButtonElement;
    this.savedSel = el('select', 'as-saved', { 'aria-label': 'Saved scripts of this model', ...HELP('Saved scripts') }) as HTMLSelectElement;
    this.examplesBtn = el('button', 'as-btn', { type: 'button', 'aria-haspopup': 'menu', ...HELP('Examples'), 'data-act': 'examples' }, 'Examples') as HTMLButtonElement;
    const exportBtn = el('button', 'as-btn', { type: 'button', ...HELP('Export'), 'data-act': 'export' }, 'Export');
    const importBtn = el('button', 'as-btn', { type: 'button', ...HELP('Import'), 'data-act': 'import' }, 'Import');
    this.fileIn = el('input', '', { type: 'file', accept: '.xrayanim,.txt,text/plain', hidden: '', 'aria-label': 'Import a script file', 'data-script-file': '1' }) as HTMLInputElement;
    const fileRow = el('div', 'as-row');
    fileRow.append(this.nameIn, saveBtn, this.delBtn);
    const fileRow2 = el('div', 'as-row');
    fileRow2.append(this.savedSel, this.examplesBtn, exportBtn, importBtn, this.fileIn);

    // editor
    const ed = el('div', 'as-editor', { ...HELP('Editor') });
    this.gutter = el('div', 'as-gutter', { 'aria-hidden': 'true' });
    this.gutterIn = el('div', 'as-gutter-in');
    this.gutter.append(this.gutterIn);
    const code = el('div', 'as-code');
    this.hl = el('pre', 'as-hl', { 'aria-hidden': 'true' });
    this.ta = el('textarea', 'as-ta', {
      'aria-label': 'Animation script',
      spellcheck: 'false',
      autocomplete: 'off',
      autocapitalize: 'off',
      autocorrect: 'off',
      wrap: 'off',
      placeholder: '-- Write a script here, or pick an example.\nfly to everything over 3 seconds',
      'data-script-text': '1',
    }) as HTMLTextAreaElement;
    code.append(this.hl, this.ta);
    ed.append(this.gutter, code);

    this.errList = el('ul', 'as-errors', { 'aria-label': 'Problems in the script', ...HELP('Problems'), 'data-script-errors': '1' });

    root.append(runRow, fileRow, fileRow2, ed, this.errList, this.buildReference());
    pane.append(root);

    // events
    this.runBtn.addEventListener('click', () => this.run());
    this.pauseBtn.addEventListener('click', () => this.togglePause());
    this.stopBtn.addEventListener('click', () => this.stop());
    this.recBtn.addEventListener('click', () => this.record());
    saveBtn.addEventListener('click', () => this.save());
    this.delBtn.addEventListener('click', () => this.armDelete());
    this.examplesBtn.addEventListener('click', () => this.openExamples());
    exportBtn.addEventListener('click', () => this.exportFile());
    importBtn.addEventListener('click', () => this.fileIn.click());
    this.fileIn.addEventListener('change', () => void this.importFile());
    this.savedSel.addEventListener('change', () => {
      const n = this.savedSel.value;
      if (n) this.load(n);
    });
    this.nameIn.addEventListener('input', () => this.updateButtons());
    this.ta.addEventListener('input', () => this.onInput());
    this.ta.addEventListener('scroll', () => this.syncScroll());
    this.ta.addEventListener('keydown', (e) => this.onKey(e));
    this.gutter.addEventListener('click', (e) => {
      const n = (e.target as HTMLElement).closest<HTMLElement>('[data-line]');
      if (n) this.selectLine(Number(n.dataset['line']));
    });
    this.errList.addEventListener('click', (e) => {
      const b = (e.target as HTMLElement).closest<HTMLElement>('[data-i]');
      const d = b ? this.diags[Number(b.dataset['i'])] : undefined;
      if (d) this.jumpTo(d);
    });

    this.reloadDoc(true);
    this.render();
    this.recompile();
    return () => this.dispose();
  }

  private buildReference(): HTMLElement {
    const d = el('details', 'as-ref', { ...HELP('Reference'), 'data-script-reference': '1' });
    d.append(el('summary', '', {}, 'Statement reference'));
    const ul = el('ul');
    for (const t of TIMING_NOTES) ul.append(el('li', '', {}, t));
    d.append(ul);
    let group = '';
    for (const s of STATEMENT_HELP) {
      if (s.group !== group) {
        group = s.group;
        d.append(el('h4', '', {}, group));
      }
      const item = el('div', 'as-item', { 'data-statement': s.id });
      item.append(el('code', '', {}, s.syntax), el('p', '', {}, s.summary), el('pre', '', {}, s.example));
      const ins = el('button', 'as-btn', { type: 'button', 'data-insert': s.id, 'aria-label': `Insert the example of ${s.id}` }, 'Insert example');
      ins.addEventListener('click', () => this.insert(s.example));
      item.append(ins);
      d.append(item);
    }
    d.append(el('h4', '', {}, 'Elements'));
    for (const e of ELEMENT_HELP) {
      const item = el('div', 'as-item');
      item.append(el('code', '', {}, e.syntax), el('p', '', {}, e.summary), el('pre', '', {}, e.example));
      d.append(item);
    }
    return d;
  }

  private dispose(): void {
    for (const t of [this.compileTimer, this.draftTimer, this.delTimer]) if (t) clearTimeout(t);
    if (this.pollTimer) clearInterval(this.pollTimer);
    this.pollTimer = null;
    this.root?.remove();
    this.mounted = false;
  }

  /** The loaded model changed: read its scripts. */
  refreshModel(): void {
    if (!this.mounted) return;
    this.reloadDoc(false);
    this.recompile();
  }

  /** The tab is shown or hidden. */
  setVisible(v: boolean): void {
    this.visible = v;
    if (v && this.mounted) {
      this.reloadDoc(false);
      this.recompile();
      this.syncScroll();
    }
    this.managePoll();
  }

  // ---------------------------------------------------------------- text

  get text(): string {
    return this.mounted ? this.ta.value : '';
  }

  /** Put a text into the editor (keeps the browser's undo when it can). */
  setText(text: string, name?: string): void {
    if (!this.mounted) return;
    this.ta.focus({ preventScroll: true });
    this.ta.select();
    let done = false;
    try {
      done = document.execCommand('insertText', false, text);
    } catch {
      done = false;
    }
    if (!done || this.ta.value !== text) this.ta.value = text;
    if (name !== undefined) this.nameIn.value = name;
    this.ta.setSelectionRange(0, 0);
    this.ta.scrollTop = 0;
    this.ta.scrollLeft = 0;
    this.onInput();
  }

  private insert(text: string): void {
    const cur = this.ta.value;
    const sep = cur.length === 0 || cur.endsWith('\n') ? '' : '\n';
    this.ta.focus({ preventScroll: true });
    this.ta.setSelectionRange(cur.length, cur.length);
    let done = false;
    try {
      done = document.execCommand('insertText', false, `${sep}${text}\n`);
    } catch {
      done = false;
    }
    if (!done) this.ta.value = `${cur}${sep}${text}\n`;
    this.onInput();
    this.ta.scrollTop = this.ta.scrollHeight;
  }

  private onInput(): void {
    this.render();
    this.updateButtons();
    if (this.compileTimer) clearTimeout(this.compileTimer);
    this.compileTimer = setTimeout(() => this.recompile(), COMPILE_MS);
    if (this.draftTimer) clearTimeout(this.draftTimer);
    this.draftTimer = setTimeout(() => this.saveDraft(), DRAFT_MS);
  }

  private onKey(e: KeyboardEvent): void {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      this.run();
      return;
    }
    if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey && !e.metaKey && !e.altKey && !e.isComposing) {
      // keep the indentation of the line; one more level after a line that opens a block
      const v = this.ta.value;
      const pos = this.ta.selectionStart;
      if (pos !== this.ta.selectionEnd) return;
      const lineStart = v.lastIndexOf('\n', pos - 1) + 1;
      const before = v.slice(lineStart, pos);
      const indent = /^[ \t]*/.exec(before)![0];
      const opens = /^\s*(together|repeat\b.*)\s*(--.*|#.*)?$/i.test(before) && !/^\s*end\b/i.test(before);
      e.preventDefault();
      const ins = `\n${indent}${opens ? '  ' : ''}`;
      let done = false;
      try {
        done = document.execCommand('insertText', false, ins);
      } catch {
        done = false;
      }
      if (!done) {
        this.ta.setRangeText(ins, pos, pos, 'end');
        this.onInput();
      }
    }
  }

  // ---------------------------------------------------------------- drawing

  private lines(): string[] {
    return this.ta.value.split('\n');
  }

  /** Redraw the coloured copy and the line numbers. */
  private render(): void {
    const lines = this.lines();
    const byLine = new Map<number, ScriptDiagnostic[]>();
    for (const d of this.diags) {
      const a = byLine.get(d.line) ?? [];
      a.push(d);
      byLine.set(d.line, a);
    }
    const frag = document.createDocumentFragment();
    lines.forEach((text, i) => {
      const n = i + 1;
      const row = el('div', n === this.playingLine ? 'as-l play' : 'as-l');
      const pieces = markPieces(highlightLine(text), byLine.get(n) ?? []);
      for (const p of pieces) {
        const cls = [p.cls ? `as-${p.cls}` : '', p.mark ? `as-mark-${p.mark}` : ''].filter(Boolean).join(' ');
        if (cls) row.append(el('span', cls, {}, p.text));
        else row.append(document.createTextNode(p.text));
      }
      if (text.length === 0) row.append(document.createTextNode('​'));
      frag.append(row);
    });
    this.hl.textContent = '';
    this.hl.append(frag);

    {
      const g = document.createDocumentFragment();
      for (let n = 1; n <= lines.length; n++) {
        const ds = byLine.get(n);
        const sev = ds?.some((d) => d.severity === 'error') ? 'error' : ds ? 'warning' : '';
        const cls = ['as-gn', sev, n === this.playingLine ? 'play' : ''].filter(Boolean).join(' ');
        g.append(el('div', cls, { 'data-line': String(n), ...(sev ? { title: ds!.map((d) => d.message).join(' ') } : {}) }, String(n)));
      }
      this.gutterIn.textContent = '';
      this.gutterIn.append(g);
    }
    this.syncScroll();
  }

  private syncScroll(): void {
    if (!this.mounted) return;
    const t = `translate(${-this.ta.scrollLeft}px, ${-this.ta.scrollTop}px)`;
    this.hl.style.transform = t;
    this.gutterIn.style.transform = `translateY(${-this.ta.scrollTop}px)`;
  }

  private renderProblems(): void {
    this.errList.textContent = '';
    this.diags.forEach((d, i) => {
      const li = el('li');
      const b = el('button', `as-err ${d.severity}`, { type: 'button', 'data-i': String(i), 'data-line': String(d.line), 'aria-label': `${d.severity} ${formatDiagnostic(d)}` });
      b.append(el('b', '', {}, `Line ${d.line}, column ${d.col}: `), document.createTextNode(d.message));
      if (d.hint) b.append(el('span', 'as-hint', {}, d.hint));
      li.append(b);
      this.errList.append(li);
    });
  }

  private updateButtons(): void {
    const p = this.deps.player();
    const playing = this.running && (p?.playing ?? false);
    this.pauseBtn.disabled = !playing;
    this.pauseBtn.textContent = playing && p?.paused ? 'Resume' : 'Pause';
    this.stopBtn.disabled = !playing && this.playingLine === null;
    const name = cleanName(this.nameIn.value);
    this.delBtn.disabled = !name || !findScript(this.doc, name);
    this.delBtn.textContent = 'Delete';
    this.delBtn.classList.remove('armed');
    this.runBtn.disabled = false;
  }

  private setStatus(text: string, kind: '' | 'bad' | 'good' = ''): void {
    this.status = text;
    this.statusKind = kind;
    this.msg.textContent = text;
    this.msg.className = `as-msg${kind ? ` ${kind}` : ''}`;
  }

  // ---------------------------------------------------------------- compile

  /** Compile the text now; refresh the list of problems, the marks and the badge. */
  recompile(): CompileResult {
    if (this.compileTimer) {
      clearTimeout(this.compileTimer);
      this.compileTimer = null;
    }
    const text = this.text;
    const r = compileScript(text, { ...this.deps.compileOptions(), name: cleanName(this.nameIn?.value ?? '') || undefined });
    this.last = r;
    this.diags = r.errors;
    const errs = r.errors.filter((e) => e.severity === 'error').length;
    const warns = r.errors.length - errs;
    this.deps.setBadge?.(errs > 0 ? String(errs) : '');
    this.renderProblems();
    this.render();
    if (!this.running) {
      if (errs > 0) this.setStatus(`${errs} error${errs === 1 ? '' : 's'}${warns ? `, ${warns} warning${warns === 1 ? '' : 's'}` : ''}. Click one to jump to it.`, 'bad');
      else if (text.trim().length === 0) this.setStatus('');
      else this.setStatus(`No errors: ${r.score!.cues.length} cue${r.score!.cues.length === 1 ? '' : 's'}, ${Math.round(r.score!.duration * 10) / 10} seconds${warns ? `, ${warns} warning${warns === 1 ? '' : 's'}` : ''}.`, 'good');
    }
    this.updateButtons();
    return r;
  }

  private jumpTo(d: ScriptDiagnostic): void {
    const lines = this.lines();
    let off = 0;
    for (let i = 0; i < d.line - 1 && i < lines.length; i++) off += lines[i]!.length + 1;
    const lineLen = lines[d.line - 1]?.length ?? 0;
    const a = off + Math.min(Math.max(d.col - 1, 0), lineLen);
    const b = off + Math.min(Math.max(d.end - 1, d.col), lineLen);
    this.ta.focus();
    this.ta.setSelectionRange(a, Math.max(a, b));
    this.revealLine(d.line);
  }

  private selectLine(line: number): void {
    const lines = this.lines();
    let off = 0;
    for (let i = 0; i < line - 1 && i < lines.length; i++) off += lines[i]!.length + 1;
    this.ta.focus();
    this.ta.setSelectionRange(off, off + (lines[line - 1]?.length ?? 0));
  }

  private revealLine(line: number): void {
    const top = (line - 1) * LINE_H;
    const h = this.ta.clientHeight;
    if (top < this.ta.scrollTop + LINE_H || top > this.ta.scrollTop + h - 2 * LINE_H) this.ta.scrollTop = Math.max(0, top - h / 2);
    this.syncScroll();
  }

  // ---------------------------------------------------------------- run

  run(): RunResult {
    this.recompile();
    const text = this.text;
    const res = runScript(text, { ...this.deps.compileOptions(), name: cleanName(this.nameIn.value) || undefined }, this.deps.player(), {
      onLine: (line) => this.setPlaying(line),
      onEnd: () => {
        this.running = false;
        this.setPlaying(null);
        this.setStatus('Finished.', 'good');
        this.updateButtons();
        this.managePoll();
      },
    });
    this.running = res.ok;
    if (res.ok) this.setStatus(res.message, 'good');
    else {
      const first = res.errors.find((e) => e.severity === 'error');
      if (first) this.jumpTo(first);
      this.setStatus(res.message, 'bad');
    }
    this.updateButtons();
    this.managePoll();
    return res;
  }

  /** Compile the text and open the video export for it. */
  record(): void {
    this.recompile();
    const name = cleanName(this.nameIn.value) || 'script';
    const first = this.diags.find((e) => e.severity === 'error');
    if (first) {
      this.jumpTo(first);
      this.setStatus(formatDiagnostic(first), 'bad');
      return;
    }
    this.deps.record?.(this.text, name);
  }

  private togglePause(): void {
    const p = this.deps.player();
    if (!p || !p.playing) return;
    if (p.paused) p.resume();
    else p.pause();
    this.setStatus(p.paused ? 'Paused.' : 'Playing.', '');
    this.updateButtons();
  }

  stop(): void {
    const p = this.deps.player();
    try {
      p?.stop();
    } catch {
      /* a player that fails to stop is already stopped */
    }
    const was = this.running;
    this.running = false;
    this.setPlaying(null);
    if (was) this.setStatus('Stopped.', '');
    this.updateButtons();
    this.managePoll();
  }

  private setPlaying(line: number | null): void {
    if (line === this.playingLine) return;
    this.playingLine = line;
    this.render();
    if (line !== null && this.mounted && document.activeElement !== this.ta) this.revealLine(line);
    this.updateButtons();
  }

  /** Poll the player while a script plays: it may stop from elsewhere (the Escape key, another feature). */
  private managePoll(): void {
    const need = this.running && this.visible;
    if (need && !this.pollTimer) {
      this.pollTimer = setInterval(() => {
        const p = this.deps.player();
        if (this.running && p && !p.playing) {
          this.running = false;
          this.setPlaying(null);
          this.setStatus('Finished.', 'good');
        }
        this.updateButtons();
        if (!this.running) this.managePoll();
      }, 400);
    } else if (!need && this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }

  // ---------------------------------------------------------------- saved scripts

  private reloadDoc(first: boolean): void {
    const key = this.deps.modelKey();
    if (!first && key === this.docKey) return;
    this.docKey = key;
    this.doc = loadDoc(this.deps.storage, key);
    this.fillSaved();
    if (this.doc.draft && (first || this.ta.value.trim() === '')) {
      this.ta.value = this.doc.draft.text;
      this.nameIn.value = this.doc.draft.name;
      const saved = findScript(this.doc, this.doc.draft.name);
      this.savedText = saved ? saved.text : null;
    }
    this.updateButtons();
  }

  private fillSaved(): void {
    const sel = this.savedSel;
    sel.textContent = '';
    sel.append(el('option', '', { value: '' }, this.doc.scripts.length ? `Saved (${this.doc.scripts.length})` : 'No saved scripts'));
    for (const s of this.doc.scripts) sel.append(el('option', '', { value: s.name }, s.name));
    const cur = findScript(this.doc, this.nameIn?.value ?? '');
    sel.value = cur ? cur.name : '';
  }

  private saveDraft(): void {
    this.draftTimer = null;
    if (!this.mounted) return;
    this.doc = { ...this.doc, draft: { name: cleanName(this.nameIn.value), text: this.ta.value } };
    saveDoc(this.deps.storage, this.docKey, this.doc);
  }

  /** Save the text under the name in the name box (a new name if it is empty). Returns the name. */
  save(name?: string): string {
    const wanted = cleanName(name ?? this.nameIn.value);
    const n = wanted || uniqueScriptName(this.doc, 'Script');
    this.nameIn.value = n;
    this.doc = upsertScript({ ...this.doc, draft: { name: n, text: this.ta.value } }, n, this.ta.value);
    const ok = saveDoc(this.deps.storage, this.docKey, this.doc);
    this.savedText = this.ta.value;
    this.fillSaved();
    this.updateButtons();
    if (ok) this.deps.toast?.(`Saved "${n}"`);
    this.setStatus(ok ? `Saved "${n}" for this model.` : 'The browser refused to store the script. Export it to keep it.', ok ? 'good' : 'bad');
    return n;
  }

  /** Load a saved script into the editor. False when there is none of that name. */
  load(name: string): boolean {
    const s = findScript(this.doc, name);
    if (!s) return false;
    this.setText(s.text, s.name);
    this.savedText = s.text;
    this.fillSaved();
    this.setStatus(`Loaded "${s.name}".`, '');
    this.recompile();
    return true;
  }

  private armDelete(): void {
    const name = cleanName(this.nameIn.value);
    if (!name || !findScript(this.doc, name)) return;
    if (!this.delBtn.classList.contains('armed')) {
      this.delBtn.classList.add('armed');
      this.delBtn.textContent = 'Click again to delete';
      if (this.delTimer) clearTimeout(this.delTimer);
      this.delTimer = setTimeout(() => this.updateButtons(), 3000);
      return;
    }
    this.remove(name);
  }

  remove(name: string): boolean {
    if (!findScript(this.doc, name)) return false;
    this.doc = removeScript(this.doc, name);
    saveDoc(this.deps.storage, this.docKey, this.doc);
    this.fillSaved();
    this.savedText = null;
    this.updateButtons();
    this.setStatus(`Deleted "${name}". The text stays in the editor.`, '');
    return true;
  }

  /** The saved scripts of this model. */
  list(): Array<{ name: string; chars: number }> {
    return this.doc.scripts.map((s) => ({ name: s.name, chars: s.text.length }));
  }

  // ---------------------------------------------------------------- examples, files

  private openExamples(): void {
    openMenu({
      at: this.examplesBtn,
      label: 'Example scripts',
      heading: 'Examples',
      items: EXAMPLES.map((e) => ({ label: e.title, act: e.id, title: e.about, help: 'Script tab/Example' })),
      onPick: (id) => this.loadExample(id),
      returnFocus: this.examplesBtn,
    });
  }

  loadExample(id: string): boolean {
    const ex = EXAMPLES.find((e) => e.id === id);
    if (!ex) return false;
    // the 4D example plays the plan "Demo": build the demo plan of the model on screen when there is none yet
    if (/schedule\s+"Demo"/.test(ex.text) && !getPlan('Demo')) {
      try {
        const demo = (window as unknown as { __xray4d?: { demoPlan(): FourDPlan } }).__xray4d?.demoPlan();
        if (demo) registerPlan('Demo', demo);
      } catch { /* no model: the example then reports the unknown plan */ }
    }
    this.setText(ex.text, ex.title);
    this.savedText = null;
    this.setStatus(`Loaded the example "${ex.title}". ${ex.about}`, '');
    this.recompile();
    return true;
  }

  exportFile(): string {
    const name = cleanName(this.nameIn.value) || 'script';
    const file = exportFileName(name);
    const text = exportText(this.ta.value);
    (this.deps.download ?? defaultDownload)(file, text);
    this.setStatus(`Exported ${file}.`, '');
    return file;
  }

  private async importFile(): Promise<void> {
    const f = this.fileIn.files?.[0];
    this.fileIn.value = '';
    if (!f) return;
    try {
      const content = await f.text();
      const r = importText(f.name, content);
      if ('error' in r) {
        this.setStatus(r.error, 'bad');
        return;
      }
      this.setText(r.text, r.name);
      this.savedText = null;
      this.setStatus(`Imported ${f.name}.`, 'good');
      this.recompile();
    } catch {
      this.setStatus('The file could not be read.', 'bad');
    }
  }

  // ---------------------------------------------------------------- for smokes

  state(): ScriptPanelState {
    const sc = this.last?.score ?? null;
    const errs = this.diags.filter((d) => d.severity === 'error').length;
    const p = this.deps.player();
    return {
      name: this.mounted ? cleanName(this.nameIn.value) : '',
      dirty: this.mounted ? this.savedText !== this.ta.value : false,
      errors: errs,
      warnings: this.diags.length - errs,
      cues: sc ? sc.cues.length : null,
      duration: sc ? sc.duration : null,
      playingLine: this.playingLine,
      status: this.status,
      running: this.running,
      paused: p?.paused ?? false,
    };
  }
}

function defaultDownload(fileName: string, text: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
