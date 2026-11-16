# Report — P2-PTW-T10

Branch: `p2/ptw-t10-client`   Commit(s): the single commit on the branch (sha in the return message)

## Deviations
- Worktree is `/home/user/wt/ip4/ptwt10` on `p2/ptw-t10-client` from `380e03f7`, as the dispatch names it, not `/home/user/wt/ptw/t10` from `p2/ip-r3` as the ticket says.
- Commit subject is `P2-IP-PTWT10: ...` as the dispatch names it, not the ticket's `P2-PTW-T10: ...`.
- The trailer names the implementing model (the harness's own), not the model the dispatch text named.
- `tests/api/test_client_permits.py` adds a second cleared controller `dan` (`world.person`, superuser and document controller). Only `dan` can approve and issue the permit for the restricted record; `sue` and `pam` cannot see it. Inside Allowed paths.
- No pins changed: `test_client_roundtrip.py`, `test_remote_client.py`, `test_client_module_roles.py` and `test_client_insp.py` pass as they are.

## Changed files
- `packages/tl-api/src/tl_api/client/permits.py` (new) — `PermitsApi`: the six reads decoded with `TypeAdapter`, `project` as a query parameter, `permit_command` over `tl_mod_permits.module.COMMANDS`.
- `packages/tl-api/src/tl_api/client/__init__.py` — `PermitsApi` in the `ApiClient` bases after `QualityApi`.
- `packages/tl-tui/src/tl_tui/client.py` — seven methods on `ClientInterface` (imports `permit_views`, `permit_iso_views`).
- `packages/tl-tui/src/tl_tui/embedded.py` — the six reads under `permits.view` (`_require_permit_view`), `utcnow()` for Lapsed, `permit_command` via `_module_command`.
- `packages/tl-tui/tests/fakes_permits.py` (new) — `FakePermitSupport`, `load_*`, the reads with view filters, board built as `permit_board`, `permit_command`, `seed_permits`.
- `packages/tl-tui/tests/fakes.py` — import, base (before `FakePunchSupport`), `_init_permits()` call.
- `tests/api/test_client_permits.py` (new) — 8 tests, both clients over one ledger.
- `packages/tl-tui/tests/test_fakes_permits.py` (new) — 14 tests.

## Commands and output
```
$ uv run ruff format --check packages/tl-api/src/tl_api/client packages/tl-tui tests/api/test_client_permits.py
453 files already formatted
$ uv run ruff check packages/tl-api/src/tl_api/client packages/tl-tui tests/api/test_client_permits.py
All checks passed!
$ uv run pyright packages/tl-api/src/tl_api/client/permits.py packages/tl-tui/src/tl_tui/client.py packages/tl-tui/src/tl_tui/embedded.py packages/tl-tui/tests/fakes_permits.py tests/api/test_client_permits.py packages/tl-tui/tests/test_fakes_permits.py
0 errors, 0 warnings, 0 informations
$ just gate tests/api/test_client_permits.py packages/tl-tui/tests/test_fakes_permits.py
part 1: exit 0, 22 passed in 19.44s
gate: PASS
$ just gate tests/api/test_client_insp.py tests/api/test_client_roundtrip.py packages/tl-tui/tests/test_remote_client.py packages/tl-tui/tests/test_client_module_roles.py
part 1: exit 0, 37 passed in 51.25s
gate: PASS
```

## Tests added
- `tests/api/test_client_permits.py::test_the_six_reads_give_equal_answers_on_both_clients[uma|rob|dora]` — embedded and `ApiClient` agree on the six reads.
- `…::test_a_controller_who_is_not_the_requester_approves_through_either_client` — `ApprovePermit` through both; the next read shows Approved.
- `…::test_the_requester_may_not_approve_through_either_client` — the S2 text on both.
- `…::test_a_missing_key_is_one_not_found_text_on_both` — "no permit" (permit and gas-test key), "no isolation".
- `…::test_a_permit_for_a_restricted_record_is_absent_for_the_lowest_clearance` — absent from rows, total and board counts for `uma`; "no permit" for detail and gas tests; `dora` reads it.
- `…::test_a_lapsed_permit_reads_lapsed_on_both_clients` — read clock moved to `valid_until + 1 min`; Lapsed on both, and in the board counts.
- `packages/tl-tui/tests/test_fakes_permits.py` — seed counts, each permit and isolation filter, total before limit, board equals the live list, missing keys, command recorded and class-checked.

## Learnings (proposed)
- `tl_mod_permits.module.COMMANDS` already holds the six isolation and gas-test commands; `iso_commands.py` has no table of its own. The "one union" in the ticket is `COMMANDS`.
- A permit for a restricted record can only be approved or issued by a controller cleared for that record. Others get "no record with that id" from the handler, so the seed needs such a controller.
- Handlers bind `now` by name at import (`handlers/permit.py`, `isolation.py`, `gas_test.py`), so patching `common.now` alone does not move them. The permits conftest patches both names; the roundtrip test does the same.
- The read paths take the clock from `utcnow()` in two places (`tl_tui.embedded`, `tl_mod_permits.routes`). A Lapsed test has to patch both.
- The fake records permit commands in `punch_commands`, as the ticket asks. The name is misleading for a reader; a `permit_commands` list would be clearer.
- Under the seeded grants, `uma` (no module grant) reads permits, so `uma` is the lowest-clearance reader, not the lowest-permission one.

## Open questions / Blocked
none
