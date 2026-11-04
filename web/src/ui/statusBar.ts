// Status bar: one thin line along the bottom of #stage, between the tool strip and the right dock. It replaces the old
// debug box (bottom left) and the red message banner (top centre), so nothing sits over the top of the canvas.
//
//   [model · elements] [x-ray on (tiers)] [F 1 · H 2 · N 3 · far 4] [message ×] [#12 IfcWall "name"] [16.7 ms] [ⓘ]
//
// The bar keeps the id `xray-overlay` (smoke scripts hide it by that id) and the message text keeps the id `xray-message`.
// The full details (Algorithm 1 and 2 timings, rays, the bucket, occlusion and alpha of the element) are in the bar's
// tooltip and in a small popover that the details button or the model segment opens. The popover also lists the
// credits of the built-in and embedded models ("About models").

export const STATUS_H = 22;

/** Credits of the built-in models; a single-file bundle sets window.__xrayModelCredits for the models it embeds. */
export const MODEL_CREDITS: Record<string, string> = {
  building: 'buildingSMART Simple-Scene: Building-Structural + Building-Architecture + Building-Hvac (IFC4)',
  'fzk-haus': 'KIT FZK-Haus (AC20-FZK-Haus.ifc, from the IfcOpenShell repository)',
  plumbing: 'buildingSMART Simple-Scene: Infra-Plumbing (IFC4)',
  synth5k: 'synthetic 5,000-element benchmark model (tools/synth_model.py)',
  'debris-demo': 'synthetic 400-element building with scattered debris for the cleanup tool (tools/synth_model.py --debris 24)',
  procedural: 'procedural demo model, built in the browser',
};

declare global {
  interface Window {
    /** Single-file bundles: name -> credit line of each embedded model. */
    __xrayModelCredits?: Record<string, string>;
    /** Single-file bundles: one line about the build (no server needed, IFC reader present or not). */
    __xrayBuildNote?: string;
  }
}

export function modelCredit(name: string): string {
  const c = window.__xrayModelCredits?.[name] ?? MODEL_CREDITS[name];
  if (c) return c;
  return name.startsWith('file:') ? 'opened from a local file' : 'no credit recorded';
}

/** What the bar shows. Plain data, so tests can check the text without a DOM. */
export interface StatusInput {
  model: string;
  elements: number;
  xray: boolean;
  tiers: boolean;
  buckets: { focus: number; host: number; near: number; far: number };
  /** The hovered element, else the first selected one. */
  element: null | {
    hovered: boolean;
    id: number;
    ifcClass: string;
    name: string | null;
    bucket: string;
    proximityWeight: number;
    occlusion: number;
    targetAlpha: number;
    alpha: number;
  };
  classifyMs: number;
  sightlinesMs: number;
  rays: number;
  frameMs: number;
  frameCpuMs: number;
  frames: number;
}

export interface StatusText {
  model: string;
  xray: string;
  buckets: string;
  element: string;
  frame: string;
  /** Multi-line full details for the tooltip and the popover. */
  details: string;
}

function fmt(n: number, digits = 2): string {
  return Number.isFinite(n) ? n.toFixed(digits) : '-';
}

export function statusText(s: StatusInput): StatusText {
  const xray = `x-ray ${s.xray ? 'on' : 'off'}${s.tiers ? ' (tiers)' : ''}`;
  const b = s.buckets;
  const e = s.element;
  const element = e ? `${e.hovered ? 'hover' : 'sel'} #${e.id} ${e.ifcClass}${e.name ? ` "${e.name}"` : ''}` : 'nothing selected';
  const lines = [
    `model ${s.model}   elements ${s.elements}   ${xray}`,
    `focus ${b.focus}  host ${b.host}  near ${b.near}  far ${b.far}`,
    `Alg1 ${fmt(s.classifyMs)} ms   Alg2 ${fmt(s.sightlinesMs)} ms, ${s.rays} rays`,
    `frame ${fmt(s.frameMs, 1)} ms (cpu ${fmt(s.frameCpuMs, 1)} ms, ${s.frames} frames)`,
  ];
  if (e) {
    lines.push(
      `${e.hovered ? 'hover' : 'selected'} #${e.id} ${e.ifcClass}${e.name ? ` "${e.name}"` : ''}`,
      `  bucket ${e.bucket}  weight ${fmt(e.proximityWeight)}  occlusion ${fmt(e.occlusion)}`,
      `  target alpha ${fmt(e.targetAlpha)}  alpha ${fmt(e.alpha)}`,
    );
  }
  return {
    model: `${s.model} · ${s.elements.toLocaleString('en-US')} el`,
    xray,
    buckets: `F ${b.focus} · H ${b.host} · N ${b.near} · far ${b.far}`,
    element,
    frame: `${fmt(s.frameMs, 1)} ms`,
    details: lines.join('\n'),
  };
}

