// Which tools the toolbar shows, and in what order. Pure (no DOM), so it is tested directly.

import type { ViewerApp } from '../app';
import type { XrayBoot, XrayTool } from './registry';

/**
 * The visible tools. Without `boot.tools`: every registered tool that is available, sorted by `order` then id (the
 * registry's order). With `boot.tools` (a packaged viewer): exactly those ids, in that order, skipping ids that are
 * not registered or not available here and repeated ids.
 */
export function visibleTools(all: readonly XrayTool[], boot: Pick<XrayBoot, 'tools'>, app?: ViewerApp): XrayTool[] {
  const ok = (t: XrayTool): boolean => {
    try {
      return !t.available || !app || t.available(app) !== false;
    } catch {
      return false;
    }
  };
  if (Array.isArray(boot.tools)) {
    const byId = new Map(all.map((t) => [t.id, t]));
    const seen = new Set<string>();
    const out: XrayTool[] = [];
    for (const id of boot.tools) {
      const t = byId.get(id);
      if (!t || seen.has(id) || !ok(t)) continue;
      seen.add(id);
      out.push(t);
    }
    return out;
  }
  return all.filter(ok);
}

/** Clamp a drawer width the user dragged to. */
export function clampDrawerWidth(w: number, viewport: number): number {
  const max = Math.max(280, Math.min(900, viewport - 80));
  return Math.round(Math.min(max, Math.max(280, w)));
}
