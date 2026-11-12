// Undo and redo stack: pure logic, no DOM and no three.js, so it runs in vitest.
//
// An entry is a record of one change with a label ("zoom", "selection", "ghost desaturate") and whatever the caller needs
// to undo and redo it. The stack knows nothing about cameras or settings: `undo(apply)` and `redo(apply)` hand the entry
// to the caller, which writes the old or the new state. While `apply` runs the stack is "applying": pushes made then are
// the undo's own changes and are ignored, so an undo never records itself.
//
// Rules:
//   - A new entry clears the redo list.
//   - At most `cap` entries are kept; the oldest go first.
//   - An entry with a `key` that follows an entry with the same key within `coalesceMs` is merged into it (a slider drag
//     is one entry). `merge` returns the merged entry, or null when the two cancel out (the slider came back): both go.
//   - While `muted` is set (a model is loading, a link is being applied) pushes are ignored.

export interface UndoEntry {
  /** What the entry changed, for the tooltip: "Undo zoom". */
  label: string;
  /** Entries with the same key that follow each other closely are merged. */
  key?: string;
  /** Time of the last change that went into the entry, ms. */
  at: number;
}

export interface UndoStackOptions<T extends UndoEntry> {
  cap?: number;
  coalesceMs?: number;
  merge?: (prev: T, next: T) => T | null;
}

export const DEFAULT_CAP = 100;
export const DEFAULT_COALESCE_MS = 600;

export class UndoStack<T extends UndoEntry> {
  private undoList: T[] = [];
  private redoList: T[] = [];
  private applying = false;
  private mutedCount = 0;
  private readonly listeners = new Set<() => void>();
  readonly cap: number;
  readonly coalesceMs: number;
  private readonly mergeFn: ((prev: T, next: T) => T | null) | undefined;

  constructor(opts: UndoStackOptions<T> = {}) {
    this.cap = Math.max(1, Math.floor(opts.cap ?? DEFAULT_CAP));
    this.coalesceMs = opts.coalesceMs ?? DEFAULT_COALESCE_MS;
    this.mergeFn = opts.merge;
  }

  get canUndo(): boolean {
    return this.undoList.length > 0;
  }
  get canRedo(): boolean {
    return this.redoList.length > 0;
  }
  get undoLabel(): string | null {
    return this.undoList[this.undoList.length - 1]?.label ?? null;
  }
  get redoLabel(): string | null {
    return this.redoList[this.redoList.length - 1]?.label ?? null;
  }
  get size(): number {
    return this.undoList.length;
  }
  /** True while undo() or redo() runs its `apply`. */
  get isApplying(): boolean {
    return this.applying;
  }
  get isMuted(): boolean {
    return this.mutedCount > 0;
  }

  /** The entries, oldest first. `redo` is the list of undone entries, next redo last. */
  list(): { undo: readonly T[]; redo: readonly T[] } {
    return { undo: [...this.undoList], redo: [...this.redoList] };
  }

  /** Ignore pushes while `fn` runs. Nests. */
  mute<R>(fn: () => R): R {
    this.mutedCount++;
    try {
      return fn();
    } finally {
      this.mutedCount--;
    }
  }

  setMuted(on: boolean): void {
    this.mutedCount = on ? Math.max(1, this.mutedCount) : 0;
  }

  /** Record a change. Returns false when it was ignored (applying or muted). */
  push(entry: T): boolean {
    if (this.applying || this.mutedCount > 0) return false;
    const last = this.undoList[this.undoList.length - 1];
    if (last && entry.key !== undefined && last.key === entry.key && this.mergeFn && entry.at - last.at <= this.coalesceMs) {
      const merged = this.mergeFn(last, entry);
      this.redoList = [];
      if (merged === null) this.undoList.pop();
      else this.undoList[this.undoList.length - 1] = merged;
      this.emit();
      return true;
    }
    this.undoList.push(entry);
    if (this.undoList.length > this.cap) this.undoList.splice(0, this.undoList.length - this.cap);
    this.redoList = [];
    this.emit();
    return true;
  }

  /** Undo the last entry through `apply`. Returns the entry, or null when there is none. */
  undo(apply: (entry: T) => void): T | null {
    const e = this.undoList[this.undoList.length - 1];
    if (!e) return null;
    this.undoList.pop();
    this.run(apply, e);
    this.redoList.push(e);
    this.emit();
    return e;
  }

  redo(apply: (entry: T) => void): T | null {
    const e = this.redoList[this.redoList.length - 1];
    if (!e) return null;
    this.redoList.pop();
    this.run(apply, e);
    this.undoList.push(e);
    this.emit();
    return e;
  }

  private run(apply: (entry: T) => void, e: T): void {
    this.applying = true;
    try {
      apply(e);
    } finally {
      this.applying = false;
    }
  }

  clear(): void {
    if (this.undoList.length === 0 && this.redoList.length === 0) return;
    this.undoList = [];
    this.redoList = [];
    this.emit();
  }

  onChange(cb: () => void): () => void {
    this.listeners.add(cb);
    return () => {
      this.listeners.delete(cb);
    };
  }

  private emit(): void {
    for (const l of this.listeners) l();
  }
}
