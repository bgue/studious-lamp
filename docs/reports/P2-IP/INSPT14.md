# Report — P2-INSP-T14 (dispatch id P2-IP-INSPT14)

Branch: `p2/insp-t14-demo`   Commit(s): see the return message

## Deviations
- Blocked, not done: `just demo P2-INSP` exits 1. SQLite passes; Postgres fails at clause 5 (see Blocked).
- Base `79e41ff0` per the dispatch (ticket says `p2/ip-r3`); the dispatch supersedes it.
- Commit subject uses `P2-IP-INSPT14:` (dispatch), not `P2-INSP-T14:` (ticket). The trailer names Claude Haiku 5.5, my own model (the dispatch's "Opus 5.5" is not my model).
- Readiness needs the IWP moved to `start-development` and `constraint-check`, then `awp worker --once` run twice (runbook and P2-I2). Not in the ticket; added.
- Reinspection is made without `--planned-on`. A planned date after today makes `record` refuse ("the time is before the day the inspection was planned").
- Clause 4 is checked inline in clauses 2 and 3; its PASS line prints after clause 3.
- Clause 7 compares 8 fields: `tl insp ls` cells against the export (`number`, `state`, `point`, `subject`, `for`, `inspector`, `scheduled`, `result`). The title is not in the export, so it is not compared.

## Changed files
- `dev/demos/P2-INSP.sh` — the demo: clauses 1-7 per backend, 7b on SQLite.
- `dev/demos/p2_insp_demo.py` — driver modes `clause5`, `clause6`, `clause6-propose`, `export`.
- `docs/reports/P2-IP/INSPT14.md` — this report.

## Commands and output
```
$ uv run ruff format --check dev/demos/p2_insp_demo.py    -> 1 file already formatted
$ uv run ruff check dev/demos/p2_insp_demo.py             -> All checks passed!
$ uv run pyright dev/demos/p2_insp_demo.py                -> 0 errors, 0 warnings, 0 informations
$ just demo P2-INSP   (SQLite, decisive lines; clauses 1-4, 6, 7 also PASS, not shown)
PASS clause 2: P123-INS-0001 rejected with one category A punch item P123-PUN-0001 linked; rob's verify refused; sue verifies
PASS clause 5: P123-INS-0003 from P123-COR-0001 is absent for uma (CLI list, total 2, API 404, MCP as uma and as the agent) and answers as a missing key; sue and dora list it
PASS clause 7b: quality: 57 records, 326 events, 6.3s; tl insp ls on the generated ledger is not empty (SQLite only)
[sqlite] clauses passed
$ just demo P2-INSP   (Postgres, decisive lines)
PASS clause 4: inspections_planned on P123-IWP-PIP-0001: n_a, blocked (Planned), ok (Scheduled), blocked (reject), ok (reinspection Scheduled)
planned P123-INS-0003  version 2
error: no inspection P123-INS-0003
FAIL the API gave 0 (cannot reach the server: ReadTimeout: timed out) and 0 (cannot reach the server: ReadTimeout: timed out)
exit 1
```
Control: `TL_DEMO_BACKENDS=postgres just demo P2-PUNCH` passes all six clauses.

## Tests added
none (the demo is the check)

## Clauses: the comparison that fails if the feature breaks [surface]
1. Checklist [CLI]: `edit` of a Published checklist refused (text); `ls` shows CHK1 `version 1 Retired`, CHK2 `version 2 Published`.
2. Hold point [CLI, punch, link]: `record` with a failed required answer gives `result reject`, `punch 1`; the punch row is category A, subject `INS1 q1:`; `link list` shows `raised against INS1`; rob's verify refused; sue's passes.
3. Reinspect [CLI]: `show INS2` has `Reinspection of INS1`; all pass gives `result accept`, `punch 0`.
4. Readiness [awp readiness]: `inspections_planned` is `n_a`, `blocked`, `ok`, `blocked`, `ok` after each step (worker run first).
5. Hidden [CLI, API, MCP]: `show` of the hidden key equals `show P123-INS-9999` after key substitution; uma's `ls` total equals its rows; API 404 and MCP get texts equal the missing-key texts; MCP list lacks the key for uma and the agent.
6. One state [API, TUI, MCP]: `show` fields equal `ApiClient.get_inspection`; palette `inspections` at 170x44 shows key and state; MCP list and get agree; the proposal is pending, `ls` unchanged until uma accepts, then one new row; no `mcp.record_*` or `mcp.verify_*` action.
7. Export [CSV, JSONL]: rows equal `ls` rows on 8 fields, same count.
7b. Generator [SQLite]: quality line without `skipped`; `tl insp ls` total at least 1.

## Learnings (proposed)
- A fresh IWP has no readiness row: `readiness show` says `no readiness` until the IWP is at constraint-check and the worker has run.
- `ls` rows are separated by two spaces (cells are single-spaced); split on `"  "`, not on whitespace.
- A transport failure reaches a driver as `ApiError` status 0, not as a 404.

## Open questions / Blocked
Blocked on Postgres, clause 5 (and so clause 6 and 7 on Postgres).
- Observed: after the IWP moves to constraint-check and the worker runs, the first API GET for a hidden inspection on Postgres does not answer in 30 s. The server log is silent. Meanwhile pg_stat_activity shows a connection active for minutes on the AWP IWP-list query (`packages/tl-modules/awp/src/tl_mod_awp/iwp_views.py`, `_iwp_rows`). P2-PUNCH has no such query and passes.
- Not confirmed: why the query runs for minutes, and which process runs it. The cause is not in `dev/demos`; a fix means a change under `packages/` (awp readiness or the IWP list), outside Allowed paths.
- Question for the supervisor: which change is authorised (an awp fix in a new ticket, or a demo step order that avoids the query)? I did not guess.
