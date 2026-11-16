# P2-X4-T06 — AGENTS.md rows, package README line, X4 follow-ups

Status: ready (names of the runbook and demo are fixed; those files land with T04 and T05c)
Tier: haiku
review: lite
Labels: docs
Depends on: none to start (cites `docs/runbooks/new-module.md` from T04 and `dev/demos/P2-X4.sh` from T05c by name); merge after T04 and T05c.
Branch: `p2/x4-t06-agents-rows`
Worktree: `/home/user/wt/x4/t06`

## Goal
`AGENTS.md` "Where things go" has two new rows, `docs/templates/package-readme.md` has one new line under "Module standard", and `docs/build-spec/DEFERRED.md` has two rows for the X4 follow-ups. Docs only.

## Brief references (pasted; exact content)
1. AGENTS.md row 1: Module hooks and the new-module guide: `ModuleSpec` hooks `commands`, `read_routers`, `tools`, `cli_groups` (lazy refs; ADR-0029; `tl new module`; runbook `docs/runbooks/new-module.md`; demo `dev/demos/P2-X4.sh`)
   | paths: core `packages/tl-core/src/tl_core/modules.py`; API `packages/tl-api/src/tl_api/commands.py`; MCP `packages/tl-mcp/src/tl_mcp/server.py`; CLI `packages/tl-cli/src/tl_cli/main.py`; scaffold `packages/tl-cli/src/tl_cli/scaffold/`.
2. AGENTS.md row 2: Worked module fixture `ext_demo` (never installed; loaded with `use_modules`; `tests/ext_demo/README.md`) | `tests/ext_demo/`; tests `tests/services/test_ext_demo_conformance.py`, `packages/tl-api/tests/test_ext_demo_api.py`, `packages/tl-mcp/tests/test_ext_demo_mcp.py`.
3. package-readme.md, under "Module standard", one bullet: a module README names its hooks (`commands`, `read_routers`, `tools`, `cli_groups`) and the command names it declares, which are unique across modules; see `docs/runbooks/new-module.md`.
4. DEFERRED.md row A (date 2026-11-16; format of the P2-X4 row there): P2-I4B's scaffold module is not on this branch (no `SCAFFOLD_COMMANDS` in the tree at X4 head); when it lands, its registry lines
   (a `commands.py` entry, `routes/scaffold.py`, its `app.py` line) are pre-hook lines: either move them into its `module.py` hooks `commands` and `read_routers` (and add `scaffold` to `IN_TREE_SURFACES`, a gated core
   edit, or move its router into its own package) or list them in `tests/tools/prehook_lines.toml` | the P2-I4B ticket.
   Row B: new modules from P2-IP (QR, INSP, PTW) are not in `IN_TREE_SURFACES`, so each hook ref sits in the module's own package (`tl_mod_<m>.routes:router`, `.tools:register_tools`, `.cli:<m>_app`); a commands row needs a
   delegation mark in row `meta` and a proposable row or an exclusion entry | P2-IP specs.
   Row C: opening a module tool to agents is a platform edit to `MCP_ACTIONS` (`tl_mcp/identity.py`); no module hook names tool actions | when a module's tool must open without a platform edit: a hook (APPROVALS line).

## Context (read these, nothing else)
- `AGENTS.md` lines 59-92, `docs/templates/package-readme.md`, `docs/build-spec/DEFERRED.md` (the rows around line 142)
may explore: (none)

## Allowed paths
- `AGENTS.md` (two rows, appended to the table)
- `docs/templates/package-readme.md` (one bullet)
- `docs/build-spec/DEFERRED.md` (three rows)
- `docs/reports/P2-X4/T06.md` (create)

## Acceptance
```
just check
```
Expected: exit 0. Diff ≤ 15 lines of table text; no model names; no other row touched.

## Tests to add
none (docs).

## Report requirements
Standard report.

## Escalation triggers
- Stop and report *Blocked* if a path named above does not exist (except the runbook and demo, which merge in the same batch).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
