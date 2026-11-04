// Open your own files: a picker button and drag and drop for .ifc / .ifczip (parsed in the browser by web-ifc, see
// model/ifcImport.ts) and .glb with an optional xray-model/1 .json sidecar. The folder "Open model" sits at the top of
// the lil-gui panel. The previous model stays on screen until the new one is ready; any failure leaves it untouched.

import type { AppPlugin, ViewerApp } from '../app';
import { parseModel } from '../model/loader';
import type { LoadedModel } from '../model/loader';
import {
  IFC_READER_AVAILABLE, IfcReaderUnavailable, ImportCancelled, importIfc, isZip, prewarmIfcReader, unzipIfc,
} from '../model/ifcImport';
import type { IfcInput, IfcProgress } from '../model/ifcImport';
import { installDropZone } from '../ui/dropZone';

/** Above this total size the loader warns (and carries on). */
export const LARGE_INPUT_BYTES = 100 * 1024 * 1024;
export const NO_IFC_READER_MESSAGE = 'This build does not include the IFC reader';

// ---------------------------------------------------------------- selection rules (pure, tested)

export interface FileLike {
  name: string;
  size: number;
}

export type OpenPlan<T extends FileLike> =
  | { kind: 'ifc'; ifc: T[]; ignored: string[]; name: string; totalBytes: number }
  | { kind: 'glb'; glb: T; sidecars: T[]; ignored: string[]; name: string; totalBytes: number }
  | { kind: 'error'; message: string };

const extOf = (name: string): string => {
  const i = name.lastIndexOf('.');
  return i < 0 ? '' : name.slice(i).toLowerCase();
};
export const baseNoExt = (name: string): string => {
  const i = name.lastIndexOf('.');
  return i <= 0 ? name : name.slice(0, i);
};

/** Model picker name: `file:<first name>` plus ` +N more` when several files are federated. */
export function modelNameFor(names: string[]): string {
  const first = names[0] ?? 'model';
  return names.length > 1 ? `file:${first} +${names.length - 1} more` : `file:${first}`;
}

/**
 * Decide what to do with a selection of files.
 *  - one or more .ifc/.ifczip: federated into one model (other files ignored)
 *  - one .glb, optionally with .json sidecar candidates
 *  - IFC mixed with glb, several glb, only .json, or nothing supported: an error with a one-line message
 */
export function planOpen<T extends FileLike>(files: T[]): OpenPlan<T> {
  if (files.length === 0) return { kind: 'error', message: 'No file selected' };
  const ifc: T[] = [];
  const glb: T[] = [];
  const json: T[] = [];
  const other: T[] = [];
  for (const f of files) {
    const e = extOf(f.name);
    if (e === '.ifc' || e === '.ifczip') ifc.push(f);
    else if (e === '.glb') glb.push(f);
    else if (e === '.json') json.push(f);
    else other.push(f);
  }
  const listNames = (l: T[]): string => (l.length <= 3 ? l.map((f) => f.name).join(', ') : `${l.slice(0, 3).map((f) => f.name).join(', ')} and ${l.length - 3} more`);
  if (ifc.length > 0 && glb.length > 0) {
    return { kind: 'error', message: 'Cannot open IFC and glb files together; drop either IFC files or one glb' };
  }
  if (ifc.length === 0 && glb.length === 0) {
    if (json.length > 0 && other.length === 0) {
      return { kind: 'error', message: `${listNames(json)}: a .json sidecar goes with its .glb file; select both` };
    }
    const bad = [...other, ...json];
    return {
      kind: 'error',
      message: `Unsupported file type: ${listNames(bad)}. Open .ifc, .ifczip or .glb files`,
    };
  }
  const empty = [...ifc, ...glb].find((f) => f.size === 0);
  if (empty) return { kind: 'error', message: `${empty.name} is empty` };
  if (glb.length > 1) return { kind: 'error', message: `Open one glb file at a time (${glb.length} selected)` };
  if (ifc.length > 0) {
    const ignored = [...other, ...json].map((f) => f.name);
    return { kind: 'ifc', ifc, ignored, name: modelNameFor(ifc.map((f) => f.name)), totalBytes: ifc.reduce((a, f) => a + f.size, 0) };
  }
  const g = glb[0]!;
  const base = baseNoExt(g.name).toLowerCase();
  const same = json.filter((j) => baseNoExt(j.name).toLowerCase() === base);
  const rest = json.filter((j) => !same.includes(j));
  return {
    kind: 'glb', glb: g, sidecars: [...same, ...rest], ignored: other.map((f) => f.name), name: modelNameFor([g.name]),
    totalBytes: g.size + json.reduce((a, f) => a + f.size, 0),
  };
}

const mb = (bytes: number): string => `${(bytes / 1048576).toFixed(1)} MB`;

