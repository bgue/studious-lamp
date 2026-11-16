# Report — P2-PTW-S4 (run as P2-IP-PTWS4)

Branch: `p2/ptw-s4-readiness`   Commit(s): see `git log` (feature commit, then this report)

## Deviations
none. Branch is `p2/ptw-s4-readiness` as the dispatch says; report path is `docs/reports/P2-IP/PTWS4.md` as dispatched (the spec names `P2-PTW/S4.md`).

## Changed files
- `packages/tl-modules/permits/src/tl_mod_permits/checks.py` — new check `permits_planned` (create)
- `packages/tl-modules/permits/pyproject.toml` — the one entry point under `throughline.readiness_checks`
- `packages/tl-modules/awp/pyproject.toml` — the placeholder's line removed
- `packages/tl-modules/awp/src/tl_mod_awp/checks_na.py` — placeholder function removed, docstring says three
- `packages/tl-modules/permits/tests/test_readiness.py` — new tests
- Pin: `dev/accept/P2-I2/T06b.py` — the `permits_planned` EXPECTED row removed, a comment and an assertion that the check still loads
- Pin `test_readiness_registry.py`: not edited (it passes: the name set is unchanged)

## Commands and output
```
$ uv run ruff format --check ... / ruff check ...   -> 149 files already formatted / All checks passed!
$ uv run pyright checks.py test_readiness.py        -> 0 errors, 0 warnings
$ just gate test_readiness.py test_readiness_registry.py -> part 1: exit 0, 30 passed; gate: PASS
$ uv run python dev/accept/P2-I2/T06b.py            -> all PASS lines, exit 0
```
Mutation: sentinel (ok->pending) killed, 5/5 targeted killed (drop Suspended from problems; invert
live-type test; drop Closed from excluded; `time.min`->`time.max`; invert the setting flag).
`uv sync --offline --all-packages --all-extras` run once.

## Tests added
- `test_none_with_the_setting_off_is_n_a_and_on_is_blocked`
- `test_a_requested_permit_is_pending_and_approved_or_active_is_ok`
- `test_cancelled_closed_and_rejected_count_in_neither`
- `test_a_rejected_suspended_or_lapsed_permit_blocks_without_another_live_one`
- `test_a_lapsed_permit_blocks_and_another_live_one_of_its_type_unblocks`
- `test_a_suspended_permit_with_another_live_one_is_not_blocked`
- `test_a_lapsed_permit_is_not_ok_and_agrees_with_permit_detail`
- `test_the_contract_the_registry_and_a_detail_without_text`

## Learnings (proposed)
- The setting read is `value_of(conn, key, project=project_of_scope(scope))` (as `tl_mod_quality.checks`).

## Open questions / Blocked
none blocking. Choices the design text leaves open (Q12 to confirm):
- Live permit = Requested, Approved, or Active and not Lapsed. A Requested permit of the type therefore unblocks.
- Handed back is not in the design table: it counts in the total, is not ok, and answers `pending` (not yet closed).
- A Suspended or Lapsed permit covered by another live permit of its type answers `pending`, not `ok`.
- Only Cancelled/Closed on the IWP (nothing counted, nothing blocking) answers as "none": `n_a`, or `blocked` when the setting is on.
- An Active permit with no `valid_until` shows Lapsed (as `rules.effective_state` does).
