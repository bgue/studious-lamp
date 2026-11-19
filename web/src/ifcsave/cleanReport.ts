// The words of the cleaned-copy report (design 2.3): what went, what was kept and marked, and why. Pure, so tests can read it.

import type { CleanReport } from './clean';

export interface KeptGroup {
  /** The reason as the worker gave it, with the line number of a referrer left out (`referenced by IFCFOO`). */
  key: string;
  /** Plain statement of the reason. */
  why: string;
  count: number;
  /** Express ids, at most `examples` of them. */
  ids: number[];
}

/** `referenced by #123 IFCFOO` -> `referenced by IFCFOO`: one group per referrer class. */
const keyOf = (because: string): string => because.replace(/^referenced by #\d+ /, 'referenced by ');

export function whyKept(key: string): string {
  if (key === 'has parts') return 'It is an assembly and some of its parts stay. Removing it would leave them without a whole.';
  if (key === 'hosts a door or window') return 'A door or window that stays stands in one of its openings. Removing it would leave the door or window in no wall.';
  if (key.startsWith('referenced by ')) return `Something other than a relationship refers to it (${key.slice('referenced by '.length)}). It would be left pointing at nothing.`;
  if (key.startsWith('part of the spatial')) return 'It belongs to the spatial structure of the project.';
  return key;
}

export function keptGroups(reports: readonly CleanReport[], examples = 5): KeptGroup[] {
  const by = new Map<string, KeptGroup>();
  for (const r of reports)
    for (const k of r.kept) {
      const key = keyOf(k.because);
      let g = by.get(key);
      if (!g) by.set(key, (g = { key, why: whyKept(key), count: 0, ids: [] }));
      g.count++;
      if (g.ids.length < examples) g.ids.push(k.expressId);
    }
  return [...by.values()].sort((a, b) => b.count - a.count || a.key.localeCompare(b.key));
}

export interface CleanTotals {
  asked: number;
  removed: number;
  cascaded: number;
  kept: number;
  linesDeleted: number;
  relationsTrimmed: number;
  relationsDeleted: number;
  fillsCut: number;
  swept: number;
  missing: number;
}

export function totals(reports: readonly CleanReport[]): CleanTotals {
  const t: CleanTotals = { asked: 0, removed: 0, cascaded: 0, kept: 0, linesDeleted: 0, relationsTrimmed: 0, relationsDeleted: 0, fillsCut: 0, swept: 0, missing: 0 };
  for (const r of reports) {
    t.asked += r.asked;
    t.removed += r.removed;
    t.cascaded += r.cascaded;
    t.kept += r.kept.length;
    t.linesDeleted += r.stats.linesDeleted;
    t.relationsTrimmed += r.stats.relationsTrimmed;
    t.relationsDeleted += r.stats.relationsDeleted;
    t.fillsCut += r.stats.fillsCut;
    t.swept += r.stats.swept;
    t.missing += r.stats.missing;
  }
  return t;
}

/** The risk statement of the design, short form (section 2.3). */
export const RISK_LINES = [
  'Safe: free-standing debris, strays, duplicates and proxies with no relationships, which is most of what cleanup finds.',
  'Kept and marked instead of removed: assemblies whose parts stay, walls that still host a door or window, anything another line refers to.',
  'Accepted loss: neighbours lose their connections (ports, path connections), and an opening can stay without its door or window.',
  'A cleaned copy is a derived file. Your original is not changed.',
] as const;
