// The unified list of views: saved views (src/views/model.ts) and markup sets (src/markup, the drawings) presented as one
// list of entries. Pure: no DOM, no three.js. Tested in tests/views-unified.test.ts. Design: docs/design/views-and-issues.md.
//
// An entry is one of
//   - a saved view; its markup set (`SavedView.drawings`), when there is one, is folded into it;
//   - a loose set that no saved view claims (a legacy sketch, a view made from an opened BCF file, a sheet page):
//     a view built from the set's own capture.

import { viewSummary } from './model';
import type { SavedView } from './model';

/** The filters of the Views tab. `sheets` shows the PDF pages (the sheets pane in the panel). */
export type ViewFilter = 'all' | 'drawings' | 'sheets' | 'issue';
export const VIEW_FILTERS: readonly ViewFilter[] = ['all', 'drawings', 'sheets', 'issue'];
export const VIEW_FILTER_LABEL: Record<ViewFilter, string> = { all: 'All', drawings: 'With drawings', sheets: 'On sheets', issue: 'In an issue' };

export function isViewFilter(v: unknown): v is ViewFilter {
  return typeof v === 'string' && (VIEW_FILTERS as readonly string[]).includes(v);
}

/** The part of a markup set the list needs. */
export interface SetLike {
  id: string;
  title: string;
  note?: string;
  thumb?: string;
  markups: ReadonlyArray<unknown>;
  view: SavedView;
  frame?: { kind: 'sheet'; sheet: string };
}

/** The part of a BCF topic the list needs. */
export interface TopicLike {
  guid: string;
  title: string;
  viewpoints: ReadonlyArray<{ guid: string; sketchId?: string; derived?: unknown }>;
}

export interface EntryIssue {
  topic: string;
  title: string;
  viewpoint: string;
}

export interface ViewEntry {
  /** `v:<saved view id>` or `s:<set id>`. */
  key: string;
  /** The saved view id, or the set id of a loose set. */
  id: string;
  /** The saved view, when there is one. Entries with a view come first and keep its order. */
  viewId?: string;
  /** The markup set that holds the drawings, or that backs the view in an issue. */
  setId?: string;
  name: string;
  note: string;
  thumb?: string;
  summary: string;
  /** Number of drawings on the view. */
  drawings: number;
  hasDrawings: boolean;
  /** A page of a PDF sheet. */
  sheet: boolean;
  /** Built from a sketch alone: no saved view behind it. */
  loose: boolean;
  /** The issue the view is a viewpoint of. */
  issue?: EntryIssue;
}

export interface EntryInput {
  views: readonly SavedView[];
  sets: readonly SetLike[];
  topics: readonly TopicLike[];
}

/** The issue a set is a viewpoint of (the viewpoint's `sketchId` is the truth), or undefined. */
export function issueOfSet(topics: readonly TopicLike[], setId: string): EntryIssue | undefined {
  for (const t of topics) {
    for (const v of t.viewpoints) if (!v.derived && v.sketchId === setId) return { topic: t.guid, title: t.title, viewpoint: v.guid };
  }
  return undefined;
}

/** Merge the saved views and the markup sets of the loaded model into one list. */
export function buildEntries(input: EntryInput): ViewEntry[] {
  const byId = new Map<string, SetLike>();
  for (const s of input.sets) byId.set(s.id, s);
  const claimed = new Set<string>();
  const out: ViewEntry[] = [];
  for (const v of input.views) {
    const s = v.drawings ? byId.get(v.drawings) : undefined;
    const set = s && !claimed.has(s.id) ? s : undefined;
    if (set) claimed.add(set.id);
    const e: ViewEntry = {
      key: `v:${v.id}`,
      id: v.id,
      viewId: v.id,
      name: v.name,
      note: set?.note ?? '',
      summary: viewSummary(v),
      drawings: set ? set.markups.length : 0,
      hasDrawings: !!set && set.markups.length > 0,
      sheet: false,
      loose: false,
    };
    const thumb = v.thumb ?? set?.thumb;
    if (thumb) e.thumb = thumb;
    if (set) {
      e.setId = set.id;
      const issue = issueOfSet(input.topics, set.id);
      if (issue) e.issue = issue;
    }
    out.push(e);
  }
  for (const s of input.sets) {
    if (claimed.has(s.id)) continue;
    const sheet = s.frame?.kind === 'sheet';
    const e: ViewEntry = {
      key: `s:${s.id}`,
      id: s.id,
      setId: s.id,
      name: s.title,
      note: s.note ?? '',
      summary: sheet ? 'sheet page' : viewSummary(s.view),
      drawings: s.markups.length,
      hasDrawings: s.markups.length > 0,
      sheet,
      loose: true,
    };
    if (s.thumb) e.thumb = s.thumb;
    const issue = issueOfSet(input.topics, s.id);
    if (issue) e.issue = issue;
    out.push(e);
  }
  return out;
}

/** The entries that pass a filter and a text (name, note, issue title; every word must match). */
export function filterEntries(entries: readonly ViewEntry[], o: { filter?: ViewFilter; query?: string } = {}): ViewEntry[] {
  const terms = (o.query ?? '').trim().toLowerCase().split(/\s+/).filter(Boolean);
  const f = o.filter ?? 'all';
  return entries.filter((e) => {
    if (f === 'drawings' && !e.hasDrawings) return false;
    if (f === 'sheets' && !e.sheet) return false;
    if (f === 'issue' && !e.issue) return false;
    if (!terms.length) return true;
    const hay = [e.name, e.note, e.issue?.title ?? ''].join(' ').toLowerCase();
    return terms.every((t) => hay.includes(t));
  });
}

/** How many entries each filter shows (for the chips). */
export function filterCounts(entries: readonly ViewEntry[]): Record<ViewFilter, number> {
  return {
    all: entries.length,
    drawings: entries.filter((e) => e.hasDrawings).length,
    sheets: entries.filter((e) => e.sheet).length,
    issue: entries.filter((e) => !!e.issue).length,
  };
}

/** The entry for a key: an entry key, a saved view id, a set id, or a name (the first match). */
export function findEntry(entries: readonly ViewEntry[], key: string): ViewEntry | undefined {
  return (
    entries.find((e) => e.key === key) ??
    entries.find((e) => e.id === key) ??
    entries.find((e) => e.setId === key) ??
    entries.find((e) => e.name === key) ??
    entries.find((e) => e.name.toLowerCase() === key.trim().toLowerCase())
  );
}

/**
 * What "Draw on this view" does for an entry: `edit` (the view has a drawing layer: restore it and show the toolbar), `layer` (a saved
 * view without one: restore it, make the layer from it, then the toolbar) or `current` (nothing is picked: save the current state as a
 * view first).
 */
export function drawPlan(e: ViewEntry | null | undefined): 'edit' | 'layer' | 'current' {
  if (!e) return 'current';
  return e.setId ? 'edit' : 'layer';
}

/** What "Make issue" does: `open` (the view is in an issue already: open it), `choose` (the chooser New issue / Add to a view in the detail). */
export function issuePlan(e: ViewEntry): 'open' | 'choose' {
  return e.issue ? 'open' : 'choose';
}
