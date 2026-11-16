# P2-IP S2 common rules (QR S2, INSP S2, PTW S2 read this first)

Replaces the "no hook fields" line of the three plans (plan-check F2): the module hooks of P2-X4 exist (branch `p2/x4`,
head 44b67625 or newer; code is that of 58cf3bcc: S1-S5, T01, T02a, T02b merged; not on the trunk), so each S2 declares its hooks. Read X4 from the tree
you are built on (the base below), never from memory.

## Base and merge note
- **Base:** a branch made from `p2/ip` with `p2/x4` merged in (the orchestrator makes it: `p2/ip-x4`). Known conflict on that merge: `tests/settings/test_phase2_keys.py`
  (a count pin) and regenerated schema files (`just gen`, `just compat-update`, re-pin). An S2 branch starts from that base, not from `p2/ip`.
- **Merge note: "waits for X4 on trunk".** No S2 branch merges into `p2/ip` before X4 is on the trunk and `p2/ip` has merged the trunk (the S2 history carries X4's commits).
  Build, gate and review may start now.
- **Order and the shared file.** One S2 per wave edits `tl_core/confidentiality.py` (plan-check F8). Order QR S2, then INSP S2, then PTW S2; a later S2 merges the earlier one
  (or `p2/ip` after it) before its own row commit and only appends. The first (QR S2) owns the edit of `tests/confidentiality/test_forms_rows.py` (see QR S2); nobody else edits it.
  `tests/tools/proposable_exclusions.toml` and `tests/tools/delegation_marks.toml`: append only, one commented block per increment.

## Hook rules (X4 D3, D6, D8, D10, D11, D12; `packages/tl-core/src/tl_core/modules.py`)
- Refs are `"<dotted.module>:<Name>"`, resolved lazily. A module outside `IN_TREE_SURFACES` (qr, permits) names **its own package only**: `tl_mod_<m>.module:COMMANDS`,
  `tl_mod_<m>.routes:router`, `tl_mod_<m>.tools:register_tools`, `tl_mod_<m>.cli:<x>_app` (group name `<x>`). `quality` is in `IN_TREE_SURFACES`: its surfaces stay in `tl_api.routes`,
  `tl_mcp`, `tl_cli`; the later tickets add their own refs.
- A command row has `model`, `handler`, `access`, optional `needs_holds`, `takes_roles`, `meta`. Shape to copy: `tests/ext_demo/src/tl_mod_ext_demo/module.py` (row class, `COMMANDS`,
  `PROPOSABLE`, `spec()`); text of routes, tools and CLI stubs: `packages/tl-cli/src/tl_cli/scaffold/templates/module/{routes,tools,cli}.py.tmpl` (lint- and pyright-clean; paste, do not retype).
- `command_words` lists every command with the row's access word (conformance rule: the words agree).
- **Marks.** Every command carries one `delegation` mark: `eligible` or `excluded:<reason>`, reasons `admin money access schema setting action external reserved`. A module outside
  `IN_TREE_SURFACES` carries it in the row's `meta`; `quality` may use `tests/tools/delegation_marks.toml` (row meta also works, one place only). `eligible` needs an agent
  `ProposableCommand` row, table word `user`, no money field, not in the exclusions file. Controller or company access is `excluded:reserved`.
- **Decided.** Every command is a `ProposableCommand` row or an entry in `tests/tools/proposable_exclusions.toml` (`Name = "reason"`). `tests/tools/proposable_undecided.txt` never grows.
- **Registries hold no hand line** for what a hook supplies (`tests/tools/test_registry_by_hooks.py`); `prehook_lines.toml` stays empty.
- Stubs for the surface hooks (qr, permits): a router with no route, a registrar that registers no tool, a Typer group the CLI can load and render in `tl --help`
  (if an empty group cannot, one hidden command, removed by the ticket that fills the file; say which). The three baseline pins are extended by union, one name each:
  `OLD_GROUPS` (`packages/tl-cli/tests/test_module_cli_groups.py`), `OLD_TOOL_NAMES` (`packages/tl-mcp/tests/test_module_tool_hooks.py`, nothing to add for an empty registrar),
  the `OLD_COMMANDS` and `expected/route_order.txt` pins (`packages/tl-api/tests/test_module_hooks_api.py`). Commands of a new module also reach `POST /commands/<Name>`:
  an agent token is refused there (`agent_must_propose`), a person needs the word.
- Dependencies of a module package that has surfaces: add `fastapi`, `mcp`, `typer` (bare names, as `tl-api` has them) and nothing else. **Do not add `tl-api`, `tl-mcp` or `tl-cli`**
  (`tl-api`, `tl-mcp`, `tl-cli` and `tl-tui` already depend on the module: that would be a cycle; the scaffold template's two lines are for modules nothing depends on). Regenerate
  `uv.lock` with `uv lock --offline`; a refusal is an escalation. Imports of `tl_api`, `tl_mcp` and `tl_cli` inside the stubs resolve in the workspace environment.
- No new `errors` hook (X4 Q3, DEFERRED): an expected failure subclasses a core error class that already has a row in `tl_api/errors.py` (as `tl_mod_quality/errors.py` does) and takes a
  fixed message; `tl_api/errors.py` is not edited.

## Traps (all three)
- Statement-count tests count SQL statements and ignore `BEGIN`, `COMMIT` and `ROLLBACK`; write the counter that way (filter on the leading keyword).
- Gate per file or small group, never a directory of `tl-api` or `tl-mcp` (16 GB box OOMs on combined runs; `tl-api/tests/test_commands.py` alone is 7-9 GB: in no gate here). One gate at a time;
  runs over about 10 minutes go to the background. Schema gates run per file. `NODE_OPTIONS=--max-old-space-size=6144 just check`.
- Provided tests are lint-clean where they land (ruff format, ruff check, pyright were run on the merged base): copy them byte-identical; a change to one is a report line.
- Confidentiality rows are `SUBJECT_LINKS` tuples `(record type, table, id column, subject column)`; the subject chain is `_HOPS = 2` flat LEFT JOINs per row; the join-budget test
  (`tests/confidentiality/test_forms_rows.py`, "under the join limit") must still pass on both adapters; a hidden subject reads as a missing record (same status, text, count), filter before LIMIT.
- No model names in committed text; commit `P2-<INC>-S2: ...` with the session trailers named in the dispatch message; do not merge, do not push.
- Escalate (write under *Blocked*, stop): a hook ref outside the module's own package is needed; `tl_api/errors.py` or `tl_core/modules.py` must change; the join budget fails;
  the uv lock cannot be regenerated; a provided test fails on its own logic.
