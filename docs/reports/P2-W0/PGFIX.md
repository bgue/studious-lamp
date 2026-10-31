# P2-W0-PGFIX: test setup for the Postgres links tests

Deviations: none. Tests only; one file changed (`tests/confidentiality/test_paths_equal_old.py`).

## Cause (confirmed)
The `world` fixture (and so `linked`, the `CorrWorld.link` helper and the document-links test) acts
as `user:u` and `user:mlee`, which have no account. `holder_for_actor` gives an account-less
`user:` actor the `user` role only on a dev ledger (SQLite with TL_ENV dev/test/ci; owner decision
D2). On Postgres it holds nothing, so `AddLink` was refused. The product is right; the setup was
wrong.

## Fix
The `world` fixture creates the accounts `u` and `mlee` (kind person, role `user`, no password)
with `accounts.create_account`, the call `tests/services/test_module_role_seams.py` and
`tests/confidentiality/test_core.py` use. They exist before any link or post is written. No
assertion changed; `CorrWorld` is untouched, so no other test's behaviour moves. The five readers
and the old-vs-new comparisons are as before (the viewers ann, bo, ctl are still not accounts).

## Runs
- `just check`: clean.
- `just gate tests/confidentiality`: `part 1: exit 0, 116 passed in 234.09s (0:03:54)` / `gate: PASS`
- `just gate-pg tests/confidentiality`: `part 1: exit 0, 226 passed in 1821.68s (0:30:21)` / `gate: PASS`

## Learning candidate
A pg-parametrised test that runs commands needs real accounts for its actors; the dev-ledger rule
does not apply on Postgres.
