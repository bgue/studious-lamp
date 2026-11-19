// The Map section of the settings panel (lil-gui), the privacy notice, and the attribution label. DOM only; the logic is in
// controller.ts so the controls can move to another panel. Docs: docs-features/map.md.

import type GUI from 'lil-gui';
import type { MapController } from './controller';
import { CUSTOM_HINT, PROVIDER_LABELS } from './providers';
import { MAX_RADIUS, MIN_RADIUS } from './settings';
import type { ProviderId } from './providers';
import { STATUS_H } from '../ui/statusBar';

export const NOTICE_ID = 'xray-map-notice';
export const ATTRIBUTION_ID = 'xray-map-attribution';

const CSS = `
#${NOTICE_ID}{position:fixed;inset:0;z-index:100001;display:flex;align-items:center;justify-content:center;background:rgba(8,10,14,.55);padding:12px;box-sizing:border-box}
#${NOTICE_ID}[hidden]{display:none}
#${NOTICE_ID} .mn-card{width:min(420px,100%);box-sizing:border-box;padding:14px 16px 12px;background:#141820;color:#dfe6ee;border:1px solid #262d3a;border-radius:8px;
  box-shadow:0 10px 36px rgba(0,0,0,.5);font:13px/1.45 system-ui,-apple-system,'Segoe UI',sans-serif}
#${NOTICE_ID} h3{margin:0 0 6px;font-size:14px}
#${NOTICE_ID} p{margin:0 0 10px}
#${NOTICE_ID} .mn-btns{display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap}
#${NOTICE_ID} button{background:#1c2230;color:inherit;border:1px solid #262d3a;border-radius:4px;padding:8px 14px;font:inherit;cursor:pointer;min-height:36px}
#${NOTICE_ID} button.mn-yes{background:#1f4a7a}
#${ATTRIBUTION_ID}{position:absolute;left:52px;bottom:${STATUS_H + 4}px;z-index:11;max-width:calc(100% - 60px);box-sizing:border-box;padding:1px 6px;border-radius:3px;
  background:rgba(255,255,255,.78);color:#222;font:10px/1.5 system-ui,-apple-system,'Segoe UI',sans-serif;pointer-events:none;user-select:text;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#${ATTRIBUTION_ID}[hidden]{display:none}
.xray-map-note{margin:2px 8px 4px;font:11px/1.4 system-ui,sans-serif;color:var(--hover-color,#9aa5b4);overflow-wrap:anywhere}
.xray-map-note:empty{display:none}
@media (max-width:700px){#${ATTRIBUTION_ID}{right:var(--dk-rail,28px);left:calc(var(--sb-rail,28px) + 4px);text-align:right;max-width:none}}
`;

function ensureStyle(): void {
  if (document.getElementById(`${NOTICE_ID}-css`)) return;
  const st = document.createElement('style');
  st.id = `${NOTICE_ID}-css`;
  st.textContent = CSS;
  document.head.appendChild(st);
}

/** The one-time notice: resolves true when the person agrees. */
export function showNotice(text: string): Promise<boolean> {
  ensureStyle();
  let root = document.getElementById(NOTICE_ID) as HTMLDivElement | null;
  root?.remove();
  root = document.createElement('div');
  root.id = NOTICE_ID;
  root.setAttribute('role', 'alertdialog');
  root.setAttribute('aria-modal', 'true');
  root.setAttribute('aria-labelledby', `${NOTICE_ID}-h`);
  const card = document.createElement('div');
  card.className = 'mn-card';
  const h = document.createElement('h3');
  h.id = `${NOTICE_ID}-h`;
  h.textContent = 'Show a map under the model?';
  const p = document.createElement('p');
  p.id = `${NOTICE_ID}-text`;
  p.textContent = text;
  const btns = document.createElement('div');
  btns.className = 'mn-btns';
  const no = document.createElement('button');
  no.type = 'button';
  no.id = `${NOTICE_ID}-no`;
  no.textContent = 'Cancel';
  const yes = document.createElement('button');
  yes.type = 'button';
  yes.id = `${NOTICE_ID}-yes`;
  yes.className = 'mn-yes';
  yes.textContent = 'Show the map';
  btns.append(no, yes);
  card.append(h, p, btns);
  root.appendChild(card);
  document.body.appendChild(root);
  yes.focus();
  return new Promise((resolve) => {
    const done = (v: boolean): void => { root!.remove(); document.removeEventListener('keydown', onKey, true); resolve(v); };
    const onKey = (e: KeyboardEvent): void => { if (e.key === 'Escape') { e.stopPropagation(); done(false); } };
    document.addEventListener('keydown', onKey, true);
    yes.addEventListener('click', () => done(true));
    no.addEventListener('click', () => done(false));
    root!.addEventListener('pointerdown', (e) => { if (e.target === root) done(false); });
  });
}

