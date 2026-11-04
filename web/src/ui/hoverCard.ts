// Hover card: the compact tooltip near the pointer (plugins/hoverInfo.ts drives it).
// The first half is pure (glob filter, row choice, positioning, text) and unit-tested without a DOM;
// the second half is the DOM element.

import type { PropValue } from '../model/ifcProps';

export type { PropValue };

export const DEFAULT_PROPERTY_FILTER =
  'Attr.ObjectType, *.IsExternal, *.LoadBearing, *.FireRating, *.Reference, Qto*.Length, Qto*.Width, Qto*.Height, Qto*.NetVolume';

// ---------------------------------------------------------------- property filter (pure)

/** Comma-separated glob patterns -> trimmed non-empty list. `*` matches any run of characters, `?` one character. */
export function parsePatterns(text: string): string[] {
  return text.split(',').map((s) => s.trim()).filter((s) => s.length > 0);
}

const reCache = new Map<string, RegExp>();

/** Case-insensitive glob (`*`, `?`) over the whole key. */
export function globToRegExp(glob: string): RegExp {
  let re = reCache.get(glob);
  if (!re) {
    const src = glob.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*').replace(/\?/g, '.');
    re = new RegExp(`^${src}$`, 'i');
    if (reCache.size > 200) reCache.clear();
    reCache.set(glob, re);
  }
  return re;
}

export function matchesGlob(key: string, glob: string): boolean {
  return globToRegExp(glob).test(key);
}

/**
 * Properties to show, in priority order: for each pattern in turn, the keys it matches (in the element's own order)
 * that no earlier pattern took. With no patterns every property qualifies in its own order. Capped at `max`.
 */
export function selectRows(props: Readonly<Record<string, PropValue>> | undefined, patterns: readonly string[], max = Infinity): Array<[string, PropValue]> {
  if (!props) return [];
  const entries = Object.entries(props);
  if (patterns.length === 0) return entries.slice(0, max);
  const out: Array<[string, PropValue]> = [];
  const taken = new Set<string>();
  for (const pat of patterns) {
    const re = globToRegExp(pat);
    for (const [k, v] of entries) {
      if (out.length >= max) return out;
      if (taken.has(k) || !re.test(k)) continue;
      taken.add(k);
      out.push([k, v]);
    }
  }
  return out;
}

/**
 * Rows for the card: the filter's rows; when the filter keeps nothing of this element (a file whose sets are named
 * differently, e.g. `BaseQuantities` instead of `Qto_*BaseQuantities`), the first `max` properties in their own order.
 */
export function cardRows(props: Readonly<Record<string, PropValue>> | undefined, patterns: readonly string[], max: number): Array<[string, PropValue]> {
  const rows = selectRows(props, patterns, max);
  return rows.length > 0 || max <= 0 ? rows : selectRows(props, [], max);
}

/** `Pset_WallCommon.IsExternal` -> `IsExternal`; keys without a dot stay whole. */
export function propLabel(key: string): string {
  const i = key.indexOf('.');
  return i < 0 ? key : key.slice(i + 1);
}

export function formatValue(v: PropValue): string {
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  return String(v);
}

// ---------------------------------------------------------------- positioning (pure)

export interface Size { w: number; h: number }
export interface Point { x: number; y: number }

/**
 * Top-left of a card of `size` for a pointer at `p` in a `view`-sized viewport. Default: right of and below the pointer,
 * `offset` px away. Flips to the left when it would run off the right edge, above when it would run off the bottom, then
 * clamps to `margin` from every edge. The card keeps clear of the pointer whenever the viewport allows it.
 */
export function placeCard(p: Point, size: Size, view: Size, offset = 16, margin = 6): Point {
  let left = p.x + offset;
  if (left + size.w > view.w - margin) {
    const flipped = p.x - offset - size.w;
    // keep the flip only when the left side has room, else take whichever side has more
    left = flipped >= margin || p.x > view.w - p.x ? flipped : left;
  }
  let top = p.y + offset;
  if (top + size.h > view.h - margin) {
    const flipped = p.y - offset - size.h;
    top = flipped >= margin || p.y > view.h - p.y ? flipped : top;
  }
  left = Math.max(margin, Math.min(left, view.w - margin - size.w));
  top = Math.max(margin, Math.min(top, view.h - margin - size.h));
  // A clamp can push the card back under the pointer in a very small viewport: move it above/below instead.
  if (p.x >= left && p.x <= left + size.w && p.y >= top && p.y <= top + size.h) {
    const below = p.y + offset;
    const above = p.y - offset - size.h;
    top = below + size.h <= view.h - margin ? below : Math.max(margin, above);
  }
  return { x: left, y: top };
}

