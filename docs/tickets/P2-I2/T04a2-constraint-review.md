# P2-I2-T04a2 — Constraint review: owner filter and groups by owner, category, age (core)

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: core, read, confidentiality
Depends on: C2 (merged)
Branch: `p2/i2-t04a2-constraint-review`
Worktree: `/home/user/wt/t04a2` (from `p2/i2` head)

## Goal
The constraint review (screen, web page, report, `tl constraint ls`) needs the open constraints grouped by owner, by category and by age band, and filtered by owner. After this ticket
`tl_core.constraints` offers `owner` as a filter of the existing list and count, and `review_groups(views, by)` that groups an already-read list. The viewer join to the subject stays exactly as C2 wrote it.

## Brief references (pasted)
> `queries.py` `_where(scope, *, subject_id, state, category, phase, blocking, viewer)` builds the conditions (first `not_hidden_each("c.subject_id", viewer)`); `list_constraints` and `count_constraints` pass the
> filters through. `ConstraintView` has `owner` (`user:<name>` or `None`), `category`, `age_days`, `aging`, `due_at`, `state`, `key`.
> Change 1 (queries.py, about 8 lines): add keyword `owner: str | None = None` to `_where`, `list_constraints`, `count_constraints`; when given, condition `c.owner = :owner`. A value of the empty string is
> refused with `ValueError`. Nothing else in the file changes; never read or copy a class; the hidden-subject join stays first.
> Change 2 (new `review.py`):
> ```python
> AGE_BANDS: Final = (("0-7", 0, 7), ("8-14", 8, 14), ("15-28", 15, 28), ("29+", 29, None))
> BY_WORDS: Final = ("owner", "category", "age")
> @dataclass(frozen=True)
> class ConstraintGroup: label: str; count: int; blocking: int; aging: int; keys: tuple[str, ...]  # keys in key order
> def review_groups(views: Sequence[ConstraintView], by: str) -> list[ConstraintGroup]: ...
> ```
> `by` not in `BY_WORDS` raises `ValueError`. `owner` groups by `view.owner` with `-` for none (the unowned group sorts last); `category` groups by `view.category`; `age` by the band of `view.age_days`.
> Groups sort by label (owner, category) or band order (age); empty bands are kept with count 0 so a screen shows every band; `blocking` counts views with `severity == 'blocking'`; `aging` counts views with `aging` true. Pure function: no SQL, no clock. Keys only, no description text in a group.
> Re-export both names and `AGE_BANDS` from `tl_core/constraints/__init__.py` (one import line and `__all__` if present).

## Context (read these, nothing else)
- `packages/tl-core/src/tl_core/constraints/queries.py` (lines 36-110 and 173-260)
- `packages/tl-core/src/tl_core/constraints/__init__.py` (imports and `__all__` only)
- `dev/accept/P2-I2/C2.py` and `dev/accept/P2-I2/c2_checks.py` (`build`, `seed`, the five-reader walk helper)
- `docs/reports/P2-I2/C2.md`

## Allowed paths
- `packages/tl-core/src/tl_core/constraints/queries.py` (the `owner` filter only)
- `packages/tl-core/src/tl_core/constraints/review.py` (create), `packages/tl-core/src/tl_core/constraints/__init__.py` (re-export lines)
- `dev/accept/P2-I2/T04a2.py` (create; helper `dev/accept/P2-I2/t04a2_checks.py` if over 70 lines)
- `docs/reports/P2-I2/T04a2.md` (create)
Not here: the access word check (entry points do it, T04c1 and T04d), any other file, new pytest (S5), SQL beyond the one condition.

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I2/C2.py
uv run python dev/accept/P2-I2/T04a2.py
just gate packages/tl-api/tests/test_confidentiality_walk.py packages/tl-modules/awp/tests
```
`T04a2.py` (SQLite temp ledger built with the C2 helpers; one `PASS <check>` per line; final `T04a2 ok`): `owner` filter returns only that owner's rows and `count_constraints` agrees; `owner=""` raises; groups by owner,
category and age on a hand-made list of `ConstraintView`s (build them with `dataclasses.replace` from one real view) pin label, count, blocking, aging and keys, with the unowned group last and empty bands present;
`by="x"` raises; as a reader below the class of a restricted subject, the owner filter finds no constraint of that subject and the count equals the count of an owner who has none (hidden looks like missing);
`C2.py` still `C2 ok`.

## Tests to add
None (S5 writes the pytest).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first, queries.py diff size. Commit subjects `P2-I2-T04a2: ...`; the commit trailer is the attribution lines your harness
requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in any committed file.

## Escalation triggers
- Stop and report *Blocked* if the owner condition cannot go in without touching the subject join, or `ConstraintView` lacks a field named above.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
