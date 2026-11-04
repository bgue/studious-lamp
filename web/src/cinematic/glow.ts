// Edge glow scope: which elements get the glowing outline (plugins/cinematic.ts applyGlow, renderer.setEdgeGlow).
//   focus  the focus set (the selection, or the focus classes)
//   near   focus + host + near buckets
//   all    every element that is not hidden (the edge shader skips hidden elements on its own)

import type { Classification } from '../types';

export const GLOW_SCOPES = ['focus', 'near', 'all'] as const;
export type GlowScope = (typeof GLOW_SCOPES)[number];
export const DEFAULT_GLOW_SCOPE: GlowScope = 'focus';

export function isGlowScope(v: unknown): v is GlowScope {
  return typeof v === 'string' && (GLOW_SCOPES as readonly string[]).includes(v);
}

/** The old `glowNear` switch: true glowed host + near, false host only. The nearest scopes are 'near' and 'focus'. */
export function glowScopeFromLegacy(glowNear: boolean): GlowScope {
  return glowNear ? 'near' : 'focus';
}

/** Element ids that glow for a scope. `count` is the element count of the model, `hidden` the ids the user hid. */
export function glowIds(scope: GlowScope, cls: Classification, count: number, hidden?: ReadonlySet<number>): Set<number> {
  const out = new Set<number>(cls.focus);
  if (scope === 'near') {
    for (const id of cls.host) out.add(id);
    for (const id of cls.near) out.add(id);
  } else if (scope === 'all') {
    for (let id = 0; id < count; id++) out.add(id);
  }
  if (hidden) for (const id of hidden) out.delete(id);
  return out;
}
