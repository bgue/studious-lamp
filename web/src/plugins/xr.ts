// WebXR plugin (experimental): enter VR, AR or field AR from a button, an action or the tool drawer. The session logic is in
// src/xr/session.ts (field AR in src/xr/fieldSession.ts) and the maths in src/xr/maths.ts and src/xr/field.ts; this file owns
// the lil-gui folder `WebXR`, the tool, the actions, the params section, the window API, the model points picked before a
// field session, the field notes to BCF, and the iPhone fallback (USDZ for AR Quick Look) and the QR link.
// See docs-features/webxr.md.
//
//   window.__xrayXr = { enter(mode), exit(), state(), setArScale(s), config, manager, field, usdz, qr }
//
// Feature detection: navigator.xr and isSessionSupported('immersive-vr') / ('immersive-ar'). The tool also shows where AR
// Quick Look exists (iPhone, iPad, Vision Pro). When nothing is supported the tool, the folder and the buttons stay hidden.

import { Mesh, MeshBasicMaterial, Raycaster, SphereGeometry, Vector2 } from 'three';
import type { AppPlugin, ViewerApp } from '../app';
import { buildUsdzScene, disposeUsdzScene, exportUsdz, openUsdz, quickLookSupported } from '../export/usdz';
import type { UsdzScene } from '../export/usdz';
import { encodeQr, qrSvg } from '../export/qr';
import { registerAction } from '../input/actions';
import { registerTool } from '../tools/registry';
import type { XrayTool } from '../tools/registry';
import { button, check, section, select, slider, statusLine } from '../tools/ui';
import type { Widget } from '../tools/ui';
import { registerParamSection } from '../ui/params';
import { FIELD_VIEWS, loadSites, modelKeyOf, parseSite, saveSiteTo } from '../xr/field';
import type { FieldView, SiteRegistration } from '../xr/field';
import { pickSurface, snapModelPoint } from '../xr/fieldSession';
import type { FieldNote } from '../xr/fieldSession';
import type { FieldAction } from '../xr/fieldOverlay';
import { AR_SCALES } from '../xr/maths';
import type { ArScale, V3 } from '../xr/maths';
import { XrManager } from '../xr/session';
import type { XrMode, XrState } from '../xr/session';

export interface XrFieldApi {
  state(): ReturnType<NonNullable<XrManager['field']>['state']> | null;
  /** Press a button of the field panel (same names as data-act). */
  act(a: FieldAction, arg?: string): void;
  /** Model points picked before the session (world coordinates). */
  readonly draft: V3[];
  /** Add a model point to the draft (normal view) or to the running session. */
  addModelPoint(p: V3): void;
  /** Room point of the next pair (XR reference space) in a running session. */
  addRealPoint(p: V3): boolean;
  /** Start or stop picking model points with clicks in the normal view. */
  pickDraft(on: boolean): void;
  clearDraft(): void;
  saveSite(name?: string): Promise<SiteRegistration | null>;
  sites(): SiteRegistration[];
  exportSite(): string | null;
  importSite(json: string): string[];
  notes(): FieldNote[];
}

export interface XrApi {
  /** Start a session (call from a user gesture, as the browser requires). */
  enter(mode: XrMode): Promise<void>;
  exit(): void;
  state(): XrState;
  setArScale(s: ArScale): void;
  readonly config: XrManager['config'];
  readonly manager: XrManager | null;
  readonly field: XrFieldApi;
  readonly usdz: { supported: boolean; build(): Promise<{ bytes: Uint8Array; elements: number; meshes: number; triangles: number }>; open(): Promise<number> };
  qr(): { url: string; svg: string; version: number };
}

declare global {
  interface Window {
    __xrayXr?: XrApi;
  }
}

let mgr: XrManager | null = null;
let appRef: ViewerApp | null = null;
let picking = false;
let fieldStatus = '';
const draftMarkers: Mesh[] = [];
const fieldListeners = new Set<() => void>();
const fieldChanged = (): void => fieldListeners.forEach((l) => l());

function download(name: string, data: BlobPart, type: string): void {
  const url = URL.createObjectURL(new Blob([data], { type }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    a.remove();
    URL.revokeObjectURL(url);
  }, 30000);
}

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------- model points before the session

