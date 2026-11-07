# P2-INT-T05 — Demo driver `dev/demos/P2-INT.sh`

Status: staged (release when T02-T04 merged)
Tier: haiku
Review: lite
Labels: docs, tests
Depends on: S1, S2, T02, T03, T04 merged
Branch: `p2/int-t05-demo`

## Goal
`just demo P2-INT` runs the eight clauses of `README.md` (Demo) on SQLite then Postgres and prints one PASS per clause.

## Context (read these, nothing else)
- `docs/tickets/P2-INT/README.md` (Demo), `dev/demos/P2-I3.sh` (driver pattern), `dev/accept/P2-INT/S1.py`, `S2.py` (clauses 1-7 are already scripted there: call them, do not copy)

## Allowed paths
- `dev/demos/P2-INT.sh` (create), `dev/accept/P2-INT/demo_cli_mcp.py` (create; clause 8: CLI flag, MCP parameter, TUI text function once each), `docs/reports/P2-INT/T05.md` (create)

## Acceptance
```
just check
just demo P2-INT
```
Expected: 8 PASS on sqlite, 8 on postgres.

## Tests to add
None (the driver is the test).

## Report requirements
Standard plus the demo's last 10 lines.

## Escalation triggers
- Stop and report *Blocked* if clause 2 needs a pre-change segment fixture not committed by S1.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
