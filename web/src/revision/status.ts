// The hand-off from a revision walk to the IFC save plan (design 1.6 and 3.7): which status each element of the revised model gets in
// `Xray_Review.RevisionStatus`, and the baseline's name for `RevisionBaseline`. This is the value of `extra.revision` of `planSave`.
// Pure: it reads a session and the head's GlobalIds. Deleted elements are not in the head file, so they have no entry.

import type { RevisionSession } from './types';

export type RevisionStatusValue = 'new' | 'changed' | 'rematched' | 'unchanged';

export interface RevisionStatus {
  status: RevisionStatusValue;
  /** The name of the model that the walk compared against. */
  baseline: string;
}

/** Every head element: its category in the diff, `unchanged` for the ones the diff does not list. Keyed by the head GlobalId. */
export function revisionStatusMap(session: Pick<RevisionSession, 'diff' | 'baseName'>, headGlobalIds: Iterable<string>): Map<string, RevisionStatus> {
  const listed = new Map<string, RevisionStatusValue>();
  for (const e of session.diff.entries) {
    if (e.head === undefined || e.category === 'deleted' || e.category === 'unchanged') continue;
    listed.set(e.head, e.category);
  }
  const out = new Map<string, RevisionStatus>();
  for (const g of headGlobalIds) out.set(g, { status: listed.get(g) ?? 'unchanged', baseline: session.baseName });
  return out;
}
