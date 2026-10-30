# P2-W0 — Phase 2 wave 0: roles, offline classes, readiness contract, targets, relay tools

Status: in-progress (round 1). Plan: `docs/build-spec/specs/wave0.md` (v0.1 with the plan check F1-F10 applied; it wins over
`roles-mvp.md` and `offline-classes.md`). Board and next steps: `STATE.md`. Owner decisions: `docs/build-spec/module-designs/OWNER-DECISIONS-2026-10-30.md`.

## Objective
After P2-W0, per-module roles decide every module command, every record type carries an offline class, the frozen readiness
contract, access-word table, Phase 2 settings keys and reserved prefixes are in, loader and publish targets are found by
entry point, and the relay tools (`dev/state.sh`, `dev/review-pack.sh`, `dev/relay-lint`) exist. Wave 1 (M3, M4, web) then starts
on one trunk with no shims.

## Demo
`just demo P2-W0` (SQLite then Postgres, 11 clauses): `wave0.md` §8. `just tour 1` once at C4.

## Order of work
Rounds, slots and critical path: `wave0.md` §7 (round 1: RM-S1 | W0-B1 | A1-A3). Process: tests deferred to TA and TB at C3 (one
end run), tours at C4, security reviews only if the owner asks (Sec rows recorded), fewer larger pieces (rule 12).

## Pieces and tickets (file names)
| Plan id | File | Round |
|---|---|---|
| RM-S1 | `S1-roles-grants.md` | 1 |
| W0-B1 | `S2-readiness-words-keys.md` | 1 |
| A1, A2, A3 | `T01-state-sh.md`, `T02-review-pack.md`, `T03-relay-lint.md` (fixtures `provided/relay-*.txt`) | 1 |
| RM-S2, W0-B2, OC-S1 | specs written in round 2 | 2 |
| RM-S3, RM-S4, OC-S2 | round 3 | 3 |
| OC-T1..T3, TA | round 4 | 4 |
| TB, DOC, DEMO | round 5 | 5 |

## Risks and escalation
`wave0.md` §9. Schema and settings merges (RM-S1, W0-B1, OC-S1) are approved by the orchestrator under P2-Q10 and logged in
`docs/reports/APPROVALS.md`.
