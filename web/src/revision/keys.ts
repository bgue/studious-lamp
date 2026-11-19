// The keys of the revision walk panel (design 3.6) and of its palette actions, as data: the panel handles them in its own key handler
// (like the review walk), the cheat sheet text and the tests read this table. Keys here are KeyboardEvent.key values, letters lower case.

export interface WalkKey {
  keys: string[];
  action: string;
  /** Same meaning as the review walk's key. */
  sameAsReview?: boolean;
}

export const REVISION_WALK_KEYS: readonly WalkKey[] = [
  { keys: ['Enter', 'y'], action: 'Accept', sameAsReview: true },
  { keys: ['2'], action: 'Accept with the other classification', sameAsReview: true },
  { keys: ['e'], action: 'Edit the classification, then accept', sameAsReview: true },
  { keys: ['r'], action: 'Reject (dispute)' },
  { keys: ['n', 'ArrowRight'], action: 'Skip (Shift+N skips the rest of the item)', sameAsReview: true },
  { keys: ['?'], action: 'Mark the decision unsure', sameAsReview: true },
  { keys: ['ArrowLeft'], action: 'Back', sameAsReview: true },
  { keys: ['[', ']'], action: 'Step to another element of the item', sameAsReview: true },
  { keys: ['a'], action: 'All alike or this element only', sameAsReview: true },
  { keys: ['u'], action: 'Undo the last decision or bulk rule', sameAsReview: true },
  { keys: ['g'], action: 'Cycle the ghost: both, head only, base only' },
  { keys: ['b'], action: 'Open the bulk rules' },
  { keys: ['Escape'], action: 'Close', sameAsReview: true },
];

/** The palette actions of the revision plugin: id and default keys (plugins/revision.ts registers exactly these). */
export const REVISION_ACTIONS: ReadonlyArray<{ id: string; keys: string[] }> = [
  { id: 'revision.walk', keys: ['Shift+v'] },
  { id: 'revision.compare', keys: [] },
  { id: 'revision.report', keys: [] },
];
