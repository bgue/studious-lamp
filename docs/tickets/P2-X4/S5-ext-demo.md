# P2-X4 S5 — Fixture module `ext_demo`: a module nobody edited `tl-api`, `tl-mcp` or `tl-cli` for

kind: piece
review: full
branch: p2/x4-s5-ext-demo
worktree: /home/user/wt/x4/s5
Status: READY (S4 merged). Was T03; moved to a piece (D11): it has an access-worded command with a handler and a read path over record text under the class filter,
both on the core list (`01-tiers.md` §3), so it fails the ticket-tier checklist (items 5 and 7). Disjoint from T02b (tl-cli templates). Gates one at a time.

## Why
Demo clauses 3 to 5 and the S4 rules need a real module that is added only through hooks. It lives under `tests/ext_demo/` (never installed, never an entry point;
only tests and the demo load it), so a pass proves the platform serves a module no platform source file names.

## Shape (decide the minimum; report what you chose)
Package `tl_mod_ext_demo` at `tests/ext_demo/src/tl_mod_ext_demo/`, module name `ext_demo`:
- record type `ext_demo.Note` (title, body); command `ExtDemoAddNote` (access `user`; row `meta={"delegation": "excluded:reserved"}`, because the module is outside
  `IN_TREE_SURFACES`; a handler on the pattern of `packages/tl-cli/src/tl_cli/scaffold/templates/record_type/handler.py.tmpl`); the command is decided by a
  `ProposableCommand` row (`agent_tool=False`) or by being listed in the spec; no money field.
- confidentiality: `ModuleSpec.confidential` with a `ConfidentialSource` for `ext_demo.Note` (pattern: `tl_mod_quality`, `views.py` and `module.py`); a note's class is set at add time
  (default `internal`); reads go through `tl_core.confidentiality.current_viewer()` and a hidden note answers as a missing one.
- surfaces, own-package refs only (`tl_mod_ext_demo.routes:router`, `.tools:register_tools`, `.cli:ext_demo_app`): `GET /modules/ext_demo/notes/{key}` (guard `document.read`; same 404
  text for hidden and missing), tool `ext_demo_get_note` (`guarded`; same text), CLI group `ext_demo` with `get` and `add`. Text and layout of the three files follow the T02b templates
  (`docs/tickets/P2-X4/T02b-scaffold-surfaces.md` step 1, already lint- and pyright-clean); the example `ping` is replaced by the note read.
- loader: `tests/ext_demo/load.py` with `def ext_demo_spec() -> ModuleSpec` (puts `tests/ext_demo/src` on `sys.path` once, imports `tl_mod_ext_demo.module`, returns `spec()`);
  consumers insert `tests/ext_demo` on `sys.path` in two lines. T05's demo uses the same loader.
- Schema: if the record type needs a LinkML file or any edit under `schema/**`, stop and report (human gate); the fallback is a stream type that the module table and views serve
  without a schema class, if the effective-schema checks allow it.

## Interfaces (verbatim, `packages/tl-core/src/tl_core/modules.py`)
```python
@dataclass(frozen=True)
class ModuleCommand: module: str; model: type[Command]; handler: ProposalHandler; access: str; needs_holds=False; takes_roles=False; meta: Mapping[str, str]
class ProposableCommand: tool: str; model; handler; access; agent_tool: bool = True
class ConfidentialSource: record_types; table; id_column; class_column; null_class=None; clearance_table=None; ...
class ModuleSpec: name; record_types; projectors; confidential; proposable; commands/read_routers/tools/cli_groups (str refs)
def use_modules(specs) / load_modules() / resolve_hook(spec, kind) / module_commands()
```
Conformance helpers to call, not copy (`tests/services/test_module_conformance.py`): `word_problems(rows, specs)`, `money_problems(rows, marks)`, `mark_problems(rows, marks, agent_rows=, exclusions=)`,
`ratchet_problems(rows, decided, [])`, `proposable_rows(specs, agent_only=False)`, `Marks({}, {})`. Marks for a module outside `IN_TREE_SURFACES` live in row `meta`.
Harnesses: `packages/tl-api/tests/harness.py` (`Harness`), `packages/tl-mcp/tests/mcp_harness.py` (`McpHarness`), walk pattern `packages/tl-api/tests/test_module_conformance_walk.py` and
`packages/tl-mcp/tests/test_module_tool_hooks.py` (tool closed until allowed, `authorize_hook`).

## Allowed paths
- `tests/ext_demo/**` (create; package, `load.py`, a short `README.md` saying it is a fixture)
- `tests/services/test_ext_demo_conformance.py` (create)
- `packages/tl-api/tests/test_ext_demo_api.py` (create)
- `packages/tl-mcp/tests/test_ext_demo_mcp.py` (create)
- `docs/reports/P2-X4/S5.md` (create)
Read-only: everything else. Any need to edit a platform source file, `schema/**` or another test is an escalation.

## Tests to add
1. `tests/services/test_ext_demo_conformance.py`: with `use_modules([spec])` added to the installed set, the S4 rule functions return no problems for the `ext_demo` rows (word, money, one mark in row meta, decided, no ratchet growth);
   the module's row is in `module_commands()`; no `hook_failures()`; a copy of the row without `meta` fails `mark_problems`.
2. `packages/tl-api/tests/test_ext_demo_api.py`: the route is served after `create_app` under `use_modules`; the five-reader walk (anonymous, agent, signed-in person without clearance, with clearance, admin) of an `internal` and a
   `restricted` note: hidden equals missing (status, body text, count) (phrase 140); `ExtDemoAddNote` over `POST /commands/ExtDemoAddNote` runs for a person and is refused without the word and for an agent (`agent_must_propose`).
3. `packages/tl-mcp/tests/test_ext_demo_mcp.py`: the tool is listed after `build_server` under `use_modules`, closed until `mcp.ext_demo_get_note` is allowed, then opens only that tool; hidden equals missing for an agent.
4. CLI: group `ext_demo` appears under `_add_module_groups` with `use_modules`; `ext_demo get <missing key>` and a hidden key print one text and exit non-zero.
Each test file works on both adapters where the harness offers it; none edits a harness.

## Acceptance (run in this order, one at a time; no two gates at once)
```
NODE_OPTIONS=--max-old-space-size=6144 just check
just gate tests/services/test_ext_demo_conformance.py tests/services/test_module_conformance.py tests/tools/test_registry_by_hooks.py
just gate packages/tl-api/tests/test_ext_demo_api.py
just gate packages/tl-mcp/tests/test_ext_demo_mcp.py packages/tl-cli/tests/test_module_cli_groups.py
```
Name files, never directories; `test_commands.py` of tl-api is not in any gate here (7-9 GB). The runner kills runs over about 10 minutes: run long gates yourself in the background.

## Mutation cap
Sentinel (the route answers a hidden note with 403 instead of 404) plus at most 5: filter after LIMIT in the list or count path if one exists; the tool skips `guarded`; the row loses `meta`;
the confidential source drops the record type; the CLI prints the hidden key's class. 3 lines in the report.

## Report
First line: deviations or none. What the record type uses (schema or fallback), the mark and decision chosen, the five-reader table in ≤ 8 lines. Builder return ≤ 15 lines.
Commit `P2-X4-S5: ...` with the session trailers; no model names in committed text.

## Escalation triggers
`schema/**` needed; a platform file must name the module; the S4 rules need an exception for it; hidden is distinguishable from missing on any surface.
