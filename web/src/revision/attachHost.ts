// The adapter between the revision walk and the stores of issues (BCF topics) and sketches (design 3.4, 5.3). Issues and sketches attach to
// elements by GlobalId. The walk needs four things: how many are attached to an element, retarget them when a rematch is accepted,
// flag them when their element was deleted, and resolve them. The reading and rewriting is pure (over the plain topic and sketch shapes,
// tested in node); `attachmentHostOf` joins it to the live controllers. Nothing is ever deleted here.

import type { Attachment } from '../bcf/attach';
import type { BcfTopic } from '../bcf/model';
import { referencedGuids } from '../markup/model';
import type { Markup, MarkupSet } from '../markup/model';
import { stripFederation } from './snapshot';

export interface AttachmentHost {
  countFor(globalId: string): { issues: number; sketches: number };
  /** Rewrite attachments from a base GlobalId to the head GlobalId. Returns how many references changed. */
  retarget(map: ReadonlyMap<string, string>): number;
  /** Add a note to the issues of deleted elements; the issues stay where they are, detached. */
  flagDeleted(globalIds: readonly string[], note: string): number;
  /** Mark the issues of these elements resolved, with a comment. Returns how many issues changed. */
  resolveIssues(globalIds: readonly string[], comment: string): number;
}

const bare = (g: string): string => stripFederation(g);

// ---------------------------------------------------------------- reading

function attachGuidList(a: Attachment | undefined): string[] {
  if (!a) return [];
  const out = [...(a.guids ?? []), ...(a.surface?.guids ?? []), ...(a.measurement?.elementGuids ?? [])];
  if (a.penetration) out.push(a.penetration.mep, a.penetration.host);
  return out;
}

/** Every element GlobalId that a topic refers to: its pin, the selection, hides and colours of its viewpoints, and their annotations. */
export function topicGuids(t: BcfTopic): Set<string> {
  const out = new Set<string>();
  if (t.pin?.elementGuid) out.add(t.pin.elementGuid);
  for (const vp of t.viewpoints) {
    for (const c of vp.data?.selection ?? []) if (c.ifcGuid) out.add(c.ifcGuid);
    for (const c of vp.data?.visibility?.exceptions ?? []) if (c.ifcGuid) out.add(c.ifcGuid);
    for (const col of vp.data?.coloring ?? []) for (const c of col.components) if (c.ifcGuid) out.add(c.ifcGuid);
    for (const a of vp.annotations ?? []) {
      if (a.anchor.elementGuid) out.add(a.anchor.elementGuid);
      for (const g of a.anchor.measurement?.elementGuids ?? []) out.add(g);
      for (const g of attachGuidList(a.attach)) out.add(g);
    }
  }
  return out;
}

export const setGuids = (s: MarkupSet): Set<string> => new Set(referencedGuids(s));

// ---------------------------------------------------------------- rewriting

const rewrite = (g: string | undefined, map: ReadonlyMap<string, string>): string | undefined => (g === undefined ? g : map.get(bare(g)) ?? g);

function retargetAttach(a: Attachment | undefined, map: ReadonlyMap<string, string>): number {
  if (!a) return 0;
  let n = 0;
  const list = (l: string[] | undefined): void => { if (l) l.forEach((g, i) => { const r = rewrite(g, map)!; if (r !== g) { l[i] = r; n++; } }); };
  list(a.guids);
  list(a.surface?.guids);
  list(a.measurement?.elementGuids);
  if (a.penetration) {
    const m = rewrite(a.penetration.mep, map)!, h = rewrite(a.penetration.host, map)!;
    if (m !== a.penetration.mep) { a.penetration.mep = m; n++; }
    if (h !== a.penetration.host) { a.penetration.host = h; n++; }
  }
  return n;
}

function retargetMarkup(m: Markup, map: ReadonlyMap<string, string>): number {
  let n = retargetAttach(m.attach, map);
  if (m.anchor) {
    const r = rewrite(m.anchor.elementGuid, map);
    if (r !== m.anchor.elementGuid) { m.anchor.elementGuid = r!; n++; }
    const el = m.anchor.measurement?.elementGuids;
    if (el) el.forEach((g, i) => { const x = rewrite(g, map)!; if (x !== g) { el[i] = x; n++; } });
  }
  return n;
}

