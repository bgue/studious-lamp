# Report — P2-INSP-T07

Branch: `p2/insp-t07-mcp-tools`   Commit(s): see the commit on this branch (final sha in the return)

## Deviations
Blocked, not done: `packages/tl-mcp/tests/test_mcp_server.py` pins the tool set and fails (see Open questions). I did not edit it, because it is outside Allowed paths.
Also outside the ticket's named edits: `test_module_tool_hooks.py` registrar count `14` became `15` (the ticket named the pin by union but not this count; the count moved by the one new `tools` ref in the quality module).

## Changed files
- `packages/tl-mcp/src/tl_mcp/insp_tools.py` (new) — `INSP_MCP_ACTIONS`; reads `list_inspections`, `get_inspection`, `list_checklists`, `get_checklist`; proposal `propose_inspection` (PlanInspection via `proposals.submit`).
- `packages/tl-mcp/src/tl_mcp/identity.py` — one import and one `| INSP_MCP_ACTIONS` line.
- `packages/tl-modules/quality/src/tl_mod_quality/module.py` — `tools` now lists `tl_mcp.insp_tools:register_insp_tools` after the punch registrar.
- `packages/tl-mcp/tests/test_insp_tools.py` (new) — 10 tests over `insp_world.py` (loaded by path, as `test_punch_tools.py` does).
- `packages/tl-mcp/tests/test_module_tool_hooks.py` — five names unioned into `OLD_TOOL_NAMES`; registrar count 14 to 15.
- `docs/reports/P2-IP/INSPT07.md` — this report.

## Commands and output
```
$ uv run ruff format --check <4 paths>
4 files already formatted
$ uv run ruff check <4 paths>
All checks passed!
$ uv run pyright <4 paths>
0 errors, 0 warnings, 0 informations
$ just gate packages/tl-mcp/tests/test_insp_tools.py
part 1: exit 0, 10 passed in 23.46s
gate: PASS
$ just gate packages/tl-mcp/tests/test_module_tool_hooks.py
part 1: exit 0, 5 passed in 1.75s
gate: PASS
$ just gate packages/tl-mcp/tests/test_confidentiality_walk.py packages/tl-mcp/tests/test_mcp_server.py
part 1: exit 1, 1 failed, 14 passed in 85.66s
FAILED packages/tl-mcp/tests/test_mcp_server.py::test_the_phase_0_surface_is_read_tools_proposing_tools_and_post_feed
gate: FAIL
```
The failing assertion (`{t.name for t in tools} == TOOLS`) lists extra items: `list_checklists`, `propose_inspection`, `list_inspections`, `get_inspection` (this ticket), plus `permit_board`, `propose_permit`, `list_permits` (permits registrar already on the base commit 705b3f5d; not this ticket's doing).

## Tests added
- `test_insp_tools.py::test_the_reads_return_rows_and_the_page_total` — list totals, filters, limit, detail, missing-key text.
- `::test_the_checklist_reads_return_rows_and_the_questions` — checklist list/detail, unknown state refused.
- `::test_a_reader_who_cannot_see_the_subject_gets_no_row_and_the_missing_key_text` — five readers, hidden subject: no row, same text as a missing key.
- `::test_the_five_readers_see_the_same_inspection_list` — the same list for all five readers.
- `::test_an_agent_without_an_allow_row_is_refused_every_tool` — closed until `INSP_MCP_ACTIONS` is allowed; the proposal files pending and plans nothing.
- `::test_a_missing_or_hidden_subject_key_is_refused_with_one_text` — propose with unknown or hidden key.
- `::test_propose_files_a_pending_proposal_that_changes_no_record`.
- `::test_accepting_the_proposal_plans_the_inspection_and_a_viewer_may_not` — viewer gets `ProposalAccessError`; `uma` plans `P123-INS-0001`.
- `::test_no_tool_schedules_records_verifies_reinspects_or_cancels`.
- `::test_the_inspection_tools_are_listed_and_the_reads_are_read_only`.

## Learnings (proposed)
- The ticket's `Worktree:` path (`/home/user/wt/insp/t07`) differs from the dispatch path; I used the dispatch path.
- `test_module_tool_hooks.py` pins a registrar count (`== 14`), not only names. Any new `tools` ref needs that number bumped; the ticket did not say so.
- `test_mcp_server.py::TOOLS` is a second exact tool-set pin, not named in the ticket's Allowed paths. Every new MCP tool hits it.
- Permits tools (`permit_board`, `propose_permit`, `list_permits`) are missing from that pin on the base commit already.
- `guarded` always reads at `LOWEST`, so the five readers see identical rows; the "five readers" tests check that.

## Open questions / Blocked
Blocked on `packages/tl-mcp/tests/test_mcp_server.py`, which is outside Allowed paths:
1. Should the five new names (`list_inspections`, `get_inspection`, `list_checklists`, `get_checklist`, `propose_inspection`) be added to `TOOLS`/`READING` in that file, under a separate ticket or an allowed-path edit?
2. The same test already fails on the base commit because the permits tools (`permit_board`, `propose_permit`, `list_permits`) are not in `TOOLS`. Should that be fixed in this ticket, or left to the owner of the permits branch?

The ticket is otherwise implemented; I have not changed anything else to get the gate green. Status: blocked on the question above.
