# P2-X4 S4 — Conformance over `load_modules()`: word check, row-or-exclusion, delegation marks, drift check

kind: piece
review: full
branch: p2/x4-s4-conformance
worktree: /home/user/wt/x4/s4
Status: READY (S1, S2, S3, T01 merged: C2). Runs with at most one light ticket beside it (T02a, tl-cli only). Never gate next to another heavy gate.

## Why
Three surfaces now build from the module hooks. A new module must be held to the same rules as the eleven in-tree ones without anyone editing a test list:
ADR-0029 decision 7 ("X4 S4 fails any command that has a Decimal, currency or amount field and is not marked `money`; also a command with neither a
mark nor a reason") and ADR-0027 decision 4 (a command is a proposable row or a listed exclusion). No new harness: the existing walks
(`packages/tl-api/tests/test_confidentiality_walk.py`, `packages/tl-mcp/tests/test_confidentiality_walk.py`) already build from the hooks since S2/S3;
S4 proves they enumerate a module added through `use_modules`, and adds the data-driven rules below.

## Interfaces (verbatim, `packages/tl-core/src/tl_core/modules.py`)
```python
def module_commands() -> tuple[ModuleCommand, ...]   # 205 rows today; .name .module .model .handler .access .meta
@dataclass(frozen=True)
class ModuleSpec: ... command_words: Mapping[str, str]; proposable: Sequence[ProposableCommand]; commands/read_routers/tools/cli_groups
IN_TREE_SURFACES: frozenset[str]   # the 11 modules that may name tl_api.routes./tl_mcp./tl_cli. refs
def load_modules() / use_modules(specs) / hook_failures() / resolve_hook(spec, kind)
```
`ProposableCommand(tool, model, handler, access, ...)`. Existing data: `tests/tools/proposable_exclusions.toml` (`[commands] Name = "reason"`).
Command meta key `delegation`: `eligible` or `excluded:<reason>`, reasons `admin money access schema setting action external reserved`;
missing means excluded (ADR-0029 dec. 7).

## Decisions carried in
- D6 (this round): `ModuleCommand.meta` is empty for all 205 rows and S4 must not edit module packages. The marks live in a data file
  `tests/tools/delegation_marks.toml` (tables `[eligible]` names with a one-line note, and `[excluded]` `Name = "<reason>"`), the same pattern as
  `proposable_exclusions.toml`. A row's own `meta["delegation"]`, when present, wins and must equal the file entry if both exist. Nothing reads the
  file at runtime: runtime still treats a missing key as excluded, so shadow mode has nothing to evaluate until the dispatcher reads the marks.
- Seeding rule (the builder classifies by hand from the names, access words and models; first match wins; the report lists the eligible set):
  1 `admin`: access `admin` or name has `Admin`. 2 `money`: any Decimal, currency or amount field (the test computes this, see test 3). 3 `access`: accounts,
  roles, module roles, agent tokens, clearances, scope grants. 4 `schema`: schema package draft/approve/publish/adopt, workflow changes. 5 `setting`.
  6 `action`: approval of an action proposal. 7 `external`: InvokeAction, webhooks, transmittal issue, email out. 8 `reserved`: confidentiality class changes,
  transitions into locked states, every name in `proposable_exclusions.toml`, access `controller` or `company`, and every command that is not an agent-proposable row
  (a policy accepts proposals, so a command no agent can propose is never delegable). Remaining commands that ARE a `ProposableCommand` row and hit no rule: `eligible`.
- F1 (S1 review, LO): a non-string item in a hook ref list gives `TypeError`, not `ModuleLoadError`. Fix it in `ModuleSpec.__post_init__` (core, small) with test 8.
  No interface change: report it as consequential.
- Legacy ratchet: modules that predate ADR-0027 d4 may have commands that are neither a proposable row nor an exclusion. Do not add 100 exclusions. Record today's
  undecided names in `tests/tools/proposable_undecided.txt` (one per line, sorted). Test 4 allows the undecided set to shrink, never grow, and requires every command
  of a module outside `IN_TREE_SURFACES` to be decided. If more than 150 names are undecided, stop and report (escalation).

## Allowed paths
- `tests/services/test_module_conformance.py` (create)
- `tests/tools/delegation_marks.toml` (create)
- `tests/tools/proposable_undecided.txt` (create)
- `tests/tools/test_registry_by_hooks.py` (create)
- `tests/tools/prehook_lines.toml` (create; see test 7)
- `packages/tl-api/tests/test_module_conformance_walk.py` (create)
- `packages/tl-mcp/tests/test_module_conformance_walk.py` (create)
- `packages/tl-core/src/tl_core/modules.py` (F1 only: `__post_init__` ref-item type check)
- `tests/services/test_module_ref_types.py` (create; test 8)
- `docs/reports/P2-X4/S4.md` (create)
Read-only: `tl_api/**`, `tl_mcp/**`, `tl_cli/**`, `packages/tl-modules/**`, `docs/adr/**`.

## Context (≤ 10)
`packages/tl-core/src/tl_core/modules.py`, `tests/tools/proposable_exclusions.toml`, `packages/tl-modules/awp/tests/test_proposable_exclusions.py` (the existing per-module pattern),
`tests/services/test_module_role_seams.py` (word table), `packages/tl-api/tests/test_confidentiality_walk.py` and `packages/tl-mcp/tests/test_confidentiality_walk.py` (enumerators),
`packages/tl-api/tests/test_auth_review.py` (`route_actions`, `AGENT_MAY_NOT`), `packages/tl-mcp/tests/test_module_tool_hooks.py`, `docs/adr/0029-*.md` §7, `docs/reports/P2-X4/S3.md`.

## Tests to add (name each file's tests after the rule)
`tests/services/test_module_conformance.py`, over `load_modules()` and `module_commands()`:
1. Floor: at least 11 modules and 200 commands (the walk found them); no `hook_failures()`.
2. Word check: for every row, `access` is a word the authorizer knows (the same table `test_module_role_seams.py` uses), and equals `spec.command_words[name]` when the
   spec declares one for it; a module that declares `command_words` for some commands declares them for all its rows.
3. Money: for every command model, any field typed `Decimal`, or named `amount`, `currency`, `price`, `rate`, `budget`, `cost` (case-insensitive), nested one level of model fields
   included, must have mark `excluded:money` (row meta or marks file). Prove the test sees one: a fake `ModuleCommand` with a `Decimal` field and no mark fails the same helper (call the helper, not pytest).
4. Row-or-exclusion with the ratchet above.
5. Delegation mark: every command has exactly one mark (meta or file), the value matches `eligible` or `excluded:<reason>` with a reason from the closed list, the file has no name that is not a
   command (stale), no command is in both tables, every `eligible` is a `ProposableCommand` row and not in `proposable_exclusions.toml` and not access `admin`/`controller`/`company`.
   A module outside `IN_TREE_SURFACES` must carry the mark in row `meta` (it cannot add to the file by editing a test list).
6. Unique names: with `use_modules` and two fake modules declaring one name, `module_commands()` raises `ModuleLoadError` naming both modules and no ref.
`tests/tools/test_registry_by_hooks.py` (source scan with `ast`, no import of the app):
7. Drift: `tl_api/commands.py`, `tl_api/app.py`, `tl_mcp/server.py`, `tl_cli/main.py` hold no import of `tl_mod_*` command tables and no hand registration of a module router, tool registrar or CLI
   group that a module's hook already supplies. A line may be exempt only if listed in `tests/tools/prehook_lines.toml` (`[lines] "<file>" = ["<module path or router name>", ...]`), which starts EMPTY.
   Integration branches that merged pre-hook registrations add their lines to it and remove them when they move to hooks. A stale entry (no such line in the file) fails.
`tests/services/test_module_ref_types.py`:
8. F1: `ModuleSpec(read_routers=(3,))`, `tools=(None,)`, `cli_groups=(b"x",)` raise `ModuleLoadError` (message names module and field, not the item).
`packages/tl-api/tests/test_module_conformance_walk.py`, `packages/tl-mcp/tests/test_module_conformance_walk.py`:
9. With a fake in-tree-named module through `use_modules` carrying one read route (api) or one read tool (mcp) that needs an argument the walk cannot fill, the walk's enumerator lists it, and the
   existing walk helper fails on it (call the helper); with a fillable one it is listed and passes. Reuse the walks' own enumerators and harness; no copy of their code.

## Acceptance (run in this order, one at a time; each is a separate gate)
```
NODE_OPTIONS=--max-old-space-size=6144 just check
just gate tests/services/test_module_conformance.py tests/services/test_module_ref_types.py tests/services/test_module_hooks.py tests/services/test_module_hooks_extra.py tests/services/test_module_role_seams.py tests/tools/test_registry_by_hooks.py
just gate packages/tl-api/tests/test_module_conformance_walk.py packages/tl-api/tests/test_module_hooks_api.py packages/tl-api/tests/test_confidentiality_walk.py
just gate packages/tl-mcp/tests/test_module_conformance_walk.py packages/tl-mcp/tests/test_module_tool_hooks.py packages/tl-mcp/tests/test_confidentiality_walk.py packages/tl-cli/tests/test_module_cli_groups.py
```
Name files, never directories. Gate 3 and 4 are the long ones: the runner kills runs over about 10 minutes, so you run them yourself in the background (harness re-invokes on exit);
never two at once; `test_auth_review.py` is not needed (the walks import its sets).

## Mutation cap
One sentinel plus at most 5: drop the money check's nested-field step; let an `eligible` mark pass for an `admin` command; accept a stale marks entry; let a non-hook import pass the drift scan;
skip the undecided-set growth check. 3 lines in the report.

## Report
First line: deviations or none. Eligible set listed (names). Count of undecided names. Builder return ≤ 15 lines. Commit `P2-X4-S4: ...` with the session trailers; no model names in committed text.

## Escalation triggers
More than 150 undecided names; a marks rule that cannot be decided from names and models (list them, do not guess `eligible`); a walk enumerator that cannot see a `use_modules` module;
any need to edit a module package, `tl_api`, `tl_mcp` or `tl_cli` source.
