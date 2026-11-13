// BCF plugin: view and author BIM Collaboration Format 2.1 / 3.0 topics. Logic in src/bcf (zip, xml, parse, write, plan,
// controller, ui); this file wires the tool, lil-gui folder, palette actions, params section and window.__xrayBcf.
//
//   window.__xrayBcf = { load, topics, applyViewpoint, clearViewpoint, createTopic, createTopics, exportZip, ... }

import type GUI from 'lil-gui';
import type { AppPlugin, ViewerApp } from '../app';
import { registerAction } from '../input/actions';
import { registerTool } from '../tools/registry';
import { registerParamSection } from '../ui/params';
import { BcfController } from '../bcf/controller';
import type { AnnotationSpec, ApplyReport, CreateTopicOptions, TopicSpec } from '../bcf/controller';
import { BcfMarkupView } from '../bcf/pins';
import type { PlaceKind } from '../bcf/pins';
import { bcfFileInput, buildDrawer, installDrop, openTopicDialog, pickBcfFile } from '../bcf/ui';
import type { BcfAnnotation, BcfProject, BcfTopic, BcfVersion, Vec3 } from '../bcf/model';

declare global {
  interface Window {
    __xrayBcf?: {
      /** Open a .bcf / .bcfzip. Replaces the loaded topics unless `merge` is true. */
      load(src: File | Blob | ArrayBuffer | Uint8Array, opts?: { merge?: boolean }): Promise<BcfProject>;
      /** Every topic of the session, whatever model it belongs to (the live array). */
      readonly topics: BcfTopic[];
      /** The topics of the loaded model (same, revised or unknown model), and those opened on purpose from another model: what the drawer lists. */
      readonly currentTopics: BcfTopic[];
      /** The topics of other models (hidden: no pin or annotation is drawn), grouped per model. */
      otherModels(): Array<{ model: string; elementCount: number; topics: Array<{ guid: string; title: string }> }>;
      /** The scope of a topic against the loaded model: `same`, `revised`, `unknown` or `different`. */
      scopeOf(topicGuid: string): import('../markup/model').ModelMatch | null;
      /** Show a topic of another model on purpose (until the model changes). */
      openOther(topicGuid: string): boolean;
      /** Make a topic belong to the loaded model. */
      moveToModel(topicGuid: string): boolean;
      deleteTopic(topicGuid: string): boolean;
      /** What the last file opened said about the model of its topics. */
      readonly lastImport: { different: number; revised: number; unknown: number; message: string } | null;
      readonly status: string;
      applyViewpoint(topicGuid: string, viewpointGuid?: string): ApplyReport;
      /** Undo the applied viewpoint (hides, colours, clip planes); `quiet` leaves the status line alone. */
      clearViewpoint(quiet?: boolean): number;
      /** The viewpoint applied now, or null. */
      readonly applied: { topic: string; viewpoint: string } | null;
      createTopic(opts: CreateTopicOptions): BcfTopic;
      /** One topic per item, each selecting and framing its GlobalIds. Camera positions are viewer coordinates. */
      createTopics(list: TopicSpec[], opts?: { snapshot?: boolean }): BcfTopic[];
      addComment(topicGuid: string, text: string, opts?: { author?: string; viewpoint?: boolean }): unknown;
      exportZip(version?: BcfVersion): Promise<Uint8Array>;
      /** exportZip, then download the file. */
      download(version?: BcfVersion): Promise<Uint8Array>;
      /** Pin a topic to a point (viewer coordinates); null removes it. */
      setPin(topicGuid: string, point: Vec3 | null, elementGuid?: string): void;
      /** Add a callout, note or arrow (anchor points in viewer coordinates) to the active viewpoint of a topic. */
      addAnnotation(topicGuid: string, spec: AnnotationSpec, viewpointGuid?: string): BcfAnnotation;
      updateAnnotation(guid: string, patch: { text?: string; offset?: [number, number] }): boolean;
      removeAnnotation(guid: string): boolean;
      /** Copies of the annotations of a topic by viewpoint guid. */
      annotations(topicGuid: string): Record<string, BcfAnnotation[]>;
      /** Link measurement `id` of the measure tool as a callout on the active viewpoint of the topic. */
      linkMeasurement(topicGuid: string, measurementId: number, text?: string): BcfAnnotation | null;
      /** Start click-to-place (Escape cancels); placeAt clicks at a client position. */
      startPlacement(kind: PlaceKind, topicGuid: string, text?: string): boolean;
      /** Add a rectangle (2 corners) or a freehand line, in canvas CSS pixels, to the active viewpoint of a topic. */
      addShape(topicGuid: string, kind: 'rect' | 'freehand', points: Array<[number, number]>, text?: string, attach?: import('../bcf/attach').Attachment): BcfAnnotation;
      /** The stable pin number of a topic. */
      pinNumber(topicGuid: string): number | null;
      placeAt(clientX: number, clientY: number): boolean;
      cancelPlacement(): void;
      pinsVisible: boolean;
      /** The snapshot of a viewpoint with the markup burned in, as written on export. */
      composeSnapshot(topicGuid: string, viewpointGuid?: string): Promise<Uint8Array | null>;
    };
  }
}