/** Rewrite one sketch's references in place. Returns how many changed. */
export function retargetSet(s: MarkupSet, map: ReadonlyMap<string, string>): number {
  let n = 0;
  const arr = (l: string[] | undefined): void => { if (l) l.forEach((g, i) => { const r = rewrite(g, map)!; if (r !== g) { l[i] = r; n++; } }); };
  arr(s.view.selection);
  arr(s.view.hides?.ids);
  arr(s.view.pins);
  for (const m of s.markups) n += retargetMarkup(m, map);
  return n;
}

/** Rewrite one topic's references in place. Returns how many changed. */
export function retargetTopic(t: BcfTopic, map: ReadonlyMap<string, string>): number {
  let n = 0;
  if (t.pin?.elementGuid) { const r = rewrite(t.pin.elementGuid, map)!; if (r !== t.pin.elementGuid) { t.pin.elementGuid = r; n++; } }
  const comps = (l: Array<{ ifcGuid?: string }>): void => { for (const c of l) if (c.ifcGuid) { const r = rewrite(c.ifcGuid, map)!; if (r !== c.ifcGuid) { c.ifcGuid = r; n++; } } };
  for (const vp of t.viewpoints) {
    comps(vp.data?.selection ?? []);
    comps(vp.data?.visibility?.exceptions ?? []);
    for (const col of vp.data?.coloring ?? []) comps(col.components);
    if (vp.markupSelection) vp.markupSelection = vp.markupSelection.map((g) => { const r = rewrite(g, map)!; if (r !== g) n++; return r; });
    for (const a of vp.annotations ?? []) {
      const r = rewrite(a.anchor.elementGuid, map);
      if (r !== a.anchor.elementGuid) { a.anchor.elementGuid = r!; n++; }
      const el = a.anchor.measurement?.elementGuids;
      if (el) el.forEach((g, i) => { const x = rewrite(g, map)!; if (x !== g) { el[i] = x; n++; } });
      n += retargetAttach(a.attach, map);
    }
  }
  return n;
}

// ---------------------------------------------------------------- over the live controllers

export interface AttachSources {
  /** The topics of the loaded model. */
  topics(): BcfTopic[];
  /** The sketches of the loaded model. */
  sets(): MarkupSet[];
  /** Called after topics or sketches were rewritten, with what changed. */
  touched(o: { topics: BcfTopic[]; sets: MarkupSet[] }): void;
  addComment(topicGuid: string, text: string): void;
  setStatus(topicGuid: string, status: string): void;
}

const RESOLVED = /^(resolved|closed|done|solved|completed|fixed|verified)$/i;

export function attachmentHost(src: AttachSources): AttachmentHost {
  const topicsOf = (ids: ReadonlySet<string>): BcfTopic[] => src.topics().filter((t) => { for (const g of topicGuids(t)) if (ids.has(bare(g))) return true; return false; });
  return {
    countFor(globalId) {
      const id = bare(globalId);
      let issues = 0, sketches = 0;
      for (const t of src.topics()) for (const g of topicGuids(t)) if (bare(g) === id) { issues++; break; }
      for (const s of src.sets()) for (const g of setGuids(s)) if (bare(g) === id) { sketches++; break; }
      return { issues, sketches };
    },
    retarget(map) {
      const m = new Map<string, string>();
      for (const [a, b] of map) if (bare(a) !== bare(b)) m.set(bare(a), bare(b));
      if (m.size === 0) return 0;
      const topics: BcfTopic[] = [], sets: MarkupSet[] = [];
      let n = 0;
      for (const t of src.topics()) { const c = retargetTopic(t, m); if (c) { topics.push(t); n += c; } }
      for (const s of src.sets()) { const c = retargetSet(s, m); if (c) { sets.push(s); n += c; } }
      if (topics.length || sets.length) src.touched({ topics, sets });
      return n;
    },
    flagDeleted(globalIds, note) {
      const ts = topicsOf(new Set(globalIds.map(bare)));
      for (const t of ts) if (!t.comments.some((c) => c.text === note)) src.addComment(t.guid, note);
      return ts.length;
    },
    resolveIssues(globalIds, comment) {
      const ts = topicsOf(new Set(globalIds.map(bare))).filter((t) => !RESOLVED.test(t.topicStatus.trim()));
      for (const t of ts) { src.addComment(t.guid, comment); src.setStatus(t.guid, 'Resolved'); }
      return ts.length;
    },
  };
}