function syncDraftMarkers(): void {
  const app = appRef;
  const m = mgr;
  if (!app || !m) return;
  for (const k of draftMarkers.splice(0)) {
    k.removeFromParent();
    k.geometry.dispose();
    (k.material as MeshBasicMaterial).dispose();
  }
  if (!picking) return;
  for (const p of m.fieldDraft) {
    const k = new Mesh(new SphereGeometry(0.06, 16, 12), new MeshBasicMaterial({ color: 0xd04fff, depthTest: false, transparent: true, opacity: 0.9 }));
    k.renderOrder = 25;
    k.position.set(p[0], p[1], p[2]);
    k.name = 'xray-xr-draft-point';
    app.renderer.scene.add(k);
    draftMarkers.push(k);
  }
  app.renderer.markDirty();
}

const ray = new Raycaster();
const ndc = new Vector2();
let downAt: { x: number; y: number } | null = null;

function onCanvasDown(e: PointerEvent): void {
  downAt = { x: e.clientX, y: e.clientY };
}

function onCanvasUp(e: PointerEvent): void {
  const app = appRef;
  const m = mgr;
  if (!picking || !app || !m || m.active || e.button !== 0 || !downAt) return;
  const moved = Math.hypot(e.clientX - downAt.x, e.clientY - downAt.y);
  downAt = null;
  if (moved > 5) return;
  const r = app.canvas.getBoundingClientRect();
  ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  app.renderer.camera.updateMatrixWorld();
  ray.setFromCamera(ndc, app.renderer.camera);
  const o = ray.ray.origin;
  const d = ray.ray.direction;
  const hit = pickSurface(app, [o.x, o.y, o.z], [d.x, d.y, d.z]);
  if (!hit) return;
  addDraftPoint(snapModelPoint(app, hit.id, hit.point, m.fieldConfig.snapRadius));
}

function addDraftPoint(p: V3): void {
  const m = mgr;
  if (!m) return;
  m.fieldDraft.push([...p]);
  fieldStatus = `${m.fieldDraft.length} model point${m.fieldDraft.length === 1 ? '' : 's'} picked: tap the same features on site, in this order.`;
  syncDraftMarkers();
  fieldChanged();
}

function setPicking(on: boolean): void {
  picking = on;
  fieldStatus = on ? 'Click wall corners, column centres or floor marks on the model (at least 2, spread apart).' : `${mgr?.fieldDraft.length ?? 0} model points kept for the field session.`;
  syncDraftMarkers();
  fieldChanged();
}

// ---------------------------------------------------------------- field notes, sites, USDZ, QR

/** Turn the snapshots of a field session into BCF topics (camera at the head pose, pin at the element). */
function notesToBcf(notes: FieldNote[]): number {
  type Bcf = { createTopic?(o: Record<string, unknown>): unknown };
  const bcf = (window as unknown as { __xrayBcf?: Bcf }).__xrayBcf;
  if (!notes.length || !mgr?.fieldConfig.notesToBcf) return 0;
  if (!bcf?.createTopic) {
    fieldStatus = `${notes.length} field snapshot${notes.length === 1 ? '' : 's'} kept in this page (no BCF plugin): use Download notes.`;
    return 0;
  }
  let n = 0;
  for (const note of notes) {
    const h = note.head.position;
    const t: V3 = [h[0] + note.forward[0] * 2, h[1] + note.forward[1] * 2, h[2] + note.forward[2] * 2];
    const lines = [
      `Field AR snapshot ${note.id}, ${note.time}.`,
      note.element ? `Element: ${note.element.name} (${note.element.globalId}).` : 'No element selected.',
      note.clearance !== null ? `Clearance from the device: ${(note.clearance * 100).toFixed(1)} cm.` : '',
      note.storey ? `Storey: ${note.storey}.` : '',
      `Head at ${h.map((v) => v.toFixed(3)).join(', ')} (viewer coordinates); ${note.text}.`,
      'The camera image is not available to a web page in WebXR: the topic snapshot is the model from the same pose; the overlay picture is in the field notes download.',
    ].filter(Boolean);
    try {
      bcf.createTopic({
        title: `Field note ${note.id}${note.element ? `: ${note.element.name}` : ''}`,
        description: lines.join('\n'),
        labels: ['field AR'],
        camera: { position: h, target: t },
        snapshot: true,
        pin: note.point ?? null,
        ...(note.element ? { pinElement: note.element.globalId } : {}),
      });
      n++;
    } catch {
      /* the BCF plugin refused one note; keep the rest */
    }
  }
  fieldStatus = `${n} field snapshot${n === 1 ? '' : 's'} added as BCF topics (camera at your position). Camera pixels are not available in WebXR.`;
  return n;
}

