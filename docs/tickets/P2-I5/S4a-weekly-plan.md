# P2-I5-S4a — weekly plan commands, commitments, outcomes, PPC (S4 part A)

Status: ready (S1, S2 merged; pairs with S3 in one round, disjoint paths)
Tier: builder
Kind: piece
Review: full
Labels: core, commands
Depends on: S1 (week events, `awp.WeeklyPlan`, `cur_awp_weekly_plan`, `cur_awp_week_commitment`, workflow `awp-weekly-plan`, words), S2 (`progress.engine.ppc`, module wiring)
Branch: `p2/i5-s4a-weekly-plan`
Worktree: `/home/user/wt/i5-s4a`
Approver: orchestrator APPROVALS line (new access-worded commands; P2-Q10) and the human gate named in STATE (S4); no schema in this piece

## Goal
A planner opens the plan of a project week, foremen commit Issued IWPs to it, the outcome of each commitment is recorded (done, or missed with a reason), and closing the week writes the PPC. The projectors, events, words and workflow exist (S1);
this piece writes the handlers, the command models, the small read functions the CLI and API tickets (T03, T04, T11a2) will call, and the ADR-0027 rows. Owns `module.py`, `names.py`, `commands.py` edits for these four commands.

## Brief references (pasted)
- One plan per project and ISO week; key `<project>-WK-<year>W<ww>` composed from the week, no allocator; workflow Draft -> Committed -> Closed (`schema/fixtures/workflows/awp-weekly-plan.yaml`; every move is made by a command of the module).
- Words (S1): `awp.week.plan` (user), `awp.week.commit` (user), `awp.week.close` (controller). Reason cap 300 (`MAX_CLEAR_REASON`). Decimals are text with one decimal; dates `YYYY-MM-DD`.
- Events (S1, `week_events.yaml`): `WeeklyPlan.Opened {week, week_start, at}`, `.IwpCommitted {iwp_id, foreman, committed_hours, at}`, `.OutcomeRecorded {iwp_id, outcome, miss_reason, at}`, `.Closed {ppc, at}`; the first three carry `feed_policy: none`. A second commit of the same IWP replaces the row (projector).
- PPC (math rule 4): done commitments / all commitments, a count, 1 dp half-up (`progress.engine.ppc`).

## Interfaces to build (names fixed here)
```python
# tl_mod_awp/commands.py additions (extra="forbid"; expected_version on every edit of an existing plan)
OpenWeeklyPlan      # project scope, week_start: date (any day; normalised to its Monday), week derived; access awp.week.plan
CommitIwpToWeek     # plan_id, iwp_id, committed_hours: Decimal text 1 dp, foreman: actor text | None (default: the IWP's foreman field, else the actor), expected_version; access awp.week.commit
RecordWeekOutcome   # plan_id, iwp_id, outcome: "done"|"missed", miss_reason: str | None, expected_version; access awp.week.commit
CloseWeek           # plan_id, expected_version; access awp.week.close
# tl_mod_awp/handlers/week.py (new); tl_mod_awp/week_views.py (new, reads only)
def list_weeks(conn, scope: str, viewer: Viewer, *, limit: int = 60) -> list[WeekRow]
def week_detail(conn, plan_id: str, viewer: Viewer) -> WeekDetail           # plan, commitments (IWP keys and states), ppc, notes; one not-found for a plan the viewer cannot open
def miss_reasons(conn, scope: str) -> list[str]                              # keys of the code list MissReason of the adopted edition (print keys, L-P2-I3-3)
```
Rules (fixed-text `AwpError` subclasses in `errors.py`; never echo input):
1. Open: one plan per project and week (a second open is refused `weekly plan: week already open`); `week` ISO year-week of the Monday; the plan starts Draft.
2. Commit: plan Draft or Committed (not Closed); the IWP is in state Issued or In progress, in the plan's project, visible to the actor; `committed_hours` > 0 and <= 9999999999.9; the first commit moves the plan Draft -> Committed (workflow move `commit`, by_module); a re-commit replaces.
3. Outcome: plan Committed; the IWP is committed in it; `missed` requires `miss_reason` in `miss_reasons(conn, scope)`; `done` refuses a reason; the outcome may be corrected until the plan is Closed (a new event, never an edit).
4. Close: plan Committed; at least one commitment, else `weekly plan: nothing committed`; every commitment has an outcome, else `weekly plan: outcomes missing`; PPC from `engine.ppc`; moves `close`; `WeeklyPlan.Closed` makes the feed card. A Closed plan takes no further week command.
5. Stale `expected_version` is the existing stale-version error. Every payload key a handler writes is declared in `week_events.yaml`; if one is missing stop and escalate (no schema edit here).
**ADR-0027:** one `ProposableCommand` row for `CommitIwpToWeek` (tool `propose_week_commitment`, access `user`); `OpenWeeklyPlan`, `RecordWeekOutcome`, `CloseWeek` go to `tests/tools/proposable_exclusions.toml` with the reason `a week is judged by the people who planned it` if the file exists on the base; if not, write the three lines in the report for the merge and add nothing else.
**ADR-0025:** handlers never read `intent` (say so in the report).

