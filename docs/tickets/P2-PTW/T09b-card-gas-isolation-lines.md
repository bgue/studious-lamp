# P2-PTW-T09b - Permit scan card: the gas test and isolation lines

Status: ready (written r6; base `p2/ip-r3`; PTW-T09 and PTW-T02 merged)
Tier: haiku
Kind: ticket
Review: full
Labels: core-module, read, confidentiality, scan-card, safety
Depends on: P2-PTW-T09 (card), P2-PTW-T02 (`iso_views`), merged
Branch: `p2/ptw-t09b-card-lines`
Worktree: `/home/user/wt/ptw/t09b` (from `p2/ip-r3`)

## Goal
The card of `permits.Permit` gains the two lines T09 deferred (D21): the newest gas test and its result, and "isolations verified n/m". Still a pure read under the viewer; no write, no clock beyond `now`; a hidden permit still answers `None`.

## Rules (decided r6)
- Line count stays <= 8 (the contract bound): the six present lines plus these two. Order: `Type, Area, Holder, Location, For, Gas test, Isolations, Revalidated`; the existing cut-to-bounds helper applies. Label <= 24, value <= 80.
- `Gas test`: from `iso_views.gas_tests_for(conn, permit_id, viewer=viewer)[0]` (newest first): `<result> at HH:MM UTC` (`taken_at` in UTC; `result` as stored, capitalised: `Pass`, `Fail`). No test yet: the value `none taken` (the line is always present: for a safety card the absence is information). No reading values (O2, LEL) on the card.
- `Isolations`: only when the permit links any. `ids = guards.linked_isolations(conn, permit_id)`; visible rows = `iso_views.isolation_list(conn, scope, limit=500, viewer=viewer).rows` whose `id` is in `ids`, where `scope` is the permit's own scope already read for the detail; `m = len(visible)`, `n = count of rows with state "Verified"`; value `<n> of <m> verified`. An isolation the viewer cannot read counts in neither n nor m (hidden looks like missing). When `m == 0` after the filter the line is left out. A card never names an isolation.
- Banner, tone, `valid_until`, `open_path`, the other lines: unchanged. No new module import beyond `iso_views` and `guards` (same package). No other SQL.

## Interfaces (verbatim; abridged)
`iso_views.gas_tests_for(conn, permit_id, *, viewer) -> list[GasRow]` (newest first; `GasRow.result: str`, `taken_at: datetime`); `iso_views.isolation_list(conn, scope, *, state=None, energy=None, limit=100, viewer) -> IsolationPage` (`rows: list[IsolationRow]`, `IsolationRow.id`, `.state` in Applied|Verified|Removed); `guards.linked_isolations(conn, permit_id) -> list[str]`. Current `_lines(detail)` in `scan_card.py` takes only the detail: widen it to take `conn`, `viewer`, `scope` (or compute the two values in the caller and pass them in; keep it pure of SQL).

## Context (read these, nothing else)
- `packages/tl-modules/permits/src/tl_mod_permits/scan_card.py`, `packages/tl-modules/permits/tests/test_scan_card.py`, `packages/tl-modules/permits/tests/permit_world.py` (names of the gas-test and isolation helpers; if none, the commands in `test_gas_commands.py` and `test_isolation_commands.py` show how a test makes them)
- `docs/reports/P2-PTW/T09.md`, `docs/reports/P2-IP/PTWT06a.md` (isolation verbs, for the walk), `packages/tl-modules/permits/src/tl_mod_permits/iso_views.py` (signatures only)

## Allowed paths
- `packages/tl-modules/permits/src/tl_mod_permits/scan_card.py` (edit)
- `packages/tl-modules/permits/tests/test_scan_card.py` (edit: update the exact-lines assertions that now see two more lines; list them; add the tests below)
- `docs/reports/P2-IP/PTWT09b.md` (create)

## Tests to add (in `test_scan_card.py`)
- no gas test: `Gas test` is `none taken`; after a passing test (real `RecordGasTest` command) `Pass at HH:MM UTC`; after a later failing one the newest decides (`Fail ...`) and the card is still the permit's state banner (the S3 auto-suspend makes it `SUSPENDED`: assert both).
- isolations: none linked, no line; two linked, one Verified: `1 of 2 verified`; both Verified `2 of 2 verified`; after `unlink` the count follows.
- hidden isolation: link an isolation whose point record is restricted; the lowest-clearance viewer sees `m` without it and never its text; a permit hidden for the viewer is still `None`.
- lines are <= 8 on a permit that has every optional line; the contract test (`test_the_provider_keeps_the_scan_card_contract`) stays green.
- the card reads no more statements than before plus the two reads (a statement-count assertion in the style of `test_views.py` if one exists; else skip and say so).

## Acceptance
```
uv run ruff format --check packages/tl-modules/permits/src/tl_mod_permits/scan_card.py packages/tl-modules/permits/tests/test_scan_card.py
uv run ruff check packages/tl-modules/permits/src/tl_mod_permits/scan_card.py packages/tl-modules/permits/tests/test_scan_card.py
uv run pyright packages/tl-modules/permits/src/tl_mod_permits/scan_card.py packages/tl-modules/permits/tests/test_scan_card.py
just gate packages/tl-modules/permits/tests/test_scan_card.py packages/tl-modules/permits/tests/test_iso_views.py tests/contract/test_scan_card_contract.py
```
Expected: clean; `gate: PASS`. No `just check`, no whole-repo pyright.

## Escalation triggers
The five-reader or contract harness tests in `tests/contract` fail for a reason other than the line count; `guards.linked_isolations` needs a viewer; the lines would pass 8.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; list each assertion updated. Commit subjects `P2-PTW-T09b: ...` with the trailers the dispatch message names; no model names.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
