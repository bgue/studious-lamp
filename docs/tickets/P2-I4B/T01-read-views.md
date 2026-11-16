# P2-I4B-T01 — Read views: scaffold register, detail, due list and the exported register

Status: ready (the provided test and the interface stub are committed on `p2/i4b`; dispatch now)
Tier: haiku
Kind: ticket
Review: full
Labels: core-module, read, confidentiality
Depends on: S1 (merged, C1)
Branch: `p2/i4b-t01-views`
Worktree: `/home/user/wt/i4b/t01` (from `p2/i4b` head)

## Goal
`tl_mod_scaffold.views` gives the API, the client fakes, the screens and the exports one read layer: the register, one scaffold with its inspections, the due list and `export_rows`
(CSV or JSONL; owner rule 2026-11-14: a report is a simple export). Nothing writes; no access word is checked here (entry points do). Every read takes keyword-only `viewer=`,
default `confidentiality.LOWEST`, and hides a scaffold through `confidentiality.not_hidden*` on the scaffold record id before LIMIT and before counting. A scaffold's inspections are
hidden with it (S1 `SUBJECT_LINKS`); the detail reads them only after the scaffold passed the filter.

## Brief references (pasted)
> Pattern: `packages/tl-modules/quality/src/tl_mod_quality/views.py` (same shape: `_FROM` join, `COALESCE(r.status, ...)` state, `not_hidden` in list and counts, `not_hidden_each` in detail, `text()` SQL, clamp 1..`MAX_LIMIT`). Tables: `cur_scaffold_scaffold t` JOIN `cur_core_record r ON r.id = t.id`; the request key by LEFT JOIN `cur_core_record rq ON rq.id = t.request_id`; the served record key by LEFT JOIN `cur_core_record sv ON sv.id = t.for_record_id`; inspections `cur_scaffold_scaffold_inspection i` JOIN `cur_core_record ir ON ir.id = i.id`.
> State: `COALESCE(r.status, 'Requested')` (`names.REQUESTED`). Standing states for the due list: `rules.STANDING_STATES` (Inspected, In Use, Modify). Overdue (list filter) = standing and `t.next_due_on < :today`; due list = standing and `t.next_due_on <= :today`, ordered `t.next_due_on, r.key, r.id`. Dates are ISO text, compared as text; the views never read the clock.
> Hidden looks like missing: absent from lists, detail `None`, `total` never counts it. Statements: list 2 (count, rows), detail 2 (scaffold, inspections), due list 1.
> Row fields: `subject` = `r.title`; `location` = `t.location_text`; `request_key` = `rq.key`; `for_key` = `sv.key`; inspection `tag` = `i.tag`, `inspector` = `i.inspector`, `inspected_on`, `result`, `note`, `key` = `ir.key` (check the column names against `schema/modules/scaffold/scaffold.yaml`).
> Export: `EXPORT_COLUMNS` order, never `id`. CSV: header line, one line per row, `\n` line ends (`csv.writer(lineterminator="\n")`), `None` is an empty cell, and a text cell starting with `=`, `+`, `-` or `@` is written with a leading `'` (spreadsheet formula guard; CSV only). JSONL: one `json.dumps` object per line in column order, `None` is `null`, no guard, last line ends with `\n`; no rows give `""` (CSV: the header line alone). Any other `fmt` (case-sensitive) is `ValueError`.
> Errors: unknown `state` (not one of `names` states `Requested Designed Erecting Inspected In Use Modify Dismantle Removed`) or `tag` (not `green yellow red`) is `ValueError`; `overdue` without `today` is `ValueError`.

## Interfaces (in the tree as a stub: dataclasses, constants and the four signatures are final; fill the four bodies, change no name, field or signature)
`packages/tl-modules/scaffold/src/tl_mod_scaffold/views.py` (read it first: it is the interface).

## Context (read these, nothing else)
- `packages/tl-modules/scaffold/src/tl_mod_scaffold/{views.py, names.py, rules.py}`, `docs/reports/P2-I4B/S1.md`
- `packages/tl-modules/quality/src/tl_mod_quality/views.py` (the pattern)
- the provided test `docs/tickets/P2-I4B/provided/T01_test_views.py` (do not edit it); `packages/tl-modules/scaffold/tests/{scaffold_world.py, conftest.py}` (they exist, nothing to add)
may explore: `schema/modules/scaffold/scaffold.yaml` (column names only)

## Allowed paths
- `packages/tl-modules/scaffold/src/tl_mod_scaffold/views.py` (bodies and private helpers; add `import csv, io, json` as needed)
- `packages/tl-modules/scaffold/tests/test_views.py` (create: byte-identical copy of the provided test)
- `docs/reports/P2-I4B/T01.md` (create)

## Acceptance
```
cp docs/tickets/P2-I4B/provided/T01_test_views.py packages/tl-modules/scaffold/tests/test_views.py
just check
just gate packages/tl-modules/scaffold/tests/test_views.py
cmp docs/tickets/P2-I4B/provided/T01_test_views.py packages/tl-modules/scaffold/tests/test_views.py
```
Expected: the 14 provided tests pass on sqlite (and on Postgres under `just gate-pg packages/tl-modules/scaffold/tests/test_views.py`, run once); `just check` clean; `cmp` silent.

## Tests to add
The provided test (copied). It builds the ledger only through commands (`World.call`; a hidden scaffold is a restricted correspondence item made with the helper plus the one projection write S1's visibility test also makes): list order, fields, filters, overdue with fixed far and past days, limit clamp and `total`, detail with inspections and reasons, absent and foreign-project keys, the due list (inclusive day, standing states only, limit, drops out when dismantled), hidden scaffolds for the lowest and a cleared viewer in all three reads, statement bounds, and the CSV and JSONL export (header, quoting, formula guard, `None`, empty, unknown format).

## Escalation triggers
- A column the views need is not on the tables; the provided test fails on a line the ticket does not explain (write the answer under Blocked; do not edit the test).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first, <= 5 decisive lines per command; pins updated outside Allowed paths (rule 12) listed (none expected). Commit subjects `P2-I4B-T01: ...`; the commit body ends with the trailer lines your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files. Do not run the whole suite.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