function notesJson(notes: FieldNote[]): string {
  return JSON.stringify({ schema: 'xray-xr-notes/1', model: appRef?.modelName ?? '', cameraPixels: 'not available in WebXR: png is the rendered overlay only', notes }, null, 1);
}

function currentSite(): SiteRegistration | null {
  const m = mgr;
  const app = appRef;
  if (!m || !app?.loaded) return null;
  return m.field?.lastSite ?? loadSites(storage(), app.modelName, modelKeyOf(app.loaded.model))[0] ?? null;
}

function importSite(json: string): string[] {
  const app = appRef;
  let v: unknown;
  try {
    v = JSON.parse(json);
  } catch (e) {
    return [`not JSON: ${e instanceof Error ? e.message : String(e)}`];
  }
  const { site, errors } = parseSite(v);
  if (!site || !app?.loaded) return errors.length ? errors : ['no model loaded'];
  const key = modelKeyOf(app.loaded.model);
  if (site.modelKey !== key) return [`the site belongs to another model (${site.model})`];
  site.model = app.modelName;
  if (!saveSiteTo(storage(), site)) return ['the browser refused to store the site'];
  fieldStatus = `Site "${site.name}" imported: the next field session restores it.`;
  fieldChanged();
  return [];
}

let usdzBusy = false;

async function buildUsdz(): Promise<{ bytes: Uint8Array; elements: number; meshes: number; triangles: number }> {
  const app = appRef;
  const g = app?.loaded?.geometry;
  if (!app || !g) throw new Error('No model loaded');
  const src = {
    positions: g.geometry.getAttribute('position').array as ArrayLike<number>,
    normals: (g.geometry.getAttribute('normal')?.array as ArrayLike<number> | undefined) ?? null,
    index: g.geometry.getIndex()!.array as ArrayLike<number>,
    ranges: g.ranges,
    vertexRanges: g.vertexRanges,
    state: app.renderer.state,
  };
  let scene: UsdzScene | null = null;
  try {
    scene = buildUsdzScene(src);
    const bytes = await exportUsdz(scene.group);
    return { bytes, elements: scene.elements, meshes: scene.buckets.length, triangles: scene.triangles };
  } finally {
    if (scene) disposeUsdzScene(scene);
  }
}

async function openUsdzNow(): Promise<number> {
  if (usdzBusy) return 0;
  usdzBusy = true;
  fieldStatus = 'Writing the USDZ file...';
  fieldChanged();
  try {
    const r = await buildUsdz();
    openUsdz(r.bytes, `${appRef?.modelName ?? 'model'}-xray.usdz`);
    fieldStatus = `USDZ: ${r.elements} elements in ${r.meshes} materials, ${(r.bytes.length / 1e6).toFixed(1)} MB. ${quickLookSupported() ? 'AR Quick Look places it on a surface you tap: no site registration.' : 'Downloaded: open it on an iPhone or iPad for AR Quick Look.'}`;
    return r.bytes.length;
  } catch (e) {
    fieldStatus = `USDZ export failed: ${e instanceof Error ? e.message : String(e)}`;
    return 0;
  } finally {
    usdzBusy = false;
    fieldChanged();
  }
}

function shareLinkQr(): { url: string; svg: string; version: number } {
  const params = (window as unknown as { __xrayParams?: { shareUrl(): string } }).__xrayParams;
  let url = location.href;
  try {
    if (params) url = params.shareUrl();
  } catch {
    /* keep the page address */
  }
  let q;
  try {
    q = encodeQr(url, url.length > 1200 ? 'L' : 'M');
  } catch {
    // too long for a QR code: the model name only
    url = `${location.origin}${location.pathname}?model=${encodeURIComponent(appRef?.modelName ?? '')}`;
    q = encodeQr(url, 'M');
  }
  return { url, svg: qrSvg(q), version: q.version };
}

