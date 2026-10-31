# P2-W0-ADOPT: "adopt this set" now adopts

Deviations: a new project-scope command `AdoptSchemaSet` (the spec allowed one only if unavoidable; see Mechanism); `docs/reference/openapi.json` regenerated with `python -m tl_api.openapi` (new route); the test's command name changed with the command (its other assertions are unchanged). No `schema/**` file, no data row, no new dependency.

## Why the old action could not work
1. The test's unfiltered offer list also held `safety_data` (test fault): filtered to `NEW_SET`.
2. `AdoptSchemaPackage 3.3.0` for P123 is refused ("pinned at both"): `x.P123@1.4.0` depends on 3.2.0.
3. A pin never makes an optional set effective: `compose._adopted` keeps an optional set only if the project extends it. Changing that rule, or storing "adopted sets" on the pin, would change other projects or need a new column (schema change), so neither was done.

## Mechanism
`AdoptSchemaSet(project, package, version, pset)` (`handlers/adoption.py`) publishes the next version of the project's extension package (`x.<project>`, 1.0.0 when it has none, else minor + 1): what the extension had, re-pointed at `package@version`, plus an empty `extends` of the set. Package gates are the existing handlers, called in order: draft, analyse, submit (classification, lint, waiver rules), approve (`approve_reviewed`, split out of `handle_approve_schema_package`; only the self-review refusal is skipped, because the adopter drafts the one mechanical extension), publish (re-checks it composes). The set is effective for that project only; other scopes keep their hash (tested).
Refused: scope not `project:<project>` (or `company` for an admin); set missing or not optional; already adopted; version below the one in force; a version move that is not additive (an administrator reads the impact report and uses `AdoptSchemaPackage`); more than one extension package for the project. No existing data is touched (additive move only).

## Access rule
`AdoptSchemaSet` is a module command with access `controller` in `API_COMMANDS` (schemareg): module-roles gives it to the schemareg `superuser` of that project, and to any admin; nobody else, no agent. `schema/settings/*.yaml` unchanged (the word `controller` already exists). The offer uses the same rule: `addable._may_adopt` reads `command_index()["AdoptSchemaSet"]` and asks `holds_word` for the viewer's holder at the record's scope; with no holder (MCP) or no schemareg module it is admin-only. API route and embedded TUI now pass a holder. `AdoptSchemaPackage` stays admin-only, unchanged. Orchestrator approval (P2-Q10) is needed only for the controller-word command and the four-eyes skip above.

## Files
- `packages/tl-modules/schemareg/src/tl_mod_schemareg/handlers/{adoption,packages}.py`, `commands.py`
- `packages/tl-core/src/tl_core/addable.py` (offer names `AdoptSchemaSet`; `holder` kwarg), `tl-api/.../routes/actions.py`
- `packages/tl-tui/src/tl_tui/{add_property,embedded,log_actions}.py`, `widgets/{add_property_form,record_view}.py` (the form sends `AdoptSchemaSet` in the project's scope; head text no longer says "pins")
- tests: `tl-api/tests/test_api_addable.py` (filter, new command, project superuser vs another project's), `test_auth_review.py` (closed to agents), `tl-modules/schemareg/tests/test_adopt_set.py` (7), `tl-tui/tests/test_add_property.py`
- docs: schemareg README (module and docs), tl-api and tl-tui READMEs, `docs/reference/openapi.json`

## Review fixes (attempt 2)
- Merged p2/w0 @10268ab first (clean).
- F1: a package not in the project's schema (ledger-only, not pinned) is refused: "an administrator adopts the package for <project> first (AdoptSchemaPackage)". F5: a registry pin of another version is refused early ("an administrator moves the pin"); README says the project's company version moves with the extension.
- F3: approval comment "Approved by AdoptSchemaSet (mechanical extension)". F4: route docstring and openapi.json regenerated.
- F6/F1 tests: the five events in order, actor and source, a refused call leaves no draft, new-package and pin refusals (schemareg tests now 11).
- F2: command-table pins in `test_commands`, `test_api_proposals` (registry 13 to 14) and `test_api_document_controller` counted the new controller command; updated. `test_module_role_seams` passes unchanged (`pick("schemareg")` now picks `AdoptSchemaSet`, which the runner decides by role on its scope).

## Mutation
Sentinel (`_may_adopt` returns True): killed. Handler guards: scope, optional, already adopted, additive, several extensions, no-package (F1), pin (F5): 7/7 killed (several-extensions after adding a test).

## Gate
`just check` ok. Parts, one at a time:
- `packages/tl-api/tests`: 4 failed, 1205 passed (the four command-table pins above); the three files re-run after the fix: 194 passed.
- `packages/tl-mcp/tests tests/services/test_module_role_seams.py`: `part 1: exit 0, 547 passed, 1 skipped in 483.96s`, PASS.
- tl-tui (test_add_property, log_actions, fakes/embedded schemareg, record/schema/properties/psets/edit tests): `part 1: exit 0, 136 passed in 60.28s`, PASS (the two earlier add-property failures are fixed by FIX-TUI).
- `just gate-pg packages/tl-modules/schemareg/tests packages/tl-api/tests/test_api_addable.py`: `part 1: exit 0, 255 passed in 481.76s`, PASS.
- Earlier part (before the merge): tl-core/tests, schemareg tests, test_api_addable, test_auth_review all passed.
The whole tl-tui directory was not run (over 30 min on this host); the files that use schemareg or the add-property form were.

## Open
4 Single-person approval and the `controller` word await the orchestrator (F1 now closed).
