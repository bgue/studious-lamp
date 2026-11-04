// Model tree data model (no DOM). Builds Storey -> ifcClass -> element and a Systems branch from a SceneModel,
// filters it, and flattens the expanded part into rows for a virtualised list.

import type { ElementId, ElementRecord, SceneModel } from '../types';

export type TreeKind = 'storey' | 'class' | 'element' | 'systems' | 'system';

export interface TreeNode {
  /** Unique within the tree. Element keys include their parent path, so an element in two branches has two keys. */
  key: string;
  kind: TreeKind;
  label: string;
  /** Untruncated text for a tooltip. */
  title: string;
  /** Number of elements below (1 for an element). */
  count: number;
  /** All element ids at or below this node, in display order. Selecting the node selects these. */
  ids: ElementId[];
  /** Set for element nodes only. */
  elementId: ElementId | null;
  children: TreeNode[];
}

export interface FlatRow {
  node: TreeNode;
  depth: number;
  expanded: boolean;
  hasChildren: boolean;
}

export const NO_STOREY_KEY = 'st:none';
export const SYSTEMS_KEY = 'sys';
const LABEL_MAX = 44;

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });

export function truncate(s: string, max = LABEL_MAX): string {
  return s.length <= max ? s : s.slice(0, Math.max(1, max - 1)) + '…';
}

export function storeyKey(storeyId: number | null | undefined, known: ReadonlySet<number>): string {
  return storeyId === null || storeyId === undefined || !known.has(storeyId) ? NO_STOREY_KEY : `st:${storeyId}`;
}

function elementLabel(e: ElementRecord): { label: string; title: string } {
  const full = e.name && e.name.trim() ? e.name : e.globalId;
  return { label: truncate(full), title: `${full}\n${e.ifcClass}  ${e.globalId}` };
}

function elementNode(e: ElementRecord, parentKey: string): TreeNode {
  const { label, title } = elementLabel(e);
  return { key: `${parentKey}/e:${e.id}`, kind: 'element', label, title, count: 1, ids: [e.id], elementId: e.id, children: [] };
}

function sortedElements(list: ElementRecord[]): ElementRecord[] {
  return [...list].sort((a, b) => collator.compare(a.name || a.globalId, b.name || b.globalId) || a.id - b.id);
}

function groupNode(kind: TreeKind, key: string, label: string, children: TreeNode[], title = label): TreeNode {
  const ids: ElementId[] = [];
  for (const c of children) for (const id of c.ids) ids.push(id);
  return { key, kind, label, title, count: ids.length, ids, elementId: null, children };
}

/**
 * Build the full tree. Storeys ascending by elevation (ties by id), elements without a storey (or with an unknown
 * storey id) under a trailing "No storey" node. Classes alphabetical, elements by natural name order.
 * Empty storeys are omitted. A "Systems" root is appended when the model has systems.
 */
export function buildTree(model: SceneModel, elements: readonly ElementRecord[] = model.elements): TreeNode[] {
  const known = new Set(model.storeys.map((s) => s.id));
  const byStorey = new Map<string, ElementRecord[]>();
  for (const e of elements) {
    const k = storeyKey(e.storey, known);
    let a = byStorey.get(k);
    if (!a) byStorey.set(k, (a = []));
    a.push(e);
  }

  const roots: TreeNode[] = [];
  const storeys = [...model.storeys].sort((a, b) => a.elevation - b.elevation || a.id - b.id);
  const order: Array<{ key: string; label: string }> = storeys.map((s) => ({ key: `st:${s.id}`, label: s.name }));
  order.push({ key: NO_STOREY_KEY, label: 'No storey' });
  for (const { key, label } of order) {
    const list = byStorey.get(key);
    if (!list || list.length === 0) continue;
    const byClass = new Map<string, ElementRecord[]>();
    for (const e of list) {
      let a = byClass.get(e.ifcClass);
      if (!a) byClass.set(e.ifcClass, (a = []));
      a.push(e);
    }
    const classes = [...byClass.keys()].sort(collator.compare);
    const children = classes.map((cls) => {
      const ck = `${key}|c:${cls}`;
      return groupNode('class', ck, cls, sortedElements(byClass.get(cls)!).map((e) => elementNode(e, ck)));
    });
    roots.push(groupNode('storey', key, label, children));
  }

  const wanted = new Set<ElementId>(elements.map((e) => e.id));
  const systems = model.relations.systems
    .map((s, i) => {
      const ids = s.elements.filter((id) => wanted.has(id) && model.elements[id]);
      const key = `${SYSTEMS_KEY}:${i}`;
      return groupNode('system', key, s.name, ids.map((id) => elementNode(model.elements[id]!, key)));
    })
    .filter((n) => n.count > 0);
  if (systems.length > 0) roots.push(groupNode('systems', SYSTEMS_KEY, 'Systems', systems));
  return roots;
}

/** True when the element's name, globalId or class contains the (already lower-cased, trimmed) query. */
export function matchesElement(e: ElementRecord, q: string): boolean {
  if (!q) return true;
  return (
    (e.name ?? '').toLowerCase().includes(q) || e.globalId.toLowerCase().includes(q) || e.ifcClass.toLowerCase().includes(q)
  );
}

/** Tree of only the matching elements (same structure and keys as buildTree). Empty query returns the full tree. */
export function filterTree(model: SceneModel, query: string): TreeNode[] {
  const q = query.trim().toLowerCase();
  if (!q) return buildTree(model);
  return buildTree(model, model.elements.filter((e) => matchesElement(e, q)));
}

/** Keys of nodes expanded by default: the storeys (their class children stay collapsed). */
export function defaultExpanded(roots: readonly TreeNode[]): Set<string> {
  const s = new Set<string>();
  for (const r of roots) if (r.kind === 'storey') s.add(r.key);
  return s;
}

/** Keys of every node that has children (used to auto-expand a filtered tree). */
export function allParentKeys(roots: readonly TreeNode[]): Set<string> {
  const s = new Set<string>();
  const walk = (n: TreeNode): void => {
    if (n.children.length === 0) return;
    s.add(n.key);
    for (const c of n.children) walk(c);
  };
  for (const r of roots) walk(r);
  return s;
}

/** Rows to display: expanded branches only. */
export function flattenTree(roots: readonly TreeNode[], isExpanded: (key: string) => boolean): FlatRow[] {
  const rows: FlatRow[] = [];
  const walk = (n: TreeNode, depth: number): void => {
    const hasChildren = n.children.length > 0;
    const expanded = hasChildren && isExpanded(n.key);
    rows.push({ node: n, depth, expanded, hasChildren });
    if (expanded) for (const c of n.children) walk(c, depth + 1);
  };
  for (const r of roots) walk(r, 0);
  return rows;
}

/** Keys of the storey node, class node and element node for an element in the storey branch. */
export function elementPath(model: SceneModel, id: ElementId): { storey: string; cls: string; element: string } | null {
  const e = model.elements[id];
  if (!e) return null;
  const known = new Set(model.storeys.map((s) => s.id));
  const storey = storeyKey(e.storey, known);
  const cls = `${storey}|c:${e.ifcClass}`;
  return { storey, cls, element: `${cls}/e:${id}` };
}
