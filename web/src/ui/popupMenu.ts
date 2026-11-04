// Small keyboard-accessible popup menu for the sidebar (the "⋯" menu of a set, the property context menu).
//
// One menu at a time. It opens next to an anchor element or at a point, focuses its first item, and closes on
// Escape (focus goes back to the opener), Tab, a click outside, a scroll of the page, or a resize.
// Arrow keys, Home and End move between items; Enter and Space activate (the items are buttons).
// An item with `confirm` asks again: the first activation changes its label, the second runs it.

import { el } from './dom';

export interface MenuItem {
  label: string;
  act: string;
  danger?: boolean;
  disabled?: boolean;
  /** Label for the second step of a two-step item (Delete -> "Click again to delete"). */
  confirm?: string;
  /** Help popover key (data-help-key). */
  help?: string;
  title?: string;
}

const STYLE_ID = 'xray-popup-menu-style';
const CSS = `
.xm-menu { position: fixed; z-index: 1000; min-width: 168px; max-width: min(280px, calc(100vw - 16px)); padding: 3px;
  background: #1a202b; color: var(--sb-fg, #dfe6ee); border: 1px solid #344055; border-radius: 5px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.45); font: 12px/1.35 system-ui, -apple-system, 'Segoe UI', sans-serif; }
.xm-menu .xm-head { padding: 3px 8px 4px; color: var(--sb-dim, #8d99a8); font-size: 11px; white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; border-bottom: 1px solid #2a3344; margin-bottom: 2px; }
.xm-menu button { display: block; width: 100%; text-align: left; background: transparent; border: 0; border-radius: 3px;
  padding: 5px 8px; color: inherit; font: inherit; cursor: pointer; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.xm-menu button:hover:not(:disabled), .xm-menu button:focus-visible { background: #243049; outline: none; }
.xm-menu button:focus { background: #243049; outline: none; }
.xm-menu button.danger { color: #ff8a80; }
.xm-menu button.armed { background: #5a2a2a; color: #fff; }
.xm-menu button:disabled { opacity: 0.45; cursor: default; }
@media (hover: none) { .xm-menu button { padding: 9px 10px; } }
`;

function ensureStyle(): void {
  if (document.getElementById(STYLE_ID)) return;
  const st = document.createElement('style');
  st.id = STYLE_ID;
  st.textContent = CSS;
  document.head.appendChild(st);
}

let current: { close: (restore: boolean) => void } | null = null;

/** Close the open menu, if any. */
export function closeMenu(): void {
  current?.close(false);
}

export interface MenuOptions {
  /** Where to put it: below an element (right-aligned) or at a viewport point. */
  at: HTMLElement | { x: number; y: number };
  items: MenuItem[];
  /** Small heading line (the set name, the property key). */
  heading?: string;
  /** Accessible name. */
  label: string;
  onPick: (act: string) => void;
  /** Focus goes here when the menu closes with Escape (default: the anchor element). */
  returnFocus?: HTMLElement | null;
  onClose?: () => void;
}

/** Open a menu. Returns the menu element (tests and smoke scripts can find it by class `xm-menu`). */
export function openMenu(o: MenuOptions): HTMLDivElement {
  ensureStyle();
  closeMenu();
  const menu = el('div', 'xm-menu', { role: 'menu', 'aria-label': o.label, tabindex: '-1' });
  if (o.heading) menu.append(el('div', 'xm-head', { title: o.heading }, o.heading));
  for (const it of o.items) {
    const b = el('button', it.danger ? 'danger' : '', { type: 'button', role: 'menuitem', 'data-act': it.act, tabindex: '-1' }, it.label);
    if (it.help) b.setAttribute('data-help-key', it.help);
    if (it.title) b.title = it.title;
    if (it.disabled) b.disabled = true;
    menu.append(b);
  }
  document.body.append(menu);

  // Position: below the anchor, right edges aligned; or at the point. Clamped to the viewport.
  const vw = document.documentElement.clientWidth || window.innerWidth;
  const vh = document.documentElement.clientHeight || window.innerHeight;
  const w = menu.offsetWidth;
  const h = menu.offsetHeight;
  let x: number;
  let y: number;
  const anchorEl = o.at instanceof HTMLElement ? o.at : null;
  if (anchorEl) {
    const r = anchorEl.getBoundingClientRect();
    x = r.right - w;
    y = r.bottom + 2;
    if (y + h > vh - 4) y = Math.max(4, r.top - h - 2);
  } else {
    const p = o.at as { x: number; y: number };
    x = p.x;
    y = p.y;
    if (y + h > vh - 4) y = Math.max(4, p.y - h);
  }
  x = Math.max(4, Math.min(x, vw - w - 4));
  y = Math.max(4, Math.min(y, vh - h - 4));
  menu.style.left = `${Math.round(x)}px`;
  menu.style.top = `${Math.round(y)}px`;
  anchorEl?.setAttribute('aria-expanded', 'true');

  const buttons = (): HTMLButtonElement[] => Array.from(menu.querySelectorAll<HTMLButtonElement>('button:not(:disabled)'));
  const focusAt = (i: number): void => {
    const bs = buttons();
    if (bs.length) bs[(i + bs.length) % bs.length]!.focus();
  };

  let closed = false;
  const onDocDown = (e: Event): void => {
    if (!menu.contains(e.target as Node) && e.target !== anchorEl && !anchorEl?.contains(e.target as Node)) close(false);
  };
  const onScroll = (e: Event): void => {
    if (!menu.contains(e.target as Node)) close(false);
  };
  const onResize = (): void => close(false);
  function close(restore: boolean): void {
    if (closed) return;
    closed = true;
    menu.remove();
    document.removeEventListener('pointerdown', onDocDown, true);
    document.removeEventListener('scroll', onScroll, true);
    window.removeEventListener('resize', onResize);
    anchorEl?.setAttribute('aria-expanded', 'false');
    if (current?.close === close) current = null;
    if (restore) (o.returnFocus ?? anchorEl)?.focus();
    o.onClose?.();
  }
  current = { close };
  document.addEventListener('pointerdown', onDocDown, true);
  document.addEventListener('scroll', onScroll, true);
  window.addEventListener('resize', onResize);

  menu.addEventListener('keydown', (e) => {
    const bs = buttons();
    const i = bs.indexOf(document.activeElement as HTMLButtonElement);
    let handled = true;
    switch (e.key) {
      case 'ArrowDown':
        focusAt(i + 1);
        break;
      case 'ArrowUp':
        focusAt(i < 0 ? -1 : i - 1);
        break;
      case 'Home':
        focusAt(0);
        break;
      case 'End':
        focusAt(-1);
        break;
      case 'Escape':
        close(true);
        break;
      case 'Tab':
        close(true);
        break;
      case 'Enter':
      case ' ':
        handled = false; // native button activation
        break;
      default:
        handled = false;
    }
    if (handled) {
      e.preventDefault();
    }
    // Keep viewer shortcuts (arrows orbit, Escape clears the selection) away from the menu.
    e.stopPropagation();
  });
  menu.addEventListener('click', (e) => {
    const b = (e.target as HTMLElement).closest<HTMLButtonElement>('button[data-act]');
    if (!b || b.disabled) return;
    const it = o.items.find((x) => x.act === b.dataset['act']);
    if (!it) return;
    if (it.confirm && !b.classList.contains('armed')) {
      b.classList.add('armed');
      b.textContent = it.confirm;
      b.focus();
      return;
    }
    close(true);
    o.onPick(it.act);
  });
  focusAt(0);
  return menu;
}
