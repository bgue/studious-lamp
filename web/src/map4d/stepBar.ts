// The three steps of the 4D tab: 1 Map (Values, Assign, Suggest, Coverage), 2 Link (Schedule, Configure, Link) and 3 Film (Style,
// Save IFC, Import / Export). Only the sections of the current step show; the film bar above stays. Each step shows its state: done
// (a check), needs attention (a count) or not started. The choice is a per-viewer convenience: it lives in the panel, not in the
// parameters or the share links. Pure state in `stepStates` / `pickStart` (tested in tests/map4d-steps.test.ts); `buildStepBar` draws.

import { el } from '../ui/dom';

export type StepId = 'map' | 'link' | 'film';
export const STEP_IDS: readonly StepId[] = ['map', 'link', 'film'];
export const STEP_LABEL: Record<StepId, string> = { map: 'Map', link: 'Link', film: 'Film' };

/** The step that holds each section (the `data-sec` ids of the panels). */
export const STEP_OF_SECTION: Record<string, StepId> = {
  values: 'map', assign: 'map', suggest: 'map', coverage: 'map',
  schedule: 'link', configure: 'link', link: 'link',
  style: 'film', tempworks: 'film', play: 'film', io: 'film',
};

export interface StepInput {
  /** Manual assignments (location, trade, zone). */
  accepted: number;
  proposed: number;
  hasSchedule: boolean;
  hasLinks: boolean;
  /** Accepted activity links. */
  acceptedLinks: number;
  ties: number;
  /** Link suggestions that wait for a decision. */
  suggestions: number;
}

export interface StepState { id: StepId; kind: 'done' | 'attention' | 'idle'; text: string }

const plural = (n: number, one: string, many: string): string => `${n} ${n === 1 ? one : many}`;

export function stepStates(i: StepInput): StepState[] {
  const map: StepState = i.proposed > 0 ? { id: 'map', kind: 'attention', text: `${i.proposed} to decide` }
    : i.accepted > 0 ? { id: 'map', kind: 'done', text: '✓ done' }
    : { id: 'map', kind: 'idle', text: 'not started' };
  const link: StepState = !i.hasSchedule ? { id: 'link', kind: 'idle', text: 'not started' }
    : !i.hasLinks || i.acceptedLinks === 0 ? { id: 'link', kind: 'idle', text: 'not linked' }
    : i.ties > 0 ? { id: 'link', kind: 'attention', text: plural(i.ties, 'tie', 'ties') }
    : i.suggestions > 0 ? { id: 'link', kind: 'attention', text: `${i.suggestions} to decide` }
    : { id: 'link', kind: 'done', text: '✓ done' };
  const film: StepState = i.acceptedLinks > 0 ? { id: 'film', kind: 'idle', text: 'ready' } : { id: 'film', kind: 'idle', text: 'not started' };
  return [map, link, film];
}

/** The step to start on: no schedule, or a schedule not linked yet: Link (Map is optional, the schedule can link by storey and class); linked: Film. */
export function pickStart(i: Pick<StepInput, 'hasSchedule' | 'acceptedLinks'>): StepId {
  return i.hasSchedule && i.acceptedLinks > 0 ? 'film' : 'link';
}

const STYLE_ID = 'xray-4d-steps-style';
const CSS = `
.x4 .x4-steps{display:flex;gap:4px}
.x4 .x4-steps button{flex:1 1 0;min-width:0;display:flex;flex-direction:column;align-items:flex-start;gap:1px;height:auto;padding:4px 8px;text-align:left;white-space:normal;border-radius:4px}
.x4 .x4-steps button b{font-weight:600;font-size:12px}
.x4 .x4-steps button small{font-size:10.5px;color:var(--sb-dim,#8d99a8);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:100%}
.x4 .x4-steps button[aria-selected=true]{background:#1f4a7a;border-color:#3b82c4;color:#fff}
.x4 .x4-steps button[aria-selected=true] small{color:#d6e6f7}
.x4 .x4-steps button[data-kind=done] small{color:#9fe3b0}
.x4 .x4-steps button[data-kind=attention] small{color:#e0b252}
.x4 .x4-steps button[aria-selected=true][data-kind=attention] small{color:#ffd98a}
.x4[data-step=map] [data-step]:not([data-step=map]):not(.x4-steps),.x4[data-step=link] [data-step]:not([data-step=link]):not(.x4-steps),.x4[data-step=film] [data-step]:not([data-step=film]):not(.x4-steps){display:none}
@media (max-width:700px){.x4 .x4-steps button{min-height:40px}}
`;

