// Quantity HUD: a small translucent card just under the top-bar search that shows the short answer of a summary
// (`42 pipe segments · Σ length 318.4 m (6 est.)`, with `by` the top 3 groups). It stays while hovered, fades about 6 s
// after the last result, goes on Escape or a click (a click also copies the text) and is hidden in kiosk mode and during
// XR, like the bar. While shown it is a reserved rect of the overlay, so labels keep out of it. Docs: docs-features/search.md.

import type { ViewerApp } from '../app';
import type { QuantitySummary } from '../query';
import { summaryLines } from '../query';
import { el } from './dom';
import { getOverlay } from './overlay';
import type { Rect } from './overlay';

export const HUD_ID = 'xray-qhud';
export const HUD_HOLD_MS = 6000;
const FADE_MS = 400;
const PHONE_QUERY = '(max-width: 700px)';
const RESERVE_KEY = 'quantity-hud';

const CSS = `
#${HUD_ID}{position:fixed;z-index:20;box-sizing:border-box;max-width:min(560px,calc(100vw - 16px));padding:6px 12px;border-radius:10px;
  font:12.5px/1.4 system-ui,-apple-system,Segoe UI,sans-serif;cursor:pointer;opacity:0;transition:opacity ${FADE_MS}ms ease;pointer-events:auto;
  color:#eef3f9;background:rgba(16,22,32,.62);border:1px solid rgba(255,255,255,.16);box-shadow:0 4px 18px rgba(0,0,0,.28);
  -webkit-backdrop-filter:blur(10px) saturate(1.2);backdrop-filter:blur(10px) saturate(1.2);text-shadow:0 1px 1px rgba(0,0,0,.25)}
#${HUD_ID}[hidden]{display:none}
#${HUD_ID}.qh-on{opacity:1}
#${HUD_ID} .qh-l1{font-weight:600;overflow-wrap:anywhere}
#${HUD_ID} .qh-l2{color:inherit;opacity:.82;overflow-wrap:anywhere}
#${HUD_ID} .qh-copied{opacity:.7;font-size:11px}
@media (prefers-color-scheme: light){#${HUD_ID}{color:#14202e;background:rgba(255,255,255,.68);border-color:rgba(0,0,0,.14);box-shadow:0 4px 18px rgba(0,0,0,.14);text-shadow:none}}
#${HUD_ID}.qh-phone{left:8px;right:8px;max-width:none;width:auto}
@media (prefers-reduced-motion: reduce){#${HUD_ID}{transition:none}}
`;

function ensureStyle(): void {
  if (document.getElementById(`${HUD_ID}-css`)) return;
  const st = document.createElement('style');
  st.id = `${HUD_ID}-css`;
  st.textContent = CSS;
  document.head.appendChild(st);
}

export interface HudState {
  visible: boolean;
  /** Fading out (shown, opacity going to 0). */
  fading: boolean;
  hiddenByHost: boolean;
  text: string;
  lines: string[];
  rect: Rect | null;
}

export class QuantityHud {
  readonly root: HTMLElement;
  /** Time the card stays after the last result, ms. */
  holdMs = HUD_HOLD_MS;
  private readonly l1: HTMLElement;
  private readonly l2: HTMLElement;
  private readonly phoneMq: MediaQueryList | null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private fadeTimer: ReturnType<typeof setTimeout> | null = null;
  private hovered = false;
  private hostHidden = false;
  private shown = false;
  private fading = false;
  private text = '';
  private lines: string[] = [];
  /** Where it goes: the element it sits under. */
  private readonly anchor: () => HTMLElement | null;

  constructor(
    private readonly app: ViewerApp,
    anchor: () => HTMLElement | null,
  ) {
    ensureStyle();
    this.anchor = anchor;
    this.root = el('div', '', { id: HUD_ID, role: 'status', 'aria-live': 'polite', 'data-help-key': 'Search bar/Quantity card', 'data-help-title': 'Quantity card' });
    this.root.hidden = true;
    this.l1 = el('div', 'qh-l1');
    this.l2 = el('div', 'qh-l2');
    this.root.append(this.l1, this.l2);
    document.body.appendChild(this.root);
    this.phoneMq = typeof window.matchMedia === 'function' ? window.matchMedia(PHONE_QUERY) : null;

    this.root.addEventListener('pointerenter', () => {
      this.hovered = true;
      this.clearTimer();
    });
    this.root.addEventListener('pointerleave', () => {
      this.hovered = false;
      if (this.shown && !this.fading) this.arm();
    });
    this.root.addEventListener('click', () => {
      void this.copy();
      this.hide();
    });
    // A press anywhere else, or Escape (when no text box has the key), dismisses it.
    document.addEventListener('pointerdown', (e) => {
      if (this.shown && !this.root.contains(e.target as Node)) this.hide();
    }, true);
    window.addEventListener('keydown', (e) => {
      if (e.key !== 'Escape' || !this.shown) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
      e.stopImmediatePropagation();
      this.hide();
    }, true);
    window.addEventListener('resize', () => this.place());
  }

