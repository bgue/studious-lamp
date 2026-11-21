// Review of the links between activities and elements (no DOM): accept or reject a suggestion, keep the decisions across a new linking run,
// read and write the links as a LinkML `LinkDataset` (the dataset of the mapping export, now with schedule, activities and links).
// The linker (src/schedule/link.ts) keeps accepted prior links and never suggests again for an activity whose link was rejected, so the
// decisions go back in as `priorLinks`. Tested in tests/map4d-link-review.test.ts.

import type { ActivityLink, FourDLinks, LinkSource, ReviewStatus } from '../schedule/types';

/** Link sources that the linker makes again from the configuration on every run: a run does not keep them as decisions. */
const SOURCES_OF_RULES: readonly LinkSource[] = ['attributes', 'override', 'property', 'native'];

export interface LinkCounts { accepted: number; proposed: number; rejected: number; superseded: number }

export function countLinks(links: FourDLinks | null): LinkCounts {
  const n: LinkCounts = { accepted: 0, proposed: 0, rejected: 0, superseded: 0 };
  for (const l of links?.links ?? []) n[l.status ?? 'proposed']++;
  return n;
}

/** The links that wait for a decision (status proposed), best confidence first. */
export function proposedLinks(links: FourDLinks | null): ActivityLink[] {
  return (links?.links ?? []).filter((l) => (l.status ?? 'proposed') === 'proposed').sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0) || a.activity.localeCompare(b.activity));
}

/** Accepted links, rejected links and everything else, for the list that shows them. */
export function linksWithStatus(links: FourDLinks | null, status: ReviewStatus): ActivityLink[] {
  return (links?.links ?? []).filter((l) => (l.status ?? 'proposed') === status);
}

/** Change the status of one link. Returns a new dataset; the same dataset when the id is unknown or nothing changes. `by` is stored as reviewed_by only when given. */
export function decideLink(links: FourDLinks, id: string, status: ReviewStatus, now: string = new Date().toISOString(), by?: string): FourDLinks {
  const list = links.links ?? [];
  const i = list.findIndex((l) => l.id === id);
  if (i < 0 || list[i]!.status === status) return links;
  const next: ActivityLink = { ...list[i]!, status, reviewed_at: now };
  if (by) next.reviewed_by = by;
  const copy = list.slice();
  copy[i] = next;
  return { ...links, links: copy };
}

/**
 * The decisions a new linking run keeps: accepted links that no rule would make again (suggestions that were accepted, manual and agent links) and rejected links (so the activity gets no new suggestion). Links made by the attribute rules and the overrides are
 * left out: the run makes them again from the configuration, which may have changed.
 */
export function decisionLinks(links: FourDLinks | null): ActivityLink[] {
  const out: ActivityLink[] = [];
  for (const l of links?.links ?? []) {
    const s = l.status ?? 'proposed';
    if (s === 'rejected') out.push({ ...l });
    else if (s === 'accepted' && !SOURCES_OF_RULES.includes(l.source as LinkSource)) out.push({ ...l });
  }
  return out;
}

export interface ParsedLinks { dataset: FourDLinks | null; problems: string[] }

const STATUS: readonly string[] = ['proposed', 'accepted', 'rejected', 'superseded'];
const ROLE: readonly string[] = ['build', 'remove'];

/** Read a LinkDataset with links (text or object). A row that is not a link is left out and listed. */
export function parseLinks(input: unknown): ParsedLinks {
  let v: unknown = input;
  if (typeof input === 'string') {
    try { v = JSON.parse(input); } catch (e) { return { dataset: null, problems: [`Not JSON: ${e instanceof Error ? e.message : String(e)}`] }; }
  }
  if (!v || typeof v !== 'object' || Array.isArray(v)) return { dataset: null, problems: ['Not a LinkDataset: expected an object.'] };
  const d = v as Record<string, unknown>;
  if (!d.model || typeof d.model !== 'object') return { dataset: null, problems: ['Not a LinkDataset: "model" is missing.'] };
  if (d.links !== undefined && !Array.isArray(d.links)) return { dataset: null, problems: ['"links" is not a list.'] };
  const problems: string[] = [];
  const links: ActivityLink[] = [];
  ((d.links as unknown[] | undefined) ?? []).forEach((r, n) => {
    const bad = (why: string): void => { problems.push(`links[${n}]: ${why}`); };
    if (!r || typeof r !== 'object') return bad('not an object');
    const o = r as Record<string, unknown>;
    if (typeof o.id !== 'string' || !o.id) return bad('no id');
    if (typeof o.activity !== 'string' || !o.activity) return bad('no activity');
    if (!ROLE.includes(o.role as string)) return bad(`role ${String(o.role)} is not build or remove`);
    if (!Array.isArray(o.elements) || o.elements.some((e) => typeof e !== 'string')) return bad('elements is not a list of GlobalIds');
    if (o.status != null && !STATUS.includes(o.status as string)) return bad(`unknown status ${String(o.status)}`);
    links.push({ ...(o as unknown as ActivityLink), status: (o.status as ReviewStatus | undefined) ?? 'proposed' });
  });
  return { dataset: { ...(d as unknown as FourDLinks), links }, problems };
}

/** The dataset as a file: reviewer names are left out unless asked for. */
export function serializeLinks(links: FourDLinks, includeReviewers = false): string {
  const out: FourDLinks = includeReviewers ? links : {
    ...links,
    links: links.links?.map((l) => { const { reviewed_by: _drop, ...rest } = l; return rest; }),
    assignments: links.assignments?.map((a) => { const { reviewed_by: _drop, ...rest } = a; return rest; }),
  };
  return JSON.stringify(out, null, 2) + '\n';
}