## Context (<= 12 files)
`packages/tl-modules/awp/src/tl_mod_awp/{module,names,commands,errors,common,guards}.py`; `handlers/progress.py`, `handlers/iwp.py` (patterns); `projectors/week.py`; `progress/engine.py` (`ppc`, `round_half_up`);
`schema/modules/awp/{week,week_events}.yaml`; `schema/fixtures/workflows/awp-weekly-plan.yaml`; `docs/reports/P2-I5/S1.md`, `S2.md`. Learn how a handler creates a record with a composed key from `handlers/cwp.py` or `handlers/iwp.py`.

## Allowed paths
- `packages/tl-modules/awp/src/tl_mod_awp/{handlers/week.py,week_views.py}` (new); `commands.py`, `names.py`, `module.py`, `errors.py` (additions only)
- `packages/tl-modules/awp/tests/{test_week.py (new),progress_world.py (extend)}`
- `tests/tools/proposable_exclusions.toml` (lines appended, if the file exists)
- `docs/reference/openapi.json` (regenerated: `python -m tl_api.openapi`), pinned lists written as the union and listed in the report: `packages/tl-api/tests/test_commands.py` (command count, +4), `packages/tl-mcp/tests/test_mcp_write_tools.py` (proposing tools, +`propose_week_commitment`), `tests/services/test_modules.py` if it pins command words
- `dev/accept/P2-I5/S4a.py`, `docs/reports/P2-I5/S4a.md` (create)
Not allowed: schema, `tl_core/**`, `actions.py` (a row for the screens is a ticket), other modules, `tl-cli`, `tl-tui`, `tl-mcp` source, `tl-api` source (registrations are supervisor glue at C2).

## Acceptance (run once each)
```
just check
uv run python dev/accept/P2-I5/S4a.py
just gate packages/tl-modules/awp/tests
just gate packages/tl-api/tests/test_commands.py packages/tl-mcp/tests/test_mcp_write_tools.py tests/services/test_modules.py
```
`S4a.py` (SQLite, dialect-neutral; helper `check(name, ok)` prints `PASS <name>` only when true, else exits 1; final `S4a ok`): open twice is refused; a Monday-normalised `week` of 2026-11-04 is `2026-W45`; commit moves the plan to Committed; a Ready IWP and an IWP of another project are refused; re-commit replaces the hours (one row);
a stale `expected_version` is refused; `missed` without a reason, with an unknown reason, and `done` with a reason are refused; close with an unjudged commitment is refused; 3 done of 4 closes at `75.0` and the plan is Closed; close of an empty plan is refused; a command on a Closed plan is refused;
a plain user cannot close (`awp.week.close`); a viewer who cannot open the plan gets not-found from `week_detail`; an agent proposal `propose_week_commitment` is accepted only by a person holding `awp.week.commit`.

## Tests to add
`packages/tl-modules/awp/tests/test_week.py`: each rule above, the feed card on Closed only, and **rebuild equality** (rebuild all projections from the ledger; `cur_awp_weekly_plan` and `cur_awp_week_commitment` equal the live tables, ppc included).

## Report requirements
Deviations first; <= 60 lines; the three `grep` answers (`intent` in `handlers/week.py`; every payload key written vs declared in `week_events.yaml`; `viewer` in `week_views.py`); pinned files changed; mutation: sentinel plus <= 5 (PPC rounding, the stale-version check, the Issued-state guard, the miss-reason check, the close word) in 3 lines.
## Escalation triggers
A payload key the schema lacks; the dispatcher cannot give a handler the viewer; the workflow move `commit` cannot be made by the module; a frozen contract change.
## Blocked
(builder writes here)
## Decision
(supervisor or orchestrator writes here)