// ---------------------------------------------------------------- the window API

const fieldApi: XrFieldApi = {
  state: () => mgr?.field?.state() ?? null,
  act: (a, arg) => mgr?.field?.act(a, arg),
  get draft() {
    return mgr?.fieldDraft ?? [];
  },
  addModelPoint(p) {
    if (mgr?.field) mgr.field.addModelPoint(p);
    else addDraftPoint(p);
  },
  addRealPoint: (p) => mgr?.field?.addRealPoint(p) ?? false,
  pickDraft: (on) => setPicking(on),
  clearDraft() {
    if (mgr) mgr.fieldDraft = [];
    syncDraftMarkers();
    fieldChanged();
  },
  saveSite: (name) => mgr?.field?.saveSite(name) ?? Promise.resolve(null),
  sites: () => (appRef?.loaded ? loadSites(storage(), appRef.modelName, modelKeyOf(appRef.loaded.model)) : []),
  exportSite: () => {
    const s = currentSite();
    return s ? JSON.stringify(s, null, 1) : null;
  },
  importSite,
  notes: () => mgr?.lastNotes ?? [],
};

const api: XrApi = {
  enter: (m) => (mgr ? mgr.enter(m) : Promise.resolve()),
  exit: () => mgr?.exit(),
  state: () => mgr!.state(),
  setArScale: (s) => mgr?.setArScale(s),
  get config() {
    return mgr!.config;
  },
  get manager() {
    return mgr;
  },
  field: fieldApi,
  usdz: {
    get supported() {
      return quickLookSupported();
    },
    build: () => buildUsdz(),
    open: () => openUsdzNow(),
  },
  qr: () => shareLinkQr(),
};

const ICON =
  '<svg viewBox="0 0 20 20" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
  '<path d="M2.5 7.5a2 2 0 0 1 2-2h11a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-3l-1.2-1.8a1.6 1.6 0 0 0-2.6 0L7.5 13.5h-3a2 2 0 0 1-2-2z"/>' +
  '<circle cx="6.8" cy="9.5" r="0.9"/><circle cx="13.2" cy="9.5" r="0.9"/></svg>';

