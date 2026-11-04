// Open your own files: a picker button and drag and drop for .ifc / .ifczip (parsed in the browser by web-ifc, see
// model/ifcImport.ts) and .glb with an optional xray-model/1 .json sidecar. The folder "Open model" sits at the top of
// the lil-gui panel. The previous model stays on screen until the new one is ready; any failure leaves it untouched.

import type { AppPlugin, ViewerApp } from '../app';
import { parseModel } from '../model/loader';
import type { LoadedModel } from '../model/loader';
import {
  AUTO_EDGES_MAX_ELEMENTS, IFC_READER_AVAILABLE, IfcReaderUnavailable, ImportCancelled, importIfc, isZip, prewarmIfcReader, unzipIfc,
} from '../model/ifcImport';
import type { EdgesOption, IfcInput, IfcProgress, StageTimings } from '../model/ifcImport';
import { registerTool } from '../tools/registry';
import { note, section } from '../tools/ui';
import { el } from '../ui/dom';
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
    case 'merge':
      return `Merging ${p.done} of ${p.total} elements`;
    case 'edges':
      if (p.skipped === 'auto') return `Edges skipped (auto: over ${AUTO_EDGES_MAX_ELEMENTS.toLocaleString('en-US')} elements)`;
      if (p.skipped === 'none') return 'Edges skipped (edges: none)';
      return `Edges ${p.done} of ${p.total} elements`;
    case 'bvh':
      return `BVH ${p.percent}% (${(p.triangles / 1e6).toFixed(2)} M triangles)`;
    case 'transfer':
      return 'Transferring geometry';
    case 'upload':
      return `Uploading ${p.elements} elements`;
  }
}

// ---------------------------------------------------------------- large-model options and stats

/** Large-model options of the `Open model` folder. They apply to the next IFC file opened. */
export interface LargeModelOptions {
  /** `auto` skips the edge geometry above 50,000 elements; `all` always builds it; `none` never does. */
  edges: EdgesOption;
  /** `common` reads the common property sets and attributes for hover cards; `none` skips property extraction. */
  properties: 'common' | 'none';
}

/** What the `largeModel` drawer and the `Model stats` line show. */
export interface ModelInfo {
  modelName: string;
  elements: number;
  triangles: number;
  vertices: number;
  edgeSegments: number;
  /** Typed-array bytes of the geometry buffers. */
  bufferBytes: number;
  /** Null when the model was not opened from a file in this session. */
  loadSeconds: number | null;
  edgesSkipped: boolean;
  bvh: 'worker' | 'lazy' | 'n/a';
  options: LargeModelOptions | null;
  /** Ordered stage name and milliseconds; empty when unknown. */
  stages: Array<[string, number]>;
}

export const formatBytesMb = (bytes: number): string => `${(bytes / 1048576).toFixed(1)} MB`;

export function statsLine(i: ModelInfo): string {
  const n = (x: number): string => Math.round(x).toLocaleString('en-US');
  return `${n(i.elements)} elements, ${n(i.triangles)} triangles, ${formatBytesMb(i.bufferBytes)} buffers, ${i.loadSeconds === null ? 'load time n/a' : `${i.loadSeconds.toFixed(1)} s`}`;
}

/** Stats of a model that is already in memory (a built-in model, a glb, or an IFC from an earlier load). */
export function infoFromLoaded(loaded: LoadedModel, modelName: string): ModelInfo {
  const g = loaded.geometry;
  const bytes = (a: { array: ArrayLike<number> & { byteLength: number } } | undefined): number => a?.array.byteLength ?? 0;
  const bufferBytes = bytes(g.geometry.getAttribute('position')) + bytes(g.geometry.getAttribute('normal')) + bytes(g.geometry.getAttribute('elementId'))
    + bytes(g.geometry.getIndex() ?? undefined) + bytes(g.edges.getAttribute('position')) + bytes(g.edges.getAttribute('elementId'));
  return {
    modelName,
    elements: loaded.model.elements.length,
    triangles: (g.geometry.getIndex()?.count ?? 0) / 3,
    vertices: g.geometry.getAttribute('position').count,
    edgeSegments: g.edges.getAttribute('position').count / 2,
    bufferBytes,
    loadSeconds: null,
    edgesSkipped: false,
    bvh: 'n/a',
    options: null,
    stages: [],
  };
}