// ---------------------------------------------------------------- content (pure)

export interface CardContent {
  title: string;
  subtitle: string;
  rows: Array<[string, PropValue]>;
  footer: string;
}

/** The `class · storey · material` line (missing parts left out). */
export function subtitleOf(ifcClass: string, storey?: string, material?: string): string {
  return [ifcClass, storey, material].filter((s): s is string => !!s && s.trim() !== '').join(' · ');
}

/** Plain-text version of a card (what the copy button puts on the clipboard). */
export function contentToText(c: CardContent): string {
  const lines = [c.title, c.subtitle];
  for (const [k, v] of c.rows) lines.push(`${k}: ${formatValue(v)}`);
  if (c.footer) lines.push(c.footer);
  return lines.filter((l) => l !== '').join('\n');
}

// ---------------------------------------------------------------- DOM

const STYLE_ID = 'xray-hover-card-style';

function ensureStyle(): void {
  if (document.getElementById(STYLE_ID)) return;
  const st = document.createElement('style');
  st.id = STYLE_ID;
  st.textContent = `
    .hc { position: fixed; left: 0; top: 0; z-index: 40; max-width: 300px; min-width: 120px; box-sizing: border-box; padding: 6px 8px 7px;
      background: var(--sb-bg, #151a22); color: var(--sb-fg, #dfe6ee); border: 1px solid var(--sb-line, #2d3748); border-radius: 5px;
      font: 12px/1.35 system-ui, -apple-system, 'Segoe UI', sans-serif; box-shadow: 0 4px 14px rgba(0,0,0,0.45);
      pointer-events: none; user-select: none; display: none; }
    .hc.frozen { pointer-events: auto; user-select: text; border-color: var(--sb-accent, #4c9aff); }
    .hc-title { font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding-right: 0; }
    .hc.frozen .hc-title { padding-right: 46px; }
    .hc-sub { color: var(--sb-dim, #8b9bb0); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-bottom: 3px; }
    .hc-rows { display: grid; grid-template-columns: auto 1fr; gap: 1px 8px; margin: 3px 0 0; padding-top: 3px; border-top: 1px solid var(--sb-line, #2d3748); }
    .hc-rows dt { color: var(--sb-dim, #8b9bb0); white-space: nowrap; max-width: 130px; overflow: hidden; text-overflow: ellipsis; }
    .hc-rows dd { margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-variant-numeric: tabular-nums; }
    .hc-foot { margin-top: 4px; color: var(--sb-dim, #8b9bb0); font-size: 11px; opacity: 0.85; }
    .hc-copy { display: none; position: absolute; right: 6px; top: 5px; height: 18px; padding: 0 6px; font: inherit; font-size: 11px; color: inherit;
      background: #1b2230; border: 1px solid #2d3748; border-radius: 3px; cursor: pointer; }
    .hc-copy:hover { background: #243049; }
    .hc.frozen .hc-copy { display: block; }
    .hc-toast { position: fixed; left: 50%; bottom: 36px; transform: translateX(-50%); z-index: 41; padding: 5px 12px; border-radius: 4px; pointer-events: none;
      background: rgba(21,26,34,0.94); color: #dfe6ee; border: 1px solid #2d3748; font: 12px system-ui, sans-serif; opacity: 0; transition: opacity 0.15s; }
    .hc-toast.on { opacity: 1; }
  `;
  document.head.appendChild(st);
}

export class HoverCard {
  readonly root: HTMLDivElement;
  private readonly titleEl: HTMLDivElement;
  private readonly subEl: HTMLDivElement;
  private readonly rowsEl: HTMLDListElement;
  private readonly footEl: HTMLDivElement;
  private readonly copyBtn: HTMLButtonElement;
  private content: CardContent | null = null;
  private shown = false;
  private frozenFlag = false;
  private toastEl: HTMLDivElement | null = null;
  private toastTimer: ReturnType<typeof setTimeout> | null = null;
  private copyTimer: ReturnType<typeof setTimeout> | null = null;
  /** Called by the copy button with the plain text; returns whether the copy worked. */
  onCopy: ((text: string) => Promise<boolean>) | null = null;