function ensureStyle(): void {
  if (document.getElementById(STYLE_ID)) return;
  const st = document.createElement('style');
  st.id = STYLE_ID;
  st.textContent = CSS;
  document.head.appendChild(st);
}

export interface StepBarHandle {
  element: HTMLElement;
  current(): StepId;
  /** Show a step (a choice of the viewer: the automatic pick stops). */
  show(id: StepId): void;
  /** Tag the sections found under `root` with their step. */
  tag(): void;
  /** Redraw the state of the steps. */
  update(input: StepInput): void;
  /** Forget the choice and pick the start step again once `ready` settles (a new model, the first draw). */
  repick(ready: Promise<unknown>, input: () => StepInput): void;
}

export function buildStepBar(root: HTMLElement, onShow?: (id: StepId) => void): StepBarHandle {
  ensureStyle();
  const bar = el('div', 'x4-steps', { role: 'tablist', 'aria-label': 'Steps of the 4D tab', 'data-x4': 'steps' });
  bar.setAttribute('data-help-key', '4D tab/Step bar');
  const tabs = new Map<StepId, HTMLButtonElement>();
  const small = new Map<StepId, HTMLElement>();
  STEP_IDS.forEach((id, n) => {
    const b = el('button', '', { type: 'button', role: 'tab', 'data-step-tab': id, id: `x4-step-${id}` });
    b.setAttribute('data-help-key', `4D tab/Step ${STEP_LABEL[id]}`);
    const s = el('small', '', undefined, '');
    small.set(id, s);
    b.append(el('b', '', undefined, `${n + 1} ${STEP_LABEL[id]}`), s);
    b.addEventListener('click', () => show(id));
    b.addEventListener('keydown', (ev) => {
      const k = ev.key;
      const at = STEP_IDS.indexOf(id);
      const to = k === 'ArrowRight' || k === 'ArrowDown' ? (at + 1) % STEP_IDS.length : k === 'ArrowLeft' || k === 'ArrowUp' ? (at + STEP_IDS.length - 1) % STEP_IDS.length : k === 'Home' ? 0 : k === 'End' ? STEP_IDS.length - 1 : -1;
      if (to < 0) return;
      ev.preventDefault();
      tabs.get(STEP_IDS[to]!)!.focus();
    });
    tabs.set(id, b);
    bar.append(b);
  });
  let cur: StepId = 'link';
  let chosen = false;
  let token = 0;
  const apply = (): void => {
    root.setAttribute('data-step', cur);
    for (const [id, b] of tabs) { b.setAttribute('aria-selected', String(id === cur)); b.tabIndex = id === cur ? 0 : -1; }
  };
  function show(id: StepId, byViewer = true): void {
    if (byViewer) { chosen = true; token++; }
    const was = cur;
    cur = id;
    apply();
    if (was !== id || byViewer) onShow?.(id);
  }
  apply();
  return {
    element: bar,
    current: () => cur,
    show: (id) => show(id),
    tag() {
      for (const d of Array.from(root.querySelectorAll<HTMLElement>('[data-sec]'))) {
        const st = STEP_OF_SECTION[d.getAttribute('data-sec') ?? ''];
        if (st) d.setAttribute('data-step', st);
      }
    },
    update(input) {
      for (const s of stepStates(input)) {
        small.get(s.id)!.textContent = s.text;
        const b = tabs.get(s.id)!;
        b.setAttribute('data-kind', s.kind);
        b.setAttribute('aria-label', `${STEP_IDS.indexOf(s.id) + 1} ${STEP_LABEL[s.id]}, ${s.text.replace('✓ ', '')}`);
      }
    },
    repick(ready, input) {
      chosen = false;
      const my = ++token;
      void ready.then(() => { if (!chosen && my === token) show(pickStart(input()), false); });
    },
  };
}
