# P2-I4B-T09c — Error rows for the scaffold refusals at the API door

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: api
Depends on: T09a (merged)
Branch: `p2/i4b-t09c-error-rows`
Worktree: `/home/user/wt/i4b/t09c` (from `p2/i4b` head)

## Goal
A domain refusal of a scaffold command (a second scaffold on one request, release without a green tag, a dismantle that an open IWP holds) answers with a stable code and its own text instead of 500 `internal_error` (T09a open question; needed by the demo, T10a). Same shape as the punch rows.

## Brief references (pasted)
> `tl_api/errors.py` is the one place that maps a `ServiceError` subclass to a status and stable code; a subclass without a row fails `test_error_table.py` for `tl_core` only, so the scaffold classes were missed.

## Interfaces (verbatim from repo at the branch point)
`tl_mod_scaffold.errors`: `ScaffoldError` (base), `ScaffoldScopeError`, `ScaffoldRuleError`, `DismantleRefused`, `ScaffoldStateError`, `StaleVersionError` (module's own, subclass of `ScaffoldError`). Existing rows to copy: `errors.py` lines 398-402 (quality: `s(qual.QualityError, "quality_error", 422)`, `QualityScopeError` 422, rule 422, state 409).
Rows to add after the quality block, with import `from tl_mod_scaffold import errors as scf` (sorted into the import block): `ScaffoldError "scaffold_error" 422`, `ScaffoldScopeError "scaffold_scope" 422`, `ScaffoldRuleError "scaffold_rule" 422`, `ScaffoldStateError "scaffold_state" 409`, `DismantleRefused "scaffold_dismantle_refused" 409`, `StaleVersionError "scaffold_stale_version" 409`.

## Context (read these, nothing else)
- `packages/tl-api/src/tl_api/errors.py` (the table, lines 380-410, and the import block)
- `packages/tl-modules/scaffold/src/tl_mod_scaffold/errors.py`
- `packages/tl-api/tests/test_api_scaffold_commands.py` (how a person signs in and sends a command; reuse its helpers by import or copy)
- `packages/tl-api/tests/test_error_table.py`
may explore: grep for the code names in `docs/reference/` only to find a pinned list.

## Allowed paths
- `packages/tl-api/src/tl_api/errors.py` (edit)
- `packages/tl-api/tests/test_api_scaffold_errors.py` (create)
- consequential pins (listed in the report, union form): any test that counts or lists the error codes
- `docs/reports/P2-I4B/T09c.md` (create)

## Acceptance
```
just check
just gate packages/tl-api/tests/test_api_scaffold_errors.py packages/tl-api/tests/test_error_table.py packages/tl-api/tests/test_api_scaffold_commands.py packages/tl-api/tests/test_openapi_baseline.py
```
Expected: all pass. If `just check` reports `openapi.json` out of date, run `python -m tl_api.openapi` once and list it as a deviation (as T09a did).

## Tests to add
`test_api_scaffold_errors.py`: through the door as a person with the words: (1) a second `RegisterScaffold` for one approved request answers 422 `scaffold_rule` with a text, no 500; (2) `ReleaseScaffold` on an Erecting scaffold answers 409 `scaffold_state` or 422 `scaffold_rule` (whichever the handler raises: assert the code that matches its class, read `handlers/scaffold.py` for it); (3) `DismantleScaffold` with a stale `expected_version` is 409 `scaffold_stale_version` if the command carries one, else drop this case and say so; (4) every class in `tl_mod_scaffold.errors` that subclasses `ServiceError` has a row (walk the module with `inspect`, as the core test does).

## Report requirements
Standard report; list each code and status added.

## Escalation triggers
- Stop if a scaffold class already has a row, or the table is not where described.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
