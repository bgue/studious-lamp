// Focus regions (F6 / Shift+F6): the 3D canvas, the left sidebar, the right sidebar and the top bar.
// `nextRegion` is pure; `focusRegion` and `currentRegion` touch the DOM. Docs: docs-features/keyboard.md (Focus rules).

export type RegionId = 'canvas' | 'left' | 'right' | 'top';
export const REGION_ORDER: readonly RegionId[] = ['canvas', 'left', 'right', 'top'];

/** The region F6 (dir 1) or Shift+F6 (dir -1) goes to from `current`, skipping regions that are not available. */
export function nextRegion(current: RegionId, dir: 1 | -1, available: (r: RegionId) => boolean): RegionId {
  const n = REGION_ORDER.length;
  const at = Math.max(0, REGION_ORDER.indexOf(current));
  for (let k = 1; k <= n; k++) {
    const r = REGION_ORDER[(at + dir * k + n * 2) % n]!;
    if (r === current) break;
    if (available(r)) return r;
  }
  return 'canvas';
}

const FOCUSABLE = 'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex]:not([tabindex="-1"])';

function shown(el: Element | null): el is HTMLElement {
  return !!el && el instanceof HTMLElement && !el.hidden && el.getClientRects().length > 0;
}

function firstFocusable(root: Element): HTMLElement | null {
  for (const c of Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE))) if (shown(c)) return c;
  return null;
}

/** The element to focus inside a visible pane: the list widget (tree, keys-own list) first, else the first control. */
function paneTarget(pane: Element): HTMLElement | null {
  for (const w of Array.from(pane.querySelectorAll<HTMLElement>('[role="tree"], [data-keys-own]'))) {
    if (!shown(w)) continue;
    if (w.tabIndex >= 0) return w;
    const f = firstFocusable(w);
    if (f) return f;
  }
  return firstFocusable(pane);
}

function regionRoot(id: RegionId, canvas: HTMLElement): HTMLElement | null {
  switch (id) {
    case 'canvas':
      return canvas;
    case 'left':
      return document.body.classList.contains('sb-collapsed') ? null : document.getElementById('sidebar');
    case 'right':
      return document.body.classList.contains('dk-collapsed') ? null : document.getElementById('dock');
    case 'top':
      return document.getElementById('xray-topbar');
  }
}

export function regionAvailable(id: RegionId, canvas: HTMLElement): boolean {
  return id === 'canvas' || regionTarget(id, canvas) !== null;
}

/** Where focus goes for a region (null when the region is closed, hidden or has nothing to focus). */
export function regionTarget(id: RegionId, canvas: HTMLElement): HTMLElement | null {
  const root = regionRoot(id, canvas);
  if (!root || !shown(root)) return null;
  switch (id) {
    case 'canvas':
      return canvas;
    case 'left': {
      for (const p of Array.from(root.querySelectorAll<HTMLElement>('.sb-pane'))) if (shown(p)) return paneTarget(p);
      return null;
    }
    case 'right': {
      for (const p of Array.from(root.querySelectorAll<HTMLElement>('.dk-pane'))) if (shown(p)) return paneTarget(p);
      return null;
    }
    case 'top':
      return root.querySelector<HTMLElement>('.tb-mode[aria-pressed="true"]') ?? firstFocusable(root);
  }
}

export function currentRegion(canvas: HTMLElement): RegionId {
  const a = document.activeElement;
  if (!a || a === document.body) return 'canvas';
  for (const id of ['top', 'left', 'right'] as const) {
    const r = id === 'top' ? document.getElementById('xray-topbar') : id === 'left' ? document.getElementById('sidebar') : document.getElementById('dock');
    if (r && r.contains(a)) return id;
  }
  return 'canvas';
}

let ringEl: HTMLElement | null = null;

export function clearRegionRing(): void {
  ringEl?.removeAttribute('data-region-ring');
  ringEl = null;
}

/** Move focus to the next or previous region and show its ring. Returns the region reached. */
export function cycleRegion(canvas: HTMLElement, dir: 1 | -1): RegionId {
  const to = nextRegion(currentRegion(canvas), dir, (r) => regionAvailable(r, canvas));
  const target = regionTarget(to, canvas);
  if (!target) return 'canvas';
  clearRegionRing();
  target.focus({ preventScroll: true });
  const ring = to === 'canvas' ? canvas : regionRoot(to, canvas);
  if (ring) {
    ring.setAttribute('data-region-ring', to);
    ringEl = ring;
  }
  return to;
}

/** Install the listeners that remove the ring again when focus leaves the region or a pointer is used. Call once. */
export function watchRegionRing(): void {
  document.addEventListener('focusout', (e) => {
    if (ringEl && !ringEl.contains((e as FocusEvent).relatedTarget as Node | null)) clearRegionRing();
  });
  document.addEventListener('pointerdown', clearRegionRing, true);
}
