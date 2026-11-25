// "What's new" plugin. On the first start of a new viewer release a small card shows the newest lines of CHANGELOG.md; "Show all
// changes" opens the whole list in a dialog; the action `help.whatsNew` (Help, command palette) opens the dialog any time.
//
// The text comes from the repository's CHANGELOG.md, imported at build time (?raw), so the single-file build carries it and
// nothing is fetched. The release number is the build's (src/whatsnew/release.ts). The last release this browser saw is kept in
// localStorage['xray.whatsnew'] only: never in settings, params, share links or packed pages.
// Rules (src/whatsnew/changelog.ts decideWhatsNew): no key -> first start ever, no card, the number is stored; older key -> card;
// packed pages, kiosk pages, ?embed and framed pages never show it.
// Card: focused when it appears, Escape or Dismiss closes it. Docs: docs-features/whats-new.md.

import type { AppPlugin } from '../app';
import { registerAction } from '../input/actions';
import { getKeymap } from '../input/keymap';
import type { Overlay } from '../input/keymap';
import { bootConfig } from '../tools/registry';
import { el } from '../ui/dom';
import { ensureKeyStyles } from '../ui/keymapView';
import changelogText from '../../../CHANGELOG.md?raw';
import { decideWhatsNew, isQuietMode, parseChangelog } from '../whatsnew/changelog';
import type { ChangelogSection } from '../whatsnew/changelog';
import { RELEASE } from '../whatsnew/release';

const KEY = 'xray.whatsnew';
const STYLE_ID = 'xray-whatsnew-style';

const CSS = `
.wn-card { position: fixed; left: 56px; bottom: 44px; z-index: 40; width: min(380px, calc(100vw - 72px)); box-sizing: border-box; max-height: 60vh; display: flex; flex-direction: column;
  background: var(--sb-bg, #141820); color: var(--sb-fg, #dfe6ee); border: 1px solid var(--sb-line, #262d3a); border-left: 3px solid var(--sb-accent, #3b9cff);
  border-radius: 8px; box-shadow: 0 10px 30px rgba(0,0,0,0.35); font: 12px/1.4 system-ui, sans-serif; outline: none; }
.wn-card:focus-visible { box-shadow: 0 0 0 2px var(--sb-accent, #3b9cff), 0 10px 30px rgba(0,0,0,0.35); }
.wn-head { display: flex; align-items: center; gap: 8px; padding: 8px 8px 4px 12px; }
.wn-title { flex: 1 1 auto; min-width: 0; font-weight: 600; font-size: 13px; }
.wn-x { flex: 0 0 auto; background: transparent; color: inherit; border: 1px solid transparent; border-radius: 4px; padding: 2px 8px; font: inherit; cursor: pointer; }
.wn-x:hover, .wn-x:focus-visible { background: var(--sb-hover, #1c2230); border-color: var(--sb-line, #262d3a); outline: none; }
.wn-body { overflow: auto; padding: 0 12px; min-height: 0; }
.wn-body ul, .wn-list ul { margin: 4px 0 6px; padding-left: 18px; }
.wn-body li, .wn-list li { margin: 2px 0; }
.wn-foot { padding: 4px 12px 10px; }
.wn-link { background: transparent; border: 0; padding: 0; color: var(--sb-accent, #3b9cff); font: inherit; text-decoration: underline; cursor: pointer; }
.wn-link:focus-visible { outline: 2px solid var(--sb-accent, #3b9cff); outline-offset: 2px; border-radius: 2px; }
.wn-list h3 { margin: 12px 0 2px; font-size: 12px; font-weight: 600; }
.wn-list h3:first-child { margin-top: 0; }
.wn-list h3 .wn-date { color: var(--sb-dim, #8d99a8); font-weight: 400; margin-left: 6px; }
.wn-dialog { width: min(640px, 100%); }
@media (max-width: 700px) { .wn-card { left: 16px; right: 16px; width: auto; bottom: 40px; max-height: 50vh; } }
`;

function ensureStyle(): void {
  if (document.getElementById(STYLE_ID)) return;
  const s = document.createElement('style');
  s.id = STYLE_ID;
  s.textContent = CSS;
  document.head.appendChild(s);
}

function heading(s: ChangelogSection): string {
  return s.release !== null ? `Version ${s.release}` : s.title;
}

function listOf(s: ChangelogSection): HTMLUListElement {
  const ul = el('ul');
  for (const l of s.lines) ul.append(el('li', '', {}, l));
  return ul;
}

/** The released sections (Unreleased is left out), newest first. */
function releasedSections(): ChangelogSection[] {
  return parseChangelog(changelogText).filter((s) => s.release !== null && s.lines.length > 0);
}

function readStored(): { stored: string | null; ok: boolean } {
  try {
    return { stored: window.localStorage.getItem(KEY), ok: true };
  } catch {
    return { stored: null, ok: false };
  }
}

function writeStored(n: number): void {
  try {
    window.localStorage.setItem(KEY, String(n));
  } catch {
    /* private window or blocked storage: the card is not shown then either (see readStored) */
  }
}

function quiet(): boolean {
  let framed = false;
  try {
    framed = window.self !== window.top;
  } catch {
    framed = true;
  }
  const boot = (window as unknown as { __xrayBoot?: { kiosk?: boolean } }).__xrayBoot;
  return isQuietMode({ boot: boot ?? (bootConfig().kiosk ? { kiosk: true } : null), search: window.location.search, framed });
}

