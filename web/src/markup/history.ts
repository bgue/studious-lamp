// Undo / redo over snapshots of a state. The markup tool records the markup list of a set before each change; undo swaps
// the list back, redo swaps it forward. Plain data, no DOM. Tested in tests/markup-history.test.ts.

export class History<T> {
  private past: T[] = [];
  private future: T[] = [];
  constructor(private readonly limit = 100, private readonly clone: (v: T) => T = (v) => JSON.parse(JSON.stringify(v)) as T) {}

  /** Record the state as it is BEFORE a change. A new change drops the redo stack. */
  record(state: T): void {
    this.past.push(this.clone(state));
    if (this.past.length > this.limit) this.past.shift();
    this.future = [];
  }

  get canUndo(): boolean {
    return this.past.length > 0;
  }
  get canRedo(): boolean {
    return this.future.length > 0;
  }
  get undoDepth(): number {
    return this.past.length;
  }
  get redoDepth(): number {
    return this.future.length;
  }

  /** The state to go back to (given the current one, kept for redo), or null when there is nothing to undo. */
  undo(current: T): T | null {
    const prev = this.past.pop();
    if (prev === undefined) return null;
    this.future.push(this.clone(current));
    return prev;
  }

  redo(current: T): T | null {
    const next = this.future.pop();
    if (next === undefined) return null;
    this.past.push(this.clone(current));
    return next;
  }

  clear(): void {
    this.past = [];
    this.future = [];
  }
}
