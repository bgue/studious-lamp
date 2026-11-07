# P2-I2-T04b — constraint text module, review screen and per-record constraint log

Status: staged (dispatch after T04c2 merges)
Tier: haiku
Kind: ticket
Review: full
Labels: tui, read, confidentiality
Depends on: T04c2
Branch: `p2/i2-t04b-constraint-screen`
Worktree: harness-created under `/home/user/wt/i2/t04b` (from `p2/i2` head)

## Goal
`tl_tui/constraint_text.py` (Textual-free pure functions, so the web twin TW2 uses the same words) and one `LogScreen` over it, `ConstraintScreen(client, project, subject_key=None)`: with no subject it is the constraint review of the project (one log, grouped on request); with a subject key it is that record's constraint log (heading `Constraints on <key>`). Pattern: P2-I1 T05a and T05d (`docs/tickets/P2-I1/T05a-cwp-text.md`, `T05d-cwp-screen.md`; `awp_text.py`, `widgets/cwp_register.py` are the models). Skill `tui-layout` applies (load it).

## Brief references (pasted; module design "Constraint review")
> One log grouped by owner then type: Constraint, IWP, Type, Owner, Need by, Age, Source. Actions: Assign, Clear, Escalate (notify), Open IWP (writes are not in this increment: `actions_for` returns `[]`).
Read model (T04c2 client; no read per row, no lookup of a subject): `client.list_constraints(project, subject=, state=, category=, phase=, blocking=, owner=, limit=)` -> rows and `total`; row fields `key state category severity owner phase due_at age_days aging source subject_key subject_type description`; `client.constraint_groups(project, by)` with `by` in `owner|category|age` -> groups `label count blocking aging truncated`; `client.get_constraint(project, key)`.

## Interfaces (create; names exact)
```python
# constraint_text.py
CONSTRAINT_COLUMNS = ("Constraint", "Subject", "Type", "State", "Owner", "Need by", "Age", "Source")
CONSTRAINT_DROP = ("Source", "Need by")      # dropped first at narrow width
CONSTRAINT_RIGHT = ("Age",)
def constraint_cells(row, labels=None) -> tuple[str, ...]   # Type = humanized category; Owner `-` when none; Need by date part or `-`; Age `<n> d`, `<n> d !` when aging; Source humanized
def constraint_summary(total, shown, *, by=None, blocking=0, aging=0, truncated=False) -> str   # `12 constraints, 4 blocking, 3 aging` / `5 of 12 ...` / `, grouped by owner` / `(first 500 only)`
def order_by_group(rows, by) -> list      # by owner|category|age: group label then key; age by the AGE_BANDS order of tl_core.constraints.review
def constraint_page(row, labels=None, technical=False, panel=False) -> Page   # identity line `<key> · <subject_key>`, state line, facts (type, severity, phase, owner, need by, source), description (limited), no ids; technical adds id-free technical rows only
```
Keys: `o` `t` `a` group by owner, type, age (same key again ungroups), `s` next state, `b` blocking only, `F5` reload; `KEY_HINTS` `/ filter  o owner  t type  a age  s state  b blocking  F5 reload  Esc back`. Enter on a row: `open_record` is not available (a constraint has no record screen here), so Enter shows the page in the panel and, at width < 120, as a modal text; hidden or missing -> error status line, no traceback.

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/awp_text.py` lines 1-130 (style: cells, `Page`, `Section`), `widgets/cwp_register.py` (all), `layout.py` names only, `widgets/log_screen.py` lines 96-225
- `packages/tl-core/src/tl_core/constraints/review.py` (AGE_BANDS, labels), `packages/tl-tui/tests/helpers.py` lines 1-60, `tests/fakes_iwp.py` (`seed_iwp`)

## Allowed paths
- `packages/tl-tui/src/tl_tui/constraint_text.py` (create), `packages/tl-tui/src/tl_tui/widgets/constraint_screen.py` (create)
- `dev/accept/P2-I2/T04b.py` (create), `docs/reports/P2-I2/T04b.md` (create)
Palette and nav entries and the IWP screen key that opens the per-record log are glue (T07c).

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I2/T04b.py            # no pytest
```
`T04b.py` (screen on `FakeClient` + `seed_iwp` through the Textual pilot as `tests/helpers.py` does): `PASS mount 80` and `PASS mount 170` (no line wider than the terminal; Subject not right of the third column; at 170 the panel shows heading, state and summary); `PASS keys` (`o t a` regroup and the order follows `order_by_group`, `b` cuts to the blocking rows, `s` cycles); `PASS subject` (`subject_key` given: only that subject's rows, heading names the key); `PASS truncated` (groups with `truncated` print the `(first 500 only)` note); `PASS missing` (`RecordNotFoundError` -> error status); `PASS words` no cell carries a 32-hex id. Ends `T04b ok`.

## Escalation triggers
- Stop if a column needs a field the client row lacks (write which; likely `subject_key`: T04c1 owes it), or a read per row would be needed.

## Tests to add
None (S5 / T-screens twins hold the pytest).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; the `tui-layout` checklist answered line by line (7 lines). Subject `P2-I2-T04b: ...`; trailer is the attribution lines your harness requires, then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
