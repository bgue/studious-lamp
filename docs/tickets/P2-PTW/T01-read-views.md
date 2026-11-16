# P2-PTW-T01 — Read views: permit register, board and counts

Status: staged (re-issue after P2-PTW-S2 merges: paste the `Interfaces` block verbatim from the S2 stub and report, then set ready)
Tier: haiku
Kind: ticket
Review: full
Labels: core-module, read, confidentiality
Depends on: P2-PTW-S2 (merged; it commits the stub `packages/tl-modules/permits/src/tl_mod_permits/views.py` and the provided test)
Branch: `p2/ptw-t01-views`
Worktree: harness-created under `/home/user/wt/ptw/t01` (from `p2/ip` head after S2)

## Goal
`tl_mod_permits.views` gives the CLI, API, MCP and screens one read layer over permits (`permit_list`, `permit_detail`, `permit_counts`, `permit_board(area)`, `permits_for`, `export_rows`; Lapsed through `rules.effective_state`). Nothing writes; no access word is checked here (entry points do). Every read takes keyword-only `viewer=`, default
`confidentiality.LOWEST` (never widened), and applies the hidden filter (the subject join of S2 is inside `hidden_sql`) before LIMIT and before counting. A hidden record is absent from lists, its detail
is `None`, counts never include it. At most two SQL statements per call; the views never read the clock (a `now` or `today` is a parameter).

## Brief references (pasted at re-issue)
> A permit is hidden through its subject; the board's counts are filtered like the list; Lapsed is shown in place of Active and is derived, never stored (design §4, §9).

## Interfaces (in the tree as a stub from S2: dataclasses final, function bodies raise `NotImplementedError`; fill the bodies, change no name, field or signature)
(paste verbatim from `packages/tl-modules/permits/src/tl_mod_permits/views.py` at re-issue)

## Context (read these, nothing else)
- `packages/tl-modules/permits/src/tl_mod_permits/views.py`, the S2 report `docs/reports/P2-PTW/S2.md`, `packages/tl-modules/permits/tests/permit_world.py` (the world helper S2 wrote)
- `packages/tl-modules/quality/src/tl_mod_quality/views.py` (the list, detail and counts pattern, abridged)
- the provided test `docs/tickets/P2-PTW/provided/T01_test_views.py` (committed by S2; do not edit it)

## Allowed paths
- `packages/tl-modules/permits/src/tl_mod_permits/views.py` (bodies only)
- `packages/tl-modules/permits/tests/test_views.py` (create: byte-identical copy of the provided test)
- `docs/reports/P2-PTW/T01.md` (create)

## Acceptance
```
just check
just gate packages/tl-modules/permits/tests/test_views.py
```
Expected: the provided tests pass; `cmp` of the test and the provided copy identical.

## Escalation triggers
A column the views need is not on the table; the provided test fails on a line the ticket does not explain (write the answer under Blocked; do not edit the test).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths listed (none expected). Commit subjects `P2-PTW-T01: ...` with the session trailers; no model names in committed text.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
