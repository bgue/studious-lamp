# P1-I8-T09b — `just demo P1-I8`, part 2: the legacy load, the lake marts and the Phase 1 exit chain

Status: staged (dispatch after T09a and every other ticket is merged; the supervisor of that round re-checks the spellings and the mart names against `tl ... --help`)
Tier: haiku
Review: lite
Labels: demo
Depends on: P1-I8-T09a merged; S6, T07a, T07b, T08 merged (they are)
Branch: `p1/i8-t09b-demo-exit`

## Goal
Append clauses 5 to 7 to `dev/demos/P1-I8.sh` (created by T09a): a legacy file through the loader stages and back out again, the two lake marts, and the Phase 1 exit chain (PDF to derived document to published to feed to webhook receiver). No code is written outside the script and its driver: every clause calls a finished command and checks its output.

## Brief references (pasted)
> **Brief 29.6 (legacy loading).** extract, bronze, profile, map, dry run, load, reconcile; a bad load is taken back by `compensate`, which ends the records the run created, all or nothing. **Brief 28 (lakehouse).** Marts for documents (status, turnaround, issues) and schedule history never hold a row the lowest reader may not read. **Brief 16, Phase 1 exit.** PDF to derived to published to feed to webhook receiver.
>
> **Clauses of this ticket.** (5) an admin opens a `dms-register` run on a CSV register of three documents (P123), runs `extract`, `profile`, `bronze`, `plan` (it counts 3 new), `load --expect-new 3`, `reconcile` (no problems), then `compensate --reason ...`; the documents are gone from the register and a second `plan` counts 3 new again. (6) after `tl lake sync`, `tl lake mart ls` lists the documents mart and the schedule-history mart, and `tl lake mart show <documents mart>` has one row per document of the register loaded in (5), none of a restricted document that a user may not read (use the restricted run of clause 5's loader option `--confidentiality restricted` for one extra file and check a plain user's `mart show` lacks it while the admin's has it). (7) the exit chain: reuse, by copying, the PDF rendition and publication steps of `dev/demos/P1-I3.sh` (clauses 2 and 5) and the receiver, allow-list, action and rule steps of `dev/demos/P1-I7.sh` (clauses 5 and 2): a rule on the publication's event posts to the feed and an action sends a signed webhook to the loopback receiver, which verifies it. End with `PASS 7: PDF -> derived -> published -> feed -> receiver`.

## Interfaces
Spellings (verify at dispatch): `tl load open FILE --project P --loader NAME [--confidentiality restricted]`; `tl load extract|profile|bronze|plan|reconcile RUN --project P`; `tl load load RUN --project P --expect-new N`; `tl load compensate RUN --project P --reason R`; `tl lake sync`; `tl lake mart ls | show NAME [--json]`; `tl load loaders`. A run is `system/table#n` (for example `dms/register#1`).

## Context (read these, nothing else)
- `dev/demos/P1-I8.sh` (T09a's script) and `dev/demos/P1-I7.sh` (clauses 2, 5 and the receiver helpers)
- `dev/demos/P1-I3.sh` and `dev/demos/p1_i3_demo.py` (the PDF and publication steps)
- `docs/tickets/P1-I8/provided/t07a-test_loader_dms_register.py.txt` (the CSV columns the loader reads) and `t08a-test_doc_marts.py.txt`
- `docs/templates/haiku-report.md`
may explore: (none)

## Allowed paths
- `dev/demos/P1-I8.sh` (modify: append clauses 5 to 7 before the end-of-backend line)
- `dev/demos/p1_i8_demo.py` (modify: a subcommand that writes the CSV registers)
- `docs/reports/P1-I8/P1-I8-T09b.md` (create: your report; commit it)

## Steps
1. Read the T09a script. Add the register CSV writer to the driver (3 documents; and a 1-document restricted file).
2. Write clause 5, then 6, then 7, each `step "[$backend] clause N: ..."` ending in a `PASS N` line. Clause 7 may start the server and the receiver as P1-I7 does.
3. Move the end-of-backend `echo` to the end; run the whole script on both adapters.

## Acceptance
```
TL_DEMO_BACKENDS="sqlite postgres" just demo P1-I8
just check
```
Expected: `PASS 1` to `PASS 7` twice, no `DEMO FAILED`; `just check` clean. Paste the PASS lines in the report.

## Tests to add
None; the script is the test.

## Report requirements
Standard report. Deviations first. Paste the PASS lines and the last 5 lines of `just check`.

## Escalation triggers
- A link of the exit chain does not exist (no event to hang the rule on, no feed card, no way to reach the receiver): stop, write which link under *Blocked*; the orchestrator decides. Never fake a link.
- Stop if you would touch anything outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