/** Stage list shown by the drawer, in pipeline order (zero entries are dropped, except the ones that always apply). */
export function stageList(t: Partial<StageTimings> & { uploadMs?: number }): Array<[string, number]> {
  const rows: Array<[string, number | undefined]> = [
    ['Reading files', t.readMs], ['Opening IFC', t.openMs], ['Meshing', t.meshMs], ['Relations and properties', t.relationsMs],
    ['Releasing web-ifc', t.releaseMs], ['Preparing (storeys, dedupe)', t.prepareMs], ['Merging', t.mergeMs], ['Edges', t.edgesMs],
    ['BVH (worker)', t.bvhMs], ['Transfer and wrap', t.handoffMs], ['GPU upload to first frames', t.uploadMs], ['Total', t.totalMs],
  ];
  return rows.filter((r): r is [string, number] => r[1] !== undefined && (r[1] > 0 || r[0] === 'Total'));
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

const LARGE_ICON = '<svg viewBox="0 0 20 20" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 3 3 6.5l7 3.5 7-3.5z"/><path d="M3 10l7 3.5 7-3.5"/><path d="M3 13.5l7 3.5 7-3.5"/></svg>';

export const fileLoaderPlugin: AppPlugin = (() => {
  let app: ViewerApp | null = null;
  let loading = false;
  let abort: AbortController | null = null;
  const ui = { open: (): void => undefined, cancel: (): void => undefined, status: 'Ready. Drop .ifc or .glb files on the viewer', stats: 'No model yet' };
  /** Applied to the next IFC file opened. */
  const large: LargeModelOptions = { edges: 'auto', properties: 'common' };
  let info: ModelInfo | null = null;
  let statsCtl: { updateDisplay(): unknown; domElement: HTMLElement } | null = null;
  const infoListeners = new Set<() => void>();
  const setInfo = (next: ModelInfo): void => {
    info = next;
    ui.stats = statsLine(next);
    statsCtl?.updateDisplay();
    const input = statsCtl?.domElement.querySelector('input');
    if (input) input.title = ui.stats;
    for (const l of infoListeners) l();
  };
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
    let readMs = 0;
    let importTimings: Partial<StageTimings> = {};
    let importInfo: Pick<ModelInfo, 'edgesSkipped' | 'bvh' | 'edgeSegments'> | null = null;
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
        readMs = performance.now() - t0;
        const res = await importIfc(inputs, {
          signal, onProgress: (p) => setStatus(progressText(p, inputs.length)),
          edges: large.edges, props: large.properties,
        });
        loaded = res.loaded;
        importTimings = res.timings;
        importInfo = { edgesSkipped: res.stats.edgesSkipped, bvh: res.stats.bvh, edgeSegments: res.stats.edgeSegments };
        console.info('[ifc-import]', JSON.stringify({
          files: inputs.length, mode: res.mode, extractMs: Math.round(res.extractMs), buildMs: Math.round(res.buildMs),
          elements: loaded.model.elements.length, edges: large.edges, properties: large.properties,
          stages: Object.fromEntries(Object.entries(res.timings).map(([k, v]) => [k, Math.round(v)])), ...res.report,
        }));
        if (res.report.duplicatesSkipped > 0 || res.report.renamed > 0) {
          console.info(`IFC federation: ${res.report.duplicatesSkipped} duplicate elements skipped, ${res.report.renamed} GlobalId clashes renamed`);
        }
      }
      if (signal.aborted) throw new ImportCancelled();
      const name = uniqueName(plan.name);
      if (plan.kind === 'ifc') {
        setStatus(progressText({ phase: 'upload', elements: loaded.model.elements.length }));
        await new Promise((r) => setTimeout(r, 0)); // let the text paint before the geometry is handed to the renderer
        if (signal.aborted) throw new ImportCancelled();
      }
      const tUp = performance.now();
      app.openLoaded(loaded, name);
      const secs = (performance.now() - t0) / 1000;
      const base = infoFromLoaded(loaded, name);
      const next: ModelInfo = {
        ...base, loadSeconds: secs, options: plan.kind === 'ifc' ? { ...large } : null,
        edgeSegments: importInfo?.edgeSegments ?? base.edgeSegments, edgesSkipped: importInfo?.edgesSkipped ?? false, bvh: importInfo?.bvh ?? 'n/a',
        stages: stageList({ ...importTimings, readMs, uploadMs: performance.now() - tUp, totalMs: performance.now() - t0 }),
      };
      setInfo(next);
      // the geometry reaches the GPU on the first frames; add that to the drawer once they have run
      requestAnimationFrame(() => requestAnimationFrame(() => {
        if (info !== next) return;
        next.stages = stageList({ ...importTimings, readMs, uploadMs: performance.now() - tUp, totalMs: performance.now() - t0 });
        for (const l of infoListeners) l();
      }));
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

  /** Drawer of the `largeModel` tool: stats and stage timings of the last load. */
  function largePanel(box: HTMLElement): () => void {
    const body = el('div');
    box.append(body);
    const render = (): void => {
      body.textContent = '';
      if (!info) {
        body.append(note('No model loaded yet.'));
        return;
      }
      const n = (x: number): string => Math.round(x).toLocaleString('en-US');
      const table = (rows: Array<[string, string]>): HTMLElement => {
        const t = el('table', 'xt-table');
        for (const [k, v] of rows) {
          const tr = el('tr');
          tr.append(el('td', undefined, undefined, k), el('td', undefined, { style: 'text-align:right' }, v));
          t.append(tr);
        }
        return t;
      };
      body.append(
        section('Model'),
        table([
          ['Name', info.modelName],
          ['Elements', n(info.elements)],
          ['Triangles', n(info.triangles)],
          ['Vertices', n(info.vertices)],
          ['Edge segments', info.edgesSkipped ? 'skipped' : n(info.edgeSegments)],
          ['Buffers', formatBytesMb(info.bufferBytes)],
          ['BVH', info.bvh === 'worker' ? 'built in the worker' : info.bvh === 'lazy' ? 'built on first use' : 'built on first use'],
          ['Load time', info.loadSeconds === null ? 'n/a' : `${info.loadSeconds.toFixed(2)} s`],
          ...(info.options ? [['edges', info.options.edges], ['properties', info.options.properties]] as Array<[string, string]> : []),
        ]),
      );
      if (info.stages.length > 0) {
        body.append(section('Stages of the last load'), table(info.stages.map(([k, ms]) => [k, ms >= 1000 ? `${(ms / 1000).toFixed(2)} s` : `${Math.round(ms)} ms`] as [string, string])));
      } else {
        body.append(note('No stage timings: this model was not opened from a file in this session.'));
      }
      body.append(note(`edges: auto skips the edge lines above ${AUTO_EDGES_MAX_ELEMENTS.toLocaleString('en-US')} elements. Options apply to the next IFC file you open.`));
    };
    infoListeners.add(render);
    render();
    return () => { infoListeners.delete(render); };
  }

  return {
    name: 'fileLoader',
    onModel(a) {
      // a model that did not come from a file load (picker, built-in): numbers without timings
      if (a.loaded && (!info || info.modelName !== a.modelName)) setInfo(infoFromLoaded(a.loaded, a.modelName));
    },
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
      folder.add(large, 'edges', ['auto', 'all', 'none']).name('edges');
      folder.add(large, 'properties', ['common', 'none']).name('properties');
      const stats = folder.add(ui, 'stats').name('Model stats');
      stats.disable();
      statsCtl = stats as unknown as typeof statsCtl;
      // the folder goes first in the panel, above the model picker
      const children = (gui as unknown as { $children: HTMLElement }).$children;
      children.insertBefore(folder.domElement, children.firstChild);

      registerTool({
        id: 'largeModel', label: 'Large model', title: 'Size, buffers and per-stage timings of the model opened last',
        icon: LARGE_ICON, order: 95, drawerWidth: 340, panel: (box) => largePanel(box),
      });

      installDropZone({ text: 'Drop IFC or glb files to open', onFiles: (files) => void openFiles(files), onDragStart: prewarmIfcReader });
    },
  };
})();
