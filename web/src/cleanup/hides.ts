// Provenance-safe hiding. Cleanup merges its matches into the controller's userHides set, but remembers which ids it
// added itself. Restore removes only those: an element the user hid before cleanup did (so it was already in the set)
// stays hidden, and an element the user unhid by hand in between is not owned any more.

export class CleanupHides {
  /** Ids that are in userHides because cleanup put them there. */
  readonly owned = new Set<number>();

  /** Add `ids` to `userHides`; returns how many were newly hidden by cleanup (already hidden ones stay user-owned). */
  hide(userHides: Set<number>, ids: Iterable<number>): number {
    let n = 0;
    for (const id of ids) {
      if (userHides.has(id)) continue;
      userHides.add(id);
      this.owned.add(id);
      n++;
    }
    return n;
  }

  /** Remove what cleanup hid (and nothing else); returns the ids made visible again. */
  restore(userHides: Set<number>): number[] {
    const out: number[] = [];
    for (const id of this.owned) {
      if (userHides.delete(id)) out.push(id);
    }
    this.owned.clear();
    return out;
  }

  /** Forget owned ids the user has since unhid (so a later manual hide of the same element is the user's). */
  prune(userHides: ReadonlySet<number>): boolean {
    let changed = false;
    for (const id of this.owned) {
      if (!userHides.has(id)) {
        this.owned.delete(id);
        changed = true;
      }
    }
    return changed;
  }

  clear(): void {
    this.owned.clear();
  }
}