const CSS = `
#xray-overlay{position:absolute;left:0;right:0;bottom:0;height:${STATUS_H}px;z-index:12;box-sizing:border-box;display:flex;align-items:stretch;
  background:var(--sb-bg,#141820);color:var(--sb-fg,#dfe6ee);border-top:1px solid var(--sb-line,#262d3a);
  font:11px/${STATUS_H - 1}px system-ui,-apple-system,'Segoe UI',sans-serif;font-variant-numeric:tabular-nums;white-space:nowrap;user-select:none;
  transition:left .15s ease,right .15s ease}
#xray-overlay *{box-sizing:border-box}
#xray-overlay .xs-seg{flex:0 1 auto;min-width:0;padding:0 8px;overflow:hidden;text-overflow:ellipsis;border-left:1px solid var(--sb-line,#262d3a)}
#xray-overlay .xs-seg:first-child{border-left:0}
#xray-overlay .xs-model{cursor:pointer;color:var(--sb-fg,#dfe6ee);flex-shrink:1;min-width:6em}
#xray-overlay.xs-msg-on .xs-buckets{display:none}
#xray-overlay .xs-model:hover,#xray-overlay .xs-more:hover{background:var(--sb-hover,#1c2230)}
#xray-overlay .xs-xray{color:var(--sb-dim,#8d99a8);flex-shrink:0}
#xray-overlay .xs-xray.on{color:#7cc4ff}
#xray-overlay .xs-buckets{color:var(--sb-dim,#8d99a8);flex-shrink:4}
#xray-overlay .xs-elem{flex:1 1 0;min-width:4em;color:#b9c4d2}
#xray-overlay .xs-frame{flex:0 0 auto;color:var(--sb-dim,#8d99a8)}
#xray-overlay .xs-msgwrap{flex:0 1 auto;max-width:50%;display:flex;align-items:stretch;padding:0;background:#7a2b1f;color:#fff;border-left:0}
#xray-overlay .xs-msgwrap #xray-message{flex:1 1 auto;min-width:0;padding:0 4px 0 8px;overflow:hidden;text-overflow:ellipsis}
#xray-overlay .xs-x,#xray-overlay .xs-more{flex:0 0 auto;padding:0 7px;background:transparent;border:0;color:inherit;font:inherit;line-height:inherit;cursor:pointer}
#xray-overlay .xs-x:hover{background:rgba(255,255,255,.15)}
#xray-overlay .xs-more{border-left:1px solid var(--sb-line,#262d3a);color:var(--sb-dim,#8d99a8)}
#xray-overlay .xs-more[aria-expanded="true"]{color:var(--sb-fg,#dfe6ee);background:var(--sb-hover,#1c2230)}
#xray-status-pop{position:absolute;right:0;bottom:${STATUS_H}px;z-index:13;max-width:min(560px,100%);max-height:60vh;overflow:auto;box-sizing:border-box;padding:6px 9px;
  background:rgba(20,24,32,.97);color:var(--sb-fg,#dfe6ee);border:1px solid var(--sb-line,#262d3a);border-radius:4px 4px 0 0;box-shadow:0 -4px 14px rgba(0,0,0,.35);
  font:11px/1.4 system-ui,-apple-system,'Segoe UI',sans-serif;user-select:text;white-space:normal}
#xray-status-pop[hidden]{display:none}
#xray-status-pop pre{margin:0 0 6px;font:11px/1.35 ui-monospace,Menlo,Consolas,monospace;white-space:pre-wrap}
#xray-status-pop .xs-h{color:var(--sb-dim,#8d99a8);text-transform:uppercase;font-size:10px;letter-spacing:.06em;font-weight:600;margin:4px 0 2px}
#xray-status-pop ul{margin:0;padding-left:16px}
#xray-status-pop li.cur{color:#fff}
body.xt-on #xray-overlay{left:44px}
body.xt-on #xray-status-pop{max-width:min(560px,calc(100% - 44px))}
/* Narrow screens (index.html): the tree and dock rails overlay the stage, so the bar starts after the left rail and the
   strip, and stops before the right rail. */
@media (max-width:700px){
  #xray-overlay{left:var(--sb-rail,28px);right:var(--dk-rail,28px)}
  body.xt-on #xray-overlay{left:calc(var(--sb-rail,28px) + 44px)}
  #xray-status-pop{right:var(--dk-rail,28px);max-width:calc(100% - var(--sb-rail,28px) - var(--dk-rail,28px))}
  body.xt-on #xray-status-pop{max-width:calc(100% - var(--sb-rail,28px) - var(--dk-rail,28px) - 44px)}
  #xray-overlay .xs-buckets{display:none}
  #xray-overlay.xs-msg-on .xs-elem,#xray-overlay.xs-msg-on .xs-frame{display:none}
  #xray-overlay .xs-msgwrap{flex:1 1 auto;max-width:none}
}
`;

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls: string, text = ''): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text) e.textContent = text;
  return e;
}

