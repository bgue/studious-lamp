# P2-INSP-T01 — Read views: checklists and inspections

Status: staged (re-issue after P2-INSP-S2 merges: paste the `Interfaces` block verbatim from the S2 stub and report, then set ready)
Tier: haiku
Kind: ticket
Review: full
Labels: core-module, read, confidentiality
Depends on: P2-INSP-S2 (merged; it commits the stub `packages/tl-modules/quality/src/tl_mod_quality/insp_views.py` and the provided test)
Branch: `p2/insp-t01-read-views`
Worktree: harness-created under `/home/user/wt/insp/t01` (from `p2/ip` head after S2)

## Goal
`tl_mod_quality.insp_views` gives the CLI, API, MCP and screens one read layer over checklists and inspections (`inspection_list`, `inspection_detail`, `inspection_counts`, `inspections_for`, `checklist_list`, `checklist_detail`, `export_rows`). Nothing writes; no access word is checked here (entry points do). Every read takes keyword-only `viewer=`, default
`confidentiality.LOWEST` (never widened), and applies the hidden filter (the subject join of S2 is inside `hidden_sql`) before LIMIT and before counting. A hidden record is absent from lists, its detail
is `None`, counts never include it. At most two SQL statements per call; the views never read the clock (a `now` or `today` is a parameter).

## Brief references (pasted at re-issue)
> Hidden looks like missing: an inspection whose subject is hidden is absent from lists, its detail is `None`, counts and totals never include it (design §7, §8).

## Interfaces (in the tree as a stub from S2: dataclasses final, function bodies raise `NotImplementedError`; fill the bodies, change no name, field or signature)
(paste verbatim from `packages/tl-modules/quality/src/tl_mod_quality/insp_views.py` at re-issue)

## Context (read these, nothing else)
- `packages/tl-modules/quality/src/tl_mod_quality/insp_views.py`, the S2 report `docs/reports/P2-INSP/S2.md`, `packages/tl-modules/quality/tests/punch_world.py (or the `insp_world.py` S2 added)` (the world helper S2 wrote)
- `packages/tl-modules/quality/src/tl_mod_quality/views.py` (the list, detail and counts pattern, abridged)
- the provided test `docs/tickets/P2-INSP/provided/T01_test_insp_views.py` (committed by S2; do not edit it)

## Allowed paths
- `packages/tl-modules/quality/src/tl_mod_quality/insp_views.py` (bodies only)
- `packages/tl-modules/quality/tests/test_insp_views.py` (create: byte-identical copy of the provided test)
- `docs/reports/P2-INSP/T01.md` (create)

## Acceptance
```
just check
just gate packages/tl-modules/quality/tests/test_insp_views.py
```
Expected: the provided tests pass; `cmp` of the test and the provided copy identical.

## Escalation triggers
A column the views need is not on the table; the provided test fails on a line the ticket does not explain (write the answer under Blocked; do not edit the test).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths listed (none expected). Commit subjects `P2-INSP-T01: ...` with the session trailers; no model names in committed text.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
