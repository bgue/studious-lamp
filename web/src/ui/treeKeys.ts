// Pure keyboard navigation over the flat rows of the model tree (WAI-ARIA tree pattern). No DOM: the view feeds the rows
// and the active index and applies the result. Docs: docs-features/right-sidebar.md (Model tree keyboard).

import type { FlatRow } from './treeModel';

export const TYPE_AHEAD_MS = 500;

const clamp = (i: number, n: number): number => Math.max(0, Math.min(n - 1, i));

/** Up, Down, Home, End, PageUp, PageDown: the new active index (the same index when nothing moves). */
export function moveActive(rows: readonly FlatRow[], active: number, key: string, page: number): number {
  const n = rows.length;
  if (n === 0) return -1;
  const a = clamp(active, n);
  const p = Math.max(1, page);
  switch (key) {
    case 'ArrowDown':
      return clamp(a + 1, n);
    case 'ArrowUp':
      return clamp(a - 1, n);
    case 'Home':
      return 0;
    case 'End':
      return n - 1;
    case 'PageDown':
      return clamp(a + p, n);
    case 'PageUp':
      return clamp(a - p, n);
    default:
      return a;
  }
}

/** Index of the parent row (the nearest earlier row one level up), or -1 for a root row. */
export function parentIndex(rows: readonly FlatRow[], i: number): number {
  const r = rows[i];
  if (!r || r.depth === 0) return -1;
  for (let j = i - 1; j >= 0; j--) if (rows[j]!.depth < r.depth) return j;
  return -1;
}

export type BranchMove = { type: 'open'; key: string } | { type: 'close'; key: string } | { type: 'move'; index: number } | { type: 'none' };

/** ArrowRight: open a closed row, else go to the first child of an open one (nothing on a leaf). */
export function rightMove(rows: readonly FlatRow[], i: number): BranchMove {
  const r = rows[i];
  if (!r || !r.hasChildren) return { type: 'none' };
  if (!r.expanded) return { type: 'open', key: r.node.key };
  return i + 1 < rows.length && rows[i + 1]!.depth > r.depth ? { type: 'move', index: i + 1 } : { type: 'none' };
}

/** ArrowLeft: close an open row, else go to the parent (nothing on a root row that is closed or a leaf). */
export function leftMove(rows: readonly FlatRow[], i: number): BranchMove {
  const r = rows[i];
  if (!r) return { type: 'none' };
  if (r.hasChildren && r.expanded) return { type: 'close', key: r.node.key };
  const p = parentIndex(rows, i);
  return p >= 0 ? { type: 'move', index: p } : { type: 'none' };
}

/** `*`: keys of the closed siblings of the row (including itself) that have children. */
export function siblingKeysToOpen(rows: readonly FlatRow[], i: number): string[] {
  const r = rows[i];
  if (!r) return [];
  const d = r.depth;
  let a = i;
  while (a - 1 >= 0 && rows[a - 1]!.depth >= d) a--;
  let b = i;
  while (b + 1 < rows.length && rows[b + 1]!.depth >= d) b++;
  const out: string[] = [];
  for (let j = a; j <= b; j++) {
    const s = rows[j]!;
    if (s.depth === d && s.hasChildren && !s.expanded) out.push(s.node.key);
  }
  return out;
}

export interface TypeAheadState {
  buffer: string;
  at: number;
}

export const EMPTY_TYPE_AHEAD: TypeAheadState = { buffer: '', at: 0 };

/**
 * Type-ahead: append `ch` to the buffer (reset after TYPE_AHEAD_MS of silence) and find the next row whose label starts
 * with it. A first letter searches after the active row; a longer buffer includes the active row, so "do" stays on "Door";
 * the same letter repeated cycles through the rows that start with it. Returns the new buffer and the matched index (-1: none).
 */
export function typeAhead(rows: readonly FlatRow[], active: number, st: TypeAheadState, ch: string, now: number): { state: TypeAheadState; index: number } {
  const fresh = now - st.at > TYPE_AHEAD_MS || st.buffer === '';
  const c = ch.toLowerCase();
  let buffer = fresh ? c : st.buffer + c;
  const n = rows.length;
  const starts = (j: number, s: string): boolean => rows[j]!.node.label.toLowerCase().startsWith(s);
  const find = (s: string, from: number): number => {
    for (let k = 0; k < n; k++) {
      const j = (from + k) % n;
      if (starts(j, s)) return j;
    }
    return -1;
  };
  const a = n === 0 ? 0 : clamp(active, n);
  let index: number;
  if (buffer.length > 1 && [...buffer].every((x) => x === buffer[0])) {
    // "ddd": cycle on the single letter.
    buffer = buffer[0]!;
    index = find(buffer, a + 1);
  } else if (buffer.length === 1) {
    index = find(buffer, a + 1);
  } else {
    index = find(buffer, a);
  }
  if (index < 0 && buffer.length > 1) {
    // No row for the longer prefix: keep the buffer, stay put.
    return { state: { buffer, at: now }, index: -1 };
  }
  return { state: { buffer, at: now }, index };
}

/** A printable character a tree takes for type-ahead (one character, not a space). */
export function isTypeAheadChar(key: string): boolean {
  return key.length === 1 && key !== ' ' && key !== '*';
}
