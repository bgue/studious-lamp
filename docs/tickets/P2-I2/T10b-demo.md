# P2-I2-T10b — `just demo P2-I2`

Status: staged (r10). Ready when T10a, TW1, TW2, TW3, T07c and S3 are merged; names and arguments refined at dispatch from their reports.
Tier: haiku
Kind: ticket
Review: full
Labels: demo
Depends on: T10a, TW1, TW2, TW3, T07c, S3, T04g (merged)
Branch: `p2/i2-t10b-demo`
Worktree: harness-created under `/home/user/wt/i2/t10b` (from `p2/i2` head)

## Goal
`just demo P2-I2` runs the nine clauses of the README (`docs/tickets/P2-I2/README.md`, "Demo clauses") plus the materials line and a sim clause 10, once on SQLite and once on Postgres, one `PASS clause N: ...` line each; a miss prints `DEMO FAILED` and exits non-zero. Pattern: `dev/demos/P2-I1.sh` and `p2_i1_demo.py` (header, backends, driver modes, TUI through the palette). Clauses that are a `tl` command live in the shell script, the rest are driver modes.

## Design (fixed)
- Files: `dev/demos/P2-I2.sh` (executable), `dev/demos/p2_i2_demo.py`. Nothing else. If the driver passes about 450 lines, the supervisor splits it at dispatch into T10b1 (clauses 1-5 and materials) and T10b2 (6-10); the files stay the same, so they run in sequence.
- Reuse the argument forms of `dev/accept/P2-I2/*.py` (written by the pieces and tickets) and `tl awp iwp ...`, `tl constraint ...`, `tl awp readiness ...` (T04d, T04d2, T04e1, T04e2). Never re-derive an argument.
- Setup by commands: one project, the 24 + 8 scope items and 3 tags by `tl awp iwp scope` (D4: no loader); a foreman; the first IWP numbers 0001 (D8).
- Clause 2: pin two drawings, make a new IFC revision of one; `documents_current` blocked, `resolve_via` names the stale pin. Clause 3: constraints by hand (`tl constraint raise`) and by the materials check (assign MTO lines to the IWP key by `work_package_id` first, D13, then reserve); need-by = planned start minus `awp.iwp.ready_lead_weeks`; the review screen groups by owner and by category. Clause 4: readiness 7/9 with the two blocked checks named, re-pin and clear gives 9/9; `IWP.Ready` reaches a loopback receiver (the receiver pattern of `dev/demos/P1-I7.sh`). Clause 5: two distinct signers holding `awp.release.signoff_roles`; a plain user refused; the same signer twice refused; a wrong record hash refused. Clause 6: issue to a foreman; permit to work reported missing, not blocking. Clause 7: oversize IWP warns, split gives two. Clause 8: an agent proposes a constraint (MCP), a person accepts it. Clause 9: the same readiness over API, TUI (palette), web (TL_WEB pages) and MCP; readiness history events in the ledger; the backlog tile shows weeks per foreman.
- Clause 10 (sim): give a sim project its awp setup by hand as an operator (as P2-I1 T08 did), run a short `tl sim` scenario naming `iwp_planner` (see `dev/accept/P2-I2/T10a.py`, `tl sim --help`), then `tl sim assert` once.
- TUI size 170x44; screens reached by the palette entries T07c registered, never by `action_*`. Backends, cleanup and exit codes exactly as `P2-I1.sh`.

## Context (read these, nothing else)
- `docs/tickets/P2-I2/README.md` (demo clauses), `dev/demos/P2-I1.sh`, `dev/demos/p2_i1_demo.py` (abridged: header and one mode of each kind)
- `docs/reports/P2-I2/T04d.md`, `T04d2.md`, `T04e1.md`, `T04e2.md`, `T07c.md`, `TW1.md`-`TW3.md`, `T10a.md` (command lines and palette ids)
may explore: `dev/accept/P2-I2/`

## Allowed paths
- `dev/demos/P2-I2.sh` (create), `dev/demos/p2_i2_demo.py` (create), `docs/reports/P2-I2/T10b.md` (create)

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
just demo P2-I2
```
Expected: ten `PASS clause N` lines per backend, no `DEMO FAILED`, exit 0, no leftover files or databases. Run the demo once; Postgres down means `ge` and stop (do not skip the backend). No pytest, no `just gate`.

## Report requirements
`docs/reports/P2-I2/T10b.md` <= 60 lines: the PASS lines of each backend (<= 5 decisive lines each), one line per clause naming its surface (CLI, API, TUI palette, web, MCP).

## Escalation triggers
- Stop and report *Blocked* if a clause cannot pass without a change in `packages/` or `schema/`, a screen cannot be opened through the palette, or the demo needs more than the two files above.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
