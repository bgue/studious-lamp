# P2-PTW-S4 - Readiness check `permits_planned` for real

Status: staged (written r5; **waits for X4 on trunk** (D8) and for INSP-S3 to merge first: same `awp/pyproject.toml` file; build, gate and review may start on `p2/ip-r3`)
Tier: ticket (full review, inside a workflow: the `t` of the plan; the orchestrator picks the implementer tier)
Kind: ticket
Review: full
Labels: readiness, permits, awp
Depends on: P2-PTW-S2, S3 and T01 (merged); P2-INSP-S3 merged; X4 on trunk
Branch: `p2/ptw-s4-readiness`
Worktree: `/home/user/wt/ptw/s4` (from `p2/ip-r3`)

## Goal
The readiness check `permits_planned` answers for real from the permits module, under the same name and the frozen contract: the awp placeholder's entry-point line is removed and the permits package registers the check. Answers are the table of `docs/build-spec/module-designs/permits.md` section 6.

## Rules
- `packages/tl-modules/permits/src/tl_mod_permits/checks.py` (create): `evaluate(conn, iwp, today)` returns a `CheckResult` with `resolve_via` (at most `MAX_RESOLVE_VIA`; the permits to act on), `count_ok`/`count_total` over the linked permits that are not Cancelled, Closed or Rejected, a detail of keys and counts only, a read-only statement set over `cur_permits_permit` joined to the IWP by its `for_record_id`; `watches` is `{"permits.Permit"}`; a failed read is `unknown` with a fixed detail; never raises, never writes, no viewer.
- Rows: `n_a` (no permit names the IWP and `permits.required_for_iwp` off); `blocked` (setting on and none exists; or a linked permit is Rejected, Suspended or Lapsed and no other live permit of that type exists for the IWP); `pending` (a linked permit is Requested); `ok` (every linked permit that is not Cancelled, Closed or Rejected is Approved or Active and not Lapsed). **Lapsed is derived, not stored**, and the contract gives `today` as a date only: decide it with `tl_mod_permits.rules.effective_state(state, valid_until, now)` with `now` the start of `today` in UTC (`datetime.combine(today, time.min, tzinfo=UTC)`), so a permit whose `valid_until` is before today's start shows Lapsed (day granularity, as the QR rule of D16). Never a second rule, never a clock read. Q12 records the choice. Approved is enough (design text).
- The setting is read the way the other module checks read theirs (see `tl_mod_materials/readiness.py`, `tl_mod_documents/readiness.py`; scope `iwp.scope`); if a check cannot read a setting through the contract, stop.
- Entry point `permits_planned = "tl_mod_permits.checks:permits_planned"` under `throughline.readiness_checks` in the permits `pyproject.toml`; delete the line of the same name from `packages/tl-modules/awp/pyproject.toml` and the placeholder function from `checks_na.py` (docstring list updated; three stay after INSP-S3). `uv sync --offline --all-packages --all-extras` once after editing a pyproject; no dependency is added.
- Pattern: `tl_mod_documents/readiness.py` and `tests/test_documents_current.py`.

## Context (read these, nothing else)
- `docs/build-spec/module-designs/permits.md` section 6, `packages/tl-core/src/tl_core/readiness/types.py`
- `packages/tl-modules/documents/src/tl_mod_documents/readiness.py`, `tests/test_documents_current.py`
- `packages/tl-modules/awp/src/tl_mod_awp/checks_na.py`, `packages/tl-core/tests/test_readiness_registry.py`, `dev/accept/P2-I2/T06b.py`
- `packages/tl-modules/permits/src/tl_mod_permits/names.py`, `rules.py` (`effective_state` signature), `views.py` (how it applies it), `tests/permit_world.py`

## Allowed paths
- `packages/tl-modules/permits/src/tl_mod_permits/checks.py` (create), `packages/tl-modules/permits/pyproject.toml` (the one entry), `packages/tl-modules/awp/pyproject.toml` (the one line removed), `packages/tl-modules/awp/src/tl_mod_awp/checks_na.py` (the placeholder removed)
- `packages/tl-modules/permits/tests/test_readiness.py` (create)
- Pins (rule 12, list each): `packages/tl-core/tests/test_readiness_registry.py` (edit only if it fails), `dev/accept/P2-I2/T06b.py` (the placeholder's `EXPECTED` row removed, a line noting the check now comes from the permits module; exits 0), any test that lists the awp placeholders by name
- `docs/reports/P2-PTW/S4.md` (create)

## Tests to add (`test_readiness.py`; permits made by the real commands of `permit_world.py`)
1. None and setting off: `n_a`; setting on and none: `blocked`.
2. A Requested permit: `pending`; Approved or Active: `ok`; `count_ok/count_total` exclude Cancelled, Closed, Rejected.
3. Rejected, Suspended and Lapsed (clock past `valid_until`) with no other live permit of the type: `blocked`, `resolve_via` names it; with another live permit of that type: not blocked.
4. A Lapsed permit is not `ok` although stored Active; the check and `views.permit_detail` agree on the same day.
5. `check_readiness_contract` passes; the registry loads exactly one `permits_planned`; the detail holds no description text or holder name.

## Acceptance
```
uv run ruff format --check packages/tl-modules/permits packages/tl-modules/awp
uv run ruff check packages/tl-modules/permits packages/tl-modules/awp
uv run pyright packages/tl-modules/permits/src/tl_mod_permits/checks.py packages/tl-modules/permits/tests/test_readiness.py
just gate packages/tl-modules/permits/tests/test_readiness.py packages/tl-core/tests/test_readiness_registry.py
uv run python dev/accept/P2-I2/T06b.py
```
Expected: clean; `gate: PASS`; the acceptance script exits 0. No `just check`, no whole-repo pyright.

## Escalation triggers
The contract cannot express a row; Lapsed cannot be decided from `today` and the stored fields through `effective_state`; a setting cannot be read; the entry-point change moves a pin outside the list above.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins listed. Commit subjects `P2-PTW-S4: ...` with the trailers the dispatch message names; no model names.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
