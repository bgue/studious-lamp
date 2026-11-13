// Ranking helpers of the search bar for the sources that are lists of labels (presets, saved views, selection sets,
// settings): one fuzzy pass over the label, a weaker pass over the extra text. Pure, no DOM.

import { fuzzyScore } from './fuzzy';

export type SectionId = 'recent' | 'query' | 'elements' | 'commands' | 'presets' | 'views' | 'sets' | 'issues' | 'settings';

export const SECTION_TITLES: Record<SectionId, string> = {
  recent: 'Recent',
  query: 'Query',
  elements: 'Elements',
  commands: 'Commands',
  presets: 'Presets',
  views: 'Saved views',
  sets: 'Selection sets',
  issues: 'Issues and sketches',
  settings: 'Settings',
};

/** Tie order of the sections when their best scores are equal. */
export const SECTION_ORDER: readonly SectionId[] = ['query', 'elements', 'commands', 'presets', 'views', 'sets', 'issues', 'settings'];

export interface Ranked<T> {
  item: T;
  /** 0 to 100. */
  score: number;
  positions: number[];
}

export interface Labeled {
  label: string;
  /** Weaker text: folder path, description, help intent. */
  extra?: string;
}

/** Fuzzy scores scale up to about 140 for an exact label; the bar compares sections on 0 to 100. */
export const normalizeFuzzy = (s: number): number => Math.max(1, Math.min(100, s / 1.4));

/** Rank items by label (positions come from the label), then by the extra text at a discount. Best first, label order on ties. */
export function rankByText<T>(items: readonly T[], query: string, text: (item: T) => Labeled, limit = 200): Ranked<T>[] {
  const q = query.trim();
  const out: Ranked<T>[] = [];
  for (const item of items) {
    const { label, extra } = text(item);
    if (!q) {
      out.push({ item, score: 1, positions: [] });
      continue;
    }
    const a = fuzzyScore(q, label);
    const b = extra ? fuzzyScore(q, extra) : null;
    if (!a && !b) continue;
    const sa = a ? normalizeFuzzy(a.score) : -1;
    const sb = b ? normalizeFuzzy(b.score) * 0.5 : -1;
    out.push({ item, score: Math.max(sa, sb), positions: a ? a.positions : [] });
  }
  out.sort((x, y) => y.score - x.score || text(x.item).label.localeCompare(text(y.item).label));
  return out.slice(0, limit);
}

export interface GroupLike {
  section: SectionId;
  rows: Array<{ score: number }>;
}

/** Order the groups by their best row, the tie order of SECTION_ORDER on equal scores. Empty groups go. */
export function orderGroups<G extends GroupLike>(groups: readonly G[]): G[] {
  const best = (g: G): number => g.rows.reduce((m, r) => Math.max(m, r.score), -1);
  return groups
    .filter((g) => g.rows.length > 0)
    .sort((a, b) => best(b) - best(a) || SECTION_ORDER.indexOf(a.section) - SECTION_ORDER.indexOf(b.section));
}

/** How many rows a section shows before "N more…". */
export const SECTION_CAP: Record<SectionId, number> = { recent: 8, query: 1, elements: 50, commands: 8, presets: 5, views: 5, sets: 5, issues: 6, settings: 8 };
/** How many rows an expanded section shows. */
export const EXPANDED_CAP = 200;
