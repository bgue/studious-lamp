# P2-I1-T08 — `just demo P2-I1`

Status: ready (r12; T11 and T05h merged; T07 merged)
Tier: haiku
Review: full
Labels: demo
Depends on: T11, T05h, T07 (merged)
Branch: `p2/i1-t08-demo`
Worktree: `/home/user/wt/i1/t08` (from `p2/i1` head)

## Goal
`just demo P2-I1` runs the nine clauses of spec §11 plus the sim clause 10 (`docs/build-spec/specs/m3-wbs-cwp.md` lines 262-277, read them) once on SQLite and once on Postgres, one `PASS clause N: ...` line each; a miss prints `DEMO FAILED` and exits non-zero. Pattern to copy: `dev/demos/P2-W0.sh` (header, TL_DEMO_BACKENDS, throw-away Postgres) and `dev/demos/p2_w0_demo.py` (driver with modes, `PASS`/`FAIL` lines). Clauses that are a `tl` command live in the shell script; the rest are driver modes.

## Design (fixed)
- Files: `dev/demos/P2-I1.sh` (executable), `dev/demos/p2_i1_demo.py`. Nothing else.
- Reuse, do not re-derive: the `tl awp ...` verbs and `tl load` targets awp_wbs / awp_cwa (see the scripts `dev/accept/P2-I1/T04c.py`, `T04d.py`, `T04e.py`, `T02.py`, `S4.py` lines 404-490 for exact arguments); samples under `schema/fixtures/awp/` (T01). Clause 4 seeds the P1-I4 demo schedule itself via the seed step of `dev/demos/p1_i4_demo.py` (import or call it, do not depend on an earlier run).
- Clause 7: the driver opens the TUI with `tl_tui.embedded.EmbeddedClient.for_target(os.environ["TL_DB"], actor="user:demo")` (pattern `p1_ux2_demo.py:271`) in a `TlApp` through `tests/helpers.run_pilot`-style code, and reaches the CWP register, WBS tree and path screen by the PALETTE (type the entry label, Enter; ids cwps wbs path), not by calling `action_*`; it also opens cwas and packages the same way for clauses 8 and 9. Size 170x44. It reads the rows the screens show and compares the CWP number with the API (`GET /awp/cwps`) and the MCP tool (`list_cwps`) answers.
- Clause 10 (sim, D43/D45): one extra `PASS clause 10` after the nine: give a sim project its awp data by hand (`tl awp cwa define`, `tl awp path define --project sim-<run>` as operator, like schedule-weeks.yaml; no core sim change), run a short `tl sim` scenario naming `workface_planner` (see `dev/accept/P2-I1/T07.py` and `tl sim --help`), then `tl sim assert` once. A pending propose_cwp proposal accepted by the approver actor shows as a CWP row.
- Backends, cleanup and exit codes exactly as P2-W0.sh. Roles as the seeded dev people in P2-W0.sh (alice user, dora, ada admin); where a superuser grant is needed use `tl admin roles grant ... --module awp --role superuser` as P2-W0 clause 2 does.

## Context (read these, nothing else)
- `docs/build-spec/specs/m3-wbs-cwp.md` lines 262-277
- `dev/demos/P2-W0.sh`, `dev/demos/p2_w0_demo.py` (abridged: header, one mode)
- `dev/accept/P2-I1/T04c.py`, `T04d.py`, `T04e.py`, `T05h.py` (arguments and harness)
may explore: `dev/accept/P2-I1/S4.py`, `T02.py`, `T10.py`

## Allowed paths
- `dev/demos/P2-I1.sh` (create)
- `dev/demos/p2_i1_demo.py` (create)
- `docs/reports/P2-I1/T08.md` (create)

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
just demo P2-I1
```
Expected: ten `PASS clause N` lines per backend, no `DEMO FAILED`, exit 0, no leftover files or databases. Run `just demo P2-I1` once; if Postgres is down, report `ge` and stop (do not skip the backend). No pytest, no `just gate`.

## Report requirements
`docs/reports/P2-I1/T08.md` (<= 60 lines): the PASS lines of each backend (<= 5 decisive lines each), one line per clause saying which surface (CLI, API, TUI palette, MCP) it used.

## Escalation triggers
- Stop and report *Blocked* if a clause cannot pass without a change in `packages/` or `schema/`, if a screen cannot be opened through the palette, or if the demo needs more than the two files above.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