function drawer(box: HTMLElement): (() => void) | void {
  const m = mgr;
  if (!m) return;
  const widgets: Widget[] = [];
  const add = (w: Widget): void => {
    widgets.push(w);
    box.appendChild(w.root);
    w.update();
  };
  const vr = button('Enter VR', () => void m.enter('vr'), { primary: true, title: 'Start a virtual reality session at real scale' });
  const ar = button('Enter AR', () => void m.enter('ar'), { primary: true, title: 'Start an augmented reality session and place the model' });
  box.append(vr, ar);
  add(select('AR scale', AR_SCALES, () => m.config.arScale, (v) => m.setArScale(v)));
  add(check('pointer rays', () => m.config.pointerRays, (v) => (m.config.pointerRays = v)));
  const leave = button('Leave XR session', () => m.exit(), { title: 'End the running session' });
  box.appendChild(leave);
  const st = statusLine('');
  box.appendChild(st);

  // field AR
  box.appendChild(section('Field AR on site'));
  const enterField = button('Enter field AR', () => void m.enter('field'), { primary: true, title: 'Overlay the model at real size on the real building' });
  const pick = button('Pick model points', () => setPicking(!picking), { title: 'Click points on the model now, tap the same points on site' });
  const clear = button('Clear model points', () => fieldApi.clearDraft(), { title: 'Forget the picked model points' });
  box.append(enterField, pick, clear);
  add(select('field look', FIELD_VIEWS, () => m.fieldConfig.view, (v: FieldView) => (m.field ? m.field.act('view', v) : (m.fieldConfig.view = v))));
  add(slider('cut radius (m)', 0, 20, 1, () => m.fieldConfig.cutRadius, (v) => (m.fieldConfig.cutRadius = v), (v) => (v ? `${v} m` : 'off')));
  add(check('storey cut', () => m.fieldConfig.storeyCut, (v) => (m.fieldConfig.storeyCut = v)));
  add(check('restore saved site', () => m.fieldConfig.restore, (v) => (m.fieldConfig.restore = v)));
  add(check('snapshots to BCF', () => m.fieldConfig.notesToBcf, (v) => (m.fieldConfig.notesToBcf = v)));
  const exp = button('Export site', () => {
    const j = fieldApi.exportSite();
    if (j) download(`${appRef?.modelName ?? 'model'}-site.json`, j, 'application/json');
  }, { title: 'Save the registration of this site as a file' });
  const imp = button('Import site', () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json,application/json';
    input.addEventListener('change', () => {
      const f = input.files?.[0];
      if (f) void f.text().then((t) => {
        const errs = importSite(t);
        if (errs.length) {
          fieldStatus = `Import failed: ${errs.join('; ')}`;
          fieldChanged();
        }
      });
    });
    input.click();
  }, { title: 'Load a registration file' });
  const notes = button('Download notes', () => download(`${appRef?.modelName ?? 'model'}-field-notes.json`, notesJson(m.lastNotes), 'application/json'), { title: 'Save the snapshots of the last field session' });
  box.append(exp, imp, notes);
  const fst = statusLine('');
  box.appendChild(fst);

  // iPhone, iPad and sharing
  box.appendChild(section('iPhone and iPad'));
  const ql = quickLookSupported();
  const usdz = button(ql ? 'Open in AR Quick Look' : 'Download USDZ', () => void openUsdzNow(), { title: 'Export the model as you see it for AR Quick Look' });
  const share = button('Share link as QR', () => {
    const q = shareLinkQr();
    qrBox.innerHTML = q.svg;
    qrBox.title = q.url;
    qrBox.hidden = false;
  }, { title: 'Show a code that opens this view on another device' });
  const qrBox = document.createElement('div');
  qrBox.className = 'xr-qr';
  qrBox.hidden = true;
  qrBox.style.cssText = 'margin:6px 0;max-width:240px';
  box.append(usdz, share, qrBox);

  const upd = (): void => {
    widgets.forEach((w) => w.update());
    vr.setDisabled(m.support.vr ? (m.active ? 'A session is running' : false) : 'Virtual reality is not supported on this device');
    ar.setDisabled(m.support.ar ? (m.active ? 'A session is running' : false) : 'Augmented reality is not supported on this device');
    enterField.setDisabled(m.support.ar ? (m.active ? 'A session is running' : false) : 'Augmented reality is not supported on this device: use AR Quick Look on iPhone and iPad');
    pick.classList.toggle('primary', picking);
    pick.setDisabled(m.active ? 'A session is running' : false);
    leave.setDisabled(m.active ? false : 'No session is running');
    notes.setDisabled(m.lastNotes.length ? false : 'No snapshots yet');
    exp.setDisabled(currentSite() ? false : 'No saved site for this model');
    st.set(m.status);
    const d = m.fieldDraft.length;
    fst.set(fieldStatus || `${d} model point${d === 1 ? '' : 's'} picked. ${loadSitesCount()} saved site${loadSitesCount() === 1 ? '' : 's'} for this model.`);
  };
  const off = m.onChange(upd);
  fieldListeners.add(upd);
  upd();
  return () => {
    off();
    fieldListeners.delete(upd);
  };
}

function loadSitesCount(): number {
  return fieldApi.sites().length;
}

