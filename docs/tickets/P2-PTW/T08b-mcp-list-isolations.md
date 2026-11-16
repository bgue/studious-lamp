# P2-PTW-T08b - MCP tool `list_isolations` (and gas tests of a permit)

Status: staged (written r5; base `p2/ip-r3` after PTW-T02 merges; PTW-T08 merged)
Tier: haiku
Kind: ticket
Review: full
Labels: mcp, permits, confidentiality, safety
Depends on: P2-PTW-T08 (`tools.py`, `PERMIT_MCP_ACTIONS`), P2-PTW-T02 (`iso_views`), merged
Branch: `p2/ptw-t08b-mcp-isolations`
Worktree: `/home/user/wt/ptw/t08b` (from `p2/ip-r3`)

## Goal
`tools.py` gains two read tools, `list_isolations(project, state?, energy?, limit)` and `list_gas_tests(project, permit_key, limit)`, closed to agents until an allow row lists them. No tool applies, verifies, removes, links or records.

## Rules
- Same shape as the T08 read tools in the same file (`guarded`, `READ_ONLY`, viewer explicit, lowest clearance by default); add the two names to `PERMIT_MCP_ACTIONS` (the tuple T08 made; the `identity.py` import line stays as it is: one tuple edit, no second line).
- `list_isolations`: default limit 50, at most `MAX_PART`; rows are the view fields minus the record `id` that the other permit tools already omit (follow T08 for what a row carries). `list_gas_tests`: the permit resolves through the permit detail view under the lowest viewer; a hidden, unknown or other-project key answers `RecordNotFoundError("no permit <key>")` exactly as `get_permit` does; a visible permit with no tests is an empty list.
- `OLD_TOOL_NAMES` in `packages/tl-mcp/tests/test_module_tool_hooks.py` and `TOOLS` in `packages/tl-mcp/tests/test_mcp_server.py` are extended by union with the two names (consequential pins, rule 12; list them in the report). `tools/list` must carry no write tool for isolations or gas tests.
- No SQL, no write, no clock.

## Context (read these, nothing else)
- `packages/tl-modules/permits/src/tl_mod_permits/tools.py` (whole), `iso_views.py` (signatures), `packages/tl-mcp/src/tl_mcp/identity.py` (the `PERMIT_MCP_ACTIONS` lines)
- `packages/tl-mcp/tests/test_permit_tools.py` (T08's harness; extend by a new file, do not edit it), `test_module_tool_hooks.py`, `test_mcp_server.py` (the `TOOLS` pin)

## Allowed paths
- `packages/tl-modules/permits/src/tl_mod_permits/tools.py` (edit), `packages/tl-mcp/src/tl_mcp/identity.py` only if the T08 tuple lives there (it should not need an edit)
- `packages/tl-mcp/tests/test_permit_iso_tools.py` (create), `packages/tl-mcp/tests/test_module_tool_hooks.py` (the pin by union), `packages/tl-mcp/tests/test_mcp_server.py` (the `TOOLS` pin by union)
- `docs/reports/P2-PTW/T08b.md` (create)

## Tests to add (`test_permit_iso_tools.py`)
1. Each tool for the five readers: no hidden row, no hidden count; the hidden permit's tests are the missing-key error, the same text as an unknown key.
2. An agent with no allow row is refused both tools; after the allow row the reads work.
3. No tool named apply, verify, remove, link, unlink or record exists in `tools/list`.
4. A failing gas test shows `fail` in `list_gas_tests`; a permit with no tests answers `[]`.
5. The two names appear in the registry pins; nothing else moved.

## Acceptance
```
uv run ruff format --check packages/tl-modules/permits packages/tl-mcp/tests/test_permit_iso_tools.py
uv run ruff check packages/tl-modules/permits packages/tl-mcp/tests/test_permit_iso_tools.py
uv run pyright packages/tl-modules/permits/src/tl_mod_permits/tools.py packages/tl-mcp/tests/test_permit_iso_tools.py
just gate packages/tl-mcp/tests/test_permit_iso_tools.py
just gate packages/tl-mcp/tests/test_module_tool_hooks.py
just gate packages/tl-mcp/tests/test_mcp_server.py
```
Expected: clean; `gate: PASS` on each line. No `just check`, no whole-repo pyright.

## Escalation triggers
An agent can read a hidden permit's gas tests or a count that includes one; the tuple edit needs more than a name.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; list pins. Commit subjects `P2-PTW-T08b: ...` with the trailers the dispatch message names; no model names.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