/** Status text for an IFC import progress event. `fileIndex`/`fileCount` add a "file n of m" suffix when federating. */
export function progressText(p: IfcProgress, fileCount = 1): string {
  switch (p.phase) {
    case 'read':
      return `Reading ${p.file}, ${mb(p.bytes)}`;
    case 'open':
      return `Opening ${p.file}, ${mb(p.bytes)}`;
    case 'meshing':
      return `Meshing ${p.done} of ${p.total}${fileCount > 1 ? ` (${p.file})` : ''}`;
    case 'relations':
      return `Reading relations${fileCount > 1 ? ` (${p.file})` : ''}`;
    case 'build':
      return 'Building model';
  }
}

// ---------------------------------------------------------------- plugin

interface SidecarCandidate { name: string; json: unknown }

async function readSidecar<T extends File>(glb: T, sidecars: T[]): Promise<unknown> {
  const base = baseNoExt(glb.name).toLowerCase();
  const candidates: SidecarCandidate[] = [];
  for (const s of sidecars) {
    const isSame = baseNoExt(s.name).toLowerCase() === base;
    let json: unknown;
    try {
      json = JSON.parse(await s.text());
    } catch {
      if (isSame) throw new Error(`${s.name} is not valid JSON`);
      continue;
    }
    const schema = (json as { schema?: unknown } | null)?.schema;
    if (schema === 'xray-model/1') candidates.push({ name: s.name, json });
    else if (isSame) throw new Error(`${s.name} is not an xray-model/1 sidecar`);
  }
  return candidates[0]?.json;
}

/** One file as a short word for status messages. */
const plural = (n: number, w: string): string => `${n} ${w}${n === 1 ? '' : 's'}`;

