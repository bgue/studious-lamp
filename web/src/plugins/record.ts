// Record plugin: the video export of fly-throughs and scripts (src/anim/record). The Rec button of the fly-through transport and the
// Record button of the Script tab open the options dialog (size, frame rate, quality, format, HUD, file name) and then export the score
// frame by frame at a fixed step, so the speed of the machine does not change the video. See docs-features/flythrough.md, Export.
//
//   window.__xrayRecord = { capabilities(), options(), dialog(subject, score, name), run(score, opts?, {download?}), flythrough(opts?),
//                           cancel(), busy, last, lastBlob() }
//
// The old window.__cinematic.record() keeps its real-time recorder (a webm of the canvas at 30 fps) for scripts.

import type { AppPlugin, ViewerApp } from '../app';
import { Recorder, capabilities, describeCapabilities } from '../anim/record/session';
import type { RecordResult } from '../anim/record/session';
import { DEFAULT_OPTIONS, fileBase, loadOptions, saveOptions } from '../anim/record/options';
import type { ExportOptions } from '../anim/record/options';
import { openOptionsDialog } from '../anim/record/ui';
import type { Score } from '../anim/score';
import { scoreEnd } from '../anim/score';
import { showToast } from '../ui/keymapView';
import { getFlythrough } from './flythrough';

export interface RecordApi {
  capabilities(): { webcodecs: boolean; mediaRecorder: boolean };
  /** The options the dialog starts with (stored per browser). */
  options(): ExportOptions;
  /** Open the options dialog for a score and record it. Null when the person cancels the dialog. */
  dialog(subject: string, score: Score, name: string): Promise<RecordResult | null>;
  /** Record a score now, without the dialog. */
  run(score: Score, opts?: Partial<ExportOptions>, hooks?: { download?: boolean }): Promise<RecordResult>;
  /** Record the active fly-through now, without the dialog. */
  flythrough(opts?: Partial<ExportOptions>, hooks?: { download?: boolean }): Promise<RecordResult>;
  cancel(): void;
  readonly busy: boolean;
  readonly last: RecordResult | null;
  lastBlob(): Blob | null;
}

declare global {
  interface Window {
    __xrayRecord?: RecordApi;
  }
}

function storage(): Storage | null {
  try {
    const s = window.localStorage;
    s.getItem('xray.probe');
    return s;
  } catch {
    return null;
  }
}

let rec: Recorder | null = null;

export const recordPlugin: AppPlugin = {
  name: 'record',

  install(app: ViewerApp) {
    const ctl = getFlythrough();
    if (!ctl) return;
    const r = new Recorder(app, { player: ctl.player, setExporting: (on) => ctl.setExporting(on) });
    rec = r;
    const note = (text: string): void => {
      showToast(text, 5000);
      app.showMessage(text);
      setTimeout(() => app.showMessage(null), 5000);
    };

    const dialog = async (subject: string, score: Score, name: string): Promise<RecordResult | null> => {
      const why = r.blocker();
      if (why) {
        note(why);
        return { ok: false, message: why };
      }
      const duration = Math.max(score.duration, scoreEnd(score.cues));
      const initial = { ...loadOptions(storage()), name: fileBase(name) };
      const chosen = await openOptionsDialog({
        subject,
        duration,
        initial,
        windowSize: r.windowSize(),
        maxSide: r.maxSide(),
        capability: describeCapabilities(capabilities()),
        timeFrames: (o) => r.timeFrames(score, o),
      });
      if (!chosen) return null;
      saveOptions(storage(), chosen);
      const res = await r.run(score, chosen);
      note(res.message);
      return res;
    };

    const api: RecordApi = {
      capabilities: () => capabilities(),
      options: () => loadOptions(storage()),
      dialog,
      run: (score, opts = {}, hooks = {}) => r.run(score, { ...DEFAULT_OPTIONS, ...opts }, hooks),
      flythrough: (opts = {}, hooks = {}) => {
        const f = ctl.store.active;
        if (!f || f.keyframes.length === 0) return Promise.resolve({ ok: false, message: 'Fly-through: add keyframes first.' });
        return r.run(ctl.compile(f), { ...DEFAULT_OPTIONS, name: f.name, ...opts }, hooks);
      },
      cancel: () => r.cancel(),
      get busy() {
        return r.busy;
      },
      get last() {
        return r.last;
      },
      lastBlob: () => r.lastBlob,
    };
    window.__xrayRecord = api;
    ctl.recordDialog = () => {
      const f = ctl.store.active;
      if (!f || f.keyframes.length === 0) {
        ctl.note('Fly-through: add keyframes first.');
        return false;
      }
      void dialog(`Fly-through "${f.name}"`, ctl.compile(f), f.name);
      return true;
    };
  },

  afterFrame() {
    rec?.afterFrame();
  },
};
