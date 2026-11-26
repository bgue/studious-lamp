// What the colour legend of a 4D film says, from the plan alone (pure): the trade colours of the trades that appear in the film and
// the state key (planned, active, built, existing, removed, critical, behind / ahead, temporary works). Used by the HUD legend
// (src/anim/hud/legend.ts) and by the storyboard PDF (src/schedule/storyboard.ts), so both show the same key.

import type { FourDPlan } from '../../schedule/types';
import { AHEAD_RGB, BEHIND_RGB, CRITICAL_RGB, EXISTING_GREY, GLOW_RGB, REMOVED_RGB, toHex, tradeColour } from './look';

export type LegendKind = 'fill' | 'glow' | 'outline' | 'ghost';

export interface LegendEntry {
  label: string;
  colour: string;
  kind: LegendKind;
}

export interface LegendContent {
  /** Trades of the activities that have elements, in order of first start (at most MAX_LEGEND_TRADES). */
  trades: LegendEntry[];
  /** Trades left out of `trades`. */
  moreTrades: number;
  states: LegendEntry[];
}

export const MAX_LEGEND_TRADES = 8;
export const BUILT_COLOUR = '#cfd6df';
export const PLANNED_COLOUR = '#7f8a99';
export const TEMPORARY_COLOUR = '#e0a35a';

/** Temporary works colours, when the plan carries them: `plan.temporary` as one { colour, label? } or a list of them. Never required. */
function temporaryEntries(plan: FourDPlan): LegendEntry[] {
  const raw = (plan as unknown as { temporary?: unknown }).temporary;
  const list = Array.isArray(raw) ? raw : raw && typeof raw === 'object' ? [raw] : [];
  const out: LegendEntry[] = [];
  for (const r of list) {
    if (!r || typeof r !== 'object') continue;
    const o = r as { colour?: unknown; color?: unknown; label?: unknown; name?: unknown };
    const colour = typeof o.colour === 'string' ? o.colour : typeof o.color === 'string' ? o.color : TEMPORARY_COLOUR;
    const label = typeof o.label === 'string' ? o.label : typeof o.name === 'string' ? o.name : 'Temporary works';
    if (!out.some((e) => e.label === label)) out.push({ label, colour, kind: 'fill' });
  }
  return out;
}

export function legendContent(plan: FourDPlan): LegendContent {
  const seen = new Map<string, { colour: string; start: number }>();
  for (const k of plan.tasks) {
    if (k.milestone || k.elements <= 0) continue;
    const key = k.trade ?? 'Work';
    const cur = seen.get(key);
    if (!cur || k.start < cur.start) seen.set(key, { colour: tradeColour(k.trade, plan.style.colours), start: k.start });
  }
  const all = [...seen.entries()].sort((a, b) => a[1].start - b[1].start || a[0].localeCompare(b[0]));
  const trades: LegendEntry[] = all.slice(0, MAX_LEGEND_TRADES).map(([label, v]) => ({ label, colour: v.colour, kind: 'fill' as const }));

  const states = new Set<string>();
  for (const e of plan.elements) for (const iv of e.intervals) states.add(iv.state);
  const hasActual = plan.progress.some((q) => q.actual !== undefined) || states.has('behind') || states.has('ahead') || plan.style.view === 'variance';
  const entries: LegendEntry[] = [];
  if (plan.style.unbuilt === 'ghost') entries.push({ label: 'Planned', colour: PLANNED_COLOUR, kind: 'ghost' });
  entries.push({ label: 'Active', colour: toHex(GLOW_RGB), kind: 'glow' });
  entries.push({ label: 'Built', colour: BUILT_COLOUR, kind: 'fill' });
  if (states.has('existing')) entries.push({ label: 'Existing', colour: toHex(EXISTING_GREY), kind: 'fill' });
  if (states.has('removed')) entries.push({ label: 'Removed', colour: toHex(REMOVED_RGB), kind: 'fill' });
  if (plan.tasks.some((k) => k.critical && !k.milestone)) entries.push({ label: 'Critical', colour: toHex(CRITICAL_RGB), kind: 'outline' });
  if (hasActual) {
    entries.push({ label: 'Behind', colour: toHex(BEHIND_RGB), kind: 'fill' });
    entries.push({ label: 'Ahead', colour: toHex(AHEAD_RGB), kind: 'fill' });
  }
  entries.push(...temporaryEntries(plan));
  return { trades, moreTrades: Math.max(0, all.length - trades.length), states: entries };
}

/** Whether the film shows the legend / the strip (style `legend` and `strip`, default on). */
export const legendOn = (plan: FourDPlan): boolean => plan.style.legend !== 'off';
export const stripOn = (plan: FourDPlan): boolean => plan.style.strip !== 'off';