  constructor() {
    ensureStyle();
    const mk = <K extends keyof HTMLElementTagNameMap>(tag: K, cls: string): HTMLElementTagNameMap[K] => {
      const e = document.createElement(tag);
      e.className = cls;
      return e;
    };
    this.root = mk('div', 'hc');
    this.root.setAttribute('role', 'tooltip');
    this.root.id = 'xray-hover-card';
    this.titleEl = mk('div', 'hc-title');
    this.subEl = mk('div', 'hc-sub');
    this.rowsEl = mk('dl', 'hc-rows');
    this.footEl = mk('div', 'hc-foot');
    this.copyBtn = mk('button', 'hc-copy');
    this.copyBtn.type = 'button';
    this.copyBtn.textContent = 'Copy';
    this.copyBtn.title = 'Copy all rows as text';
    this.copyBtn.addEventListener('click', async () => {
      if (!this.content || !this.onCopy) return;
      const ok = await this.onCopy(contentToText(this.content));
      this.copyBtn.textContent = ok ? 'Copied' : 'Failed';
      if (this.copyTimer) clearTimeout(this.copyTimer);
      this.copyTimer = setTimeout(() => (this.copyBtn.textContent = 'Copy'), 1200);
    });
    this.root.append(this.titleEl, this.copyBtn, this.subEl, this.rowsEl, this.footEl);
    document.body.appendChild(this.root);
  }

  get visible(): boolean {
    return this.shown;
  }

  get frozen(): boolean {
    return this.frozenFlag;
  }

  get rect(): DOMRect {
    return this.root.getBoundingClientRect();
  }

  /** Fill the card; the caller positions it with `moveTo`. */
  setContent(c: CardContent): void {
    this.content = c;
    this.titleEl.textContent = c.title;
    this.titleEl.title = c.title;
    this.subEl.textContent = c.subtitle;
    this.subEl.style.display = c.subtitle ? '' : 'none';
    this.rowsEl.textContent = '';
    for (const [k, v] of c.rows) {
      const dt = document.createElement('dt');
      dt.textContent = propLabel(k);
      dt.title = k;
      const dd = document.createElement('dd');
      dd.textContent = formatValue(v);
      dd.title = formatValue(v);
      this.rowsEl.append(dt, dd);
    }
    this.rowsEl.style.display = c.rows.length ? '' : 'none';
    this.setFooter(c.footer);
  }

  setFooter(text: string): void {
    if (this.content) this.content.footer = text;
    if (this.footEl.textContent !== text) this.footEl.textContent = text;
    this.footEl.style.display = text ? '' : 'none';
  }

  show(): void {
    this.shown = true;
    this.root.style.display = 'block';
  }

  hide(): void {
    this.shown = false;
    this.setFrozen(false);
    this.root.style.display = 'none';
  }

  setFrozen(on: boolean): void {
    this.frozenFlag = on;
    this.root.classList.toggle('frozen', on);
  }

  moveTo(p: Point, view: Size): void {
    const size = { w: this.root.offsetWidth, h: this.root.offsetHeight };
    const at = placeCard(p, size, view);
    this.root.style.transform = `translate(${Math.round(at.x)}px, ${Math.round(at.y)}px)`;
  }

  /** Short message at the bottom of the screen. */
  toast(text: string, ms = 1300): void {
    if (!this.toastEl) {
      this.toastEl = document.createElement('div');
      this.toastEl.className = 'hc-toast';
      this.toastEl.setAttribute('role', 'status');
      document.body.appendChild(this.toastEl);
    }
    this.toastEl.textContent = text;
    this.toastEl.classList.add('on');
    if (this.toastTimer) clearTimeout(this.toastTimer);
    this.toastTimer = setTimeout(() => this.toastEl?.classList.remove('on'), ms);
  }

  dispose(): void {
    this.root.remove();
    this.toastEl?.remove();
  }
}
