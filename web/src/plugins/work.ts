// Work plugin: keeps the 3D sketches and the issues of each model in IndexedDB (src/work) and puts them back when the model loads.
// It registers no params section and no share link, and adds nothing to saved views or presets: what is kept stays in this browser.
// Wires the persistence to the controllers, the "Clear all" of the Issues panel and window.__xrayWork. Docs: docs-features/issues.md.

import type { AppPlugin, ViewerApp } from '../app';
import { WorkPersistence } from '../work/persist';
import { bcfController } from './bcf';
import { markupController } from './markup';
import { sheetsController } from './sheets';

declare global {
  interface Window {
    __xrayWork?: {
      /** Wait for the write of what changed. */
      save(): Promise<void>;
      /** Wait until the saved sketches and issues of the loaded model are back in the session. */
      restored(): Promise<void>;
      /** 3D sketches and issues of the loaded model, as "Clear all" would remove them. */
      counts(): { sketches: number; issues: number };
      /** Remove them from the session and from the saved copy. */
      clear(): Promise<{ sketches: number; issues: number }>;
      /** Forget the saved copy of every model. */
      wipe(): Promise<void>;
      /** Remove every 3D sketch and issue of every model from the session and forget the saved copies. */
      reset(): Promise<void>;
      /** Whether the saved copy survives a reload (false without IndexedDB). */
      readonly persistent: boolean;
      readonly status: string;
    };
  }
}

let work: WorkPersistence | null = null;

export function workPersistence(): WorkPersistence | null {
  return work;
}

export const workPlugin: AppPlugin = {
  name: 'work',

  install(app: ViewerApp): void {
    const mk = markupController();
    const bcf = bcfController();
    if (!mk || !bcf) return;
    const w = new WorkPersistence(app, mk, bcf);
    work = w;
    w.sheetsReady = async () => { await sheetsController()?.initDone; };
    w.bytesOfPdf = async (sha) => {
      const c = sheetsController();
      const d = c?.store.docs.find((x) => x.sha256 === sha);
      return c && d ? c.store.bytesOf(d) : null;
    };
    const issues = window.__xrayIssues?.controller;
    if (issues) issues.work = { counts: () => w.counts(), clear: () => w.clearModel() };
    window.__xrayWork = {
      save: () => w.save(),
      restored: () => w.whenRestored(),
      counts: () => w.counts(),
      clear: () => w.clearModel(),
      wipe: () => w.wipe(),
      reset: () => w.reset(),
      get persistent() {
        return w.persistent;
      },
      get status() {
        return w.status;
      },
    };
  },

  onModel(): void {
    void work?.onModel();
  },
};
