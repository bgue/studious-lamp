# P2-INS-T01 — Activity text: columns, words, why, related mark (INS-A2)

Status: draft (written round 1 against the S1 contract; the next round re-reads the merged `ActivityRow` and refreshes the pasted block before dispatch)
Tier: haiku
review: lite
Labels: tui
Depends on: S1 merged (`tl_core.insights.types.ActivityRow`, `ActivityPage`)
Branch: `p2/ins-t01-activity-text`
Worktree: `/home/user/wt/ins-t01`

## Goal
`tl_tui/record_activity_text.py` exists: pure functions (no client call, no I/O, no `textual` import, so the web client can reuse the words) that turn
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

## Interfaces (verbatim from the repo at the branch point; pasted after S1 merges)
```python
ActivityKind = Literal["change", "move", "link", "file", "post", "proposal", "constraint", "check"]
class ActivityRow(BaseModel):
    event: Event; kind: ActivityKind; related: bool = False; from_id: str | None = None
    from_key: str | None = None; why: str | None = None; decided_by: str | None = None; note: str | None = None
class ActivityPage(BaseModel):
    rows: list[ActivityRow]; next_before_seq: int | None
```
Functions to write (all pure; `labels: Labels | None`, `technical: bool` keyword):
`activity_columns(rows, *, technical)`, `activity_cells(row, labels, *, technical, with_why)`, `kind_word(kind)`, `who_text(row, labels)`, `what_text(row, labels, *, technical)`,
`why_text(row)`, `from_text(row)`, `page_has_why(rows)`, `filter_title(revisions_only, related, text)` (`Activity` plus ` · Revisions only` / ` · Related off` / ` · "text"`), `row_matches(row, text, labels)` (case-insensitive over the What, Who and From cells).

## Context (<= 6 files)
`packages/tl-tui/src/tl_tui/record_text.py` (`event_label`, `event_summary`, `history_*`); `display.py` (`humanize`, `actor_label`); `text.py` (`timestamp`); `readiness_text.py` (the pattern); `packages/tl-tui/tests/test_awp_text.py` (test style); S1's `types.py`.
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/record_activity_text.py` (create)
- `packages/tl-tui/tests/test_record_activity_text.py` (create)
- `docs/reports/P2-INS/T01.md` (create)
Not allowed: `record_view.py`, `layout.py`, any widget, `client.py`.

## Acceptance
```
just check
uv run pytest packages/tl-tui/tests/test_record_activity_text.py -q
```
Expected: all pass; `just check` clean (the test file is under 200 lines).

## Tests to add (`test_record_activity_text.py`, built from small `ActivityRow` literals)
One test per kind word; a proposal accepted by a person; a proposal filed by an agent; a readiness row with `note`; a related row (`↳ KEY`) and a non-related one (`—`); `page_has_why` false then true; `activity_columns` in plain and technical modes and `with_why` off; `filter_title` for the four states; `row_matches` hit and miss; `display.find_technical` finds nothing in plain cells of every row used; an unknown event type falls back to `humanize`.

## Report requirements
`docs/templates/haiku-report.md`, <= 60 lines; deviations first; paste the two command outputs (<= 5 lines each).

## Commit
`P2-INS-T01: <imperative summary>`; trailer lines as `docs/build-spec/SUPERVISOR-PROMPT.md`; no model names. Do not merge; do not push.

## Escalation triggers
- Stop and report *Blocked* if `ActivityRow` differs from the pasted block; an existing helper you need is private; a word in the table has no `labels` source.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
