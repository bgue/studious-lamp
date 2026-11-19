// Save IFC: the original file bytes plus one appended block with the classification, review state and cleanup marks
// (design docs/design/ifc-save-and-revision.md, section 1). Pure core in src/ifcsave; this file is the dialog, the file
// writing and the scripting hook.
//
//   window.__xrayIfcSave = { open(), close(), sources(), plan(opts?), save(opts?), attach(files), lastOutputs(), busy() }
//   action ifc.save ("Save IFC...", command palette), button "Save IFC" in the Open model folder
//
// Reviewer names and comments leave the viewer only when the box "Include reviewer names and comments" is ticked in the dialog
// (or `includeReviewers: true` is passed to save()). The box is not remembered, not a setting and not in the params document.

import type { AppPlugin, ViewerApp } from '../app';
import { defaultSchema } from '../classify/schema';
import type { ClassificationSchema, ClassifyResult } from '../classify/types';
import { registerAction } from '../input/actions';
import { cleanupMarks, planOf } from '../ifcsave/collect';
import { SaveCancelled, startSave } from '../ifcsave/client';
import { DEFAULT_SAVE_OPTIONS, UnsupportedSchemaError } from '../ifcsave/plan';
import type { FileSavePlan, SaveExtra, SaveOptions } from '../ifcsave/plan';
import { duplicatesOf, makeSource, sourcesOf, checkAttach } from '../ifcsave/source';
import type { IfcSource } from '../ifcsave/source';
import { outputName } from '../ifcsave/run';
import type { SaveProgress, SavedFile } from '../ifcsave/run';
import { downloadBlob } from '../cinematic/flythrough';
import { el } from '../ui/dom';

export interface SaveSummary {
  files: Array<{ name: string; source: string; bytes: number; lines: number; elements: number; replaced: boolean }>;
  mode: 'worker' | 'main';
  /** Where the files went: the browser's download, a file or folder the user picked, or nowhere (`target: 'none'`). */
  target: 'download' | 'file' | 'folder' | 'none';
  ms: number;
}

export interface SaveRequest {
  includeReviewers?: boolean;
  includeCleanupMarks?: boolean;
  scope?: 'all' | 'reviewed';
  /** Default `download`. `none` keeps the outputs for `lastOutputs()` and writes nothing (tests, measurements). */
  target?: 'download' | 'none';
  /** Skip the worker (tests). */
  forceMainThread?: boolean;
  onProgress?(p: SaveProgress): void;
}

export interface PlanSummary {
  files: Array<{ fileName: string; outName: string; family: string; elements: number; base: number }>;
  /** Elements that carry data, over all files. */
  elements: number;
  /** Cleanup marks that would be written. */
  cleanupMarked: number;
  duplicatesSkipped: number;
}

export interface IfcSaveApi {
  open(): void;
  close(): void;
  busy(): boolean;
  /** The retained sources of the model on screen (names, sizes, schemas), or [] when it has none (glb, sample). */
  sources(): Array<{ fileName: string; size: number; schema: string; maxExpressId: number; ownerHistoryId: number | null; classifications: number }>;
  plan(req?: SaveRequest): PlanSummary;
  save(req?: SaveRequest): Promise<SaveSummary>;
  /** Attach source files to a model that was not opened from IFC (glb + sidecar), or pick a moved file again. */
  attach(files: File[]): Promise<AttachOutcome>;
  /** The output blobs of the last save with `target: 'none'`. */
  lastOutputs(): Array<{ name: string; blob: Blob }>;
}

export interface AttachOutcome {
  ok: boolean;
  message: string;
  attached: string[];
}

declare global {
  interface Window {
    __xrayIfcSave?: IfcSaveApi;
    showSaveFilePicker?: (o?: unknown) => Promise<FileHandleLike>;
    showDirectoryPicker?: (o?: unknown) => Promise<DirHandleLike>;
  }
}