/** The attribution label, in the stage next to the canvas. Hidden until tiles are drawn. */
export class AttributionLabel {
  readonly el: HTMLDivElement;
  constructor(stage: HTMLElement) {
    ensureStyle();
    this.el = document.createElement('div');
    this.el.id = ATTRIBUTION_ID;
    this.el.hidden = true;
    stage.appendChild(this.el);
  }
  set(text: string | null): void {
    const t = text ?? '';
    if (this.el.textContent !== t) this.el.textContent = t;
    this.el.hidden = !text;
  }
}

interface Model {
  enabled: boolean;
  provider: ProviderId;
  customUrl: string;
  apiKey: string;
  attribution: string;
  opacity: number;
  radius: number;
  location: string;
}

export interface MapPanel {
  folder: GUI;
  refresh(): void;
  /** The line below the controls. */
  note: HTMLElement;
}

/** The "Map" folder of the settings panel. `align` opens the manual aligner. */
export function buildMapFolder(gui: GUI, ctl: MapController, align: () => void): MapPanel {
  ensureStyle();
  const m: Model = {
    enabled: false, provider: ctl.settings.provider, customUrl: ctl.secrets.url.get() ?? '', apiKey: ctl.secrets.key.get() ?? '',
    attribution: ctl.settings.customAttribution, opacity: ctl.settings.opacity, radius: ctl.settings.radius, location: ctl.statusLine,
  };
  const folder = gui.addFolder('Map');
  folder.close();
  const providers: Record<string, ProviderId> = Object.fromEntries(PROVIDER_LABELS);
  const enabled = folder.add(m, 'enabled').name('show map under model');
  const provider = folder.add(m, 'provider', providers).name('provider');
  const url = folder.add(m, 'customUrl').name('URL template');
  const key = folder.add(m, 'apiKey').name('API key');
  const attr = folder.add(m, 'attribution').name('attribution');
  const opacity = folder.add(m, 'opacity', 0, 1, 0.05).name('opacity');
  const radius = folder.add(m, 'radius', MIN_RADIUS, MAX_RADIUS, 5).name('radius (m)');
  const location = folder.add(m, 'location').name('location').disable().listen();
  const alignBtn = folder.add({ align: () => align() }, 'align').name('Align manually…');
  const reset = folder.add({ reset: () => { void ctl.setManual(null, true); } }, 'reset').name('Use the model’s own place');
  const note = document.createElement('div');
  note.className = 'xray-map-note';
  note.id = 'xray-map-note';
  folder.$children.appendChild(note);

  const keyInput = key.domElement.querySelector('input');
  if (keyInput) { keyInput.type = 'password'; keyInput.autocomplete = 'off'; keyInput.setAttribute('autocapitalize', 'off'); }
  const urlInput = url.domElement.querySelector('input');
  if (urlInput) { urlInput.placeholder = CUSTOM_HINT; urlInput.autocomplete = 'off'; urlInput.spellcheck = false; }

  const refresh = (): void => {
    m.enabled = ctl.settings.enabled;
    m.provider = ctl.settings.provider;
    m.opacity = ctl.settings.opacity;
    m.radius = ctl.settings.radius;
    m.location = ctl.statusLine;
    const custom = ctl.settings.provider === 'custom';
    url.show(custom); key.show(custom); attr.show(custom);
    reset.show(!!ctl.manual);
    const lines: string[] = [];
    if (ctl.problem) lines.push(ctl.problem[0]!.toUpperCase() + ctl.problem.slice(1) + '.');
    const prov = ctl.activeProvider;
    if (prov?.note) lines.push(prov.note);
    if (!ctl.georef) lines.push('The place of the model is not known. Use Align manually to enter it.');
    lines.push(...ctl.result.notes.map((n) => n + '.'));
    note.textContent = lines.join(' ');
    folder.controllersRecursive().forEach((c) => c.updateDisplay());
  };

  enabled.onChange((v: boolean) => { void ctl.setEnabled(v).then(refresh); });
  provider.onChange((v: ProviderId) => {
    const was = ctl.settings.enabled;
    ctl.patch({ provider: v });
    // another provider is another party: the notice comes again before it is asked
    if (was && !ctl.settings.enabled) void ctl.setEnabled(true).then(refresh);
    refresh();
  });
  url.onFinishChange((v: string) => { ctl.secrets.url.set(v); ctl.recompute(); });
  key.onFinishChange((v: string) => { ctl.secrets.key.set(v); ctl.recompute(); });
  attr.onFinishChange((v: string) => ctl.patch({ customAttribution: v }));
  opacity.onChange((v: number) => ctl.patch({ opacity: v }));
  radius.onChange((v: number) => ctl.patch({ radius: v }));
  void location; void alignBtn;
  ctl.onChange(refresh);
  refresh();
  return { folder, refresh, note };
}
