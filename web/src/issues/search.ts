// Search index of issues and sketches for the top-bar search: title, note or description, and comment text. Pure.
// Tested in tests/issues-search.test.ts.

import type { BcfTopic } from '../bcf/model';
import type { MarkupSet } from '../markup/model';

export type IssueHitField = 'title' | 'description' | 'note' | 'comment';

export interface IssueHit {
  kind: 'issue' | 'sketch';
  /** Topic guid or sketch id. */
  id: string;
  title: string;
  /** One line under the title: what it is, its status, and where the text matched. */
  sub: string;
  field: IssueHitField;
  /** Character positions of the match in the title (for highlighting), empty when the title did not match. */
  positions: number[];
  /** 0 to 100. */
  score: number;
}

const FIELD_SCORE: Record<IssueHitField, number> = { title: 90, note: 60, description: 60, comment: 40 };

function terms(q: string): string[] {
  return q.toLowerCase().split(/\s+/).filter(Boolean);
}

function hasAll(text: string, ts: readonly string[]): boolean {
  const t = text.toLowerCase();
  return ts.every((x) => t.includes(x));
}

function positionsOf(text: string, ts: readonly string[]): number[] {
  const t = text.toLowerCase();
  const out = new Set<number>();
  for (const x of ts) {
    const i = t.indexOf(x);
    if (i >= 0) for (let k = 0; k < x.length; k++) out.add(i + k);
  }
  return [...out].sort((a, b) => a - b);
}

function snippet(text: string, ts: readonly string[]): string {
  const flat = text.replace(/\s+/g, ' ').trim();
  const i = flat.toLowerCase().indexOf(ts[0] ?? '');
  const from = Math.max(0, i - 20);
  const cut = flat.slice(from, from + 70);
  return `${from > 0 ? '…' : ''}${cut}${from + 70 < flat.length ? '…' : ''}`;
}

export interface IssueSearchInput {
  topics: readonly BcfTopic[];
  sets: readonly MarkupSet[];
}

/**
 * Issues and sketches whose title, note, description or comment text holds every word of the query (case does not matter).
 * Best first: a title hit before a note or description hit before a comment hit.
 */
export function searchIssues(input: IssueSearchInput, query: string, limit = 50): IssueHit[] {
  const ts = terms(query);
  if (!ts.length) return [];
  const out: IssueHit[] = [];
  for (const t of input.topics) {
    const parts: Array<[IssueHitField, string]> = [['title', t.title], ['description', t.description ?? ''], ...t.comments.map((c): [IssueHitField, string] => ['comment', c.text])];
    // Words may spread over fields: title plus description counts as a title hit.
    const joined = parts.map((p) => p[1]).join(' ');
    if (!hasAll(joined, ts)) continue;
    const hit = parts.find(([, text]) => text && hasAll(text, ts));
    const field: IssueHitField = hit ? hit[0] : 'title';
    const text = hit ? hit[1] : t.title;
    const meta = [t.topicStatus, t.priority].filter(Boolean).join(', ');
    out.push({
      kind: 'issue', id: t.guid, title: t.title, field, positions: positionsOf(t.title, ts), score: FIELD_SCORE[field],
      sub: `Issue${meta ? `, ${meta}` : ''}${field === 'title' ? '' : `: ${field} "${snippet(text, ts)}"`}`,
    });
  }
  for (const s of input.sets) {
    const legacy = s.markups.flatMap((m) => m.comments.map((c) => c.text));
    const parts: Array<[IssueHitField, string]> = [['title', s.title], ['note', s.note ?? ''], ...legacy.map((x): [IssueHitField, string] => ['comment', x])];
    const joined = parts.map((p) => p[1]).join(' ');
    if (!hasAll(joined, ts)) continue;
    const hit = parts.find(([, text]) => text && hasAll(text, ts));
    const field: IssueHitField = hit ? hit[0] : 'title';
    const text = hit ? hit[1] : s.title;
    out.push({
      kind: 'sketch', id: s.id, title: s.title, field, positions: positionsOf(s.title, ts), score: Math.max(1, FIELD_SCORE[field] - 5),
      sub: `Sketch, ${s.markups.length} drawing${s.markups.length === 1 ? '' : 's'}${field === 'title' ? '' : `: ${field} "${snippet(text, ts)}"`}`,
    });
  }
  out.sort((a, b) => b.score - a.score || a.title.localeCompare(b.title));
  return out.slice(0, limit);
}
