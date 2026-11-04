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
import type { ApplyReport, CreateTopicOptions, TopicSpec } from '../bcf/controller';
import { bcfFileInput, buildDrawer, installDrop, openTopicDialog, pickBcfFile } from '../bcf/ui';
import type { BcfProject, BcfTopic, BcfVersion } from '../bcf/model';

declare global {
  interface Window {
    __xrayBcf?: {
      /** Open a .bcf / .bcfzip. Replaces the loaded topics unless `merge` is true. */
      load(src: File | Blob | ArrayBuffer | Uint8Array, opts?: { merge?: boolean }): Promise<BcfProject>;
      readonly topics: BcfTopic[];
      readonly status: string;
      applyViewpoint(topicGuid: string, viewpointGuid?: string): ApplyReport;
      clearViewpoint(): number;
      createTopic(opts: CreateTopicOptions): BcfTopic;
      /** One topic per item, each selecting and framing its GlobalIds. Camera positions are viewer coordinates. */
      createTopics(list: TopicSpec[], opts?: { snapshot?: boolean }): BcfTopic[];
      addComment(topicGuid: string, text: string, opts?: { author?: string; viewpoint?: boolean }): unknown;
      exportZip(version?: BcfVersion): Promise<Uint8Array>;
      /** exportZip, then download the file. */
      download(version?: BcfVersion): Promise<Uint8Array>;
    };
  }
}

const ICON =
  '<svg viewBox="0 0 20 20" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round">' +
  '<path d="M3.5 4.5h13v9h-6l-3.5 3v-3h-3.5z"/><path d="M6.5 8h7M6.5 10.5h4.5"/></svg>';

let ctl: BcfController | null = null;

function obj(v: unknown): Record<string, unknown> {
  return v && typeof v === 'object' ? (v as Record<string, unknown>) : {};
}

export const bcfPlugin: AppPlugin = {
  name: 'bcf',

  install(app: ViewerApp): void {
    const c = new BcfController(app);
    ctl = c;

    registerTool({
      id: 'bcf',
      label: 'BCF',
      title: 'BCF issues: open, review, create and export BIM Collaboration Format topics',
      icon: ICON,
      order: 80,
      panel: (container) => buildDrawer(container, c),
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
      get status() {
        return c.status;
      },
      applyViewpoint: (t, v) => c.applyViewpoint(t, v),
      clearViewpoint: () => c.clearViewpoint(),
      createTopic: (o) => c.createTopic(o),
      createTopics: (l, o) => c.createTopics(l, o),
      addComment: (t, x, o) => c.addComment(t, x, o),
      exportZip: (v) => c.exportZip(v),
      download: (v) => c.download(v),
    };
  },

  onModel(): void {
    ctl?.onModel();
  },

  afterFrame(_app: ViewerApp, now: number): void {
    ctl?.tick(now);
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
