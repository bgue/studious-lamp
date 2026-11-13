// Which model an item (a markup set, a BCF topic) belongs to, and what that means for the loaded model. Pure: no DOM, no
// three.js. Reuses ModelIdentity and compareModels of model.ts. Tested in tests/markup-scope.test.ts.
//
//   same       the model the item was made on: shown.
//   revised    same project, new revision (same name, other content): shown, flagged; attached targets that no longer fit are
//              detached and flagged as possibly already designed.
//   unknown    the item names no model (a BCF from another tool, an old file): shown, tagged "model unknown".
//   different  another model: hidden (nothing is drawn in 3D or on the overlay) and listed under "Other models".
//
// A federation of several IFC files is one model of the viewer (one name, one element list), so an item belongs to the
// federation as a whole; there is no per-file ownership.

import { compareModels, modelIdentity } from './model';
import type { ModelIdentity, ModelMatch } from './model';

export type { ModelIdentity, ModelMatch } from './model';

export interface ScopeInfo {
  match: ModelMatch;
  /** Drawn and listed with the current items. False: hidden, listed under "Other models". */
  visible: boolean;
  /** Short tag for lists: empty for the same model. */
  tag: string;
  /** The longer explanation (tooltips, status lines). */
  note: string;
}

/** The scope of an item made on `owner` while `now` is loaded. No model loaded (`now` null): everything counts as current. */
export function scopeOf(owner: ModelIdentity | null | undefined, now: ModelIdentity | null | undefined): ScopeInfo {
  if (!now) return { match: 'same', visible: true, tag: '', note: '' };
  const { match, message } = compareModels(owner ?? undefined, now);
  switch (match) {
    case 'same': return { match, visible: true, tag: '', note: '' };
    case 'revised': return { match, visible: true, tag: 'revised model', note: `${message} Targets that no longer fit are detached and may already be designed.` };
    case 'unknown': return { match, visible: true, tag: 'model unknown', note: 'The item does not say which model it was made on; it is shown on this one.' };
    default: return { match, visible: false, tag: 'other model', note: message };
  }
}

/** A stable key of a model identity (groups the items of one model). */
export function identityKey(id: ModelIdentity | null | undefined): string {
  return id ? `${id.name.trim().toLowerCase()}|${id.elementCount}|${id.guidHash}` : 'unknown';
}

/** "Name (n elements)". */
export function modelLabel(id: ModelIdentity | null | undefined): string {
  if (!id) return 'unknown model';
  return `${id.name || 'unnamed model'} (${id.elementCount} element${id.elementCount === 1 ? '' : 's'})`;
}

export interface OtherGroup<T> {
  key: string;
  model: ModelIdentity;
  label: string;
  items: T[];
}

export interface Split<T> {
  /** Items shown with the current model, in their order, each with its scope (same, revised or unknown). */
  here: Array<{ item: T; scope: ScopeInfo }>;
  /** Items of other models, grouped per model, in first-seen order. */
  other: OtherGroup<T>[];
  /** Number of items of other models. */
  otherCount: number;
}

/** Split items into those of the current model and those of other models. `shown` forces an item into the first list (opened on purpose). */
export function splitByScope<T>(items: readonly T[], ownerOf: (t: T) => ModelIdentity | null | undefined, now: ModelIdentity | null | undefined, shown: (t: T) => boolean = () => false): Split<T> {
  const here: Split<T>['here'] = [];
  const groups = new Map<string, OtherGroup<T>>();
  let otherCount = 0;
  for (const item of items) {
    const owner = ownerOf(item);
    const scope = scopeOf(owner, now);
    if (scope.visible || shown(item)) {
      here.push({ item, scope });
      continue;
    }
    otherCount++;
    const key = identityKey(owner);
    let g = groups.get(key);
    if (!g) {
      g = { key, model: owner!, label: modelLabel(owner), items: [] };
      groups.set(key, g);
    }
    g.items.push(item);
  }
  return { here, other: [...groups.values()], otherCount };
}

// ---------------------------------------------------------------- the identity of the loaded model

interface LoadedLike {
  loaded: object | null | undefined;
  modelName: string;
  controller: { model: { elements: ReadonlyArray<{ globalId?: string | null }> } };
}

const cache = new WeakMap<object, ModelIdentity>();

/**
 * The identity of the model that is loaded in the viewer, computed once per model load (the cache is keyed by the loaded
 * model object). Null while no model is loaded. Shared by the markup tool and the BCF tool.
 */
export function loadedIdentity(app: LoadedLike): ModelIdentity | null {
  const loaded = app.loaded;
  if (!loaded) return null;
  let id = cache.get(loaded);
  if (!id || id.name !== app.modelName) {
    const els = app.controller.model.elements;
    id = modelIdentity(app.modelName, els.length, els.map((e) => e.globalId).filter((g): g is string => !!g));
    cache.set(loaded, id);
  }
  return id;
}
