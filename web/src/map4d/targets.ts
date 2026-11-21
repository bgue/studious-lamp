// Which elements an assignment goes to: the selection, a criteria query, a storey, a selection set, or explicit ids.
// Pure over the model and plain inputs (the plugin supplies the selection and the sets). Tested in tests/map4d-targets.test.ts.

import { runQuery } from '../query';
import { globalIdsToIds, isCriteria } from '../selectionSets';
import type { SelectionSet } from '../selectionSets';
import type { ElementId, SceneModel } from '../types';

export type Target =
  | { selection: true }
  | { query: string }
  | { storey: string | number }
  | { set: string }
  | { ids: readonly number[] }
  | { globalIds: readonly string[] };

export interface TargetContext {
  model: Pick<SceneModel, 'elements' | 'storeys' | 'byGlobalId'> & Partial<SceneModel>;
  selection: readonly ElementId[];
  sets: readonly SelectionSet[];
}

export interface Resolved { ids: ElementId[]; error?: string }

export function resolveTarget(t: Target, c: TargetContext): Resolved {
  const m = c.model;
  if ('selection' in t) return { ids: [...c.selection] };
  if ('ids' in t) return { ids: t.ids.filter((i) => i >= 0 && i < m.elements.length) };
  if ('globalIds' in t) return { ids: globalIdsToIds(m as SceneModel, t.globalIds) };
  if ('query' in t) {
    const r = runQuery(m as SceneModel, t.query);
    return r.error ? { ids: [], error: r.error.message } : { ids: r.ids };
  }
  if ('storey' in t) {
    const s = typeof t.storey === 'number' ? m.storeys.find((x) => x.id === t.storey) : m.storeys.find((x) => x.name === t.storey);
    if (!s) return { ids: [], error: `No storey named ${t.storey}` };
    const ids: ElementId[] = [];
    m.elements.forEach((e, i) => { if (e.storey === s.id) ids.push(i); });
    return { ids };
  }
  const set = c.sets.find((s) => s.name === t.set);
  if (!set) return { ids: [], error: `No selection set named ${t.set}` };
  if (isCriteria(set)) {
    const r = runQuery(m as SceneModel, set.query);
    if (!r.error) return { ids: r.ids };
  }
  return { ids: globalIdsToIds(m as SceneModel, set.globalIds) };
}
