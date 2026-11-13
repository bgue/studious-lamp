// Keep a full-area view (the sheet viewer, the placement view) clear of the chrome over the canvas edges: the tool strip and drawer,
// the rails of a phone, the top and status bars. DOM only.

/** What lies over the edges of the canvas (as in src/ui/overlay.ts). */
export const EDGE_CHROME = ['#xray-toolbar', '#xray-toolbar-drawer', '#sidebar', '#dock', '#xray-overlay', '#xray-topbar'];

/** Set the insets of `root` (an absolutely positioned view in the canvas area) so that it does not lie under the edge chrome. */
export function fitToChrome(root: HTMLElement, chrome: readonly string[] = EDGE_CHROME): void {
  const host = root.offsetParent as HTMLElement | null;
  if (!host) return;
  const c = host.getBoundingClientRect();
  const ins = { top: 0, right: 0, bottom: 0, left: 0 };
  for (const sel of chrome) {
    const e = document.querySelector(sel);
    if (!(e instanceof HTMLElement) || e.hidden || e.getClientRects().length === 0 || e === root) continue;
    const r = e.getBoundingClientRect();
    if (!r.width || !r.height || r.right <= c.left || r.left >= c.right || r.bottom <= c.top || r.top >= c.bottom) continue;
    if (r.height >= c.height * 0.6) {
      if (r.left - c.left < c.right - r.right) ins.left = Math.max(ins.left, r.right - c.left);
      else ins.right = Math.max(ins.right, c.right - r.left);
    } else if (r.bottom >= c.bottom - 1) ins.bottom = Math.max(ins.bottom, c.bottom - r.top);
    else if (r.top <= c.top + 1) ins.top = Math.max(ins.top, r.bottom - c.top);
  }
  const st = root.style;
  const set = (k: 'left' | 'right' | 'top' | 'bottom', v: number): void => { const t = `${Math.round(v)}px`; if (st[k] !== t) st[k] = t; };
  set('left', ins.left);
  set('right', ins.right);
  set('top', ins.top);
  set('bottom', ins.bottom);
}
