# P2-X4-T04 — runbook: add a module that brings its own commands, routes, tools and CLI group

Status: ready (T02b and S5 merged at 338e5265, 30e31f3d)
Tier: haiku
review: lite
Labels: docs
Depends on: T02b merged
Branch: `p2/x4-t04-runbook`
Worktree: `/home/user/wt/x4/t04`

## Goal
`docs/runbooks/new-module.md` exists, from `docs/templates/runbook.md`: an author who has never seen X4 can scaffold a module, add a record type and a command row, and
knows what the three surfaces are, which one is closed to agents, and what is not built. `docs/runbooks/README.md` lists it. Docs only; no code, no schema.

## Brief references (pasted; state these facts, do not add others)
1. Steps, in order (each with its command and the expected line): `uv run tl new module <name>` (stdout lists each `created <path>`; stderr lists the next steps: `uv lock && uv sync --all-packages`,
   edit `docs/modules/<name>/README.md` and `schema/modules/<name>/module.yaml`, `uv run tl new record-type <name>.<Class>`, `just check && just test`); add a record type; add a command row.
2. Command row (`tl_core.modules.ModuleCommand`, in `<package>/commands.py` `COMMANDS`): `module`, `model` (the Command class; its class name is the command name and is unique across all installed
   modules, a clash stops the process at load), `handler` `(UnitOfWork, Any) -> CommandResult`, `access` (the access word the person needs), `meta={"delegation": "excluded:reserved"}`
   (`eligible` or `excluded:<reason>`; a missing mark means excluded). A command an agent may propose also needs a `ProposableCommand` in the spec; one that is not proposable needs an entry in
   `tests/tools/proposable_exclusions.toml`; in-tree legacy marks live in `tests/tools/delegation_marks.toml` (a row's `meta` wins). Money fields and the access word are checked by `tests/services/test_module_conformance.py`.
3. The three surfaces the scaffold writes, all inside the module's own package and named by refs on the `ModuleSpec` (`read_routers`, `tools`, `cli_groups`): `routes.py` (`GET /modules/<name>/ping`,
   `guard("document.read")`, fixed text), `tools.py` (`register_tools`, tool `<name>_ping`, read-only), `cli.py` (`<name>_app`, so `tl <name> ping` prints the name). Refs outside the own package are
   refused (ADR-0029; only the 11 in-tree modules may name `tl_api.routes.`, `tl_mcp.`, `tl_cli.` refs).
4. Closed by default: an agent may call only the actions on its allow list. A module tool's action is `mcp.<tool>` (`mcp.<name>_ping`). Today the list is `MCP_ACTIONS` in
   `packages/tl-mcp/src/tl_mcp/identity.py` (explicit names, no prefix rule), so opening a module tool for agents is a reviewed platform edit and an orchestrator decision; there is no module hook
   for it (say so; it is not a DEFERRED row yet, flag it in the report). Routes: agents hold `document.read` and the other `AGENT_ACTIONS` only.
5. Reads: a route or tool that returns record text reads through the viewer's class filter (`tl_core.confidentiality`, `ConfidentialSource` on the spec); a hidden record answers exactly as a
   missing one (same status, same text, same count). Worked example: `tests/ext_demo/` (`tests/ext_demo/README.md`), never installed; its tests are `tests/services/test_ext_demo_conformance.py`,
   `packages/tl-api/tests/test_ext_demo_api.py`, `packages/tl-mcp/tests/test_ext_demo_mcp.py`.
6. No errors hook: `ModuleSpec` has no `errors` hook, so a new module raises the core error classes (they have rows in `tl_api/errors.py`). The `docs/build-spec/DEFERRED.md` row (P2-X4) says when to add one.
7. A hook that cannot be resolved fails that module's hook only, with one fixed message (`module '<name>': hook '<hook>' cannot be resolved`, no ref in it); the other modules still load (`hook_failures()`).
8. TUI: not hooked. Screens still import modules by name; a module without screens reads through the generic record views.

## Context (read these, nothing else)
- `docs/templates/runbook.md`, `docs/runbooks/README.md`
- `docs/runbooks/requisitions.md` (style of a module runbook; do not copy content)
- `tests/ext_demo/README.md`
- `docs/reports/P2-X4/T02b.md`
may explore: (none)

## Allowed paths
- `docs/runbooks/new-module.md` (create)
- `docs/runbooks/README.md` (one list line)
- `docs/reports/P2-X4/T04.md` (create)

## Acceptance
```
just check
```
Expected: exit 0. Every command in the runbook exists (`uv run tl new module --help` prints). Runbook ≤ 120 lines, no model names, plain technical wording, no claim beyond the brief references.

## Tests to add
none (docs).

## Report requirements
Standard report (`docs/templates/haiku-report.md`); list any brief reference you could not state as written.

## Escalation triggers
- Stop and report *Blocked* if a fact above contradicts the code you read.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
