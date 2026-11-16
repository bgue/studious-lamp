# Runbook — add a module with its own command, route, tool and CLI group

Purpose: scaffold a new module, add one record type and one command row, and know which of its three surfaces an agent can reach (none by default). Ticket: P2-X4-T04.

## When to use
- Trigger: a new module is needed and it must bring its own commands, a read route, an agent tool and a CLI group.
- Not for: changing an existing in-tree module. For a requisition-style module, read `docs/runbooks/requisitions.md` as an example of a finished module.

## Before you start
- Access needed: a checkout with `uv` and `just` installed. Writing a module is a code change: it goes through a ticket (AGENTS.md ground rule 1).
- The module name is lower_snake_case, for example `inspection`.
- Safe to run during business hours: yes. The scaffold writes files only; nothing is installed until you run `uv sync`.

## Steps
1. Preview the files, then write them. `--dry-run` prints the files and writes nothing.
   ```
   uv run tl new module inspection --dry-run
   uv run tl new module inspection
   ```
   Expected: `--dry-run` lists the files. The real run's stdout has one `created <path>` line per file. The paths are under `packages/tl-modules/inspection/`, `schema/modules/inspection/module.yaml` and `docs/modules/inspection/`.
   Expected on stderr, the next steps:
   ```
   uv lock && uv sync --all-packages
   edit docs/modules/inspection/README.md and schema/modules/inspection/module.yaml
   uv run tl new record-type inspection.<Class>
   just check && just test
   ```
2. Lock and install the new package.
   ```
   uv lock && uv sync --all-packages
   ```
   Expected: `uv.lock` is updated to include the new package; the sync finishes without error.
3. Edit the two files the scaffold names: `docs/modules/inspection/README.md` (what the module is for) and `schema/modules/inspection/module.yaml` (its record types and classes).
4. Add a record type. The name is `<module>.<Class>`, for example `inspection.Finding`.
   ```
   uv run tl new record-type inspection.Finding
   ```
   Expected: a schema stub, a handler, tests and a spec page for the class are written. The scaffold does not set a confidentiality class; the module declares it on `ModuleSpec.confidential` (see the Reads section below).
5. Add a command row. Each module lists its commands in `COMMANDS` in `<package>/commands.py`. A row is a `tl_core.modules.ModuleCommand` with these fields:
   - `module`: the module name.
   - `model`: the Command class. Its class name is the command name. The name must be unique across all installed modules, and must not equal a core command name (see Names a module may not reuse below).
   - `handler`: a callable `(UnitOfWork, Any) -> CommandResult`.
   - `access`: the access word the person needs to run it.
   - `meta`: a `delegation` mark, for example `{"delegation": "excluded:reserved"}`. The value is `eligible` or `excluded:<reason>`. A missing mark means excluded.
6. Decide on agent proposals for the command.
   - If an agent may propose it, add a `ProposableCommand` entry in the spec.
   - If it is not proposable, add an entry to `tests/tools/proposable_exclusions.toml`.
   - In-tree legacy marks live in `tests/tools/delegation_marks.toml`. A row's `meta` wins over that file.
   - Money fields and the access word are checked by `tests/services/test_module_conformance.py`.
7. Check and test.
   ```
   just check && just test
   ```
   Expected: both exit 0.

## The three surfaces the scaffold writes
All three live in the module's own package, `tl_mod_<name>`, and are named by a reference on the `ModuleSpec`.

| File | Hook on `ModuleSpec` | What it does |
|---|---|---|
| `routes.py` | `read_routers` | `GET /modules/<name>/ping`, guarded by `guard("document.read")`, fixed text. |
| `tools.py` | `tools` (`register_tools`) | One read-only tool, `<name>_ping`. |
| `cli.py` | `cli_groups` (`<name>_app`) | `tl <name> ping` prints the module name. |

- A reference to anything outside the module's own package is refused (ADR-0029). Only the 11 in-tree modules may name `tl_api.routes.`, `tl_mcp.` or `tl_cli.` references.
- The TUI is not hooked. Screens still import modules by name. A module without its own screens reads through the generic record views.

## Names a module may not reuse
- A module may not reuse a core command name, MCP tool name, CLI group name, route path or `command_words` key. Start-up clash checks refuse the whole hook of a module that does (`tl_core.modules.core_command_names` and `refused_hook`; the router mount in `tl_api/app.py`). The refusal is the same fixed message as an unresolvable hook.
- Module routers mount after the core routers, and every route needs a `guard(...)` dependency or the router is refused.
- `tl new module` refuses a name that is a core name.
- Module MCP resources and prompts are refused for now; a module registers tools only.

## Agents: closed by default
- An agent may call only the actions on its allow list.
- A module tool's action is `mcp.<tool>`, for example `mcp.<name>_ping`.
- The list is `MCP_ACTIONS` in `packages/tl-mcp/src/tl_mcp/identity.py`. It names actions explicitly, with no prefix rule.
- Opening a module tool to agents is a reviewed platform edit and an orchestrator decision. There is no module hook for it. It is not yet a row in `docs/build-spec/DEFERRED.md`; raise it in the ticket report.
- Routes: agents hold `document.read` and the other `AGENT_ACTIONS` only. A new route is denied to agents until someone allows it.

## Reads and confidentiality
- A route or tool that returns record text reads through the viewer's class filter (`tl_core.confidentiality`, ADR-0016). The module declares each source as a `ConfidentialSource` in `ModuleSpec.confidential` (`tl_core/modules.py`); the record-type scaffold does not.
- A hidden record answers exactly as a missing one: same status, same text, same count.
- Worked example: `tests/ext_demo/` (see `tests/ext_demo/README.md`). It is a test fixture and is never installed. Its tests are `tests/services/test_ext_demo_conformance.py`, `packages/tl-api/tests/test_ext_demo_api.py` and `packages/tl-mcp/tests/test_ext_demo_mcp.py`.

## Errors
- `ModuleSpec` has no `errors` hook. A new module raises the core error classes, which already have rows in `packages/tl-api/src/tl_api/errors.py`.
- `docs/build-spec/DEFERRED.md` (row P2-X4) says when to add an errors hook.

## Verify
- `uv run tl new module --help` prints the usage with the `name` argument.
- `uv run tl new record-type --help` prints the usage.
- `just check && just test` exits 0.
- `hook_failures()` lists nothing for the new module.

## Roll back
- Before the commit: delete the paths the scaffold printed, and restore `uv.lock` with git if you changed it and want the old lock back.
- A hook that cannot be resolved fails only that module's hook, with one fixed message: `module '<name>': hook '<hook>' cannot be resolved`. The message has no reference in it. The other modules still load. Find the failing hook with `hook_failures()`.

## Not built yet
- No errors hook (see above).
- No module hook to open a module tool to agents (see above).
- No TUI hook.

## Related
- `docs/runbooks/requisitions.md`: a finished module, for its style.
- `tests/ext_demo/README.md`: the worked example.
- `docs/runbooks/proposal-review-queue.md`: how a person reviews an agent proposal.
- `docs/build-spec/DEFERRED.md`: the P2-X4 row.
- ADR-0016 (confidentiality), ADR-0029 (module references).