const ICON =
  '<svg viewBox="0 0 20 20" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round">' +
  '<path d="M3.5 4.5h13v9h-6l-3.5 3v-3h-3.5z"/><path d="M6.5 8h7M6.5 10.5h4.5"/></svg>';

let ctl: BcfController | null = null;
let markup: BcfMarkupView | null = null;

/** The remembered author name (localStorage `xray.bcf.author`), shared with the markup tool. */
export const sharedAuthor = {
  get(): string {
    if (ctl) return ctl.author;
    try {
      return window.localStorage.getItem('xray.bcf.author') ?? '';
    } catch {
      return '';
    }
  },
  set(a: string): void {
    if (ctl) ctl.setAuthor(a);
    else {
      try {
        window.localStorage.setItem('xray.bcf.author', a.trim());
      } catch {
        /* ignore */
      }
    }
  },
};

function obj(v: unknown): Record<string, unknown> {
  return v && typeof v === 'object' ? (v as Record<string, unknown>) : {};
}

export const bcfPlugin: AppPlugin = {
  name: 'bcf',

  install(app: ViewerApp): void {
    const c = new BcfController(app);
    ctl = c;
    const view = new BcfMarkupView(c);
    markup = view;

    registerTool({
      id: 'bcf',
      label: 'BCF',
      title: 'BCF issues: open, review, create and export BIM Collaboration Format topics',
      icon: ICON,
      order: 80,
      panel: (container) => buildDrawer(container, c, view),
    });

    const gui = app.panel;
    if (gui) buildGui(gui, c);

    registerParamSection('bcf', {
      collect: () => ({ author: c.author, exportVersion: c.exportVersion }),
      apply: (value, bad, path) => {
        const o = obj(value);
        if (o['author'] !== undefined) {
          if (typeof o['author'] === 'string') c.setAuthor(o['author']);
          else bad.push(`${path}.author`);
        }
        if (o['exportVersion'] !== undefined) {
          if (o['exportVersion'] === '2.1' || o['exportVersion'] === '3.0') c.setExportVersion(o['exportVersion']);
          else bad.push(`${path}.exportVersion`);
        }
        gui?.controllersRecursive().forEach((k) => k.updateDisplay());
      },
    });

    registerAction({ id: 'bcf.open', label: 'BCF: open file', group: 'BCF', keys: [], run: () => pickBcfFile(c) });
    registerAction({ id: 'bcf.create', label: 'BCF: create topic from view', group: 'BCF', keys: [], run: () => openTopicDialog(c) });
    registerAction({ id: 'bcf.export', label: 'BCF: export', group: 'BCF', keys: [], run: () => void c.download() });
    registerAction({ id: 'bcf.clear', label: 'BCF: clear viewpoint', group: 'BCF', keys: [], run: () => void c.clearViewpoint() });

    installDrop(c);
    bcfFileInput(c); // the hidden picker input exists from the start (scripts and tests can feed it)

    window.__xrayBcf = {
      load: (src, opts) => c.load(src, opts),
      get topics() {
        return c.topics;
      },
      get currentTopics() {
        return c.currentTopics;
      },
      otherModels: () => c.otherModels().map((g) => ({ model: g.model.name, elementCount: g.model.elementCount, topics: g.items.map((t) => ({ guid: t.guid, title: t.title })) })),
      scopeOf: (g) => {
        const t = c.topic(g);
        return t ? c.scopeOf(t).match : null;
      },
      openOther: (g) => c.openOther(g),
      moveToModel: (g) => c.moveToModel(g),
      deleteTopic: (g) => c.deleteTopic(g),
      get lastImport() {
        return c.lastImport ? { ...c.lastImport } : null;
      },
      get status() {
        return c.status;
      },
      applyViewpoint: (t, v) => c.applyViewpoint(t, v),
      clearViewpoint: (quiet) => c.clearViewpoint(quiet === true),
      get applied() {
        return c.applied ? { ...c.applied } : null;
      },
      createTopic: (o) => c.createTopic(o),
      createTopics: (l, o) => c.createTopics(l, o),
      addComment: (t, x, o) => c.addComment(t, x, o),
      exportZip: (v) => c.exportZip(v),
      download: (v) => c.download(v),
      setPin: (t, p, g) => c.setPin(t, p, g),
      addAnnotation: (t, spec, v) => c.addAnnotation(t, spec, v),
      updateAnnotation: (g, p) => c.updateAnnotation(g, p),
      removeAnnotation: (g) => c.removeAnnotation(g),
      annotations: (t) => c.annotations(t),
      linkMeasurement: (t, id, text) => {
        const m = view.measurements().find((x) => x.id === id);
        if (!m) return null;
        return c.addAnnotation(t, { type: 'callout', text, anchor: { kind: 'measurement', measurement: m } });
      },
      startPlacement: (k, t, text) => view.start(k, t, text),
      addShape: (t, k, pts, text, attach) => c.addShape(t, k, pts, text, undefined, attach),
      pinNumber: (t) => {
        const topic = c.topic(t);
        return topic ? c.pinNumber(topic) : null;
      },
      placeAt: (x, y) => view.placeAtClient(x, y),
      cancelPlacement: () => view.cancel(),
      get pinsVisible() {
        return c.pinsVisible;
      },
      set pinsVisible(on: boolean) {
        c.setPinsVisible(on);
      },
      composeSnapshot: (t, v) => {
        const topic = c.topic(t);
        const ref = topic && (v ? topic.viewpoints.find((r) => r.guid === v) : topic.viewpoints.find((r) => r.snapshot));
        return topic && ref ? c.composeSnapshot(topic, ref) : Promise.resolve(null);
      },
    };
  },

  onModel(): void {
    markup?.cancel(true);
    ctl?.onModel();
  },

  afterFrame(_app: ViewerApp, now: number): void {
    ctl?.tick(now);
    markup?.tick();
  },
};

function buildGui(gui: GUI, c: BcfController): void {
  const folder = gui.addFolder('BCF');
  folder.close();
  const actions = {
    open: () => pickBcfFile(c),
    create: () => openTopicDialog(c),
    export21: () => void c.download('2.1'),
    export30: () => void c.download('3.0'),
    clear: () => void c.clearViewpoint(),
  };
  folder.add(actions, 'open').name('Open BCF');
  folder.add(actions, 'create').name('Create topic from view');
  folder.add(actions, 'export21').name('Export BCF 2.1');
  folder.add(actions, 'export30').name('Export BCF 3.0');
  folder.add(actions, 'clear').name('Clear viewpoint');
  const st = new Proxy({} as { status: string }, { get: () => c.status, set: () => true });
  const ctrl = folder.add(st, 'status').name('BCF status').disable();
  c.onChange(() => ctrl.updateDisplay());
}
