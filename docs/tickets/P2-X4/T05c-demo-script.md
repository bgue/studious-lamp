# P2-X4-T05c — demo script `dev/demos/P2-X4.sh` (seven clauses, both adapters)

Status: staged (waits T05a and T05b merged; then ready)
Tier: haiku
review: full
Labels: tests
Depends on: T05a, T05b merged
Branch: `p2/x4-t05c-demo-script`
Worktree: `/home/user/wt/x4/t05c`

## Goal
`just demo P2-X4` runs the seven demo clauses on `sqlite` and `postgres` (`TL_DEMO_BACKENDS`, default `sqlite postgres`), each ending in `PASS clause N: ...` printed only after its check passed. Copy the
frame of `dev/demos/P2-X2.sh` (workdir, trap, `quiet`, `tl`, `step`, `fail`, `clause`, backend loop, Postgres create and drop through `dev/demos/p1_i0_demo.py pg-create|pg-drop`); no `tl serve`, no `as` sessions
(the drivers run the API in process). Per backend: `tl init --dev`, then
- clause 1: `tl new module probe --root "$workdir/scaf"`; stdout has 15 `created ` lines of the EXPECTED list shape (a `routes.py`, `tools.py` and `cli.py` among them); then `driver clause1`.
- clause 2: `driver clause2`.
- clause 3 to 5: `ext clause3`, `ext clause4`, `ext clause5`.
- clause 6: `driver clause6`.
- clause 7: `uv run python -m tl_api.openapi --compat` exits 0 (the baseline compare: additive changes pass), and `uv run python -m tl_api.openapi --check` exits 0 (the committed document matches the routes); print the two exit statuses as `ok` lines.
Shell helpers `driver() { uv run python dev/demos/p2_x4_demo.py "$@" ...; }` and `ext() { uv run python dev/demos/p2_x4_ext_demo.py "$@" ...; }` take the mode as their first argument, as `driver` does in P2-X2.sh,
with a `fail` on non-zero. Export `TL_DB` per backend and `P2_X4_WORKDIR="$workdir"`. Header comment: the seven clauses and the D7, D13, D14 wording (scaffold has no command; tool is the read tool).

## Provided test (copy byte-identical; checked ruff format, ruff check, pyright at the target path)
`docs/tickets/P2-X4/provided/test_demo_p2_x4_script.py` to `tests/services/test_demo_p2_x4_script.py` (4 tests).

## Context (read these, nothing else)
- `dev/demos/P2-X2.sh`
- `docs/reports/P2-X4/T05a.md`, `T05b.md` (the modes, as merged)
may explore: (none)

## Allowed paths
- `dev/demos/P2-X4.sh` (create, executable like its siblings)
- `tests/services/test_demo_p2_x4_script.py` (create, provided)
- `docs/reports/P2-X4/T05c.md` (create)

## Acceptance
```
just check
just gate tests/services/test_demo_p2_x4_script.py tests/services/test_demo_p2_x4_drivers.py
TL_DEMO_BACKENDS=sqlite just demo P2-X4
```
Expected: gate PASS; the demo prints seven `PASS clause N` lines and `P2-X4 demo OK on: sqlite`. The Postgres run (`just dev up` first; exit 3 means the cluster is down) is the orchestrator's DONE step.

## Tests to add
The provided file only.

## Report requirements
Standard report; the seven PASS lines (≤ 8 lines).

## Escalation triggers
- Stop and report *Blocked* if a driver mode as merged differs from the names above.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
