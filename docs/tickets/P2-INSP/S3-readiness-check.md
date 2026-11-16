# P2-INSP-S3 - Readiness check `inspections_planned` for real

Status: staged (written r5; **waits for X4 on trunk** (D8); build, gate and review may start on `p2/ip-r3`; merges BEFORE PTW-S4: same awp pyproject file)
Tier: ticket (full review, inside a workflow: the `t` of the plan; the orchestrator picks the implementer tier)
Kind: ticket
Review: full
Labels: readiness, quality, awp
Depends on: P2-INSP-S2 and T01 (merged); X4 on trunk
Branch: `p2/insp-s3-readiness`
Worktree: `/home/user/wt/insp/s3` (from `p2/ip-r3`)

## Goal
The readiness check `inspections_planned` answers for real from the quality module, under the same name and the frozen contract (`tl_core/readiness/types.py`): the awp placeholder's entry-point line is removed and the quality package registers the check (two checks with one name is an error by contract). Answers are the table of `docs/build-spec/module-designs/inspections.md` section 5.

## Rules
- `packages/tl-modules/quality/src/tl_mod_quality/checks.py` (create): `evaluate(conn, iwp, today)` returns a `CheckResult` with `resolve_via` (at most `MAX_RESOLVE_VIA`), `count_ok` (Scheduled or better) and `count_total` (cancelled ones count in neither), a detail of keys and counts only (never a title or text), a read-only statement set over `cur_quality_inspection` joined to the IWP by `for_iwp_id`; `watches` is `{"quality.Inspection"}`; a failed read is `unknown` with a fixed detail; never raises, never writes, takes no viewer (a job runs it).
- Rows: `n_a` (none and `quality.inspections.required_for_iwp` off); `blocked` (setting on and none planned; a linked Planned inspection; a hold-point inspection Done with `reject` and no reinspection child); `pending` (all Scheduled or better and one scheduled before `iwp.planned_start` not yet Done); else `ok`. A hold point not yet released does not un-ready an issued IWP.
- The setting is read the way the other module checks read theirs (see `tl_mod_materials/readiness.py`, `tl_mod_documents/readiness.py`; scope `iwp.scope`); if a check cannot read a setting through the contract, stop (escalation).
- Entry point `inspections_planned = "tl_mod_quality.checks:inspections_planned"` under `throughline.readiness_checks` in the quality `pyproject.toml`; delete the line of the same name from `packages/tl-modules/awp/pyproject.toml` and the placeholder function from `checks_na.py` (docstring list updated; the other four stay). Run `uv sync --offline --all-packages --all-extras` once after editing a pyproject so entry points are re-read; no dependency is added.
- Pattern: `tl_mod_documents/readiness.py` and `packages/tl-modules/documents/tests/test_documents_current.py` (`ContractWorld`, `check_readiness_contract`).

## Context (read these, nothing else)
- `docs/build-spec/module-designs/inspections.md` section 5, `packages/tl-core/src/tl_core/readiness/types.py`
- `packages/tl-modules/documents/src/tl_mod_documents/readiness.py`, `tests/test_documents_current.py`
- `packages/tl-modules/awp/src/tl_mod_awp/checks_na.py`, `packages/tl-core/tests/test_readiness_registry.py`, `dev/accept/P2-I2/T06b.py`
- `packages/tl-modules/quality/src/tl_mod_quality/names.py`, `tests/insp_world.py`

## Allowed paths
- `packages/tl-modules/quality/src/tl_mod_quality/checks.py` (create), `packages/tl-modules/quality/pyproject.toml` (the one entry), `packages/tl-modules/awp/pyproject.toml` (the one line removed), `packages/tl-modules/awp/src/tl_mod_awp/checks_na.py` (the placeholder removed)
- `packages/tl-modules/quality/tests/test_readiness.py` (create)
- Pins (rule 12, list each): `packages/tl-core/tests/test_readiness_registry.py` (the name set is unchanged; edit only if it fails), `dev/accept/P2-I2/T06b.py` (the placeholder's `EXPECTED` row removed, a line noting the check now comes from the quality module; the script still exits 0), any test that lists the awp placeholders by name
- `docs/reports/P2-INSP/S3.md` (create)

## Tests to add (`test_readiness.py`; inspections made by the real commands of `insp_world.py`; `today` is the only clock)
1. None and setting off: `n_a`; setting on and none: `blocked`.
2. A linked Planned inspection: `blocked`, `resolve_via` names it; a hold-point Done with reject and no reinspection: `blocked`; after the reinspection exists: not blocked.
3. All Scheduled or better and one before `planned_start` not Done: `pending`; all Scheduled or better: `ok`; `count_ok/count_total` as above; a Cancelled inspection counts in neither.
4. An unreleased hold point on an issued IWP stays `ok`.
5. `check_readiness_contract` passes; the registry loads exactly one `inspections_planned`; the detail holds no record title.

## Acceptance
```
uv run ruff format --check packages/tl-modules/quality packages/tl-modules/awp
uv run ruff check packages/tl-modules/quality packages/tl-modules/awp
uv run pyright packages/tl-modules/quality/src/tl_mod_quality/checks.py packages/tl-modules/quality/tests/test_readiness.py
just gate packages/tl-modules/quality/tests/test_readiness.py packages/tl-core/tests/test_readiness_registry.py
uv run python dev/accept/P2-I2/T06b.py
```
Expected: clean; `gate: PASS`; the acceptance script exits 0. No `just check`, no whole-repo pyright.

## Escalation triggers
The contract cannot express a row; the check needs a table the module does not own; a setting cannot be read; the entry-point change moves a pin outside the list above.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins listed. Commit subjects `P2-INSP-S3: ...` with the trailers the dispatch message names; no model names.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
