# Report — P2-INSP-T07

Branch: `p2/insp-t07-mcp-tools`   Commit(s): `c53e8f9b` (implementation) and the ruling commit on top (final sha in the return)

## Deviations
- `packages/tl-mcp/tests/test_mcp_server.py` edited under the ruling (added to Allowed paths). Pinned tool set extended by union: the base's permit tools (`list_permits`, `get_permit`, `permit_board` as reads; `propose_permit` as a proposal) and the five insp tools. Nothing removed.
- `packages/tl-mcp/tests/test_module_tool_hooks.py` registrar count 14 to 15: accepted by the ruling.
- Report path is `docs/reports/P2-IP/INSPT07.md` as dispatched; the ticket names `docs/reports/P2-INSP/T07.md`.

## Changed files
- `packages/tl-mcp/src/tl_mcp/insp_tools.py` (new, from c53e8f9b) — `INSP_MCP_ACTIONS`; reads `list_inspections`, `get_inspection`, `list_checklists`, `get_checklist`; proposal `propose_inspection` (PlanInspection via `proposals.submit`).
- `packages/tl-mcp/src/tl_mcp/identity.py` (from c53e8f9b) — one import, one `| INSP_MCP_ACTIONS` line.
- `packages/tl-modules/quality/src/tl_mod_quality/module.py` (from c53e8f9b) — `tools` appends `tl_mcp.insp_tools:register_insp_tools`.
- `packages/tl-mcp/tests/test_insp_tools.py` (new, from c53e8f9b) — 10 tests.
- `packages/tl-mcp/tests/test_module_tool_hooks.py` (from c53e8f9b) — five names unioned into `OLD_TOOL_NAMES`; count 14 to 15.
- `packages/tl-mcp/tests/test_mcp_server.py` (ruling commit) — `READING` gets the permit reads (PTW-T08) and the four insp reads (P2-INSP-T07); `TOOLS` gets `propose_permit` and `propose_inspection`, one comment line each.
- `docs/reports/P2-IP/INSPT07.md` — this report.

## Commands and output
```
$ just gate packages/tl-mcp/tests/test_insp_tools.py
part 1: exit 0, 10 passed in 24.46s
gate: PASS
$ just gate packages/tl-mcp/tests/test_module_tool_hooks.py
part 1: exit 0, 5 passed in 1.74s
gate: PASS
$ just gate packages/tl-mcp/tests/test_mcp_server.py
part 1: exit 0, 9 passed in 6.82s
gate: PASS
$ uv run ruff format --check <6 changed paths>
6 files already formatted
$ uv run ruff check <6 changed paths>
All checks passed!
$ uv run pyright <6 changed paths>
0 errors, 0 warnings, 0 informations
```
Before the ruling, `test_mcp_server.py` failed on `{t.name for t in tools} == TOOLS` with extras `list_permits`, `get_permit`, `permit_board`, `propose_permit` (PTW-T08, present on base 705b3f5d) and `list_inspections`, `get_inspection`, `list_checklists`, `get_checklist`, `propose_inspection` (this ticket). No right-side extras.

## Tests added
- `test_insp_tools.py::test_the_reads_return_rows_and_the_page_total` — list totals, filters, limit, detail, missing-key text.
- `test_insp_tools.py::test_the_checklist_reads_return_rows_and_the_questions` — checklist list and detail; unknown state refused.
- `test_insp_tools.py::test_a_reader_who_cannot_see_the_subject_gets_no_row_and_the_missing_key_text` — five readers; hidden subject gives no row and the same text as a missing key.
- `test_insp_tools.py::test_the_five_readers_see_the_same_inspection_list`.
- `test_insp_tools.py::test_an_agent_without_an_allow_row_is_refused_every_tool`.
- `test_insp_tools.py::test_a_missing_or_hidden_subject_key_is_refused_with_one_text`.
- `test_insp_tools.py::test_propose_files_a_pending_proposal_that_changes_no_record`.
- `test_insp_tools.py::test_accepting_the_proposal_plans_the_inspection_and_a_viewer_may_not` — viewer gets `ProposalAccessError`.
- `test_insp_tools.py::test_no_tool_schedules_records_verifies_reinspects_or_cancels`.
- `test_insp_tools.py::test_the_inspection_tools_are_listed_and_the_reads_are_read_only`.

## Learnings (proposed)
- `test_mcp_server.py::TOOLS` is a second exact tool-set pin that the ticket did not name. Every new MCP tool hits it; name it in Allowed paths up front.
- `test_module_tool_hooks.py` pins a registrar count, not only names; a new `tools` ref bumps it.
- The ticket's `Worktree:` path (`/home/user/wt/insp/t07`) differs from the dispatch path (`/home/user/wt/ip4/inspt07`).

## Open questions / Blocked
none
