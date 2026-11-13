# P2-I5-T12 — Demo `dev/demos/P2-I5.sh`: clauses 1 to 6, 9 and 10, SQLite then Postgres

Status: staged (last code ticket: needs T06c2, T06b, T07b, T09, T16, S4b, T04, T04b, T01 merged)
Tier: haiku
Kind: ticket
Review: full
Labels: demo, tests
Depends on: T06c2, T06b, T07b, T09, T16, S4b
Branch: `p2/i5-t12-demo`
Worktree: harness-created under `/home/user/wt/i5/t12` (from `p2/i5` head)

## Goal
`just demo P2-I5` runs the exit clauses of the increment on a fresh ledger, once on SQLite and once on Postgres, and ends `PASS clause N` for N in 1 to 6, 9, 10 (7 and 8 are roadmap 3c; 6 has no PDF; 5 reads "the roll-up reads", D17). Pattern: `dev/demos/P2-I2.sh` (helpers `tl`, `as`, `expect`, `refuse`, `clause`, `run_backend`, the cleanup trap) with the driver `dev/demos/p2_i2_demo.py` for what the shell cannot do (TUI pilot, MCP session).

## Brief references (pasted; `docs/tickets/P2-I5/README.md` "Demo clauses" is the spec of record)
Each clause is the commands named, with an `expect`/`refuse` on the text the tool prints (read the report of the ticket that made the verb for the exact text):
1. Rules of credit: `tl schema package ...` flow for `schema/fixtures/packages/co.acme.awp@1.1.0.yaml` (S1 report, deviation 1: the package form; runbook `docs/runbooks/schema-package-change.md`) published by a controller; a copy with weights summing to 101 is refused by the lint with its fixed message (L008); `tl awp roc show`, `tl awp roc set co.acme.awp@1.1.0` adopts it (T01); a plain user's publish is refused.
2. A new XER snapshot (`tl xer define|upload|publish`, a worker run) then `tl awp look-ahead --schedule MAIN --weeks 4` (T04) lists the weeks' activities with their IWPs, `ready <ok>/<total>` and need-by dates (planned start minus `awp.iwp.ready_lead_weeks`, 4).
3. A check-raised constraint (the readiness worker raises it) is cleared as waived by a holder of `core.constraint.waive` with `--reason`: a plain user is refused, a missing reason is refused, `tl awp iwp show` shows it waived with who and why (S4b); then `tl awp iwp hash`, two `signoff`s and `issue` release the Ready IWPs (I2).
4. A blocking constraint raised on an Issued IWP, then `tl awp worker --once` twice: the IWP is On hold after the first, nothing changes after the second (the replay writes no second `IWP.Held`, count the events with `tl events`); `tl awp week open`, `week commit` for the foremen, a stale `--expected-version` is refused.
5. `tl awp iwp item-move|step|start-work|complete-field` (T04b) move earned % per `tl awp iwp progress` as the S2 rules say; `week outcome` and `week close` give PPC (`tl awp week ppc`, `tl awp report kpi_ppc`, `kpi_constraint_free`: both equal a ledger recount made by the driver with SQL); `tl awp export progress --project P --period 2026-W45` writes the CSV by cost code (a cell starting `=`, `+`, `-` or `@` is quoted: seed one cost code title `=cmd` and check the line) (S3).
6. `tl awp iwp pack NUMBER --out FILE --attach` (T07a): the file holds the headings of the template, `not tracked yet`, and an `<svg` per drawing when `segno` is installed (else the `note:` line); the file is in slot `pack` (`tl file ls --slot pack`).
9. The driver opens the TUI headless as the foreman (a pilot as `p2_i2_demo.py` does): the app mounts on the IWP log with the mine filter and the summary names the foreman (T06c2); with `tui.landing=default` set for that person it opens on the grid.
10. Agents over MCP (`agent_session` of the driver): `propose_progress` and `propose_week_commitment` are filed and a person accepts them (the commitment is in `week show`); `ClearConstraint` as a waive and `CloseWeek` by an agent are refused (excluded, with reasons); the same week read over the CLI, the TUI client, the API and MCP gives the same commitment count; then `uv run pytest -q` of the three T16 files passes (the five-reader walk).
- Backends: `TL_DEMO_BACKENDS` default "sqlite postgres" (P2-I2.sh header); an unreachable Postgres is a failure; exits non-zero and prints `DEMO FAILED` when a clause is not met; leaves nothing behind.

## Context (read these, nothing else)
- `dev/demos/P2-I2.sh` (1-130 and the clause bodies), `dev/demos/p2_i2_demo.py` (54-135, 181-260), the reports `docs/reports/P2-I5/{S1,S2,S3,S4a,S4b,T01,T03,T04,T04b,T06c2,T07a,T09,T16}.md` for texts and flags, `docs/runbooks/schema-package-change.md`

## Allowed paths
- `dev/demos/P2-I5.sh` (create, executable), `dev/demos/p2_i5_demo.py` (create)
- `docs/reports/P2-I5/T12.md`; no source change (a missing verb or a wrong text is a finding under Blocked)

## Acceptance
```
just check
just demo P2-I5
```
Expected: eight `PASS clause N` lines per backend (1 2 3 4 5 6 9 10), then no `DEMO FAILED`; the run is shown in the report (the PASS lines only).

## Tests to add
None (the demo is the test).

## Escalation triggers
- A clause cannot be met with the merged verbs (name the clause and the missing verb or text); the Postgres cluster is down (`just dev up`; report it as an environment failure, not a code one).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths listed. Commit subjects `P2-I5-T12: ...`; trailer is the attribution lines your harness requires then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
