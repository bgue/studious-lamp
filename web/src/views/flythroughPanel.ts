// DOM of the "Fly-through" section of the Views tab: the fly-through list, the transport (play, pause, stop, record), a timeline
// bar with a playhead, a strip of keyframe cards (drag or use the buttons to reorder) and the editor of the selected keyframe.
// State lives in src/plugins/flythrough.ts; the panel calls back through FlyHost and re-renders on render().

import { el, esc } from '../ui/dom';
import type { FlyKeyframe, FlyThrough, Timing } from '../anim/flythrough';
import type { KeyframePatch } from '../anim/store';
import { DEFAULT_LABEL_FIELDS, parseFieldList } from '../anim/hud/fields';
import type { HudSettings } from '../anim/hud/settings';
import { LABEL_SIZE_MAX, LABEL_SIZE_MIN } from '../anim/hud/settings';

export interface FlyState {
  playing: boolean;
  paused: boolean;
  recording: boolean;
  time: number;
  duration: number;
}

export interface FlyHost {
  list(): readonly FlyThrough[];
  active(): FlyThrough | null;
  setActive(id: string): void;
  create(): void;
  rename(name: string): void;
  duplicate(): void;
  remove(): void;
  exportFile(): void;
  importFile(file: File): void;
  timing(): Timing;
  state(): FlyState;
  savedViews(): Array<{ id: string; name: string }>;
  addCurrent(): void;
  addSaved(viewId: string): void;
  buildFromViews(): void;
  buildFromSets(): void;
  update(index: number, patch: KeyframePatch): void;
  updateFromCurrent(index: number): void;
  insertAfter(index: number): void;
  goTo(index: number): void;
  removeKeyframe(index: number): void;
  move(from: number, to: number): void;
  setOptions(o: Partial<Pick<FlyThrough, 'timing' | 'speed' | 'segmentS' | 'lookAtSelection' | 'loop'>>): void;
  hud(): HudSettings;
  setHud(patch: Partial<HudSettings>): void;
  play(fromIndex?: number): void;
  pause(): void;
  resume(): void;
  stop(): void;
  record(): void;
  seekTime(t: number): void;
  /** The section is open (the 3D path shows while the Views tab is open). */
  onExpanded(open: boolean): void;
}

const UI_KEY = 'xray.flythrough.ui';
const STYLE_ID = 'xray-flythrough-style';
const CSS = `
.fl { flex: 0 0 auto; border-top: 1px solid var(--sb-line); margin-top: 4px; }
.fl-head { display: flex; align-items: center; gap: 6px; padding: 5px 6px; cursor: pointer; background: transparent; border: 0; width: 100%; color: inherit; font: inherit; text-align: left; }
.fl-head:hover { background: var(--sb-hover); }
.fl-head .fl-caret { width: 12px; color: var(--sb-dim); }
.fl-head .fl-title { font-weight: 700; }
.fl-head .fl-sum { color: var(--sb-dim); font-size: 11px; margin-left: auto; white-space: nowrap; }
.fl-body { padding: 2px 6px 8px; display: flex; flex-direction: column; gap: 6px; }
.fl-body[hidden] { display: none; }
.fl-row { display: flex; gap: 4px; align-items: center; flex-wrap: wrap; }
.fl-row .inp { min-width: 0; }
.fl-row select.inp { height: 22px; padding: 0 2px; color: inherit; font: inherit; }
.fl-row select.inp option { background: #141820; color: #dfe6ee; }
.fl-grow { flex: 1 1 90px; }
.fl-sp { flex: 1 1 auto; }
.fl .btn { padding: 2px 7px; }
.fl .btn.on { background: #1f4a7a; border-color: #2d6aa8; }
.fl .btn:disabled { opacity: 0.45; cursor: default; }
.fl-time { font-variant-numeric: tabular-nums; color: var(--sb-dim); font-size: 11px; margin-left: auto; }
.fl-bar { position: relative; height: 22px; border-radius: 3px; background: #0e1218; border: 1px solid var(--sb-line); cursor: pointer; touch-action: none; overflow: hidden; }
.fl-seg { position: absolute; top: 9px; height: 4px; background: #2a3a55; }
.fl-tick { position: absolute; top: 3px; width: 2px; height: 14px; background: #6b86b3; margin-left: -1px; }
.fl-tick.sel { background: var(--sb-accent); width: 3px; margin-left: -1px; }
.fl-hold { position: absolute; top: 6px; height: 10px; background: rgba(59, 156, 255, 0.3); }
.fl-head-line { position: absolute; top: 0; bottom: 0; width: 2px; margin-left: -1px; background: #ffb454; pointer-events: none; }
.fl-cards { display: flex; flex-wrap: wrap; gap: 6px; align-items: flex-start; }
.fl-card { position: relative; width: 104px; border: 1px solid var(--sb-line); border-radius: 4px; background: #0e1218; overflow: hidden; }
.fl-card.sel { border-color: var(--sb-accent); box-shadow: 0 0 0 1px var(--sb-accent); }
.fl-card.dragging { opacity: 0.45; }
.fl-card.drop-before { box-shadow: inset 3px 0 0 var(--sb-accent); }
.fl-card.drop-after { box-shadow: inset -3px 0 0 var(--sb-accent); }
.fl-card .fl-shot { display: block; width: 100%; padding: 0; border: 0; background: #1b2230; cursor: pointer; aspect-ratio: 16 / 10; }
.fl-card .fl-shot img { display: block; width: 100%; height: 100%; object-fit: cover; }
.fl-card .fl-noshot { display: flex; width: 100%; height: 100%; align-items: center; justify-content: center; color: var(--sb-dim); font-size: 10px; }
.fl-card .fl-n { position: absolute; left: 3px; top: 3px; background: rgba(14, 18, 24, 0.75); border-radius: 3px; padding: 0 4px; font-size: 10px; }
.fl-card .fl-grip { position: absolute; right: 3px; top: 3px; background: rgba(14, 18, 24, 0.75); border-radius: 3px; padding: 0 3px; cursor: grab; touch-action: none; user-select: none; font-size: 11px; letter-spacing: -2px; }
.fl-card .fl-cap { padding: 2px 4px 3px; }
.fl-card .fl-name { font-weight: 600; font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fl-card .fl-meta { color: var(--sb-dim); font-size: 10px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.fl-card .fl-mv { display: flex; gap: 2px; padding: 0 3px 3px; }
.fl-card .fl-mv .btn { flex: 1 1 0; padding: 0; font-size: 11px; line-height: 16px; }
.fl-edit { border: 1px solid var(--sb-line); border-radius: 4px; padding: 6px; display: flex; flex-direction: column; gap: 5px; background: #0b0f15; }
.fl-edit label { display: flex; align-items: center; gap: 4px; font-size: 11px; color: var(--sb-dim); }
.fl-edit .inp.num { width: 56px; }
.fl-edit textarea.inp { width: 100%; box-sizing: border-box; min-height: 40px; resize: vertical; font: inherit; }
.fl-msg { color: var(--sb-dim); min-height: 14px; font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fl-empty { color: var(--sb-dim); padding: 4px 2px; }
@media (hover: none) { .fl .btn { padding: 5px 9px; } .fl-card .fl-mv .btn { line-height: 24px; } }
`;

