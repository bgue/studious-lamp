// The phone panel of the field AR mode: a WebXR DOM overlay (the `dom-overlay` feature of Chrome on Android) with big touch
// targets for the registration, the nudges, the looks, the cut, the measure and the snapshot, plus the info card of the tapped
// element and the elevation line. The root covers the screen and lets taps through to the session (a tap on the camera image is
// an XR `select`); a tap on a button calls `beforexrselect.preventDefault()`, so it does not also count as a select.
// Safe-area insets keep the buttons clear of notches; in landscape the panel moves to the right edge.
//
// Without dom-overlay (Quest Browser, Vision Pro) the element is still in the page, which a headset does not show; the session
// then draws a text panel in the scene instead (xr/fieldSession.ts).

export type FieldAction =
  | 'mark' | 'undo' | 'toReal' | 'addPair' | 'reregister' | 'floor' | 'save' | 'export'
  | 'view' | 'cut' | 'radius' | 'nudge' | 'step' | 'measure' | 'snapshot' | 'exit' | 'clear';

export interface OverlayModel {
  status: string;
  step: 'model' | 'real' | 'done';
  instruction: string;
  pairs: string[];
  residuals: string;
  elevation: string;
  view: string;
  cutOn: boolean;
  cutText: string;
  nudgeStep: string;
  card: { title: string; subtitle: string; rows: Array<[string, string]>; extra: string[] } | null;
  notes: number;
  canSave: boolean;
  registered: boolean;
}

const CSS = `
#xray-xr-field{position:fixed;inset:0;z-index:1000;pointer-events:none;font:15px/1.3 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#eef3f8;
  padding:env(safe-area-inset-top) env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left);box-sizing:border-box;display:flex;flex-direction:column;justify-content:space-between}
#xray-xr-field[hidden]{display:none}
#xray-xr-field .xf-box{pointer-events:auto;background:rgba(14,20,28,.78);border-radius:14px;margin:8px;padding:8px 10px;backdrop-filter:blur(4px)}
#xray-xr-field .xf-top{display:flex;gap:8px;align-items:flex-start}
#xray-xr-field .xf-top .xf-text{flex:1;min-width:0}
#xray-xr-field .xf-status{font-weight:600}
#xray-xr-field .xf-elev,#xray-xr-field .xf-res{font-size:13px;opacity:.85}
#xray-xr-field .xf-card{font-size:13px}
#xray-xr-field .xf-card b{font-size:15px}
#xray-xr-field .xf-card[hidden]{display:none}
#xray-xr-field .xf-row{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
#xray-xr-field button{pointer-events:auto;min-height:48px;min-width:48px;padding:0 12px;border-radius:12px;border:1px solid rgba(255,255,255,.25);
  background:rgba(40,52,66,.92);color:#eef3f8;font:inherit;font-weight:600;touch-action:manipulation}
#xray-xr-field button.on{background:#2f7fd8;border-color:#7fb6f2}
#xray-xr-field button.primary{background:#e08a1e;border-color:#ffc06a;flex:1 1 140px}
#xray-xr-field button[disabled]{opacity:.4}
#xray-xr-field .xf-step{font-size:14px}
#xray-xr-field .xf-pairs{font-size:13px;opacity:.9}
#xray-xr-field details summary{cursor:pointer;min-height:36px;line-height:36px;font-weight:600;pointer-events:auto}
#xray-xr-field .xf-pad{display:grid;grid-template-columns:repeat(4,minmax(48px,1fr));gap:6px}
#xray-xr-field .xf-panel{max-height:58vh;overflow:auto}
@media (orientation:landscape){
  #xray-xr-field{flex-direction:row;align-items:stretch}
  #xray-xr-field .xf-left{flex:1;display:flex;flex-direction:column;justify-content:space-between;min-width:0}
  #xray-xr-field .xf-panel{width:min(380px,46vw);max-height:none;overflow:auto}
}
`;

