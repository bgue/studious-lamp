# P2-PTW-T15 - Demo `dev/demos/P2-PTW.sh`: eight clauses, SQLite then Postgres

Status: staged (r6; dispatch after PTW-T11 merges; base `p2/ip-r3` head at dispatch)
Tier: haiku
Kind: ticket
Review: full
Labels: demo, tests, safety
Depends on: P2-PTW-T03, T04, T05, T06a, T06b, T07, T07b, T08, T08b, T10, T11, S4, S5 (all merged)
Branch: `p2/ptw-t15-demo`
Worktree: `/home/user/wt/ptw/t15` (from `p2/ip-r3`)

## Goal
`just demo P2-PTW` runs the eight clauses of `docs/build-spec/module-designs/permits.md` section 10 once on SQLite and once on Postgres, one `PASS clause N: ...` line each. **A PASS line is printed only after a real check returned success**; a miss prints `DEMO FAILED` and exits non-zero; no `echo PASS` on a path that checked nothing. Same method as `docs/tickets/P2-INSP/T14-demo.md`, `docs/tickets/P2-QR/T11-demo.md` and `dev/demos/P2-PUNCH.sh`. Verbs from the merged CLI and `docs/reports/P2-IP/{PTWT04,PTWT06a,PTWT07b,PTWT10,PTWT11,PTWS4}.md`, `docs/reports/P2-PTW/*.md`, `packages/tl-cli/tests/test_cli_permit_write.py`, `test_cli_isolation.py` (merged CLI wins; a difference is the first line of your report).

## The clock (decided r6, D35)
No CLI, API or MCP read takes a clock: they read the real time. Clause 2 therefore moves the clock only where it is a parameter: the driver (in-process on the same ledger file or Postgres database, `open_uow`) calls `tl_mod_permits.views.permit_detail/permit_list/permit_board(..., now=<after valid_until>)` and `tl_mod_permits.lapse.run_once(factory, project, now)`; "reads Lapsed on every surface" becomes "on the views, the board and the card" (`scan_card` provider `.card(..., now)`) and the report says the CLI, API and MCP lapse reads are proved by `test_views_lapse.py` and the walks, not here. No clause sleeps.

## Clauses
Setup by commands: project `P123`; `ipetrov` approver and issuer, `lhartmann` second verifier, `cbrooks` and `pnair` requesters (the roster of the demo project, D29: read how `dev/seed/demo_project/permits.py` names and grants them; reuse the grants through `tl admin roles grant`); `uma` a plain user; `dora` for the restricted record; one IWP as `P2-I2.sh`; gas limits are the shipped defaults.
1. Hot work: `tl permit request` for the IWP (type hot work); `approve` by the requester refused (S2 text), by `ipetrov` passes; `issue` refused without a gas test, refused after a failing `tl gastest record` (the S3 failure auto-suspends only an Active or Lapsed gas-test permit: read `PTWS3`/S3 report for the exact state after a failed test on an Approved one), passes after a passing one; `tl permit show` is Active with a `valid_until` at shift end.
2. Shift change (the clock note above): lapse flagged once (second `run_once` returns 0 and writes no event: count events through the ledger); `revalidate` is refused without a fresh gas test (S2 text) and passes after one; the permit is Active again.
3. Stop work: `uma` (a plain user holding the word) suspends; a plain user cannot resume; `ipetrov` resumes; `handback` then `close`.
4. Confined space with an isolation: `tl isolation apply`, `link` to the permit; `issue` refused until `verify` by someone other than the applier (`lhartmann`); `tl isolation remove` refused while the permit is live, allowed after close.
5. Readiness (`tl awp readiness show <IWP> --project P123`, the `permits_planned` line): `n_a` with no permit; `pending` on request; `ok` on approval; `blocked` when suspended; lapsed is read by the driver through `checks.evaluate(conn, iwp, today=<after valid_until>)`.
6. Hidden subject: a permit for a record restricted by `dora` answers `uma` as `tl permit show P123-PTW-9999` does (byte for byte; the text is "error: no permit <KEY>" for both); `ls`, `board` counts and `export` omit it with unchanged totals; the driver reads API (404, same text) and MCP as `uma` and as an agent.
7. One state over CLI, API, TUI and MCP: `ApiClient.get_permit` equals the `tl permit show` fields; the TUI at 170x44 through the palette id `permits` shows the key and `Active`; MCP `list_permits`, `get_permit`, `permit_board` agree; an agent's `propose_permit` is pending until `uma` accepts it; no tool that issues or resumes is in `MCP_ACTIONS`.
8. Export: `tl permit export --format csv` and `jsonl` rows equal `tl permit ls` (field by field); `tl permit export --gas-tests` rows equal `tl gastest ls`.
Tail clause 8b on SQLite only: the generator section (PTW-T03: `just demo-project <fresh db> --sections core,engineering,awp,constraints,permits` or the section list its report names) prints a `permits:` line without `skipped` and `tl permit ls` is non-empty for Active, Lapsed and Suspended.

## Context (read these, nothing else)
- `docs/build-spec/module-designs/permits.md` section 10, `dev/demos/P2-PUNCH.sh`, `p2_punch_demo.py` (abridged), the reports listed above
may explore: `packages/tl-modules/permits/tests/permit_world.py`

## Allowed paths
- `dev/demos/P2-PTW.sh` (create, executable), `dev/demos/p2_ptw_demo.py` (create), `docs/reports/P2-IP/PTWT15.md` (create)

## Acceptance
```
uv run ruff format --check dev/demos/p2_ptw_demo.py
uv run ruff check dev/demos/p2_ptw_demo.py
uv run pyright dev/demos/p2_ptw_demo.py
just demo P2-PTW
```
Expected: clauses 1-8 on both backends plus 8b on SQLite, no `DEMO FAILED`, exit 0, no leftovers. Run once; Postgres down means `ge` and stop. No pytest, no `just gate`, no `just check`. The report names, per clause, the comparison that would fail if the feature broke.

## Escalation triggers
A clause cannot pass without a change in `packages/`, `schema/` or `dev/seed` (name it); a verb above differs from the merged CLI beyond a name; the clock cannot be passed in-process as described; the demo needs more than the two files.

## Report requirements
`docs/reports/P2-IP/PTWT15.md` <= 60 lines: PASS lines per backend (<= 5 decisive lines), one line per clause naming its surface. Standard report (`docs/templates/haiku-report.md`), deviations first. Commit subjects `P2-PTW-T15: ...` with the trailers the dispatch message names; no model names.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