function ensureStyle(): void {
  if (document.getElementById(STYLE_ID)) return;
  const st = document.createElement('style');
  st.id = STYLE_ID;
  st.textContent = CSS;
  document.head.appendChild(st);
}

const hk = (key: string, title?: string): Record<string, string> => ({ 'data-help-key': `Sidebar/${key}`, 'data-help-title': title ?? key.replace(/^Fly-through /, '') });

export function fmtTime(s: number): string {
  const t = Math.max(0, Math.round(s));
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}`;
}

function sec(n: number): string {
  return `${Math.round(n * 10) / 10} s`;
}

export class FlythroughPanel {
  readonly root: HTMLDivElement;
  private readonly headBtn: HTMLButtonElement;
  private readonly sum: HTMLSpanElement;
  private readonly body: HTMLDivElement;
  private readonly listSel: HTMLSelectElement;
  private readonly playBtn: HTMLButtonElement;
  private readonly pauseBtn: HTMLButtonElement;
  private readonly stopBtn: HTMLButtonElement;
  private readonly recBtn: HTMLButtonElement;
  private readonly fromBtn: HTMLButtonElement;
  private readonly timeEl: HTMLSpanElement;
  private readonly bar: HTMLDivElement;
  private readonly cards: HTMLDivElement;
  private readonly edit: HTMLDivElement;
  private readonly msg: HTMLDivElement;
  private readonly timingSel: HTMLSelectElement;
  private readonly speedInp: HTMLInputElement;
  private readonly speedLbl: HTMLLabelElement;
  private readonly lookChk: HTMLInputElement;
  private readonly loopChk: HTMLInputElement;
  private readonly hudEls: { progress: HTMLInputElement; compass: HTMLInputElement; scaleBar: HTMLInputElement; labelSize: HTMLInputElement; captionPosition: HTMLSelectElement };
  private readonly savedSel: HTMLSelectElement;
  private readonly fileInput: HTMLInputElement;
  private head: HTMLDivElement | null = null;
  private selected = 0;
  private open: boolean;
  private drag: { from: number; to: number; el: HTMLElement } | null = null;
  private editKey = '';
  private editEls: Record<string, HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement> = {};

  constructor(private readonly host: FlyHost) {
    ensureStyle();
    let open = true;
    try {
      open = window.localStorage.getItem(UI_KEY) !== 'closed';
    } catch {
      open = true;
    }
    this.open = open;
    this.root = el('div', 'fl');
    this.headBtn = el('button', 'fl-head', { type: 'button', 'aria-expanded': String(open), ...hk('Fly-through section', 'Fly-through section') });
    this.headBtn.innerHTML = '<span class="fl-caret" aria-hidden="true"></span><span class="fl-title">Fly-through</span>';
    this.sum = el('span', 'fl-sum');
    this.headBtn.append(this.sum);
    this.body = el('div', 'fl-body');
    this.body.hidden = !open;
    this.root.append(this.headBtn, this.body);

    // Row 1: which fly-through.
    this.listSel = el('select', 'inp fl-grow', { 'aria-label': 'Fly-through', ...hk('Fly-through list') });
    const newBtn = el('button', 'btn', { type: 'button', title: 'Start a new fly-through', ...hk('Fly-through new') }, 'New');
    const menuBtn = el('button', 'btn', { type: 'button', 'aria-label': 'More fly-through actions', title: 'Rename, duplicate, delete, export or import', ...hk('Fly-through menu') }, '⋯');
    const row1 = el('div', 'fl-row');
    row1.append(this.listSel, newBtn, menuBtn);

    // Row 2: transport.
    this.playBtn = el('button', 'btn', { type: 'button', title: 'Play from the start', ...hk('Fly-through play') }, '▶ Play');
    this.pauseBtn = el('button', 'btn', { type: 'button', title: 'Pause or resume (Space)', ...hk('Fly-through pause') }, '❚❚');
    this.stopBtn = el('button', 'btn', { type: 'button', title: 'Stop and put the view back (Escape)', ...hk('Fly-through stop') }, '■');
    this.fromBtn = el('button', 'btn', { type: 'button', title: 'Play from the selected keyframe', ...hk('Fly-through play from') }, '▶ From');
    this.recBtn = el('button', 'btn', { type: 'button', title: 'Record a video (size, frame rate and format)', ...hk('Fly-through record') }, '● Rec');
    this.timeEl = el('span', 'fl-time');
    const row2 = el('div', 'fl-row');
    row2.append(this.playBtn, this.pauseBtn, this.stopBtn, this.fromBtn, this.recBtn, this.timeEl);

    this.bar = el('div', 'fl-bar', { role: 'slider', tabindex: '0', 'aria-label': 'Fly-through timeline', 'aria-valuemin': '0', ...hk('Fly-through timeline') });

    // Row 3: add.
    const addBtn = el('button', 'btn primary', { type: 'button', title: 'Add the current view as a keyframe', ...hk('Fly-through add keyframe') }, 'Add keyframe');
    this.savedSel = el('select', 'inp fl-grow', { 'aria-label': 'Add a saved view as a keyframe', title: 'Add a saved view as a keyframe', ...hk('Fly-through add saved view') });
    const fromViews = el('button', 'btn', { type: 'button', title: 'Replace the keyframes with one per saved view', ...hk('Fly-through from views') }, 'From views');
    const fromSets = el('button', 'btn', { type: 'button', title: 'Replace the keyframes with one per selection set', ...hk('Fly-through from sets') }, 'From sets');
    const row3 = el('div', 'fl-row');
    row3.append(addBtn, this.savedSel);
    const row3b = el('div', 'fl-row');
    row3b.append(fromViews, fromSets);

    // Row 4: options.
    this.timingSel = el('select', 'inp', { 'aria-label': 'How the travel time is set', ...hk('Fly-through timing') });
    this.timingSel.append(el('option', '', { value: 'speed' }, 'Constant speed'), el('option', '', { value: 'seconds' }, 'Seconds per move'));
    this.speedInp = el('input', 'inp num', { type: 'number', min: '0.1', step: '0.5', 'aria-label': 'Speed or seconds', ...hk('Fly-through speed') });
    this.speedInp.style.width = '58px';
    this.speedLbl = el('label', '', {}, '');
    this.speedLbl.style.cssText = 'display:flex;align-items:center;gap:3px;font-size:11px;color:var(--sb-dim)';
    this.speedLbl.append(this.speedInp, el('span', 'fl-unit', {}, 'm/s'));
    this.lookChk = el('input', '', { type: 'checkbox', ...hk('Fly-through look at selection') });
    const lookLbl = el('label', '', { ...hk('Fly-through look at selection') });
    lookLbl.style.cssText = 'display:flex;align-items:center;gap:3px;font-size:11px;color:var(--sb-dim)';
    lookLbl.append(this.lookChk, 'Look at selection');
    this.loopChk = el('input', '', { type: 'checkbox', ...hk('Fly-through loop') });
    const loopLbl = el('label', '', { ...hk('Fly-through loop') });
    loopLbl.style.cssText = 'display:flex;align-items:center;gap:3px;font-size:11px;color:var(--sb-dim)';
    loopLbl.append(this.loopChk, 'Loop');
    const row4 = el('div', 'fl-row');
    row4.append(this.timingSel, this.speedLbl, lookLbl, loopLbl);

    // Row 5: the on-screen display (HUD).
    const chk = (label: string, help: string): { input: HTMLInputElement; label: HTMLLabelElement } => {
      const input = el('input', '', { type: 'checkbox', ...hk(help) });
      const l = el('label', '', { ...hk(help) });
      l.style.cssText = 'display:flex;align-items:center;gap:3px;font-size:11px;color:var(--sb-dim)';
      l.append(input, label);
      return { input, label: l };
    };
    const hp = chk('Progress bar', 'Fly-through progress bar');
    const hc = chk('Compass', 'Fly-through compass');
    const hs = chk('Scale bar', 'Fly-through scale bar');
    const hsize = el('input', 'inp num', { type: 'number', min: String(LABEL_SIZE_MIN), max: String(LABEL_SIZE_MAX), step: '1', 'aria-label': 'Label font size in pixels', ...hk('Fly-through label size') });
    hsize.style.width = '50px';
    const hsizeL = el('label', '', { ...hk('Fly-through label size') });
    hsizeL.style.cssText = 'display:flex;align-items:center;gap:3px;font-size:11px;color:var(--sb-dim)';
    hsizeL.append('Label size', hsize, 'px');
    const hpos = el('select', 'inp', { 'aria-label': 'Where captions show', ...hk('Fly-through caption position') });
    hpos.append(el('option', '', { value: 'bottom' }, 'Captions at bottom'), el('option', '', { value: 'top' }, 'Captions at top'));
    this.hudEls = { progress: hp.input, compass: hc.input, scaleBar: hs.input, labelSize: hsize, captionPosition: hpos };
    const hudHead = el('div', 'fl-sub', {}, 'On-screen display');
    hudHead.style.cssText = 'font-size:11px;color:var(--sb-dim);margin-top:2px';
    const row5 = el('div', 'fl-row');
    row5.append(hp.label, hc.label, hs.label);
    const row6 = el('div', 'fl-row');
    row6.append(hsizeL, hpos);

    this.msg = el('div', 'fl-msg', { 'aria-live': 'polite' });
    this.cards = el('div', 'fl-cards', { role: 'list', 'aria-label': 'Keyframes' });
    this.edit = el('div', 'fl-edit');
    this.fileInput = el('input', '', { type: 'file', accept: 'application/json,.json' });
    this.fileInput.style.display = 'none';
    this.body.append(row1, row2, this.bar, row3, row3b, row4, hudHead, row5, row6, this.msg, this.cards, this.edit, this.fileInput);

    this.wire(newBtn, menuBtn, addBtn, fromViews, fromSets);
  }

  say(text: string): void {
    this.msg.textContent = text;
    this.msg.title = text;
  }

  get expanded(): boolean {
    return this.open;
  }

  get selectedIndex(): number {
    return this.selected;
  }

  select(i: number): void {
    this.selected = i;
    this.render();
  }

  private setOpen(open: boolean): void {
    this.open = open;
    this.body.hidden = !open;
    this.headBtn.setAttribute('aria-expanded', String(open));
    this.headBtn.querySelector('.fl-caret')!.textContent = open ? '▾' : '▸';
    try {
      window.localStorage.setItem(UI_KEY, open ? 'open' : 'closed');
    } catch {
      /* ignore */
    }
    this.host.onExpanded(open);
  }

  private wire(newBtn: HTMLElement, menuBtn: HTMLElement, addBtn: HTMLElement, fromViews: HTMLElement, fromSets: HTMLElement): void {
    const h = this.host;
    this.headBtn.addEventListener('click', () => this.setOpen(!this.open));
    this.listSel.addEventListener('change', () => h.setActive(this.listSel.value));
    newBtn.addEventListener('click', () => h.create());
    menuBtn.addEventListener('click', () => this.openMenu(menuBtn));
    this.playBtn.addEventListener('click', () => h.play());
    this.fromBtn.addEventListener('click', () => h.play(this.selected));
    this.pauseBtn.addEventListener('click', () => (h.state().paused ? h.resume() : h.pause()));
    this.stopBtn.addEventListener('click', () => h.stop());
    this.recBtn.addEventListener('click', () => h.record());
    addBtn.addEventListener('click', () => h.addCurrent());
    this.savedSel.addEventListener('change', () => {
      if (this.savedSel.value) h.addSaved(this.savedSel.value);
      this.savedSel.value = '';
    });
    fromViews.addEventListener('click', () => h.buildFromViews());
    fromSets.addEventListener('click', () => h.buildFromSets());
    this.timingSel.addEventListener('change', () => h.setOptions({ timing: this.timingSel.value === 'seconds' ? 'seconds' : 'speed' }));
    this.speedInp.addEventListener('change', () => {
      const v = Number(this.speedInp.value);
      if (!(v > 0)) return this.render();
      const f = h.active();
      h.setOptions(f?.timing === 'seconds' ? { segmentS: v } : { speed: v });
    });
    this.lookChk.addEventListener('change', () => h.setOptions({ lookAtSelection: this.lookChk.checked }));
    this.loopChk.addEventListener('change', () => h.setOptions({ loop: this.loopChk.checked }));
    const he = this.hudEls;
    he.progress.addEventListener('change', () => h.setHud({ progress: he.progress.checked }));
    he.compass.addEventListener('change', () => h.setHud({ compass: he.compass.checked }));
    he.scaleBar.addEventListener('change', () => h.setHud({ scaleBar: he.scaleBar.checked }));
    he.labelSize.addEventListener('change', () => {
      const v = Number(he.labelSize.value);
      if (Number.isFinite(v)) h.setHud({ labelSize: v });
      else this.render();
    });
    he.captionPosition.addEventListener('change', () => h.setHud({ captionPosition: he.captionPosition.value === 'top' ? 'top' : 'bottom' }));
    this.fileInput.addEventListener('change', () => {
      const f = this.fileInput.files?.[0];
      if (f) h.importFile(f);
      this.fileInput.value = '';
    });
    // Timeline: a press or a drag seeks.
    const seekFrom = (e: PointerEvent): void => {
      const r = this.bar.getBoundingClientRect();
      const total = h.timing().total;
      if (total <= 0 || r.width <= 0) return;
      h.seekTime(Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)) * total);
    };
    this.bar.addEventListener('pointerdown', (e) => {
      seekFrom(e);
      const move = (ev: PointerEvent): void => seekFrom(ev);
      const up = (): void => {
        window.removeEventListener('pointermove', move);
        window.removeEventListener('pointerup', up);
      };
      window.addEventListener('pointermove', move);
      window.addEventListener('pointerup', up);
    });
    this.bar.addEventListener('keydown', (e) => {
      const st = h.state();
      const step = e.shiftKey ? 5 : 1;
      if (e.key === 'ArrowRight') h.seekTime(st.time + step);
      else if (e.key === 'ArrowLeft') h.seekTime(Math.max(0, st.time - step));
      else return;
      e.preventDefault();
      e.stopPropagation();
    });
    // Cards.
    this.cards.addEventListener('click', (e) => {
      const t = e.target as HTMLElement;
      const card = t.closest<HTMLElement>('[data-i]');
      if (!card) return;
      const i = Number(card.dataset['i']);
      const act = t.closest<HTMLElement>('[data-act]')?.dataset['act'];
      if (act === 'left') h.move(i, i - 1);
      else if (act === 'right') h.move(i, i + 1);
      else if (act === 'grip') return;
      else {
        this.selected = i;
        this.render();
        h.goTo(i);
      }
    });
    this.cards.addEventListener('keydown', (e) => {
      const card = (e.target as HTMLElement).closest<HTMLElement>('[data-i]');
      if (!card) return;
      const i = Number(card.dataset['i']);
      if (e.altKey && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) {
        const to = i + (e.key === 'ArrowLeft' ? -1 : 1);
        h.move(i, to);
        this.selected = to;
        this.render();
        this.cards.querySelector<HTMLElement>(`[data-i="${to}"] .fl-shot`)?.focus();
      } else if (e.key === 'Delete') h.removeKeyframe(i);
      else return;
      e.preventDefault();
      e.stopPropagation();
    });
    this.cards.addEventListener('pointerdown', (e) => this.onGripDown(e));
    this.root.addEventListener('keydown', (e) => {
      const t = e.target as HTMLElement;
      if (t.matches('input, textarea, select')) {
        e.stopPropagation(); // typing is not a viewer shortcut
        if (e.key === 'Escape') t.blur();
      }
    });
  }

  private openMenu(anchor: HTMLElement): void {
    void import('../ui/popupMenu').then(({ openMenu }) => {
      anchor.setAttribute('aria-expanded', 'true');
      openMenu({
        at: anchor,
        label: 'Fly-through actions',
        items: [
          { label: 'Rename', act: 'rename', help: 'Sidebar/Fly-through rename' },
          { label: 'Duplicate', act: 'duplicate', help: 'Sidebar/Fly-through duplicate' },
          { label: 'Export file', act: 'export', help: 'Sidebar/Fly-through export' },
          { label: 'Import file', act: 'import', help: 'Sidebar/Fly-through import' },
          { label: 'Delete', act: 'delete', danger: true, confirm: 'Click again to delete', help: 'Sidebar/Fly-through delete' },
        ],
        onPick: (act) => {
          if (act === 'rename') {
            const f = this.host.active();
            const n = f ? window.prompt('Name of the fly-through', f.name) : null;
            if (n && n.trim()) this.host.rename(n.trim());
          } else if (act === 'duplicate') this.host.duplicate();
          else if (act === 'export') this.host.exportFile();
          else if (act === 'import') this.fileInput.click();
          else if (act === 'delete') this.host.remove();
        },
        onClose: () => anchor.removeAttribute('aria-expanded'),
      });
    });
  }

  // ---------------------------------------------------------------- drag to reorder

  private onGripDown(e: PointerEvent): void {
    const t = e.target as HTMLElement;
    const grip = t.closest<HTMLElement>('[data-act="grip"]');
    if (!grip || e.button !== 0) return;
    const card = grip.closest<HTMLElement>('[data-i]');
    if (!card) return;
    e.preventDefault();
    const from = Number(card.dataset['i']);
    this.drag = { from, to: from, el: card };
    card.classList.add('dragging');
    try {
      grip.setPointerCapture(e.pointerId);
    } catch {
      /* synthetic events */
    }
    const move = (ev: PointerEvent): void => this.onGripMove(ev);
    const up = (ev: PointerEvent): void => {
      grip.removeEventListener('pointermove', move);
      grip.removeEventListener('pointerup', up);
      grip.removeEventListener('pointercancel', up);
      this.onGripUp(ev.type === 'pointerup');
    };
    grip.addEventListener('pointermove', move);
    grip.addEventListener('pointerup', up);
    grip.addEventListener('pointercancel', up);
  }

  private cardEls(): HTMLElement[] {
    return Array.from(this.cards.querySelectorAll<HTMLElement>('[data-i]'));
  }

  private onGripMove(e: PointerEvent): void {
    const d = this.drag;
    if (!d) return;
    const items = this.cardEls();
    for (const it of items) it.classList.remove('drop-before', 'drop-after');
    let best: HTMLElement | null = null;
    let bestD = Infinity;
    for (const it of items) {
      const r = it.getBoundingClientRect();
      const dx = e.clientX < r.left ? r.left - e.clientX : e.clientX > r.right ? e.clientX - r.right : 0;
      const dy = e.clientY < r.top ? r.top - e.clientY : e.clientY > r.bottom ? e.clientY - r.bottom : 0;
      const dist = dx * dx + dy * dy;
      if (dist < bestD) {
        bestD = dist;
        best = it;
      }
    }
    if (!best) return;
    const r = best.getBoundingClientRect();
    const after = e.clientX > r.left + r.width / 2;
    const bi = Number(best.dataset['i']);
    let to = after ? bi + 1 : bi;
    if (to > d.from) to--;
    d.to = to;
    if (bi !== d.from) best.classList.add(after ? 'drop-after' : 'drop-before');
  }

  private onGripUp(commit: boolean): void {
    const d = this.drag;
    this.drag = null;
    if (!d) return;
    for (const it of this.cardEls()) it.classList.remove('drop-before', 'drop-after', 'dragging');
    if (commit && d.to !== d.from) {
      this.selected = d.to;
      this.host.move(d.from, d.to);
    }
  }

  // ---------------------------------------------------------------- render

  render(): void {
    const h = this.host;
    const f = h.active();
    const list = h.list();
    this.headBtn.querySelector('.fl-caret')!.textContent = this.open ? '▾' : '▸';
    const keys = f?.keyframes ?? [];
    const tm = h.timing();
    this.sum.textContent = f ? `${keys.length} keyframe${keys.length === 1 ? '' : 's'}${keys.length ? ` · ${fmtTime(tm.total)}` : ''}` : '';
    if (!this.open) return;

    this.listSel.innerHTML = '';
    for (const x of list) {
      const o = el('option', '', { value: x.id }, x.name);
      if (f && x.id === f.id) o.selected = true;
      this.listSel.append(o);
    }
    if (list.length === 0) this.listSel.append(el('option', '', { value: '' }, 'No fly-through yet'));
    this.timingSel.value = f?.timing ?? 'speed';
    const secs = f?.timing === 'seconds';
    if (document.activeElement !== this.speedInp) this.speedInp.value = String(secs ? f?.segmentS ?? 3 : f?.speed ?? 3);
    (this.speedLbl.querySelector('.fl-unit') as HTMLElement).textContent = secs ? 's' : 'm/s';
    this.lookChk.checked = f?.lookAtSelection === true;
    this.loopChk.checked = f?.loop === true;
    const hud = h.hud();
    this.hudEls.progress.checked = hud.progress;
    this.hudEls.compass.checked = hud.compass;
    this.hudEls.scaleBar.checked = hud.scaleBar;
    if (document.activeElement !== this.hudEls.labelSize) this.hudEls.labelSize.value = String(hud.labelSize);
    this.hudEls.captionPosition.value = hud.captionPosition;

    // Saved views to add.
    const saved = h.savedViews();
    this.savedSel.innerHTML = '';
    this.savedSel.append(el('option', '', { value: '' }, saved.length ? 'Add saved view...' : 'No saved views'));
    for (const v of saved) this.savedSel.append(el('option', '', { value: v.id }, v.name));
    this.savedSel.disabled = saved.length === 0;

    if (this.selected >= keys.length) this.selected = Math.max(0, keys.length - 1);
    this.renderCards(keys, tm);
    this.renderBar(keys, tm);
    this.renderEdit(keys);
    this.renderTransport();
  }

  private renderTransport(): void {
    const st = this.host.state();
    const f = this.host.active();
    const n = f?.keyframes.length ?? 0;
    this.playBtn.disabled = n < 1 || st.recording;
    this.playBtn.classList.toggle('on', st.playing && !st.paused);
    this.pauseBtn.disabled = !st.playing;
    this.pauseBtn.classList.toggle('on', st.paused);
    this.pauseBtn.title = st.paused ? 'Resume (Space)' : 'Pause (Space)';
    this.stopBtn.disabled = !st.playing;
    this.fromBtn.disabled = n < 1 || st.recording;
    this.recBtn.disabled = n < 1 || st.recording || st.playing;
    this.recBtn.classList.toggle('on', st.recording);
    this.timeEl.textContent = `${fmtTime(st.playing ? st.time : 0)} / ${fmtTime(this.host.timing().total)}`;
  }

  private renderCards(keys: readonly FlyKeyframe[], tm: Timing): void {
    const html: string[] = [];
    keys.forEach((k, i) => {
      const travel = i === 0 ? '' : `${sec(tm.travel[i]!)}`;
      const meta = [travel && `to ${travel}`, k.hold > 0 ? `hold ${sec(k.hold)}` : ''].filter(Boolean).join(' · ') || 'start';
      const img = k.view.thumb ? `<img src="${k.view.thumb}" alt="" width="160" height="100" loading="lazy">` : '<span class="fl-noshot">no picture</span>';
      html.push(
        `<div class="fl-card${i === this.selected ? ' sel' : ''}" role="listitem" data-i="${i}" ${'data-help-key="Sidebar/Fly-through keyframe card" data-help-title="Keyframe card"'}>` +
          `<button type="button" class="fl-shot" aria-label="Select keyframe ${i + 1}: ${esc(k.name)}" title="${esc(k.name)}: select and go to">${img}</button>` +
          `<span class="fl-n">${i + 1}</span>` +
          `<span class="fl-grip" data-act="grip" title="Drag to reorder (Alt+Left, Alt+Right)" aria-hidden="true" data-help-key="Sidebar/Fly-through keyframe handle" data-help-title="Keyframe handle">⋮⋮</span>` +
          `<div class="fl-cap"><div class="fl-name">${esc(k.name)}</div><div class="fl-meta" title="${esc(meta)}">${esc(meta)}</div></div>` +
          `<div class="fl-mv"><button type="button" class="btn" data-act="left" aria-label="Move earlier" title="Move earlier"${i === 0 ? ' disabled' : ''} data-help-key="Sidebar/Fly-through move earlier" data-help-title="Move earlier">◀</button>` +
          `<button type="button" class="btn" data-act="right" aria-label="Move later" title="Move later"${i === keys.length - 1 ? ' disabled' : ''} data-help-key="Sidebar/Fly-through move later" data-help-title="Move later">▶</button></div>` +
          `</div>`,
      );
    });
    this.cards.innerHTML = html.join('') || '<div class="fl-empty">No keyframes yet. Set up the view, then press Add keyframe.</div>';
  }

  private renderBar(keys: readonly FlyKeyframe[], tm: Timing): void {
    const total = tm.total;
    this.bar.setAttribute('aria-valuemax', String(Math.round(total)));
    if (total <= 0) {
      this.bar.innerHTML = '';
      this.head = null;
      return;
    }
    const pct = (t: number): string => `${(t / total) * 100}%`;
    const parts: string[] = [];
    keys.forEach((k, i) => {
      if (i > 0) parts.push(`<div class="fl-seg" style="left:${pct(tm.depart[i - 1]!)};width:${((tm.arrive[i]! - tm.depart[i - 1]!) / total) * 100}%"></div>`);
      if (k.hold > 0) parts.push(`<div class="fl-hold" style="left:${pct(tm.arrive[i]!)};width:${(k.hold / total) * 100}%"></div>`);
      parts.push(`<div class="fl-tick${i === this.selected ? ' sel' : ''}" style="left:${pct(tm.arrive[i]!)}" title="${esc(k.name)}"></div>`);
    });
    parts.push('<div class="fl-head-line" style="left:0"></div>');
    this.bar.innerHTML = parts.join('');
    this.head = this.bar.querySelector('.fl-head-line');
  }

  private num(label: string, key: string, help: string, value: string, step = '0.5', placeholder = ''): HTMLLabelElement {
    const l = el('label', '', { ...hk(help) });
    const inp = el('input', 'inp num', { type: 'number', min: '0', step, ...(placeholder ? { placeholder } : {}), 'aria-label': label, ...hk(help) });
    inp.value = value;
    this.editEls[key] = inp;
    l.append(label, inp, 's');
    return l;
  }

  private renderEdit(keys: readonly FlyKeyframe[]): void {
    const k = keys[this.selected];
    if (!k) {
      this.edit.innerHTML = '';
      this.edit.style.display = 'none';
      this.editKey = '';
      return;
    }
    this.edit.style.display = '';
    // Keep the fields (and the focus) while the same keyframe is edited; only their values follow.
    const sig = `${k.id}|${this.selected}|${keys.length}`;
    if (sig === this.editKey) {
      this.syncEdit(k);
      return;
    }
    this.editKey = sig;
    this.editEls = {};
    this.edit.innerHTML = '';
    const h = this.host;
    const i = this.selected;
    const name = el('input', 'inp fl-grow', { type: 'text', 'aria-label': 'Keyframe name', ...hk('Fly-through keyframe name') });
    this.editEls['name'] = name;
    const rowN = el('div', 'fl-row');
    rowN.append(name);
    const mk = (text: string, help: string, title: string, fn: () => void, cls = 'btn'): HTMLButtonElement => {
      const b = el('button', cls, { type: 'button', title, ...hk(help) }, text);
      b.addEventListener('click', fn);
      return b;
    };
    const rowB = el('div', 'fl-row');
    rowB.append(
      mk('Go to', 'Fly-through go to', 'Move the camera to this keyframe', () => h.goTo(this.selected)),
      mk('Update', 'Fly-through update', 'Replace this keyframe with the current view', () => h.updateFromCurrent(this.selected)),
      mk('Insert after', 'Fly-through insert', 'Add the current view after this keyframe', () => h.insertAfter(this.selected)),
      mk('Delete', 'Fly-through delete keyframe', 'Delete this keyframe', () => h.removeKeyframe(this.selected)),
    );
    const rowT = el('div', 'fl-row');
    const travel = this.num('Travel', 'travel', 'Fly-through travel', '', '0.5', 'auto');
    const hold = this.num('Hold', 'hold', 'Fly-through hold', '0');
    rowT.append(travel, hold);
    const rowE = el('div', 'fl-row');
    const ease = el('input', '', { type: 'checkbox', ...hk('Fly-through ease') });
    this.editEls['ease'] = ease;
    const easeL = el('label', '', { ...hk('Fly-through ease') });
    easeL.append(ease, 'Ease');
    const fade = el('input', '', { type: 'checkbox', ...hk('Fly-through fade') });
    this.editEls['fade'] = fade;
    const fadeL = el('label', '', { ...hk('Fly-through fade') });
    fadeL.append(fade, 'Fade');
    const fadeLen = el('input', 'inp num', { type: 'number', min: '5', max: '100', step: '5', 'aria-label': 'Fade length in percent of the travel', ...hk('Fly-through fade length') });
    this.editEls['fadeFraction'] = fadeLen;
    const fadeLenL = el('label', '', { ...hk('Fly-through fade length') });
    fadeLenL.append(fadeLen, '%');
    const sw = el('select', 'inp', { 'aria-label': 'When discrete changes happen', ...hk('Fly-through switch') });
    sw.append(el('option', '', { value: 'start' }, 'Switch at start'), el('option', '', { value: 'mid' }, 'Switch at middle'), el('option', '', { value: 'end' }, 'Switch at end'));
    this.editEls['switchAt'] = sw;
    rowE.append(easeL, fadeL, fadeLenL, sw);
    const capT = el('input', 'inp', { type: 'text', placeholder: 'Caption title', 'aria-label': 'Caption title', ...hk('Fly-through caption title') });
    const capX = el('textarea', 'inp', { placeholder: 'Caption text', 'aria-label': 'Caption text', rows: '2', ...hk('Fly-through caption text') });
    this.editEls['capTitle'] = capT;
    this.editEls['capText'] = capX;
    const lab = el('input', '', { type: 'checkbox', ...hk('Fly-through label selection') });
    this.editEls['labels'] = lab;
    const labL = el('label', '', { ...hk('Fly-through label selection') });
    labL.style.cssText = 'display:flex;align-items:center;gap:3px;font-size:11px;color:var(--sb-dim)';
    labL.append(lab, 'Label selection');
    const labF = el('input', 'inp fl-grow', { type: 'text', placeholder: DEFAULT_LABEL_FIELDS.join(', '), 'aria-label': 'Label fields', ...hk('Fly-through label fields') });
    this.editEls['labelFields'] = labF;
    const hov = el('input', '', { type: 'checkbox', ...hk('Fly-through hover card') });
    this.editEls['hover'] = hov;
    const hovL = el('label', '', { ...hk('Fly-through hover card') });
    hovL.style.cssText = 'display:flex;align-items:center;gap:3px;font-size:11px;color:var(--sb-dim)';
    hovL.append(hov, 'Hover card');
    const rowL = el('div', 'fl-row');
    rowL.append(labL, labF, hovL);
    this.edit.append(rowN, rowB, rowT, rowE, capT, capX, rowL);

    const num = (key: string): number | null => {
      const v = (this.editEls[key] as HTMLInputElement).value.trim();
      return v === '' ? null : Number(v);
    };
    name.addEventListener('change', () => h.update(i, { name: name.value }));
    (this.editEls['travel'] as HTMLInputElement).addEventListener('change', () => {
      const v = num('travel');
      h.update(i, { travel: v === null || !Number.isFinite(v) ? null : v });
    });
    (this.editEls['hold'] as HTMLInputElement).addEventListener('change', () => h.update(i, { hold: num('hold') ?? 0 }));
    ease.addEventListener('change', () => h.update(i, { ease: ease.checked }));
    fade.addEventListener('change', () => h.update(i, { fade: fade.checked }));
    fadeLen.addEventListener('change', () => h.update(i, { fadeFraction: (num('fadeFraction') ?? 40) / 100 }));
    sw.addEventListener('change', () => h.update(i, { switchAt: sw.value as 'start' | 'mid' | 'end' }));
    const cap = (): void => h.update(i, { caption: { title: capT.value, text: capX.value } });
    capT.addEventListener('change', cap);
    capX.addEventListener('change', cap);
    const labelPatch = (): void => h.update(i, { labels: lab.checked ? { fields: parseFieldList(labF.value) } : null });
    lab.addEventListener('change', labelPatch);
    labF.addEventListener('change', () => {
      if (lab.checked) labelPatch();
    });
    hov.addEventListener('change', () => h.update(i, { hover: hov.checked }));
    this.syncEdit(k);
  }

  private syncEdit(k: FlyKeyframe): void {
    const set = (key: string, v: string | boolean): void => {
      const e = this.editEls[key];
      if (!e || document.activeElement === e) return;
      if (typeof v === 'boolean') (e as HTMLInputElement).checked = v;
      else e.value = v;
    };
    set('name', k.name);
    set('travel', k.travel === undefined ? '' : String(k.travel));
    set('hold', String(k.hold));
    set('ease', k.ease);
    set('fade', k.fade);
    set('fadeFraction', String(Math.round(k.fadeFraction * 100)));
    set('switchAt', k.switchAt);
    set('capTitle', k.caption?.title ?? '');
    set('capText', k.caption?.text ?? '');
    set('labels', !!k.labels);
    set('labelFields', k.labels && k.labels.fields.join(', ') !== DEFAULT_LABEL_FIELDS.join(', ') ? k.labels.fields.join(', ') : '');
    set('hover', k.hover === true);
    const first = this.selected === 0;
    const noSel = k.view.selection.length === 0;
    for (const key of ['labels', 'labelFields', 'hover']) {
      const e = this.editEls[key];
      if (e) {
        (e as HTMLInputElement).disabled = noSel;
        e.title = noSel ? 'This keyframe has no selection. Select elements, then press Update.' : '';
      }
    }
    for (const key of ['travel', 'fade', 'fadeFraction']) {
      const e = this.editEls[key];
      if (e) (e as HTMLInputElement).disabled = first;
    }
  }

  /** Update the playhead and the time (call every frame while playing). */
  tick(): void {
    if (!this.open) return;
    const st = this.host.state();
    const tm = this.host.timing();
    if (this.head && tm.total > 0) this.head.style.left = `${Math.min(100, (Math.max(0, st.playing ? st.time : 0) / tm.total) * 100)}%`;
    this.renderTransport();
  }
}