interface WritableLike { write(data: Blob): Promise<void>; close(): Promise<void> }
interface FileHandleLike { createWritable(): Promise<WritableLike> }
interface DirHandleLike { getFileHandle(name: string, o: { create: boolean }): Promise<FileHandleLike> }

interface ClassifyLike {
  results(): ClassifyResult[];
  schema(): unknown;
  review?: { history(): Array<import('../classify/reviewLog').ReviewCommit> };
}
interface CleanupLike {
  hiddenByCleanup?(): number[];
  readonly lastReport: { matches: Array<{ id: number; globalId: string; rules: string[]; reasons: string[] }> } | null;
}

const mb = (n: number): string => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);
const plural = (n: number, w: string): string => `${n.toLocaleString('en-US')} ${w}${n === 1 ? '' : 's'}`;

const STYLE_ID = 'xray-ifcsave-style';
const CSS = `
.xis-back{position:fixed;inset:0;z-index:2000;background:rgba(5,8,12,.6);display:flex;align-items:center;justify-content:center;padding:16px}
.xis-back[hidden]{display:none}
.xis-box{background:#141922;color:#d7dee8;border:1px solid #2d3748;border-radius:8px;width:min(560px,100%);max-height:calc(100vh - 32px);overflow:auto;display:flex;flex-direction:column;gap:10px;padding:14px 16px;font:13px/1.4 system-ui,sans-serif;box-shadow:0 12px 40px rgba(0,0,0,.5)}
.xis-box h2{margin:0;font-size:15px;font-weight:600}
.xis-box p{margin:0}
.xis-dim{color:#8d99a8;font-size:12px}
.xis-warn{color:#e0b252;font-size:12px}
.xis-err{color:#ff8f8f;font-size:12px}
.xis-files{display:flex;flex-direction:column;gap:4px;border:1px solid #262d3a;border-radius:4px;padding:6px 8px;background:#10141b}
.xis-file{display:flex;justify-content:space-between;gap:12px;align-items:baseline}
.xis-file span:first-child{overflow-wrap:anywhere}
.xis-file span:last-child{color:#8d99a8;white-space:nowrap;font-size:12px}
.xis-check{display:flex;gap:8px;align-items:flex-start;cursor:pointer}
.xis-check input{margin-top:3px}
.xis-sel{display:flex;gap:8px;align-items:center}
.xis-sel select{background:#0e1218;color:inherit;border:1px solid #262d3a;border-radius:3px;height:26px;padding:0 6px;font:inherit}
.xis-prog{height:6px;background:#10141b;border:1px solid #262d3a;border-radius:3px;overflow:hidden}
.xis-prog i{display:block;height:100%;width:0;background:#2d6aa8;transition:width .1s}
.xis-row{display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap}
.xis-btn{background:#1c2430;color:inherit;border:1px solid #2d3748;border-radius:4px;height:30px;padding:0 14px;font:inherit;cursor:pointer}
.xis-btn.primary{background:#2d6aa8;border-color:#3b82c4;color:#fff}
.xis-btn:disabled{opacity:.45;cursor:default}
.xis-btn:focus-visible,.xis-check input:focus-visible,.xis-sel select:focus-visible{outline:2px solid #3b9cff;outline-offset:1px}
`;

function ensureStyle(): void {
  if (document.getElementById(STYLE_ID)) return;
  const st = document.createElement('style');
  st.id = STYLE_ID;
  st.textContent = CSS;
  document.head.appendChild(st);
}

/** The message for a source file that cannot be read any more (moved, renamed or changed on disk). */
export const UNREADABLE_MESSAGE = (name: string): string => `${name} can no longer be read (it was moved, renamed or changed on disk). Pick the file again with "Attach the source IFC".`;

const isUnreadable = (e: unknown): boolean => {
  const n = (e as { name?: string } | null)?.name;
  return n === 'NotReadableError' || n === 'NotFoundError' || n === 'SecurityError';
};