function h<K extends keyof HTMLElementTagNameMap>(tag: K, cls?: string, text?: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

export class FieldOverlay {
  readonly root: HTMLDivElement;
  private readonly els: Record<string, HTMLElement> = {};
  private readonly buttons = new Map<string, HTMLButtonElement>();
  private last = '';

  constructor(private readonly act: (a: FieldAction, arg?: string) => void) {
    if (!document.getElementById('xray-xr-field-css')) {
      const st = h('style');
      st.id = 'xray-xr-field-css';
      st.textContent = CSS;
      document.head.appendChild(st);
    }
    const root = h('div');
    root.id = 'xray-xr-field';
    root.hidden = true;
    root.setAttribute('aria-label', 'Field AR controls');
    this.root = root;
    // A tap on the panel is not a select in the session.
    root.addEventListener('beforexrselect', (e) => {
      const t = e.target as Element | null;
      if (t && t !== root && t.closest('.xf-box')) e.preventDefault();
    });

    const left = h('div', 'xf-left');
    const top = h('div', 'xf-box xf-top');
    const text = h('div', 'xf-text');
    this.els.status = text.appendChild(h('div', 'xf-status'));
    this.els.elev = text.appendChild(h('div', 'xf-elev'));
    top.append(text, this.btn('exit', 'Exit', 'End the field session'));
    const card = h('div', 'xf-box xf-card');
    card.hidden = true;
    this.els.card = card;
    left.append(top, card);

    const panel = h('div', 'xf-box xf-panel');
    this.els.step = panel.appendChild(h('div', 'xf-step'));
    this.els.pairs = panel.appendChild(h('div', 'xf-pairs'));
    this.els.res = panel.appendChild(h('div', 'xf-res'));
    const reg = h('div', 'xf-row');
    reg.append(
      this.btn('mark', 'Mark point', 'Mark the point under the centre ring', 'primary'),
      this.btn('undo', 'Undo', 'Remove the last point'),
      this.btn('toReal', 'Done picking', 'Stop picking model points and tap the same points in the room'),
    );
    panel.appendChild(reg);
    const reg2 = h('div', 'xf-row');
    reg2.append(
      this.btn('addPair', '+ Pair', 'Add a point pair'),
      this.btn('reregister', 'Register again', 'Tap the room points again'),
      this.btn('floor', 'Floor here', 'Put the floor of this storey at the ring'),
      this.btn('save', 'Save site', 'Save this registration for the next visit'),
    );
    panel.appendChild(reg2);
    const look = h('div', 'xf-row');
    look.append(this.btn('view:x-ray', 'X-ray', 'Show only the services', '', 'view', 'x-ray'), this.btn('view:ghosted', 'Ghosted', 'Services with faint structure', '', 'view', 'ghosted'), this.btn('view:full', 'Full', 'The whole model', '', 'view', 'full'));
    panel.appendChild(look);
    const cut = h('div', 'xf-row');
    cut.append(this.btn('cut', 'Cut', 'Cut the model around you and at the ceiling'), this.btn('radius:-1', 'Cut -', 'Smaller cut', '', 'radius', '-1'), this.btn('radius:1', 'Cut +', 'Larger cut', '', 'radius', '1'));
    this.els.cutText = cut.appendChild(h('span', 'xf-res'));
    panel.appendChild(cut);
    const nud = h('details');
    nud.appendChild(h('summary', undefined, 'Nudge'));
    const pad = h('div', 'xf-pad');
    const n = (k: string, label: string, title: string): HTMLButtonElement => this.btn(`nudge:${k}`, label, title, '', 'nudge', k);
    pad.append(
      n('left', '◀', 'Move the model left'), n('fwd', '▲', 'Move the model away'), n('back', '▼', 'Move the model closer'), n('right', '▶', 'Move the model right'),
      n('up', 'Up', 'Raise the model'), n('down', 'Down', 'Lower the model'), n('ccw', '⟲', 'Turn the model left'), n('cw', '⟳', 'Turn the model right'),
    );
    nud.appendChild(pad);
    const stepRow = h('div', 'xf-row');
    stepRow.append(this.btn('step', '1 cm', 'Change the nudge step'));
    nud.appendChild(stepRow);
    panel.appendChild(nud);
    const tools = h('div', 'xf-row');
    tools.append(this.btn('measure', 'Measure', 'Distance from you and the ring to the selected element'), this.btn('snapshot', 'Snapshot', 'Save the overlay picture and your position'), this.btn('clear', 'Clear', 'Clear the selection'));
    panel.appendChild(tools);
    root.append(left, panel);
  }

  private btn(key: string, label: string, title: string, cls = '', action?: FieldAction, arg?: string): HTMLButtonElement {
    const b = h('button', cls, label);
    b.type = 'button';
    b.title = title;
    b.setAttribute('aria-label', title);
    b.dataset.act = key;
    const a = (action ?? key) as FieldAction;
    b.addEventListener('click', (e) => {
      e.preventDefault();
      this.act(a, arg);
    });
    this.buttons.set(key, b);
    return b;
  }

  show(on: boolean): void {
    if (on && !this.root.isConnected) document.body.appendChild(this.root);
    this.root.hidden = !on;
    if (!on) this.root.remove();
  }

  update(m: OverlayModel): void {
    const key = JSON.stringify(m);
    if (key === this.last) return;
    this.last = key;
    this.els.status!.textContent = m.status;
    this.els.elev!.textContent = m.elevation;
    this.els.step!.textContent = m.instruction;
    this.els.pairs!.textContent = m.pairs.join('  ·  ');
    this.els.res!.textContent = m.residuals;
    this.els.cutText!.textContent = m.cutText;
    const card = this.els.card!;
    card.hidden = !m.card;
    card.replaceChildren();
    if (m.card) {
      card.appendChild(h('b', undefined, m.card.title));
      card.appendChild(h('div', undefined, m.card.subtitle));
      for (const [k, v] of m.card.rows) card.appendChild(h('div', undefined, `${k}: ${v}`));
      for (const x of m.card.extra) card.appendChild(h('div', undefined, x));
    }
    const b = (k: string): HTMLButtonElement => this.buttons.get(k)!;
    for (const v of ['x-ray', 'ghosted', 'full']) b(`view:${v}`).classList.toggle('on', m.view === v);
    b('cut').classList.toggle('on', m.cutOn);
    b('step').textContent = m.nudgeStep;
    b('mark').disabled = m.step === 'done';
    b('mark').textContent = m.step === 'model' ? 'Pick model point' : 'Mark room point';
    b('toReal').disabled = m.step !== 'model';
    b('save').disabled = !m.canSave;
    b('floor').disabled = !m.registered;
    b('snapshot').textContent = m.notes ? `Snapshot (${m.notes})` : 'Snapshot';
  }
}
