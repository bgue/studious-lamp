// Export / import plugin: a top-level lil-gui folder "Export / import" with
//   Export JSON, Copy JSON, Import JSON, Copy share URL, Export Python dict, Reset to defaults.
// The document format (schema `xray-params/1`) and the apply logic live in ui/params.ts.
//
// A share URL carries a compact subset in the fragment: `#p=<base64url JSON>`. On startup the plugin reads it
// and applies it once, after the model has loaded (then removes the fragment so a later reload does not
// override what the user did since). `window.__xrayParams` exposes collect/apply/shareUrl/toPython for scripts.
//
// Nothing is persisted by this plugin. Applying selectionSets writes the existing `xray.sets.<model>` key.

import type { AppPlugin, ViewerApp } from '../app';
import { copyText } from '../ui/dom';
import {
  applyParams,
  collectParams,
  defaultParams,
  shareFromHash,
  shareUrl,
  toPython,
} from '../ui/params';
import type { XrayParams } from '../ui/params';

declare global {
  interface Window {
    __xrayParams?: {
      collect(): XrayParams;
      apply(params: unknown): string[];
      json(): string;
      python(): string;
      shareUrl(): string;
      reset(): Promise<string[]>;
    };
  }
}

let pendingShare: Partial<XrayParams> | null = null;
let fileInput: HTMLInputElement | null = null;
let msgTimer: ReturnType<typeof setTimeout> | null = null;

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function download(name: string, text: string, mime: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: mime }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function notify(app: ViewerApp, text: string, ms = 4000): void {
  app.showMessage(text);
  if (msgTimer) clearTimeout(msgTimer);
  msgTimer = setTimeout(() => app.showMessage(null), ms);
}

function summary(what: string, bad: string[]): string {
  if (bad.length === 0) return `${what}.`;
  const shown = bad.slice(0, 6).join(', ');
  return `${what}; ${bad.length} key${bad.length === 1 ? '' : 's'} not applied: ${shown}${bad.length > 6 ? ', ...' : ''}`;
}

/** Parsed /xray.config.json (or the embedded copy of the single-file bundle), for "Reset to defaults". */
async function loadConfig(): Promise<unknown> {
  const embedded = (window as unknown as { __xrayEmbeddedConfig?: unknown }).__xrayEmbeddedConfig;
  if (embedded) return embedded;
  try {
    const r = await fetch('/xray.config.json');
    return r.ok ? await r.json() : null;
  } catch {
    return null;
  }
}

async function resetToDefaults(app: ViewerApp): Promise<string[]> {
  const cfg = await loadConfig();
  return applyParams(app, defaultParams(app, cfg));
}

function applyShared(app: ViewerApp, share: Partial<XrayParams>): string[] {
  const mismatch = typeof share.model === 'string' && share.model !== app.modelName;
  const bad = applyParams(app, share, { skipCamera: mismatch });
  // `model` is only a hint for which model to open; a mismatch (fallback to the demo model) is reported.
  return mismatch ? [...bad.filter((k) => k !== 'model'), `model (shared: ${share.model}, loaded: ${app.modelName}; camera skipped)`] : bad;
}

export const exportParamsPlugin: AppPlugin = {
  name: 'exportParams',

  install(app) {
    const jsonText = (): string => JSON.stringify(collectParams(app), null, 2) + '\n';
    const base = (): { origin: string; pathname: string } => ({ origin: location.origin, pathname: location.pathname });

    window.__xrayParams = {
      collect: () => collectParams(app),
      apply: (p) => applyParams(app, p),
      json: jsonText,
      python: () => toPython(collectParams(app)),
      shareUrl: () => shareUrl(collectParams(app), base()),
      reset: () => resetToDefaults(app),
    };

    pendingShare = shareFromHash(location.hash);
    if (!pendingShare && /(^|[#&])p=/.test(location.hash)) console.warn('exportParams: could not decode the #p= fragment');

    fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.accept = 'application/json,.json';
    fileInput.style.display = 'none';
    fileInput.addEventListener('change', () => {
      const file = fileInput?.files?.[0];
      if (!file) return;
      void file.text().then((text) => {
        let data: unknown;
        try {
          data = JSON.parse(text);
        } catch (e) {
          notify(app, `Import failed: ${e instanceof Error ? e.message : String(e)}`);
          return;
        }
        notify(app, summary('Parameters imported', applyParams(app, data)));
      });
      if (fileInput) fileInput.value = '';
    });
    document.body.appendChild(fileInput);

    const panel = app.panel;
    if (!panel) return;
    const f = panel.addFolder('Export / import');
    f.close();
    const actions = {
      exportJson: () => {
        download(`xray-params-${app.modelName}-${today()}.json`, jsonText(), 'application/json');
      },
      copyJson: () => {
        void copyText(jsonText()).then((ok) => notify(app, ok ? 'Parameters copied as JSON.' : 'Could not copy to the clipboard.', 2500));
      },
      importJson: () => fileInput?.click(),
      copyShare: () => {
        const url = shareUrl(collectParams(app), base());
        void copyText(url).then((ok) => notify(app, ok ? `Share URL copied (${url.length} characters).` : 'Could not copy to the clipboard.', 2500));
      },
      exportPython: () => {
        download(`xray-params-${app.modelName}-${today()}.py`, toPython(collectParams(app)), 'text/x-python');
      },
      reset: () => {
        void resetToDefaults(app).then((bad) => notify(app, summary('Parameters reset to defaults', bad)));
      },
    };
    f.add(actions, 'exportJson').name('Export JSON');
    f.add(actions, 'copyJson').name('Copy JSON');
    f.add(actions, 'importJson').name('Import JSON');
    f.add(actions, 'copyShare').name('Copy share URL');
    f.add(actions, 'exportPython').name('Export Python dict');
    f.add(actions, 'reset').name('Reset to defaults');
  },

  onModel(app) {
    const share = pendingShare;
    if (!share) return;
    pendingShare = null;
    const bad = applyShared(app, share);
    try {
      const u = new URL(location.href);
      u.hash = '';
      history.replaceState(null, '', u);
    } catch {
      /* ignore */
    }
    if (bad.length > 0) notify(app, summary('Shared view applied', bad), 6000);
  },
};