export const xrPlugin: AppPlugin = {
  name: 'xr',

  install(app: ViewerApp): void {
    const m = new XrManager(app);
    mgr = m;
    appRef = app;
    window.__xrayXr = api;
    m.onFieldEnd = (notes) => {
      notesToBcf(notes);
      fieldChanged();
    };
    app.canvas.addEventListener('pointerdown', onCanvasDown);
    app.canvas.addEventListener('pointerup', onCanvasUp);

    registerAction({
      id: 'xr.vr',
      label: 'WebXR: enter VR (experimental)',
      group: 'Modes',
      keys: [],
      description: 'Start an immersive virtual reality session at real scale',
      enabled: () => m.support.vr && !m.active,
      run: () => void m.enter('vr'),
    });
    registerAction({
      id: 'xr.ar',
      label: 'WebXR: enter AR (experimental)',
      group: 'Modes',
      keys: [],
      description: 'Start an augmented reality session and place the model',
      enabled: () => m.support.ar && !m.active,
      run: () => void m.enter('ar'),
    });
    registerAction({
      id: 'xr.field',
      label: 'WebXR: enter field AR (experimental)',
      group: 'Modes',
      keys: [],
      description: 'Overlay the model at real size on the real building, registered by point pairs',
      enabled: () => m.support.ar && !m.active,
      run: () => void m.enter('field'),
    });

    const tool: XrayTool = {
      id: 'xr',
      label: 'WebXR',
      title: 'WebXR (experimental): look at the model in VR, place it in AR, or overlay it on site',
      icon: ICON,
      order: 95,
      drawerWidth: 340,
      available: () => m.support.vr || m.support.ar || quickLookSupported(),
      panel: (box) => drawer(box),
      isActive: () => m.active,
    };
    registerTool(tool);

    registerParamSection('xr', {
      collect: () => ({
        scale: m.config.arScale,
        pointerRays: m.config.pointerRays,
        fieldView: m.fieldConfig.view,
        cutRadius: m.fieldConfig.cutRadius,
        storeyCut: m.fieldConfig.storeyCut,
      }),
      apply(value, bad, path) {
        if (value === null || typeof value !== 'object') {
          bad.push(path);
          return;
        }
        const o = value as Record<string, unknown>;
        for (const k of Object.keys(o)) {
          const v = o[k];
          if (k === 'scale' && typeof v === 'string' && (AR_SCALES as readonly string[]).includes(v)) m.setArScale(v as ArScale);
          else if (k === 'pointerRays' && typeof v === 'boolean') m.config.pointerRays = v;
          else if (k === 'fieldView' && typeof v === 'string' && (FIELD_VIEWS as readonly string[]).includes(v)) m.fieldConfig.view = v as FieldView;
          else if (k === 'cutRadius' && typeof v === 'number' && Number.isFinite(v)) m.fieldConfig.cutRadius = Math.min(50, Math.max(0, v));
          else if (k === 'storeyCut' && typeof v === 'boolean') m.fieldConfig.storeyCut = v;
          else bad.push(`${path}.${k}`);
        }
        refresh();
      },
    });

    // The folder stays hidden until the device is checked (and for good when neither VR nor AR is supported).
    const gui = app.panel;
    let controllers: Array<{ updateDisplay(): unknown }> = [];
    let refresh = (): void => controllers.forEach((c) => c.updateDisplay());
    if (gui) {
      const folder = gui.addFolder('WebXR');
      folder.close();
      folder.hide();
      const actions = { enterVr: () => void m.enter('vr'), enterAr: () => void m.enter('ar'), enterField: () => void m.enter('field') };
      const cVr = folder.add(actions, 'enterVr').name('Enter VR');
      const cAr = folder.add(actions, 'enterAr').name('Enter AR');
      const cField = folder.add(actions, 'enterField').name('Enter field AR');
      const cScale = folder.add(m.config, 'arScale', [...AR_SCALES]).name('AR scale').onChange((v: ArScale) => m.setArScale(v));
      const cLook = folder.add(m.fieldConfig, 'view', [...FIELD_VIEWS]).name('field look').onChange((v: FieldView) => m.field?.act('view', v));
      const view = { status: m.status };
      const cStatus = folder.add(view, 'status').name('XR status').disable();
      const cRays = folder.add(m.config, 'pointerRays').name('pointer rays');
      controllers = [cScale, cLook, cStatus, cRays];
      refresh = (): void => {
        view.status = m.status;
        controllers.forEach((c) => c.updateDisplay());
      };
      const sync = (): void => {
        const { vr, ar } = m.support;
        if (vr || ar) folder.show();
        else folder.hide();
        if (vr) cVr.show();
        else cVr.hide();
        if (ar) {
          cAr.show();
          cField.show();
        } else {
          cAr.hide();
          cField.hide();
        }
        refresh();
      };
      m.onChange(sync);
    }

    // Check the device, then show the tool (re-registering tells the toolbar to look at available() again).
    void m.detect().then(() => registerTool(tool));
  },

  onModel(): void {
    // model points belong to one model
    if (mgr) mgr.fieldDraft = [];
    picking = false;
    syncDraftMarkers();
  },

  beforeFrame(_app: ViewerApp, now: number, dt: number): void {
    mgr?.beforeFrame(now, dt);
  },

  afterFrame(): void {
    mgr?.afterFrame();
  },
};


