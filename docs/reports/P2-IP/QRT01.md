# Report — P2-QR-T01 (run id P2-IP-QRT01)

Branch: `p2/qr-t01-read-views`   Commit(s): see `git log -1` on the branch (single implementation commit)

Status: BLOCKED. Acceptance gate fails on one provided test; the test is not edited.

## Deviations
- Report path: written to `docs/reports/P2-IP/QRT01.md` as the launch brief asked; the ticket's Allowed paths name `docs/reports/P2-QR/T01.md`.
- Commit subject uses the launch brief's form `P2-IP-QRT01: ...`; the ticket says `P2-QR-T01: ...`.
- Trailer names Claude Haiku 5.5 (the implementer's own model), not Opus 5.5 as the brief text said.
- `views.py` module docstring still says "stub ... Names raise NotImplementedError until T01"; left untouched (docstring is out of the "bodies and imports" scope). It is now stale.

## Changed files
- `packages/tl-modules/qr/src/tl_mod_qr/views.py` — bodies of `codes_for_record`, `code_counts`, `export_rows`; `_state`, `_row`, `_text` helpers; imports. `CodeRow` and all signatures unchanged.
- `packages/tl-modules/qr/tests/test_views.py` — byte-identical copy of `docs/tickets/P2-QR/provided/T01_test_views.py` (cmp silent).
- `docs/reports/P2-IP/QRT01.md` — this report.

Implementation notes: `codes_for_record` is one statement (`target_id = :record AND not_hidden("c.target_id")`, `ORDER BY issued_at DESC, id DESC LIMIT 100`). `code_counts` is one grouped statement; state via CASE with `substr(expires_on,1,10) < :today`, `today` from `tl_core.util.utcnow()`. Both reads use the default `LOWEST` viewer and apply the hidden filter before LIMIT/COUNT.

## Commands and output
```
$ cmp docs/tickets/P2-QR/provided/T01_test_views.py packages/tl-modules/qr/tests/test_views.py
(silent, exit 0)
$ just check
... uv run ruff check . / ruff format --check . / pyright / tl_schema.generate --check / tl_api.openapi --compat / check_licences.py
licences ok
check=0
$ just gate packages/tl-modules/qr/tests/test_views.py
part 1: exit 1, 1 failed, 8 passed in 9.86s
FAILED packages/tl-modules/qr/tests/test_views.py::test_at_most_one_hundred_rows_newest_first[sqlite]
gate: FAIL
```
Failure detail: `test_views.py:39` (`world.serve(service.issue ...)` inside the 100-iteration loop, line 92) raises `QrRuleError: that record has as many live scan codes as it may have; revoke one first` from `service.py:154`. Platform default `qr.codes_per_record_max` is 20 (`schema/settings/platform.yaml:478`). The test never calls `world.cap(...)`.

## Tests added
- `packages/tl-modules/qr/tests/test_views.py` (provided, unedited): 9 tests. 8 pass; `test_at_most_one_hundred_rows_newest_first` fails as above.

## Learnings (proposed)
- The provided test needs 100 live codes on one record, but the default live cap is 20. The ticket does not mention the cap. The `World.cap()` helper exists in `qr_world.py` but the test does not call it. A spec-level fix (test calls `world.cap(100)` before the loop, or the cap is raised in a fixture) is needed; that is outside this ticket's authority.

## Open questions / Blocked
Blocked: `test_at_most_one_hundred_rows_newest_first` fails at test line 92 because the per-record live cap (default 20, `qr.codes_per_record_max`) refuses the 21st `IssueScanCode`. The ticket's escalation trigger covers a provided-test failure not explained by the ticket. Options for the supervisor: (a) the provided test calls `world.cap(100)` before issuing (test change, needs its owner); (b) a fixture-level cap in `conftest.py` (outside Allowed paths); (c) accept a different row count. I did not edit the test, did not change the cap, and did not skip the test. Please decide; I can finish once the test is settled.
