# P2-I4B-S2 — Merge trunk (P2-X4 hooks) and move scaffold onto the module hooks

kind: piece
review: full
branch: p2/i4b (work on a new branch `p2/i4b-s2-hooks` from p2/i4b, merged back by the orchestrator)
worktree: /home/user/wt/i4b-s2
Base: `p2/i4b` 013d36b3. Trunk `claude/wizardly-allen-m2v96s` 92969fca now carries P2-X4 (DEFERRED "P2-X4 follow-up A").
Labels: core interface (registry lines), merge.

## Why
P2-X4 builds the API command table, read routers, MCP tools and CLI groups from each module's `ModuleSpec` hooks
(`commands`, `read_routers`, `tools`, `cli_groups`; `tl_core/modules.py`, ADR-0029, `docs/reports/P2-X4.md`). P2-I4B added the
scaffold module before X4 with hand-written registry lines: `from tl_mod_scaffold.module import SCAFFOLD_COMMANDS` and
`*_module_specs("scaffold", SCAFFOLD_COMMANDS)` in `packages/tl-api/src/tl_api/commands.py`, a scaffold router line in
`packages/tl-api/src/tl_api/app.py`, and possibly MCP/CLI lines. A plain `git merge` of trunk conflicts in openapi.json, app.py,
commands.py, test_api_document_controller.py, test_api_proposals.py, test_commands.py.

## Goal
1. `git merge --no-ff claude/wizardly-allen-m2v96s` into `p2/i4b-s2-hooks`. Resolve every conflict by taking trunk's hooked
   form of the registry files and declaring scaffold's surfaces on its `ModuleSpec` instead:
   `commands="tl_mod_scaffold.module:SCAFFOLD_COMMANDS"`, `read_routers=(...)`, `tools=(...)`, `cli_groups=(...)` pointing at where
   scaffold's router, tool registrar and CLI app live today. Scaffold is not in `IN_TREE_SURFACES`; if its surfaces live in
   `tl_api.routes.scaffold` / `tl_mcp.*` / `tl_cli.*`, either add `scaffold` to `IN_TREE_SURFACES` (one line, core interface:
   say so in the report for an APPROVALS line) or move the surface into `tl_mod_scaffold` (prefer whichever is fewer lines).
2. No hand-written scaffold lines remain in tl-api, tl-mcp or tl-cli registries; `tests/tools/prehook_lines.toml` stays empty and
   the registry drift test passes.
3. Test pins: union both sides (controller set, command count, agent decisions, route_order.txt, openapi.json regenerated with
   `uv run python -m tl_api.openapi` — never hand-edited; OLD_* lists). Decide any new scaffold control actions in
   `packages/tl-api/tests/test_auth_review.py` (TagScaffoldGreen is already AGENT_MAY_NOT). Delegation marks for scaffold
   commands in `tests/tools/delegation_marks.toml` (safety acts excluded:reserved; the undecided ratchet may not grow).
4. Behaviour unchanged: scaffold routes, commands, tools and CLI answer exactly as before.

## Gates (one `just gate` call per tl-api / tl-mcp file; never `just check` or whole-repo pyright on this box)
ruff check + format on changed files; `uv run pyright <changed .py>`; `uv run python -m tl_schema.generate --check`,
`uv run python -m tl_api.openapi --check`; then `just gate` on: packages/tl-api/tests/test_commands.py,
test_api_document_controller.py, test_api_proposals.py, test_auth_review.py, test_module_hooks_api.py, test_run_command.py,
test_api_scaffold*.py (whatever exists), packages/tl-modules/scaffold/tests, tests/tools/test_registry_by_hooks.py,
tests/tools/test_delegation_marks*.py (whatever exists), tests/services/test_module_conformance.py, packages/tl-mcp/tests/test_mcp_server.py,
packages/tl-cli/tests/test_module_cli_groups.py. Save the summary in `.gate/summary.txt`.

## Report
`docs/reports/P2-I4B/S2.md`, at most 60 lines, no model names. Commit trailers exactly:
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4
