# P2-REL-T05 — `dev/release/smoke.sh`: clean install and both server paths

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: tooling, tests
Depends on: S2, T03, T04 merged on p2/rel; wave 2 merged on the trunk (reads `tl awp`)
Branch: `p2/rel-t05-smoke`
Wave 2: **yes**

## Goal
One command, `dev/release/smoke.sh <release dir>`, proves the release works the way a user gets it: no checkout on the path.
It ends `smoke: PASS` or `smoke: FAIL <step>`; every step prints one line. Each step is a bash function.

## Requirements
1. Work in `mktemp -d`, outside the repository; `cd` there; `env -i` plus `HOME`, `PATH`, `TL_*` set explicitly so nothing leaks from the developer's shell.
2. Step `install`: `uv venv --python 3.12`, then `uv pip install --find-links <dir> tl-cli`; assert `tl --version` and `tl-tui --version` equal the version in `SHA256SUMS` file names. `python -I -c "import tl_core; print(tl_core.__file__)"` must not point into the repository.
3. Step `try-it`: unpack the starter, set the `START.txt` environment, start `tl serve` in the background on a free loopback port (record the pid; stop it with `kill <pid>`, never `pkill`), wait for `/health` with a bounded loop of `curl` attempts (max 30 x 1 s; this is start-up readiness, not log polling), sign in as the demo account through `POST /auth/sign-in` (password from stdin file, never an argument), `curl` the records route of P200 and assert a non-empty list, call one `tl awp` read command on the ledger with `--db` and assert exit 0 (choose the cheapest list command that exists on the trunk after wave 2; name it in the report). Check `/health` carries the version (T02) when present.
4. Step `real-server` (only when `TL_PG_URL` is set, else `skip real-server: no Postgres` and the run still passes): new database on that URL, `tl init`, `tl admin bootstrap --username boss --password-stdin`, `TL_ENV=prod TL_OBJECT_SECRET=<random> TL_TRUSTED_PROXY_HEADER=X-Forwarded-For tl serve --host 0.0.0.0 --port <free>`; assert: sign-in as `boss` works; the `demo` account does not exist; a request with a token from a dev token file is refused; `tl serve --host 0.0.0.0` with `TL_ENV` unset exits 2 (S2).
5. Step `session-file`: after `tl login` the session file is mode 600 (`stat`; handle GNU and BSD `stat` flags) (Sec-5).
6. Always stop servers in a `trap ... EXIT`; never touch `/tmp/pytest-of-root`.
7. Test `dev/tests/test_smoke_script.py`: runs only `bash -n` on the script and pins the step names from `smoke.sh --list`. The real run is the acceptance.

## Context (read these, nothing else)
- `dev/release/build.sh`, `dev/release/starter.sh` (T03, T04), `docs/tickets/P2-REL/S2-real-server-mode.md` (what the server refuses)
- `docs/runbooks/accounts-and-access.md` lines 1–40, `docs/runbooks/run-on-postgres.md` lines 1–40 (database creation)
may explore: none

## Allowed paths
- `dev/release/smoke.sh` (create), `dev/tests/test_smoke_script.py` (create), `justfile` (one recipe `release-smoke`)
- `docs/reports/P2-REL/T05.md`

## Acceptance
```
just check
just gate dev/tests/test_smoke_script.py
just release-build && just release-starter && dev/release/smoke.sh dist/release-0.1.0
```
Expected: `smoke: PASS`; with `TL_PG_URL` set from the SessionStart hook the real-server step runs (say which).

## Escalation triggers
Stop and report *Blocked* if a step needs a product change (that is a finding for the supervisor, not an edit), or the install step needs a dependency not in the wheels.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
