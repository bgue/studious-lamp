// Issue pins and drawings while a score plays. Pure part: which of the two show at each moment (default: both hidden; PlayOptions.overlays,
// the 4D plan style `issuesInFilm` and `overlays` cues change it) and the gate that tells a viewer what to apply, once per change. The
// viewer part (ViewerOverlays) hides and shows the overlay layers of the issue pins and of the drawings with a CSS class, so putting
// them back is exactly the removal of the class: nothing else of the issue and drawing state is touched.

import type { Cue, PlayOptions, Score } from './score';
import type { FourDPlan } from '../schedule/types';

export interface OverlayState {
  issues: boolean;
  drawings: boolean;
}

/** What shows when playback starts: the option, else the 4D plan's style (`issuesInFilm` of a schedule cue's plan), else nothing. */
export function overlayDefault(score: Pick<Score, 'cues'>, opts?: PlayOptions['overlays'], planOf?: (cue: Extract<Cue, { kind: 'schedule4d' }>) => FourDPlan | null): OverlayState {
  let base = false;
  if (planOf) {
    for (const c of score.cues) {
      if (c.kind !== 'schedule4d') continue;
      if (planOf(c)?.style.issuesInFilm === true) {
        base = true;
        break;
      }
    }
  }
  return { issues: opts?.issues ?? base, drawings: opts?.drawings ?? base };
}

/** The state after an `overlays` cue: a field the cue does not name stays. */
export function applyOverlayCue(cur: OverlayState, cue: Extract<Cue, { kind: 'overlays' }>): OverlayState {
  return { issues: cue.issues ?? cur.issues, drawings: cue.drawings ?? cur.drawings };
}

/**
 * Tracks the state of a play and reports changes. `show` is what the viewer should draw: begin() hides what the default hides, end()
 * gives everything back (both true), whatever the cues did in between.
 */
export class OverlayGate {
  private state: OverlayState | null = null;

  constructor(private readonly apply: (s: OverlayState) => void) {}

  get active(): boolean {
    return this.state !== null;
  }

  get current(): OverlayState | null {
    return this.state ? { ...this.state } : null;
  }

  begin(initial: OverlayState): void {
    this.state = { ...initial };
    this.apply({ ...initial });
  }

  cue(c: Extract<Cue, { kind: 'overlays' }>): void {
    if (!this.state) return;
    const next = applyOverlayCue(this.state, c);
    if (next.issues === this.state.issues && next.drawings === this.state.drawings) return;
    this.state = next;
    this.apply({ ...next });
  }

  end(): void {
    if (!this.state) return;
    this.state = null;
    this.apply({ issues: true, drawings: true });
  }
}

const STYLE_ID = 'xray-playback-overlays';
export const HIDE_ISSUES_CLASS = 'xray-hide-issues';
export const HIDE_DRAWINGS_CLASS = 'xray-hide-drawings';
/** The overlay layers (src/ui/overlay.ts `layer(name)`): the issue pins, the drawings on the model, the sketches of sheets in 3D. */
const ISSUE_LAYERS = ['bcf-markup'];
const DRAWING_LAYERS = ['markup', 'sheet-sketches'];

/** The CSS that hides the layers while the class is on the root element. */
export function overlayCss(): string {
  const rule = (cls: string, layers: string[]): string => `html.${cls} ${layers.map((l) => `.xray-svg-overlay g[data-layer="${l}"]`).join(`, html.${cls} `)}{display:none !important}`;
  return `${rule(HIDE_ISSUES_CLASS, ISSUE_LAYERS)}\n${rule(HIDE_DRAWINGS_CLASS, DRAWING_LAYERS)}`;
}

/** Viewer side: toggles the two classes on <html> (and installs the style once). */
export function applyOverlaysToDom(s: OverlayState, doc: Document = document): void {
  if (!doc.getElementById(STYLE_ID)) {
    const st = doc.createElement('style');
    st.id = STYLE_ID;
    st.textContent = overlayCss();
    doc.head.appendChild(st);
  }
  doc.documentElement.classList.toggle(HIDE_ISSUES_CLASS, !s.issues);
  doc.documentElement.classList.toggle(HIDE_DRAWINGS_CLASS, !s.drawings);
}
