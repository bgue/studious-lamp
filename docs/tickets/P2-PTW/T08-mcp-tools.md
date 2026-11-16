# P2-PTW-T08 - MCP tools of the permits module (permit reads and propose_permit)

Status: ready (written r4; base `p2/ip-r3`; PTW-S2 and T01 merged; `list_isolations` waits for T02)
Tier: haiku
Kind: ticket
Review: full
Labels: mcp, permits, confidentiality, safety
Depends on: P2-PTW-S2 (stub `tools.py`, `propose_permit` row), P2-PTW-T01 (views), merged
Branch: `p2/ptw-t08-mcp-tools`
Worktree: `/home/user/wt/ptw/t08` (from `p2/ip-r3`)

## Goal
`tl_mod_permits/tools.py` registers `list_permits`, `get_permit`, `permit_board` and `propose_permit` in `register_tools(server, ctx)` (the hook already names it). Each is closed to agents until an allow row lists it. There is no tool that approves, issues, suspends, resumes, hands back, closes or cancels. `list_isolations` is PTW-T08b after PTW-T02.

## Rules
- Pattern: `tl_mcp/punch_tools.py` whole (`guarded`, `READ_ONLY`, `PROPOSES`, `IntentParam`, `proposals.submit`, the actions tuple and its import into `tl_mcp/identity.py` `MCP_ACTIONS`); imports of `tl_mcp.*` are allowed in the module package. Name the tuple `PERMIT_MCP_ACTIONS` and add it to `identity.py` the same way (one import line and one tuple line).
- Reads under `guarded` (lowest clearance), `viewer=` explicit, `now = utcnow()` once per call; a missing, hidden or other-project key answers `RecordNotFoundError("no permit <key>")`; `list_permits(project, state?, permit_type?, area?, holder?, limit)` (default 50, at most `MAX_PART`), `get_permit(project, key)`, `permit_board(project, area?)`. States are the shown ones (`Lapsed` in place of `Active`).
- `propose_permit(project, permit_type, area, location_text, work_description, holder, needed_from, needed_until, for_key?, summary?, intent)`: `for_key` resolves with `get_record` under the lowest viewer; files `proposals.submit` of `RequestPermit` as `propose_punch_item_impl` does; the accepting person needs `permits.request`. The row stays `excluded:reserved` for policy auto-accept (D10; do not touch the marks).
- `OLD_TOOL_NAMES` in `packages/tl-mcp/tests/test_module_tool_hooks.py` is extended by union with the four names.

## Context (read these, nothing else)
- `packages/tl-mcp/src/tl_mcp/punch_tools.py` (whole), `packages/tl-mcp/src/tl_mcp/identity.py` (the `PUNCH_MCP_ACTIONS` lines only)
- `packages/tl-modules/permits/src/tl_mod_permits/tools.py`, `views.py` (signatures), `commands.py` (`RequestPermit`, lines 59-93)
- `packages/tl-mcp/tests/test_punch_tools.py` (1-140), `packages/tl-mcp/tests/test_module_tool_hooks.py`, `packages/tl-modules/permits/tests/permit_world.py`

## Allowed paths
- `packages/tl-modules/permits/src/tl_mod_permits/tools.py` (edit), `packages/tl-mcp/src/tl_mcp/identity.py` (the one import and the one tuple line)
- `packages/tl-mcp/tests/test_permit_tools.py` (create), `packages/tl-mcp/tests/test_module_tool_hooks.py` (the pin by union)
- `docs/reports/P2-PTW/T08.md` (create)

## Tests to add (`test_permit_tools.py`; ledger from `permit_world.World`, harness as `test_punch_tools.py`)
1. Each read tool for the five readers: the reader who cannot see a restricted-for-record permit gets no row, no count, and the missing-key error for it.
2. An agent with no allow row is refused every tool; after the allow row the reads work and `propose_permit` files a pending proposal that creates no permit.
3. Accepting as a person with `permits.request` creates the permit as that person (the requester is the accepting actor); without the word it is refused.
4. No tool named approve, issue, suspend, resume, hand back, close or cancel exists (`tools/list`).
5. A Lapsed permit shows `Lapsed` in `list_permits`, `get_permit` and `permit_board`.
6. The tool names appear in the registry pin; nothing else moved.

## Acceptance
```
uv run ruff format --check packages/tl-modules/permits packages/tl-mcp/src/tl_mcp/identity.py packages/tl-mcp/tests/test_permit_tools.py
uv run ruff check packages/tl-modules/permits packages/tl-mcp/src/tl_mcp/identity.py packages/tl-mcp/tests/test_permit_tools.py
uv run pyright packages/tl-modules/permits packages/tl-mcp/src/tl_mcp/identity.py packages/tl-mcp/tests/test_permit_tools.py
just gate packages/tl-mcp/tests/test_permit_tools.py
just gate packages/tl-mcp/tests/test_module_tool_hooks.py
```
Expected: clean on those paths; `gate: PASS` on each line. No `just check` (the orchestrator runs it at DONE), no whole-repo pyright, never `packages/tl-api/tests/test_commands.py`.

## Escalation triggers
An agent can read a hidden permit or a count that includes one; a proposal field the intent parameter cannot carry; `identity.py` needs more than the two lines.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; list pins and regenerated files outside Allowed paths. Commit subjects `P2-PTW-T08: ...` with the trailers the dispatch message names; no model names.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