  get visible(): boolean {
    return this.shown;
  }

  /** Show the short answer of a summary and restart the fade timer. */
  show(s: QuantitySummary): void {
    this.showLines(summaryLines(s));
  }

  showLines(lines: string[]): void {
    if (this.hostHidden) return;
    this.lines = lines;
    this.text = lines.join('\n');
    this.l1.textContent = lines[0] ?? '';
    this.l2.textContent = lines[1] ?? '';
    this.l2.hidden = !lines[1];
    this.root.setAttribute('aria-label', this.text.replace(/\n/g, '. '));
    this.root.hidden = false;
    this.clearFade();
    this.fading = false;
    this.shown = true;
    getOverlay(this.app).reserve(RESERVE_KEY, () => this.canvasRect());
    this.place();
    // Next frame, so the opacity transition runs from 0 on a first show.
    void this.root.offsetWidth;
    this.root.classList.add('qh-on');
    this.clearTimer();
    if (!this.hovered) this.arm();
  }

  /** Fade out now (Escape, a click, the timer). */
  hide(immediate = false): void {
    if (!this.shown) return;
    this.clearTimer();
    this.shown = false;
    this.hovered = false;
    this.root.classList.remove('qh-on');
    const done = (): void => {
      this.fading = false;
      this.root.hidden = true;
      getOverlay(this.app).reserve(RESERVE_KEY, null);
    };
    if (immediate) {
      done();
      return;
    }
    this.fading = true;
    this.fadeTimer = setTimeout(done, FADE_MS + 40);
  }

  /** Kiosk mode and XR sessions: gone, and it stays gone. */
  setHidden(hidden: boolean): void {
    if (hidden === this.hostHidden) return;
    this.hostHidden = hidden;
    if (hidden) this.hide(true);
  }

  state(): HudState {
    return { visible: this.shown, fading: this.fading, hiddenByHost: this.hostHidden, text: this.text, lines: this.lines, rect: this.shown || this.fading ? this.canvasRect() : null };
  }

  async copy(): Promise<boolean> {
    const text = this.text;
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      try {
        const ta = el('textarea', '', { 'aria-hidden': 'true' });
        ta.value = text;
        ta.style.cssText = 'position:fixed;left:-1000px;top:0;opacity:0';
        document.body.appendChild(ta);
        ta.select();
        const ok = document.execCommand('copy');
        ta.remove();
        return ok;
      } catch {
        return false;
      }
    }
  }

  // ------------------------------------------------------------------------------------------------ internals

  private arm(): void {
    this.clearTimer();
    this.timer = setTimeout(() => {
      this.timer = null;
      this.hide();
    }, this.holdMs);
  }

  private clearTimer(): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
  }

  private clearFade(): void {
    if (this.fadeTimer) clearTimeout(this.fadeTimer);
    this.fadeTimer = null;
  }

  /** Just under the search host (and the top bar), centred on it; the whole width on a phone. */
  private place(): void {
    if (!this.shown) return;
    const a = this.anchor();
    const bar = document.getElementById('xray-topbar');
    const ar = a?.getBoundingClientRect();
    const br = bar?.getBoundingClientRect();
    const bottom = Math.max(ar && ar.height > 0 ? ar.bottom : 0, br && br.height > 0 ? br.bottom : 0);
    const top = (bottom > 0 ? bottom : 40) + 6;
    const phone = !!this.phoneMq?.matches;
    this.root.classList.toggle('qh-phone', phone);
    this.root.style.top = `${Math.round(top)}px`;
    if (phone) {
      this.root.style.left = '';
      this.root.style.right = '';
      return;
    }
    const vw = window.innerWidth;
    const w = this.root.offsetWidth;
    const cx = ar && ar.width > 0 ? ar.left + ar.width / 2 : vw / 2;
    this.root.style.right = 'auto';
    this.root.style.left = `${Math.round(Math.max(8, Math.min(cx - w / 2, vw - w - 8)))}px`;
  }

  private canvasRect(): Rect | null {
    if (this.root.hidden) return null;
    const r = this.root.getBoundingClientRect();
    if (r.width <= 0) return null;
    const c = this.app.canvas.getBoundingClientRect();
    return { x: r.left - c.left, y: r.top - c.top, w: r.width, h: r.height };
  }
}