export const ifcSavePlugin: AppPlugin = (() => {
  let app: ViewerApp | null = null;
  let running: { cancel(): void } | null = null;
  let last: Array<{ name: string; blob: Blob }> = [];
  let dlg: Dialog | null = null;

  const classify = (): ClassifyLike | undefined => (window as unknown as { __xrayClassify?: ClassifyLike }).__xrayClassify;
  const cleanup = (): CleanupLike | undefined => (window as unknown as { __xrayCleanup?: CleanupLike }).__xrayCleanup;
  const schema = (): ClassificationSchema => (classify()?.schema() as ClassificationSchema | undefined) ?? defaultSchema();
  const sources = (): IfcSource[] => (app?.loaded ? sourcesOf.get(app.loaded) ?? [] : []);

  const ownedCleanup = (): Map<string, { rules: string[]; reasons: string[] }> => {
    const c = cleanup();
    const model = app?.loaded?.model;
    if (!c || !model || !c.hiddenByCleanup) return new Map();
    return cleanupMarks(c.hiddenByCleanup(), model, c.lastReport?.matches ?? []);
  };

  const options = (r: SaveRequest = {}): SaveOptions => ({
    ...DEFAULT_SAVE_OPTIONS,
    includeReviewers: r.includeReviewers === true,
    includeCleanupMarks: r.includeCleanupMarks ?? ownedCleanup().size > 0,
    scope: r.scope ?? 'all',
    toolVersion: 'xray-viewer',
  });

  /** Hook for ticket T4: the revision walk fills this with `RevisionStatus` by GlobalId (design 3.7). */
  const revisionStates = (): SaveExtra['revision'] =>
    (window as unknown as { __xrayRevision?: { saveStates?(): SaveExtra['revision'] } }).__xrayRevision?.saveStates?.();

  const buildPlans = (o: SaveOptions): FileSavePlan[] => {
    const model = app?.loaded?.model;
    if (!model) return [];
    const c = classify();
    return planOf({
      model, sources: sources(), results: c?.results() ?? [], schema: schema(), options: o,
      history: o.includeReviewers ? c?.review?.history() : undefined,
      cleanup: o.includeCleanupMarks ? ownedCleanup() : undefined,
      revision: revisionStates(),
    });
  };

  const summarise = (plans: FileSavePlan[], o: SaveOptions): PlanSummary => ({
    files: plans.map((p) => ({ fileName: p.fileName, outName: outputName(p.fileName), family: p.family, elements: p.elements.length, base: p.base })),
    elements: plans.reduce((a, p) => a + p.elements.length, 0),
    cleanupMarked: o.includeCleanupMarks ? plans.reduce((a, p) => a + p.elements.filter((e) => e.cleanup).length, 0) : 0,
    duplicatesSkipped: app?.loaded ? duplicatesOf.get(app.loaded) ?? 0 : 0,
  });

  // ------------------------------------------------------------ writing

  type Target = { kind: 'download' } | { kind: 'file'; handle: FileHandleLike } | { kind: 'folder'; dir: DirHandleLike } | { kind: 'none' };

  /** Ask for the destination first, while the click still counts as a user action (a long save would lose it). Null: the user cancelled. */
  async function chooseTarget(files: number, suggested: string): Promise<Target | null> {
    try {
      if (files === 1 && window.showSaveFilePicker) {
        const handle = await window.showSaveFilePicker({ suggestedName: suggested, types: [{ description: 'IFC file', accept: { 'application/x-step': ['.ifc'] } }] });
        return { kind: 'file', handle };
      }
      if (files > 1 && window.showDirectoryPicker) return { kind: 'folder', dir: await window.showDirectoryPicker({ mode: 'readwrite' }) };
    } catch (e) {
      if ((e as { name?: string })?.name === 'AbortError') return null;
      console.info('[ifc-save] file picker failed, using a download:', e instanceof Error ? e.message : String(e));
    }
    return { kind: 'download' };
  }

  async function write(saved: SavedFile[], target: Target): Promise<void> {
    const blobs = saved.map((f) => ({ name: f.outName, blob: new Blob(f.parts, { type: 'application/octet-stream' }) }));
    if (target.kind === 'none') { last = blobs; return; }
    if (target.kind === 'file') {
      const w = await target.handle.createWritable();
      await w.write(blobs[0]!.blob);
      await w.close();
    } else if (target.kind === 'folder') {
      for (const b of blobs) {
        const w = await (await target.dir.getFileHandle(b.name, { create: true })).createWritable();
        await w.write(b.blob);
        await w.close();
      }
    } else {
      for (const [i, b] of blobs.entries()) {
        if (i > 0) await new Promise((r) => setTimeout(r, 300));
        downloadBlob(b.blob, b.name);
      }
    }
  }

  async function doSave(req: SaveRequest, target: Target): Promise<SaveSummary> {
    if (running) throw new Error('A save is already running');
    const o = options(req);
    const plans = buildPlans(o);
    const srcs = sources();
    if (plans.length === 0) throw new Error('This model has no source IFC. Attach the source IFC first.');
    const jobs = plans.map((plan) => {
      const s = srcs.find((x) => x.fileName === plan.fileName);
      if (!s) throw new Error(`No source file for ${plan.fileName}. Attach the source IFC first.`);
      return { plan, blob: s.blob };
    });
    const t0 = performance.now();
    const run = startSave(jobs, schema(), o, req.onProgress, req.forceMainThread);
    running = run;
    try {
      const { files, mode } = await run.promise;
      await write(files, target);
      return {
        files: files.map((f) => ({ name: f.outName, source: f.fileName, bytes: f.bytes, lines: f.lines, elements: f.elements, replaced: f.replaced })),
        mode, target: target.kind, ms: performance.now() - t0,
      };
    } finally {
      running = null;
    }
  }

  async function attach(files: File[]): Promise<AttachOutcome> {
    const model = app?.loaded?.model;
    if (!app?.loaded || !model) return { ok: false, message: 'No model is open.', attached: [] };
    const names = [...new Set(model.elements.map((e) => e.file).filter((n): n is string => !!n))];
    const current = sourcesOf.get(app.loaded) ?? [];
    const next = [...current];
    const attached: string[] = [];
    const problems: string[] = [];
    for (const f of files) {
      const target = names.length <= 1 ? names[0] ?? f.name : names.find((n) => n.toLowerCase() === f.name.toLowerCase());
      if (!target) { problems.push(`${f.name}: this model came from ${names.length} files (${names.slice(0, 3).join(', ')}${names.length > 3 ? ', ...' : ''}); pick the file with the same name`); continue; }
      let check;
      try {
        check = await checkAttach(f, model.elements.filter((e) => names.length <= 1 || e.file === target));
      } catch (e) {
        problems.push(`${f.name}: ${isUnreadable(e) ? UNREADABLE_MESSAGE(f.name) : e instanceof Error ? e.message : String(e)}`);
        continue;
      }
      if (!check.ok) { problems.push(`${f.name}: this is not the file the model came from (${check.matched} of ${check.total} elements found)`); continue; }
      const src = makeSource(target, f, check.schema ?? '', check.info);
      const i = next.findIndex((s) => s.fileName === target);
      if (i >= 0) next[i] = src;
      else next.push(src);
      attached.push(target);
    }
    if (attached.length > 0) sourcesOf.set(app.loaded, next);
    const missing = names.filter((n) => !next.some((s) => s.fileName === n));
    const message = [
      attached.length ? `Attached ${attached.join(', ')}.` : '',
      ...problems,
      missing.length ? `Still missing: ${missing.join(', ')}.` : '',
    ].filter(Boolean).join(' ');
    return { ok: attached.length > 0 && problems.length === 0, message, attached };
  }

  // ------------------------------------------------------------ dialog

  class Dialog {
    private readonly back = el('div', 'xis-back', { hidden: '' });
    private readonly box = el('div', 'xis-box', { role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'xis-title' });
    private body = el('div');
    private opts: { includeReviewers: boolean; includeCleanupMarks: boolean; scope: 'all' | 'reviewed' } = { includeReviewers: false, includeCleanupMarks: true, scope: 'all' };
    private message = '';
    private progress: { text: string; frac: number } | null = null;
    private readonly onKey = (ev: KeyboardEvent): void => {
      if (ev.key === 'Escape' && !running) { ev.stopPropagation(); this.hide(); }
    };

    constructor() {
      ensureStyle();
      this.box.append(el('h2', undefined, { id: 'xis-title' }, 'Save IFC'), this.body);
      this.back.append(this.box);
      this.back.addEventListener('mousedown', (ev) => { if (ev.target === this.back && !running) this.hide(); });
      document.body.appendChild(this.back);
    }

    get visible(): boolean { return !this.back.hidden; }

    show(): void {
      // every opening starts with the safe choices: the reviewer box is never remembered
      const owned = ownedCleanup().size;
      this.opts = { includeReviewers: false, includeCleanupMarks: owned > 0, scope: 'all' };
      this.message = '';
      this.progress = null;
      this.back.hidden = false;
      document.addEventListener('keydown', this.onKey, true);
      this.render();
      (this.box.querySelector('button.primary, button') as HTMLElement | null)?.focus();
    }

    hide(): void {
      if (running) return;
      this.back.hidden = true;
      document.removeEventListener('keydown', this.onKey, true);
    }

    private render(): void {
      const body = el('div');
      body.style.cssText = 'display:flex;flex-direction:column;gap:10px';
      const srcs = sources();
      const o: SaveOptions = { ...DEFAULT_SAVE_OPTIONS, ...this.opts };
      let plans: FileSavePlan[] = [];
      let fatal = '';
      if (!app?.loaded) fatal = 'No model is open.';
      else if (srcs.length === 0) fatal = 'This model was not opened from an IFC file in this session (a glb, a sample or a link), so there is no file to add to.';
      else {
        try { plans = buildPlans(o); } catch (e) { fatal = e instanceof UnsupportedSchemaError ? e.message : e instanceof Error ? e.message : String(e); }
      }
      const names = app?.loaded ? [...new Set(app.loaded.model.elements.map((e) => e.file).filter((n): n is string => !!n))] : [];
      const missing = names.filter((n) => !srcs.some((s) => s.fileName === n));
      const total = plans.reduce((a, p) => a + p.elements.length, 0);
      const marks = this.opts.includeCleanupMarks ? plans.reduce((a, p) => a + p.elements.filter((e) => e.cleanup).length, 0) : 0;

      body.append(el('p', 'xis-dim', undefined, 'The file is written as a copy: your original bytes stay as they are, and one block with the classification is added before the end of the data. Nothing leaves your computer.'));

      if (srcs.length > 0) {
        const list = el('div', 'xis-files');
        for (const s of srcs) {
          const p = plans.find((x) => x.fileName === s.fileName);
          list.append(el('div', 'xis-file', undefined, undefined));
          const row = list.lastElementChild!;
          row.append(el('span', undefined, undefined, `${s.fileName} → ${outputName(s.fileName)}`), el('span', undefined, undefined, `${mb(s.blob.size)}, ${s.schema}${p ? `, ${plural(p.elements.length, 'element')}` : ''}`));
        }
        body.append(list);
      }
      if (fatal) body.append(el('p', 'xis-err', undefined, fatal));
      if (missing.length > 0) body.append(el('p', 'xis-warn', undefined, `No source file for ${missing.join(', ')}. Attach it to save into it.`));
      const dups = app?.loaded ? duplicatesOf.get(app.loaded) ?? 0 : 0;
      if (srcs.length > 1 || dups > 0) {
        body.append(el('p', 'xis-dim', undefined, `${plural(srcs.length, 'file')} open: each is saved as its own file.${dups > 0 ? ` ${plural(dups, 'duplicate element')} exist only in the first file that has them; their twins in a later file get no data.` : ''}`));
      }

      // scope
      const scopeRow = el('label', 'xis-sel');
      const sel = el('select', undefined, { 'aria-label': 'Which elements to write' });
      for (const [v, t] of [['all', 'All classified elements'], ['reviewed', 'Only reviewed elements']] as const) {
        const op = el('option', undefined, { value: v }, t);
        if (v === this.opts.scope) op.selected = true;
        sel.append(op);
      }
      sel.addEventListener('change', () => { this.opts.scope = sel.value as 'all' | 'reviewed'; this.render(); });
      scopeRow.append(el('span', undefined, undefined, 'Write'), sel);
      body.append(scopeRow);

      const checkBox = (label: string, hint: string, get: boolean, set: (v: boolean) => void, disabled = false): HTMLElement => {
        const lab = el('label', 'xis-check');
        const input = el('input', undefined, { type: 'checkbox' });
        input.checked = get;
        input.disabled = disabled;
        input.addEventListener('change', () => { set(input.checked); this.render(); });
        const text = el('span');
        text.append(el('span', undefined, undefined, label), el('br'), el('span', 'xis-dim', undefined, hint));
        lab.append(input, text);
        return lab;
      };
      const owned = ownedCleanup().size;
      body.append(
        checkBox('Include reviewer names and comments', 'Off: no name or comment is written. On: the name of who confirmed a label and the review comments go into the file.',
          this.opts.includeReviewers, (v) => { this.opts.includeReviewers = v; }),
        checkBox('Mark cleanup matches', owned > 0 ? `Nothing is removed. The ${plural(marks || owned, 'element')} that cleanup hid get Xray_Cleanup.FlaggedForRemoval.` : 'Cleanup has not hidden anything, so there is nothing to mark.',
          this.opts.includeCleanupMarks && owned > 0, (v) => { this.opts.includeCleanupMarks = v; }, owned === 0),
      );
      const pset = schema().psetName;
      if (pset.startsWith('Pset_')) body.append(el('p', 'xis-warn', undefined, `The property set name ${pset} starts with Pset_, which buildingSMART reserves; some checkers will flag it. It is written as given.`));
      if (!fatal && total === 0) body.append(el('p', 'xis-warn', undefined, this.opts.scope === 'reviewed' ? 'No element has been reviewed yet.' : 'Nothing is classified yet and cleanup has no marks. Classify the model first.'));

      if (this.message) body.append(el('p', this.message.startsWith('Saved') ? 'xis-dim' : 'xis-err', undefined, this.message));
      if (this.progress) {
        const bar = el('div', 'xis-prog', { role: 'progressbar', 'aria-valuemin': '0', 'aria-valuemax': '100', 'aria-valuenow': String(Math.round(this.progress.frac * 100)) });
        const fill = el('i');
        fill.style.width = `${Math.round(this.progress.frac * 100)}%`;
        bar.append(fill);
        body.append(bar, el('p', 'xis-dim', undefined, this.progress.text));
      }

      const btns = el('div', 'xis-row');
      // attach: a model with no source, a missing file, or a file that cannot be read any more
      if (app?.loaded && (srcs.length === 0 || missing.length > 0 || this.message.includes('Attach the source'))) {
        const input = el('input', undefined, { type: 'file', accept: '.ifc', multiple: '' });
        input.style.display = 'none';
        input.addEventListener('change', () => {
          const picked = Array.from(input.files ?? []);
          input.value = '';
          if (picked.length === 0) return;
          void attach(picked).then((r) => { this.message = r.message; this.render(); });
        });
        const b = el('button', 'xis-btn', { type: 'button' }, 'Attach the source IFC...');
        b.addEventListener('click', () => input.click());
        btns.append(input, b);
      }
      const running_ = !!running;
      const cancel = el('button', 'xis-btn', { type: 'button' }, running_ ? 'Cancel save' : 'Close');
      cancel.addEventListener('click', () => { if (running) running.cancel(); else this.hide(); });
      const go = el('button', 'xis-btn primary', { type: 'button' }, 'Save IFC');
      go.disabled = running_ || !!fatal || total === 0 || plans.length === 0 || missing.length > 0;
      go.addEventListener('click', () => void this.go(plans));
      btns.append(cancel, go);
      body.append(btns);
      this.body.replaceWith(body);
      this.body = body;
    }

    private async go(plans: FileSavePlan[]): Promise<void> {
      const target = await chooseTarget(plans.length, outputName(plans[0]?.fileName ?? 'model.ifc'));
      if (!target) return;
      this.message = '';
      this.progress = { text: 'Starting', frac: 0 };
      this.render();
      try {
        const s = await doSave({ ...this.opts, onProgress: (p) => {
          this.progress = { text: `${{ locate: 'Reading the end of', emit: 'Writing the block for', splice: 'Assembling' }[p.phase]} ${p.file}`, frac: (p.done + (p.phase === 'locate' ? 0 : p.phase === 'emit' ? 0.4 : 0.8)) / p.total };
          this.render();
        } }, target);
        const total = s.files.reduce((a, f) => a + f.bytes, 0);
        this.progress = null;
        this.message = `Saved ${s.files.map((f) => f.name).join(', ')} (${mb(total)}, ${plural(s.files.reduce((a, f) => a + f.lines, 0), 'line')} added, ${(s.ms / 1000).toFixed(1)} s).`;
        app?.showMessage(null);
      } catch (e) {
        this.progress = null;
        if (e instanceof SaveCancelled) this.message = 'Save cancelled. Nothing was written.';
        else if (isUnreadable(e)) this.message = UNREADABLE_MESSAGE(sources()[0]?.fileName ?? 'The source file');
        else this.message = `Could not save: ${e instanceof Error ? e.message : String(e)}`;
      }
      if (this.visible) this.render();
    }
  }

  const ensureDialog = (): Dialog => (dlg ??= new Dialog());

  const api: IfcSaveApi = {
    open: () => ensureDialog().show(),
    close: () => dlg?.hide(),
    busy: () => !!running,
    sources: () => sources().map((s) => ({ fileName: s.fileName, size: s.blob.size, schema: s.schema, maxExpressId: s.maxExpressId, ownerHistoryId: s.ownerHistoryId, classifications: s.classifications.length })),
    plan(req) {
      const o = options(req);
      return summarise(buildPlans(o), o);
    },
    save: (req = {}) => doSave(req, { kind: req.target === 'none' ? 'none' : 'download' }),
    attach,
    lastOutputs: () => last,
  };

  return {
    name: 'ifcSave',
    install(a) {
      app = a;
      window.__xrayIfcSave = api;
      registerAction({
        id: 'ifc.save', label: 'Save IFC...', group: 'File', keys: [],
        description: 'Save a copy of the open IFC file with the classification, review state and cleanup marks added',
        run: () => api.open(),
      });
      // The File menu of the top bar does not exist yet: the button sits in the Open model folder, next to Open IFC.
      const panel = a.panel as unknown as { folders: Array<{ $title: HTMLElement; add(o: object, p: string): { name(n: string): unknown }; domElement: HTMLElement }> } | undefined;
      const folder = panel?.folders.find((f) => f.$title.textContent === 'Open model');
      if (folder) {
        const ui = { save: (): void => api.open() };
        folder.add(ui, 'save').name('Save IFC');
      }
    },
  };
})();