export class StatusBar {
  readonly root: HTMLDivElement;
  readonly pop: HTMLDivElement;
  private readonly model = el('span', 'xs-seg xs-model');
  private readonly xray = el('span', 'xs-seg xs-xray');
  private readonly buckets = el('span', 'xs-seg xs-buckets');
  private readonly msgWrap = el('span', 'xs-seg xs-msgwrap');
  private readonly msg = el('span', '');
  private readonly elem = el('span', 'xs-seg xs-elem');
  private readonly frame = el('span', 'xs-seg xs-frame');
  private readonly more = el('button', 'xs-more', 'ⓘ');
  private details = '';
  private modelName = '';

  constructor(host: HTMLElement) {
    if (!document.getElementById('xray-status-style')) {
      const st = document.createElement('style');
      st.id = 'xray-status-style';
      st.textContent = CSS;
      document.head.appendChild(st);
    }
    const root = el('div', '');
    root.id = 'xray-overlay';
    root.setAttribute('role', 'status');
    root.setAttribute('aria-label', 'Status bar');
    this.msg.id = 'xray-message';
    this.msg.style.display = 'none';
    this.msgWrap.style.display = 'none';
    const x = el('button', 'xs-x', '×');
    x.type = 'button';
    x.title = 'Dismiss message';
    x.setAttribute('aria-label', 'Dismiss message');
    x.addEventListener('click', () => this.setMessage(null));
    this.msgWrap.append(this.msg, x);
    this.more.type = 'button';
    this.more.title = 'Details and model credits';
    this.more.setAttribute('aria-label', 'Status details');
    this.more.setAttribute('aria-expanded', 'false');
    this.more.addEventListener('click', () => this.toggle());
    this.model.addEventListener('click', () => this.toggle());
    this.model.setAttribute('role', 'button');
    this.model.tabIndex = 0;
    this.model.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        this.toggle();
      }
    });
    root.append(this.model, this.xray, this.buckets, this.msgWrap, this.elem, this.frame, this.more);
    // Help tooltips (src/plugins/help.ts reads data-help-key; the texts are in src/ui/helpText.ts).
    root.setAttribute('data-help-key', 'Status bar');
    this.model.setAttribute('data-help-key', 'Status bar/Model name');
    this.more.setAttribute('data-help-key', 'Status bar/Details button');
    x.setAttribute('data-help-key', 'Status bar/Dismiss button');
    this.root = root;
    this.pop = el('div', '');
    this.pop.id = 'xray-status-pop';
    this.pop.hidden = true;
    this.pop.setAttribute('role', 'dialog');
    this.pop.setAttribute('aria-label', 'Status details');
    host.append(root, this.pop);
    document.addEventListener('pointerdown', (e) => {
      if (this.pop.hidden) return;
      const t = e.target as Node;
      if (!this.pop.contains(t) && !this.more.contains(t) && !this.model.contains(t)) this.toggle(false);
    });
  }

  get open(): boolean {
    return !this.pop.hidden;
  }

  toggle(open = this.pop.hidden): void {
    this.pop.hidden = !open;
    this.more.setAttribute('aria-expanded', String(open));
    if (open) this.renderPop();
  }

  /** Red segment with a dismiss button; null clears it. */
  setMessage(text: string | null): void {
    this.msg.textContent = text ?? '';
    this.msg.title = text ?? '';
    const d = text ? '' : 'none';
    this.msg.style.display = d;
    this.msgWrap.style.display = d;
    this.root.classList.toggle('xs-msg-on', !!text);
  }

  get message(): string {
    return this.msg.style.display === 'none' ? '' : (this.msg.textContent ?? '');
  }

  update(s: StatusInput): void {
    const t = statusText(s);
    if (s.model !== this.modelName) {
      this.modelName = s.model;
      this.model.title = `${s.model}: ${modelCredit(s.model)}\nClick for details and the credits of all models.`;
    }
    this.set(this.model, t.model);
    this.set(this.xray, t.xray);
    this.xray.classList.toggle('on', s.xray);
    this.set(this.buckets, t.buckets);
    this.buckets.title = 'Buckets: focus, host, near, far';
    this.set(this.elem, t.element);
    this.elem.title = t.element;
    this.set(this.frame, t.frame);
    if (t.details !== this.details) {
      this.details = t.details;
      this.root.title = t.details;
      if (this.open) this.renderPop();
    }
  }

  private set(e: HTMLElement, text: string): void {
    if (e.textContent !== text) e.textContent = text;
  }

  private renderPop(): void {
    const p = this.pop;
    p.textContent = '';
    p.append(el('div', 'xs-h', 'Details'), el('pre', '', this.details));
    p.append(el('div', 'xs-h', 'About models'));
    const ul = el('ul', '');
    const names = new Set<string>([...Object.keys(window.__xrayModelCredits ?? MODEL_CREDITS)]);
    if (this.modelName) names.add(this.modelName);
    for (const n of names) {
      const li = el('li', n === this.modelName ? 'cur' : '');
      li.append(el('b', '', n), document.createTextNode(`: ${modelCredit(n)}`));
      ul.append(li);
    }
    p.append(ul);
    if (window.__xrayBuildNote) p.append(el('div', 'xs-h', 'This file'), el('div', '', window.__xrayBuildNote));
  }
}
