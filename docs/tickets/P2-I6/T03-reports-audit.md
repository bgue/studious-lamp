# P2-I6-T03 — Base reports audit against §12 for M3, M4 and M9

Status: draft (staged-blocked: waits for P2-I5 merged to the trunk and merged into `p2/i6`)
Tier: haiku
Kind: ticket
Review: lite
Labels: docs
Depends on: P2-I5 on trunk (its weekly-plan reports must exist to be audited); merges before X4 S2 (`12-extension-plan.md` §3)
Branch: `p2/i6-t03-reports-audit`
Worktree: harness-created under `/home/user/wt/i6/t03` (from `p2/i6` head)

## Haiku-ability checklist (run r1)
1 context: 6 files (yes). 2 interfaces: nothing is built, the audit reads CLI help and `openapi.json` (yes). 3 acceptance commands with expected output below (yes).
4 diff: one table file and up to about 12 draft tickets of 15 lines (yes, under 400 lines; split the drafts across two commits if more). 5 no supervisor-tier row (yes).
6 docs only (yes). 7 verifiable from the diff and the command outputs pasted in the report (yes). `lite`: docs and a table.

## Goal
`docs/reports/P2-I6/T03-reports-audit.md` has one row per base report that brief §12 lists for M3 (AWP/WBS), M4 (Materials) and M9 (Requisitions/WO), each with the
CLI command and the API route that run it today, or `GAP`. Every `GAP` is a draft ticket under `docs/tickets/P2-I6/drafts/`. The audit is the input of exit demo clause 5
("every §12 M3, M4 and M9 base report runs from the CLI and the API with a non-empty result").

## Brief references (pasted, §12 rows)
> AWP/WBS: CWP/IWP status; IWP readiness & constraint log; constraints by type/owner/age; backlog of ready IWPs (weeks of backlog).
> Materials: Stock on hand by location/item; transaction log; MTO vs received vs issued; shortages against IWPs; equipment utilisation & location; consumable usage by cost code; heat number traceability.
> Requisitions/WO: Open requisitions; scaffold register (status, tag colour, inspection due); scaffold quantities on hire; labor requisition forecast by craft/week; WO backlog.
> Known mapping to check (not trusted): materials `stock_on_hand`, `movement_log`, `mto_status`, `shortages`, `heat_trace`, `consumables_by_cost_code` (`tl mat report NAME`, route `/projects/{project}/materials/reports/{name}`); AWP `tl awp report NAME`, route `/projects/{project}/awp/reports/{name}`; requisitions `tl req ls`, `tl wo ls` (reads), forecast and reports deferred (I4-A trim, roadmap 3c); scaffold reports wait for the I4-B scaffold module; equipment utilisation & location needs toolcrib (I4-B).
> Brief §12 also says reports are runnable in TUI, API, MCP; this audit covers the CLI and the API only (demo clause 5).

## Interfaces (the audit's table; copy this shape)
```
| # | Module | §12 report | CLI command | API route | Non-empty on seed? | Status | Draft ticket |
```
Status is `OK` (both run), `CLI-ONLY`, `API-ONLY`, `GAP` (neither), or `BLOCKED-BY <increment>` (needs a module not built yet). "Non-empty on seed" is `yes`, `no` or `n/a`, from the demo seed (`dev/seed`, `just seed`; do not run the long seed: read the demo script and the report tests to see what they seed, say so in the note).

## Context (read these, nothing else)
- `docs/brief-v0.4.md` §12 lines 1490-1512 (already pasted above; open only to confirm)
- `docs/reference/openapi.json` (search for `reports`, `requisitions`, `work-orders`, `awp`; do not read it whole)
- `packages/tl-cli/src/tl_cli/{awp_report,mat_report,req_read}.py`
- `docs/runbooks/{awp,materials,requisitions}.md`
- `docs/build-spec/DEFERRED.md` (grep `req`)
may explore: `packages/tl-cli/tests/` for the report names the tests run.

## Allowed paths
- `docs/reports/P2-I6/T03-reports-audit.md` (create; the table, then 3 lines of notes)
- `docs/tickets/P2-I6/drafts/D<nn>-<slug>.md` (create; one per gap; header `Status: draft`, goal, what the report shows, which view or command exists, dependency; <= 15 lines each, no steps)
- `docs/reports/P2-I6/T03.md` (create)

## Acceptance
Run and paste the five-line result of each in the report:
```
uv run tl awp report --help
uv run tl mat report --help
uv run tl req --help
uv run tl wo --help
grep -c '"/projects/{project}/.*report' docs/reference/openapi.json
```
Expected: the table has exactly 16 rows (4 + 7 + 5, in the §12 order); every row names a command and route that appear in the help or `openapi.json` outputs, or is `GAP` / `BLOCKED-BY` with a draft ticket; the number of files in `drafts/` equals the number of `GAP` and `BLOCKED-BY` rows (blocked rows may share a draft when one module is the cause: say which in the Draft ticket column).

## Tests to add
None (docs). The reviewer checks the table against the pasted command output.

## Report requirements
Standard report, <= 60 lines. Commit subjects `P2-I6-T03: ...`; trailers `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Escalation triggers
- A report exists under a name the table cannot match to a §12 row (write the question under Blocked); a command in the help output does not run.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
