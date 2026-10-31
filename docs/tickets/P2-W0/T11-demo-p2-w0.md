# P2-W0-T11 (DEMO) — `just demo P2-W0` (11 clauses) and the two tour additions

Status: ready
Tier: haiku
Kind: ticket
Review: lite
Labels: demo, tour
Depends on: RM-S3, W0-B2, A1 to A3, T05 (merged); T09, T10 not needed
Branch: `p2/w0-t11-demo`

## Goal
`just demo P2-W0` proves the wave's exit clauses once on SQLite and once on Postgres, one `PASS` line each, and `dev/tour/phase1.py`
shows the module roles log and the offline class row (F8). You do **not** run the tour (the orchestrator runs `just tour 1` once).

Do not discuss the commit trailer in the report; no model names anywhere in committed files.

## Brief references (pasted): the clauses (`wave0.md` §8)
1. Seeded ledger: `alice` (user), `dora` (document_controller), `ada` (admin). With no grant alice registers a document in P1 and cannot
   issue it (403); dora issues it, and also runs one correspondence and one schedule controller act.
2. `tl admin roles grant alice --project P1 --module documents --role superuser --reason demo`: alice issues in P1, is refused in P2,
   still cannot read a restricted P1 record.
3. dora granted `viewer` of documents in P2 is refused `RegisterDocument` there and still issues in P1; `GET /records/{id}/actions` in P2
   offers her nothing.
4. `tl admin roles effective alice --project P1` lists every module with its source; `GET /events` as alice shows no grant events, as ada it does;
   alice cannot grant.
5. An agent proposal of `IssueRevision` accepted by alice runs; accepted by bob (plain user) is 403.
6. A grant with project `company` for a stand-in module with `company_roles` true (carrying the fine word `awp.cwp.release`) is accepted;
   for `documents` it is refused `no_company_roles`.
7. `OFFLINE_CLASSES` has one entry per record type; `capture_allowed("documents.Revision","IssueRevision",node="device")` is `central_act`,
   `CreateRevision` is `draft`, `cost.CostCode` is `online_only`, anything on `authority` is allowed; `TL_NODE_KIND=device uv run tl serve` stops (exit 2).
8. `GET /record-types` lists `engineering.Tag` `full`; the record screen shows the offline line in technical mode only.
9. `load_checks()` is empty and `check_readiness_contract` passes on the sample check; a body with `correlation_id: rollup:x` or `source: job:x`
   is 422; `awp.iwp.ready_lead_weeks` reads 4.
10. `tl load targets` lists `tags` and `documents`; a load through the `tags` target gives the P1-I8 result; a derived document publishes through
    the `documents` publish target as in P1-I3 (reuse those drivers: `dev/demos/p1_i8_demo.py`, `p1_i3_demo.py`).
11. `just state P2-W0` prints at most 40 lines; `just relay-lint docs/tickets/P2-W0/provided/relay-ok.txt` passes and `relay-bad.txt` fails.

## Method
- Pattern: `dev/demos/P1-I8.sh` (header comment, backends list `TL_DEMO_BACKENDS` default "sqlite postgres", throw-away Postgres, `step`, `expect`,
  `refuse`, `as NAME`, `DEMO FAILED`, trap cleanup). Copy its skeleton and helpers; change nothing in it.
- `tl` commands (clauses 2, 4, 7 serve line, 10, 11) run in the script. Clauses that need the API (3 actions, 4 events, 5, 6, 8, 9) run in
  `dev/demos/p2_w0_demo.py`, which opens the ledger named by `TL_DB` with the API test client in process, the way `dev/accept/P2-W0/RM-S2.py`
  and `OC-T1.py` do (read them for the app and client set-up; the stand-in module for clause 6 is patched in as `RM-S2.py` does). The driver's
  modes print one `PASS <clause>` line each and exit 1 on a miss; the script prints the clause number on its own `PASS clause N` line.
- Seed people through `tl admin user add` with `--password-stdin` (documented dev passwords, as P1-I8); `ada` is admin.

## Tour additions (`dev/tour/phase1.py`, F8)
1. In `section_plain_record_screen`, the technical toggle (shot `23f-record-technical`): add the needle `"Offline class"` to the `until` and to the
   `tk.shot_tui` arguments (one line each).
2. New `section_module_roles(ws)` called last in `main` under `print("P2-W0: module roles", flush=True)`: `renew_sessions(ws)`, a `Shell` titled
   "Module roles, as an admin" running `tl admin roles grant amy --project P123 --module documents --role superuser --reason "covers issue"`, `ls`,
   `effective amy --project P123` as `demo`, saved as `25a-module-roles-cli`; then a TUI shot `25b-module-roles-log` (admin app, `F10`, key `m`,
   wait for `amy`, `documents`). Follow `section_accounts` for the exact calls.

## Context (read these, nothing else)
- `dev/demos/P1-I8.sh` (skeleton) and `dev/demos/p1_i8_demo.py` (driver style)
- `dev/accept/P2-W0/RM-S2.py` and `dev/accept/P2-W0/OC-T1.py` (API client set-up; clause logic to restate as PASS lines)
- `dev/tour/phase1.py` lines 169 to 226 (`section_accounts`) and 2074 to 2175 (record screen)
may explore: `dev/accept/P2-W0/{RM-S3,OC-S2,W0-B1,W0-B2}.py`

## Allowed paths
- `dev/demos/P2-W0.sh` (create, executable), `dev/demos/p2_w0_demo.py` (create), `dev/tour/phase1.py` (the two additions only)
- `docs/reports/P2-W0/T11.md` (create)

## Acceptance (run these once; no pytest, no `just gate`, no tour)
```
just check
TL_DEMO_BACKENDS=sqlite just demo P2-W0 2>&1 | tail -15
just demo P2-W0 2>&1 | tail -15
uv run python dev/tour/phase1.py --help | head -3
```
Expected: `just check` clean; eleven `PASS clause N` lines per backend and a final `P2-W0 demo OK on: sqlite postgres`; no `DEMO FAILED`.
If Postgres is down the second run is a failure, not a skip (report it, do not edit the script to skip).

## Tests to add
None (the demo is its test).

## Report requirements
Standard report (`docs/templates/haiku-report.md`): the tails of the two demo runs, one line per clause that needed a judgement call. Deviations first.

## Escalation triggers
- A clause cannot be met because behaviour differs from the text above (report the clause and the observed output; do not weaken the clause).
- Anything outside Allowed paths needs a change.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
