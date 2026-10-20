# P1-I8-T09a — `just demo P1-I8`, part 1: the script, the schema lifecycle, adoption, waivers, crosswalk and export

Status: staged (dispatch after S9, T05a4a, T05a4b and T05a4c are merged; the supervisor of that round checks every command below against `tl ... --help` and `docs/tickets/P1-I8/provided/` before it dispatches)
Tier: haiku
Review: lite
Labels: demo, schema-registry
Depends on: all `tl schema` commands of T05a1 to T05a4c and S9 merged on `p1/i8`
Branch: `p1/i8-t09a-demo-schema`

## Goal
`just demo P1-I8` runs `dev/demos/P1-I8.sh`, once on SQLite and once on Postgres, and ends every clause in a `PASS` line. This ticket creates the script, by the pattern of `dev/demos/P1-I7.sh` (read its first 100 lines: the process-group helpers, `quiet`, `tl`, `step`, `fail`, `as`, `expect`, `refuse`, the backend loop and the Postgres create/drop), and its clauses 1 to 4 on the schema workbench's command line. Clauses 5 to 7 (loaders, marts, the Phase 1 exit chain) are T09b, which appends to the same script. No schema rule is written here: every clause calls a finished `tl` command and checks its output.

## Brief references (pasted)
> **Brief 27.8.** `tl schema` CLI: `lint`, `diff`, `classify`, `impact --project P123`, `test --sample 1000`, `publish`, `adopt`, `crosswalk`, `promote`, `export-git` / `import-git`. **Brief 6.3.** A waiver relaxes one property on one project; it is a ledgered record with a reason, an approver and an expiry.
>
> **Clauses of this ticket.** (1) a person drafts an additive version of `co.acme.engineering` (3.3.0: a new optional property), analyses it, and the classification says `worst additive`; the author submits it; the author cannot approve it (`forbidden` or `cannot approve`), the admin can; publish makes it adoptable. A draft that retypes a property (4.0.0) is analysed as breaking and `submit` is refused. (2) `tl schema package impact co.acme.engineering@3.3.0 --project P999` prints a digest; `tl schema adopt P999 co.acme.engineering 3.3.0 --impact-sha256 <digest>` pins it; `tl schema adoptions` lists the pin. (3) a person requests a waiver for `psets.valve_data.size_in` on P999 for 30 days; the admin approves; `tl schema waiver ls` shows it Approved until the date; the admin revokes it and the list shows Revoked. (4) `tl schema crosswalk --project P123` prints `valve_data.body_material  MaterialCode  SS316L-NACE  SS316L  mapped`; `tl schema export-git DIR` writes the published versions; a second run says `unchanged`; `tl schema import-git DIR --dry-run` says nothing to draft; a file edited by hand makes `import-git` print `problem ... exists with other text` and exit 1.

## Interfaces
No code is pasted. Spellings (from `--help`, verify at dispatch): `tl schema package draft FILE | analyse REF | classify REF | submit REF | approve REF | publish REF | impact REF --project P | ls`; `tl schema adopt PROJECT PACKAGE VERSION --impact-sha256 D`; `tl schema adoptions`; `tl schema waiver request PROJECT PATH --reason R --expires YYYY-MM-DD | approve REF | revoke REF --reason R | ls`; `tl schema crosswalk --project P`; `tl schema export-git DIR`; `tl schema import-git DIR [--dry-run]`. `dev/demos/p1_i8_demo.py prepare WORKDIR` (you write it, small) writes `pkg-3.3.0.yaml` (the fixture `schema/fixtures/co.acme.engineering@3.2.0.yaml` with version 3.3.0 and one more optional property in `valve_data`) and `pkg-4.0.0.yaml` (version 4.0.0 and `size_in` with `range: int`).

## Context (read these, nothing else)
- `dev/demos/P1-I7.sh` (lines 1 to 100 and 150 to 245: the pattern)
- `docs/tickets/P1-I8/provided/t05a2-test_cli_schema_gov.py.txt` and `t05a3-test_cli_schema_waiver.py.txt` (what each command prints)
- `docs/tickets/P1-I8/provided/t05a4a-test_cli_schema_crosswalk.py.txt` and `t05a4c-test_cli_schema_import.py.txt`
- `docs/templates/haiku-report.md`
may explore: (none)

## Allowed paths
- `dev/demos/P1-I8.sh` (create), `dev/demos/p1_i8_demo.py` (create)
- `docs/reports/P1-I8/P1-I8-T09a.md` (create: your report; commit it)

## Steps
1. Create the script from the P1-I7 pattern: the helpers, the loop over `TL_DEMO_BACKENDS` (default `sqlite postgres`), a new ledger per backend, the dev admin `demo` and a second person `amy` (as P1-I7 does); no server is needed (the CLI works on the ledger).
2. Write clauses 1 to 4 as above, each `step "[$backend] clause N: ..."` and ending in `echo "PASS N: ..."`. Use `expect` and `refuse`; never `|| true` over a command that must succeed.
3. Write `p1_i8_demo.py prepare`. End the script's backend function with `echo "[$backend] clauses 1-4 passed"` (T09b moves it).
4. Run `bash dev/demos/P1-I8.sh` (SQLite and Postgres; `just dev up` first when Postgres is down).

## Acceptance
```
TL_DEMO_BACKENDS="sqlite postgres" just demo P1-I8
just check
```
Expected: `PASS 1` to `PASS 4` twice, no `DEMO FAILED`; `just check` clean. Paste the PASS lines in the report.

## Tests to add
None; the script is the test.

## Report requirements
Standard report. Deviations first (a command spelled differently from this ticket is a deviation: say what you used and why). Paste the PASS lines and the last 5 lines of `just check`.

## Escalation triggers
- A command prints something the clause cannot check, or a clause needs a command that does not exist: stop, write it under *Blocked*; never skip the clause.
- Stop if you would touch anything outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
