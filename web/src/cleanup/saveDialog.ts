// The "Save cleaned model" summary dialog: what will change (removed, simplified, instanced), triangles and estimated size
// before and after, the strip-properties switch, then Save and, after saving, "Open the saved file to check".
// The dialog only shows numbers and calls back; the export itself lives in cleanup/glbExport.ts.

import type { PlanStats } from './plan';
import { fmtBytes } from './work';

export interface SaveDialogHooks {
  /** Stats for the plan with or without name and property data. */
  stats(stripProps: boolean): PlanStats;
  /** Build and download the glb; resolves with its size and file name. */
  save(stripProps: boolean): Promise<{ bytes: number; fileName: string }>;
  /** Open the file that was just saved in the viewer. */
  openSaved(): Promise<void>;
  initialStrip: boolean;
  onStrip(strip: boolean): void;
}

const STYLE_ID = 'xray-cleanup-dialog-style';
const CSS = `
#xray-save-dialog { position: fixed; inset: 0; z-index: 1000; display: flex; align-items: center; justify-content: center; background: rgba(8, 10, 14, 0.55); font: 13px/1.4 system-ui, -apple-system, 'Segoe UI', sans-serif; }
#xray-save-dialog .box { box-sizing: border-box; width: min(460px, calc(100vw - 24px)); max-height: calc(100vh - 24px); overflow: auto; background: #141820; color: #dfe6ee; border: 1px solid #262d3a; border-radius: 8px; padding: 16px; box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5); }
#xray-save-dialog h2 { margin: 0 0 10px; font-size: 16px; font-weight: 600; }
#xray-save-dialog table { width: 100%; border-collapse: collapse; margin: 6px 0 10px; }
#xray-save-dialog td { padding: 4px 0; border-bottom: 1px solid #262d3a; vertical-align: top; }
#xray-save-dialog td:first-child { color: #8d99a8; padding-right: 12px; }
#xray-save-dialog td:last-child { text-align: right; font-variant-numeric: tabular-nums; }
#xray-save-dialog label { display: flex; gap: 8px; align-items: center; margin: 8px 0; }
#xray-save-dialog .note { color: #8d99a8; font-size: 12px; margin: 6px 0; }
#xray-save-dialog .result { margin: 8px 0; color: #7fd18b; }
#xray-save-dialog .result.err { color: #ff8a80; }
#xray-save-dialog .row { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; margin-top: 12px; }
#xray-save-dialog button { font: inherit; padding: 7px 12px; border-radius: 6px; border: 1px solid #2c3647; background: #1c2230; color: inherit; cursor: pointer; min-height: 34px; }
#xray-save-dialog button.primary { background: #1f4a7a; border-color: #3b9cff; }
#xray-save-dialog button:disabled { opacity: 0.5; cursor: default; }
`;

const n = (v: number): string => Math.round(v).toLocaleString('en-US');

function reasonText(by: Record<string, number>): string {
  const parts = Object.entries(by).map(([k, v]) => `${n(v)} ${k}`);
  return parts.length ? ` (${parts.join(', ')})` : '';
}

/** Show the dialog (one at a time). Returns a function that closes it. */
export function showSaveDialog(hooks: SaveDialogHooks): () => void {
  document.getElementById('xray-save-dialog')?.remove();
  if (!document.getElementById(STYLE_ID)) {
    const st = document.createElement('style');
    st.id = STYLE_ID;
    st.textContent = CSS;
    document.head.appendChild(st);
  }
  const root = document.createElement('div');
  root.id = 'xray-save-dialog';
  root.setAttribute('role', 'dialog');
  root.setAttribute('aria-modal', 'true');
  root.setAttribute('aria-label', 'Save cleaned model');
  const box = document.createElement('div');
  box.className = 'box';
  root.appendChild(box);
  const title = document.createElement('h2');
  title.textContent = 'Save cleaned model';
  const table = document.createElement('table');
  const note = document.createElement('p');
  note.className = 'note';
  note.textContent = 'The file is a .glb with one node per element, named by GlobalId. It carries no storeys or relations; the IFC class, name and properties go in the node extras.';
  const label = document.createElement('label');
  const strip = document.createElement('input');
  strip.type = 'checkbox';
  strip.checked = hooks.initialStrip;
  strip.setAttribute('data-act', 'strip');
  label.append(strip, document.createTextNode('Strip names and property data'));
  const result = document.createElement('div');
  result.className = 'result';
  result.hidden = true;
  const row = document.createElement('div');
  row.className = 'row';
  const mk = (act: string, text: string, cls = ''): HTMLButtonElement => {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = text;
    b.setAttribute('data-act', act);
    if (cls) b.className = cls;
    return b;
  };
  const bSave = mk('save', 'Save .glb', 'primary');
  const bOpen = mk('open', 'Open the saved file to check');
  bOpen.hidden = true;
  const bClose = mk('close', 'Close');
  row.append(bOpen, bClose, bSave);
  box.append(title, table, label, note, result, row);

  const render = (): void => {
    const s = hooks.stats(strip.checked);
    const rows: Array<[string, string]> = [
      ['Elements', `${n(s.elementsBefore)} to ${n(s.elementsAfter)}`],
      ['Removed', `${n(s.removed)}${reasonText(s.removedByReason)}`],
      ['Simplified', n(s.simplified)],
      ['Instanced', s.instanceGroups > 0 ? `${n(s.instancedElements)} elements in ${n(s.instanceGroups)} groups` : '0'],
      ['Triangles drawn', `${n(s.trianglesBefore)} to ${n(s.trianglesAfter)}`],
      ['Triangles stored', `${n(s.trianglesStoredBefore)} to ${n(s.trianglesStoredAfter)}`],
      ['Estimated size', `${fmtBytes(s.bytesBefore)} to ${fmtBytes(s.bytesAfter)}`],
    ];
    table.replaceChildren(
      ...rows.map(([k, v]) => {
        const tr = document.createElement('tr');
        const a = document.createElement('td');
        a.textContent = k;
        const b = document.createElement('td');
        b.textContent = v;
        b.setAttribute('data-row', k);
        tr.append(a, b);
        return tr;
      }),
    );
  };
  render();
  strip.addEventListener('change', () => {
    hooks.onStrip(strip.checked);
    render();
  });

  const close = (): void => {
    document.removeEventListener('keydown', onKey, true);
    root.remove();
  };
  function onKey(e: KeyboardEvent): void {
    if (e.key === 'Escape') {
      e.stopPropagation();
      close();
    }
  }
  document.addEventListener('keydown', onKey, true);
  bClose.addEventListener('click', close);
  root.addEventListener('pointerdown', (e) => {
    if (e.target === root) close();
  });
  bSave.addEventListener('click', () => {
    bSave.disabled = true;
    result.hidden = false;
    result.className = 'result';
    result.textContent = 'Writing the file...';
    hooks.save(strip.checked).then(
      (r) => {
        result.textContent = `Saved ${r.fileName}, ${fmtBytes(r.bytes)}.`;
        bOpen.hidden = false;
        bSave.disabled = false;
      },
      (err: unknown) => {
        result.className = 'result err';
        result.textContent = `Could not save: ${err instanceof Error ? err.message : String(err)}`;
        bSave.disabled = false;
      },
    );
  });
  bOpen.addEventListener('click', () => {
    bOpen.disabled = true;
    hooks.openSaved().then(close, (err: unknown) => {
      result.className = 'result err';
      result.textContent = `Could not open the file: ${err instanceof Error ? err.message : String(err)}`;
      bOpen.disabled = false;
    });
  });
  document.body.appendChild(root);
  bSave.focus();
  return close;
}