export const fileLoaderPlugin: AppPlugin = (() => {
  let app: ViewerApp | null = null;
  let loading = false;
  let abort: AbortController | null = null;
  const ui = { open: (): void => undefined, cancel: (): void => undefined, status: 'Ready. Drop .ifc or .glb files on the viewer' };
  let statusCtl: { updateDisplay(): unknown; domElement: HTMLElement } | null = null;
  let cancelCtl: { disable(d?: boolean): unknown } | null = null;
  let messageTimer: ReturnType<typeof setTimeout> | null = null;
  let input: HTMLInputElement | null = null;

  const setStatus = (text: string): void => {
    ui.status = text;
    statusCtl?.updateDisplay(); // the bound object already holds `text`, so setValue() would see no change
    const el = statusCtl?.domElement.querySelector('input');
    if (el) el.title = text;
  };
  const setLoading = (on: boolean): void => {
    loading = on;
    cancelCtl?.disable(!on);
  };
  /** Red banner on top of the viewer, cleared after a while so it does not outlive its news. */
  const banner = (text: string | null, ms = 10000): void => {
    app?.showMessage(text);
    if (messageTimer) clearTimeout(messageTimer);
    messageTimer = null;
    if (text) {
      messageTimer = setTimeout(() => {
        messageTimer = null;
        app?.showMessage(null);
      }, ms);
    }
  };
  const fail = (text: string): void => {
    setStatus(text);
    banner(text);
  };

  /** A name the model picker does not list yet (opening the same file twice adds " (2)"). */
  const uniqueName = (name: string): string => {
    const select = (app?.panel?.controllers.find((c) => c.property === 'model') as unknown as { $select?: HTMLSelectElement } | undefined)?.$select;
    const taken = new Set(select ? Array.from(select.options).map((o) => o.value) : []);
    if (!taken.has(name)) return name;
    for (let i = 2; ; i++) if (!taken.has(`${name} (${i})`)) return `${name} (${i})`;
  };

  async function openFiles(files: File[]): Promise<void> {
    if (!app) return;
    if (loading) {
      setStatus('Still loading; press Cancel load first');
      return;
    }
    const plan = planOpen(files);
    if (plan.kind === 'error') {
      fail(plan.message);
      return;
    }
    const t0 = performance.now();
    abort = new AbortController();
    const signal = abort.signal;
    setLoading(true);
    banner(null);
    const warn = plan.totalBytes > LARGE_INPUT_BYTES ? `Large input (${mb(plan.totalBytes)}); this may be slow or run out of memory. ` : '';
    if (warn) banner(warn.trim(), 8000);
    try {
      let loaded: LoadedModel;
      if (plan.kind === 'glb') {
        setStatus(`${warn}Reading ${plan.glb.name}, ${mb(plan.glb.size)}`);
        const buf = await plan.glb.arrayBuffer();
        if (buf.byteLength < 12 || new DataView(buf).getUint32(0, true) !== 0x46546c67) {
          throw new Error(`${plan.glb.name} is not a valid glb file`);
        }
        const sidecar = await readSidecar(plan.glb as File, plan.sidecars as File[]);
        if (signal.aborted) throw new ImportCancelled();
        setStatus('Building model');
        await new Promise((r) => setTimeout(r, 0));
        try {
          loaded = await parseModel(buf, sidecar);
        } catch (e) {
          throw new Error(`${plan.glb.name} could not be read as glb (${e instanceof Error ? e.message : String(e)})`);
        }
        if (loaded.model.elements.length === 0) throw new Error(`${plan.glb.name} contains no meshes`);
      } else {
        if (!IFC_READER_AVAILABLE) throw new IfcReaderUnavailable();
        const inputs: IfcInput[] = [];
        for (const f of plan.ifc) {
          if (signal.aborted) throw new ImportCancelled();
          setStatus(`${warn}Reading ${f.name}, ${mb(f.size)}`);
          let bytes: Uint8Array = new Uint8Array(await f.arrayBuffer());
          let name = f.name;
          if (isZip(bytes)) {
            try {
              const z = await unzipIfc(bytes);
              bytes = z.bytes;
              name = z.name.split('/').pop() ?? f.name;
            } catch (e) {
              throw new Error(`${f.name} could not be unzipped (${e instanceof Error ? e.message : String(e)})`);
            }
          } else if (extOf(f.name) === '.ifczip') {
            throw new Error(`${f.name} is not a valid zip archive`);
          }
          // transferable copy that is exactly the file (a zip entry may be a view)
          inputs.push({ name, data: bytes.byteOffset === 0 && bytes.byteLength === bytes.buffer.byteLength ? (bytes.buffer as ArrayBuffer) : (bytes.slice().buffer as ArrayBuffer) });
        }
        const res = await importIfc(inputs, { signal, onProgress: (p) => setStatus(progressText(p, inputs.length)) });
        loaded = res.loaded;
        console.info('[ifc-import]', JSON.stringify({
          files: inputs.length, mode: res.mode, extractMs: Math.round(res.extractMs), buildMs: Math.round(res.buildMs),
          elements: loaded.model.elements.length, ...res.report,
        }));
        if (res.report.duplicatesSkipped > 0 || res.report.renamed > 0) {
          console.info(`IFC federation: ${res.report.duplicatesSkipped} duplicate elements skipped, ${res.report.renamed} GlobalId clashes renamed`);
        }
      }
      if (signal.aborted) throw new ImportCancelled();
      const name = uniqueName(plan.name);
      app.openLoaded(loaded, name);
      const secs = (performance.now() - t0) / 1000;
      const ignored = plan.ignored.length > 0 ? `; ignored ${plural(plan.ignored.length, 'unsupported file')}` : '';
      setStatus(`Loaded ${loaded.model.elements.length} elements in ${secs.toFixed(1)} s${ignored}`);
      banner(null);
    } catch (e) {
      if (e instanceof ImportCancelled || signal.aborted) setStatus('Load cancelled');
      else if (e instanceof IfcReaderUnavailable) fail(NO_IFC_READER_MESSAGE);
      else {
        const text = e instanceof Error ? e.message : String(e);
        console.info('[open-file] failed:', e instanceof Error ? e.stack ?? e.message : e); // expected for bad input: not a console warning
        fail(text.replace(/\s+/g, ' ').trim());
      }
    } finally {
      abort = null;
      setLoading(false);
    }
  }

  return {
    name: 'fileLoader',
    install(a) {
      app = a;
      const gui = a.panel;
      if (!gui) return;
      input = document.createElement('input');
      input.type = 'file';
      input.id = 'xray-open-file-input';
      input.multiple = true;
      input.accept = '.ifc,.ifczip,.glb,.json';
      input.style.display = 'none';
      input.addEventListener('change', () => {
        const files = input ? Array.from(input.files ?? []) : [];
        if (input) input.value = ''; // the same file can be opened again
        if (files.length > 0) void openFiles(files);
      });
      document.body.appendChild(input);

      const folder = gui.addFolder('Open model');
      ui.open = () => {
        prewarmIfcReader(); // wasm start-up overlaps with the file dialog
        input?.click();
      };
      ui.cancel = () => abort?.abort();
      folder.add(ui, 'open').name('Open IFC or glb file');
      const cancel = folder.add(ui, 'cancel').name('Cancel load');
      cancel.disable(true);
      cancelCtl = cancel;
      const status = folder.add(ui, 'status').name('Load status');
      status.disable();
      statusCtl = status as unknown as typeof statusCtl;
      // the folder goes first in the panel, above the model picker
      const children = (gui as unknown as { $children: HTMLElement }).$children;
      children.insertBefore(folder.domElement, children.firstChild);

      installDropZone({ text: 'Drop IFC or glb files to open', onFiles: (files) => void openFiles(files), onDragStart: prewarmIfcReader });
    },
  };
})();
