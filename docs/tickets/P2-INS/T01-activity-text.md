# P2-INS-T01 — Activity text: columns, words, why, related mark (INS-A2)

Status: ready (round 2, against merged S1 @2fbcdcf)
Tier: haiku
review: lite
Labels: tui
Depends on: S1 merged (it is: `tl_core.insights.types`). Runs in one workflow with T02: the stub below is committed on p2/ins, T02 imports it and never edits it
Branch: `p2/ins-t01-activity-text`
Worktree: `/home/user/wt/ins-t01`

## Goal
`tl_tui/record_activity_text.py` (a stub is in the tree: frozen signatures, placeholder bodies for 6 of the 9 functions; you replace the bodies and add the missing 3) holds the real text: pure functions (no client call, no I/O, no `textual` import, so the web client can reuse the words) that turn
`ActivityRow`s into table columns and cells, in plain words by default. The module is NOT named `activity_text` (plan check F3: the schedule has an activity screen).

## Brief references (pasted; spec A1.1, A1.4, A3)
| Column | Plain text |
|---|---|
| When | `2026-11-07 14:02` (`text.timestamp`) |
| Who | `Maria Lee`, `Agent: planner`; a decided proposal: `Agent: planner, accepted by Maria Lee` (`display.actor_label`) |
| Kind | Change, Move, Link, File, Post, Proposal, Constraint, Check run (from `row.kind`) |
| What | `record_text.event_label(event_type)` plus `event_summary` for the record's own rows; proposal rows `Proposal filed`, `Proposal accepted`, `Proposal rejected`; readiness rows `Readiness checked: <row.note>`; unknown types fall back to `humanize` |
| Why | `row.why` or `—`; the column is dropped when no row of the page has one |
| From | `↳ <row.from_key>` for a related row, `—` otherwise |
Technical mode: columns `#` (event stream version), `When`, `Event` (type), `Actor`, `Summary` as `record_text.history_columns(True)` and `history_cells` give for the record's own rows; related rows add `From`.
Narrow width: drop `Kind`, then `From`, shorten `What`, `Why` last (module-local tuple like `READINESS_DROP` in `readiness_text.py`; do not edit `layout.py`).
Never name a model type or provider. Hidden records have no rows, so nothing here filters.

## Interfaces (verbatim from the repo at @2fbcdcf; `packages/tl-core/src/tl_core/insights/types.py`)
```python
ActivityKind = Literal["change", "move", "link", "file", "post", "proposal", "constraint", "check"]
class ActivityRow(BaseModel):
    event: Event; kind: ActivityKind; related: bool = False; from_id: str | None = None
    from_key: str | None = None; why: str | None = None; decided_by: str | None = None; note: str | None = None
class ActivityPage(BaseModel):
    rows: list[ActivityRow]; next_before_seq: int | None
```
Event (`tl_core.ledger`) fields used: `seq`, `stream_version`, `event_type`, `actor`, `recorded_at` (datetime), `payload`. Helpers to call, not rewrite:
`record_text.event_label(event_type) -> str`, `record_text.event_summary(event, labels=None, *, technical=True) -> str`, `record_text.history_columns(technical)`, `history_cells(event, labels, *, technical)`,
`display.actor_label(labels, actor) -> str`, `display.humanize(name)`, `display.find_technical(text, labels=None) -> list[str]`, `text.timestamp(iso_str | None) -> str`, `text.EMPTY` (the dash).
Frozen signatures already in the stub (do not change): `kind_word(kind)`, `page_has_why(rows)`, `activity_columns(rows, *, technical)`, `activity_cells(row, labels, *, technical, with_why)`, `filter_title(revisions_only, related, text)`, `row_matches(row, text, labels)`.
To add (pure, same file): `who_text(row, labels)`, `what_text(row, labels, *, technical)`, `why_text(row)`, `from_text(row)`. `activity_columns` leaves `Why` out when `page_has_why(rows)` is false; `activity_cells` is called with `with_why=page_has_why(rows)` and has as many cells as the columns.
`filter_title` is `Activity` plus ` · Revisions only` / ` · Related off` / ` · "text"` (in that order, each only when active). `row_matches`: case-insensitive over the What, Who and From cells.

## Context (<= 6 files)
`packages/tl-tui/src/tl_tui/record_activity_text.py` (the stub); `record_text.py` (`event_label`, `event_summary`, `history_*`); `display.py`; `readiness_text.py` (the pattern, `READINESS_DROP`); `packages/tl-tui/tests/test_awp_text.py` (test style).
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/record_activity_text.py` (modify: replace bodies, add 4 functions)
- `packages/tl-tui/tests/test_record_activity_text.py` (create)
- `docs/reports/P2-INS/T01.md` (create)
Not allowed: changing a frozen signature, `record_view.py`, `layout.py`, any widget, `client.py`.

## Acceptance
```
just check
just gate packages/tl-tui/tests/test_record_activity_text.py
```
Expected: all pass; `just check` clean (the test file is under 200 lines).

## Tests to add (`test_record_activity_text.py`, built from small `ActivityRow` literals)
One test per kind word; a proposal accepted by a person; a proposal filed by an agent; a readiness row with `note`; a related row (`↳ KEY`) and a non-related one (`—`); `page_has_why` false then true; `activity_columns` in plain and technical modes and `with_why` off; `filter_title` for the four states; `row_matches` hit and miss; `display.find_technical` finds nothing in plain cells of every row used; an unknown event type falls back to `humanize`.

## Report requirements
`docs/templates/haiku-report.md`, <= 60 lines; deviations first; paste the two command outputs (<= 5 lines each).

## Commit
`P2-INS-T01: <imperative summary>`; trailer lines as `docs/build-spec/SUPERVISOR-PROMPT.md`; no model names. Do not merge; do not push.

## Escalation triggers
- Stop and report *Blocked* if `ActivityRow` differs from the pasted block; a frozen signature cannot give the table in the Brief references; an existing helper you need is private; a word in the table has no `labels` source.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
