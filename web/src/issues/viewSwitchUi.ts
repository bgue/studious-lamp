// The segmented control `3D · Plan · Section`, drawn in the issue detail, the sketch detail and the floating drawing toolbar.
// DOM only; the switch itself is src/issues/derivedSwitch.ts (through MarkupController.viewSwitch). Works at 360 px: the three
// buttons share the width and never wrap.

import { MODE_LABEL, VIEW_MODES } from './derivedViews';
import type { ViewMode } from './derivedViews';

const STYLE_ID = 'view-switch-styles';
const CSS = `
.vs-seg { display: flex; border: 1px solid #3b6c9c; border-radius: 8px; overflow: hidden; min-width: 0; max-width: 100%; flex: 0 1 auto; }
.vs-seg button { flex: 1 0 auto; min-width: 44px; min-height: 30px; padding: 0 8px; border: 0; background: #1c2f45; color: #eaf2ff; font: 600 12px system-ui, sans-serif; cursor: pointer; white-space: nowrap; border-radius: 0; }
.vs-seg button + button { border-left: 1px solid #3b6c9c; }
.vs-seg button[aria-pressed=true] { background: #1f4a7a; color: #fff; box-shadow: inset 0 -2px 0 #3b9cff; }
.vs-seg button:hover:not([aria-pressed=true]) { background: #26405e; }
.vs-seg button:disabled { opacity: 0.4; cursor: default; }
.vs-row { display: flex; align-items: center; gap: 6px; min-width: 0; }
.vs-row .vs-label { color: #9fc4ee; font: 600 11px system-ui, sans-serif; white-space: nowrap; }
.vs-row .vs-seg { flex: 1 1 auto; }
`;

const TITLE: Record<ViewMode, string> = {
  '3d': 'Back to the 3D view of the sketch: its own camera, and the section you had',
  plan: 'A top-down plan cut about 1.2 m above the storey, framed on what the sketch is tied to',
  section: 'A vertical section through what the sketch is tied to, with a short depth',
};

export interface SwitchHost {
  mode(): ViewMode;
  apply(mode: ViewMode): void;
}

function ensureStyles(): void {
  if (document.getElementById(STYLE_ID)) return;
  const st = document.createElement('style');
  st.id = STYLE_ID;
  st.textContent = CSS;
  document.head.appendChild(st);
}

/** The control. `labelled` adds the word "View" in front (the panels do; the toolbar is short of room). */
export function buildViewSwitch(host: SwitchHost, o: { labelled?: boolean; helpKey?: string } = {}): HTMLElement {
  ensureStyles();
  const seg = document.createElement('div');
  seg.className = 'vs-seg';
  seg.setAttribute('role', 'group');
  seg.setAttribute('aria-label', '3D, Plan or Section view of the sketch');
  seg.setAttribute('data-view-switch', '');
  if (o.helpKey) seg.setAttribute('data-help-key', o.helpKey);
  const now = host.mode();
  for (const m of VIEW_MODES) {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = MODE_LABEL[m];
    b.title = TITLE[m];
    b.setAttribute('data-view-mode', m);
    b.setAttribute('aria-pressed', String(m === now));
    b.addEventListener('click', () => host.apply(m));
    seg.appendChild(b);
  }
  if (!o.labelled) return seg;
  const row = document.createElement('div');
  row.className = 'vs-row';
  const label = document.createElement('span');
  label.className = 'vs-label';
  label.textContent = 'View';
  row.append(label, seg);
  return row;
}
