# P2-PUNCH-T07 — Generator: the `quality` section builds punch items

Status: staged (dispatch after S2 merges; disjoint from T01)
Tier: haiku
Kind: ticket
Review: full
Labels: seed, tests
Depends on: S2 (merged)
Branch: `p2/punch-t07-seed`
Worktree: harness-created under `/home/user/wt/punch/t07` (from `p2/punch` head)

## Goal
`dev/seed/demo_project/quality.py` (a stub that prints `quality: not built yet`; the registry skips the section while `quality.PunchItem` is not installed, and it is installed now) builds about 30 punch items on P200 through the real command handlers, one unit of work per command, as the roster people. The section keeps `register("quality", build, needs=("quality.PunchItem",))`. Commands are the S2 models (`tl_mod_quality.commands`; `from_record_id` is a record id, `due_on` an ISO date, `assignee` text like `user:cbrooks`). Do not pass `at` on clear or verify: it defaults to now and may not be before the day the item was raised (real clock), so `cleared_on` and `verified_on` are real dates while `due_on` follows the project calendar. The build draws from its own `rng` and the project calendar (`START`, `TODAY`); nothing reads the clock.

## Brief references (pasted)
> People (`dev/seed/demo_project/core.py` `PEOPLE`): `hsato` (Hana Sato, quality inspector) raises and verifies; the foremen `cbrooks` (piping) and `pnair` (civil) are assignees and clear; `ipetrov` and `lhartmann` may raise. The verifier must differ from the clearer (S2). `hsato` gets `("quality", "superuser")` in `PEOPLE` (the only roster change; `grant_module_role` as the other grants).
> Items (about 30): 12 Open (3 overdue, `due_on` before `TODAY`), 8 Cleared, 7 Verified, 2 Void (one voided from Open, one from Cleared), 1 reopened once (Cleared then Reopened, back to Open, `reopen_count` 1). Sources: 14 raised from IWPs (the constraints section makes the IWPs), 6 from engineering tags, 2 from CWPs, the rest free-standing; categories A, B, C in the ratio 3:5:2; areas the six `AREAS` codes; systems from the awp WBS system level when present, else text like `47-01`. Two sources are restricted correspondence items when the correspondence section ran (raised by `ipetrov`, a document controller); with none, say so in the section's printed note.
> The section prints nothing of its own beyond what the runner prints (`quality: <n> records, <m> events, <t>s`).

## Context (read these, nothing else)
- `dev/seed/demo_project/quality.py`, `constraints.py` (lines 1-60 and 95-140: how a section reads earlier records and runs handlers), `world.py` (`run`, `on`, `rows`)
- `dev/seed/demo_project/core.py` (`PEOPLE` and the grant loop), `registry.py`
- `docs/reports/P2-PUNCH/S2.md` (command models and handlers), `tests/tools/test_demo_project_materials.py` (lines 1-60: the child-process pattern)

## Allowed paths
- `dev/seed/demo_project/quality.py`, `dev/seed/demo_project/core.py` (the one grant line)
- `tests/tools/test_demo_project_quality.py` (create); consequential pins in union form, listed: `tests/tools/test_demo_project.py` (the total counts; the runbook says about 2034 records), `tests/tools/test_demo_project_anchors.py` if it fails
- `docs/runbooks/demo-project.md` (the `quality` section row, the new totals, and the removal of the "skipped" sentence for quality)
- `docs/reports/P2-PUNCH/T07.md` (create)

## Acceptance
```
just check
just gate tests/tools/test_demo_project_quality.py tests/tools/test_demo_project.py tests/tools/test_demo_project_awp.py
```
(the demo-project gates take minutes: background.)

## Tests to add
`tests/tools/test_demo_project_quality.py` (child process on a fresh SQLite ledger, `--sections core,engineering,awp,constraints,quality`): the counts above by state; every item has a key `P200-PUN-nnnn` with no gap; `reopen_count` 1 on exactly one item; three items overdue (`due_on < TODAY`, state Open); every non-free-standing item has one `raised_against` link to an existing record; for each Verified item `verified_by` differs from `cleared_by`; two runs with one seed give the same keys and states; the same run without `quality` in `--sections` leaves the rest of the project byte-identical in record counts for the other types; with `--sections core,quality` (no sources) the section builds only free-standing items and does not fail.

## Escalation triggers
- A handler name or command field differs from the S2 report (the merged code wins: report it first); a pinned count in another test file breaks (list it, update as union); the section needs a source record type no earlier section makes.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths (rule 12) listed. Commit subjects `P2-PUNCH-T07: ...`; the commit body ends with the trailer lines `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