class ChangesDialog implements Overlay {
  private root: HTMLElement | null = null;
  private opener: Element | null = null;
  private registered = false;
  private readonly onKey = (e: KeyboardEvent): void => {
    if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      this.close();
    }
  };

  isOpen(): boolean {
    return this.root !== null;
  }

  open(): void {
    if (this.root) return;
    if (!this.registered) {
      getKeymap()?.registerOverlay(this);
      this.registered = true;
    }
    ensureKeyStyles();
    ensureStyle();
    this.opener = document.activeElement;
    const back = el('div', 'kx-backdrop', { role: 'dialog', 'aria-modal': 'true', 'aria-label': "What's new" });
    const panel = el('div', 'kx-panel wn-dialog');
    const head = el('div', 'kx-head');
    const close = el('button', 'kx-btn', { type: 'button', 'data-help-key': 'Release notes/Close' }, 'Close');
    head.append(el('span', 'kx-title', {}, "What's new"), el('span', 'kx-grow'), close);
    const body = el('div', 'kx-body wn-list', { 'data-help-key': 'Release notes/Changes list', tabindex: '0', 'aria-label': 'All changes' });
    const secs = releasedSections();
    if (secs.length === 0) body.append(el('div', 'kx-dim', {}, 'No release notes in this build.'));
    for (const s of secs) {
      const h = el('h3', '', {}, heading(s));
      if (s.date) h.append(el('span', 'wn-date', {}, s.date));
      body.append(h, listOf(s));
    }
    panel.append(head, body, el('div', 'kx-foot', {}, 'Esc or a click outside closes this list.'));
    back.append(panel);
    document.body.appendChild(back);
    this.root = back;
    back.addEventListener('mousedown', (e) => {
      if (e.target === back) this.close();
    });
    close.addEventListener('click', () => this.close());
    window.addEventListener('keydown', this.onKey, true);
    close.focus();
  }

  close(): void {
    if (!this.root) return;
    window.removeEventListener('keydown', this.onKey, true);
    this.root.remove();
    this.root = null;
    const o = this.opener;
    this.opener = null;
    if (o instanceof HTMLElement && o.isConnected) o.focus({ preventScroll: true });
  }
}

let card: HTMLElement | null = null;
let pending: { newest: ChangelogSection; release: number; dialog: ChangesDialog } | null = null;

function closeCard(): void {
  card?.remove();
  card = null;
}

function showCard(newest: ChangelogSection, dialog: ChangesDialog, canvas: HTMLElement): void {
  ensureStyle();
  closeCard();
  const c = el('div', 'wn-card', { role: 'dialog', 'aria-label': "What's new", tabindex: '-1', 'data-help-key': 'Release notes/Card' });
  const head = el('div', 'wn-head');
  const dismiss = el('button', 'wn-x', { type: 'button', 'aria-label': 'Dismiss', 'data-help-key': 'Release notes/Dismiss' }, 'Dismiss');
  head.append(el('span', 'wn-title', {}, `What's new in version ${newest.release}`), dismiss);
  const body = el('div', 'wn-body');
  body.append(listOf(newest));
  const foot = el('div', 'wn-foot');
  const all = el('button', 'wn-link', { type: 'button', 'data-help-key': 'Release notes/Show all changes' }, 'Show all changes');
  foot.append(all);
  c.append(head, body, foot);
  document.body.appendChild(c);
  card = c;
  const dismissCard = (): void => {
    const hadFocus = c.contains(document.activeElement);
    closeCard();
    if (hadFocus) canvas.focus({ preventScroll: true });
  };
  dismiss.addEventListener('click', dismissCard);
  all.addEventListener('click', () => {
    closeCard();
    dialog.open();
  });
  c.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      dismissCard();
    }
  });
  const a = document.activeElement;
  if (!a || a === document.body || a === canvas) c.focus({ preventScroll: true });
}

declare global {
  interface Window {
    /** For scripts and smokes: the card and the dialog. */
    __xrayWhatsNew?: { release: number | null; open(): void; cardShown(): boolean };
  }
}

export const whatsNewPlugin: AppPlugin = {
  name: 'whatsNew',

  install(app) {
    const dialog = new ChangesDialog();
    window.__xrayWhatsNew = { release: RELEASE, open: () => dialog.open(), cardShown: () => card !== null };
    registerAction({
      id: 'help.whatsNew',
      label: "What's new",
      group: 'Other',
      keys: [],
      description: 'Show what changed in each release of the viewer.',
      run: () => dialog.open(),
    });

    const st = readStored();
    const newest = releasedSections()[0] ?? null;
    const d = decideWhatsNew({ current: RELEASE, stored: st.stored, storageOk: st.ok, quiet: quiet(), hasLines: newest !== null });
    if (RELEASE !== null && d.store && !d.show) writeStored(RELEASE);
    // the card waits for the first model, so it does not sit over the loading text; the number is stored when it shows
    if (d.show && newest && RELEASE !== null) pending = { newest, release: RELEASE, dialog };
  },

  onModel(app) {
    const p = pending;
    if (!p) return;
    pending = null;
    writeStored(p.release);
    showCard(p.newest, p.dialog, app.canvas);
  },
};
