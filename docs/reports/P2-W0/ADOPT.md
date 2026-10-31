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

## Mutation
Sentinel (`_may_adopt` returns True): killed. Handler guards: scope, optional, already adopted, additive, several extensions: 5/5 killed (the last after adding a test: it had survived).

## Gate
`just check`: ok. `just gate test_api_addable test_auth_review packages/tl-core/tests packages/tl-modules/schemareg/tests test_add_property`: `part 1: exit 1, 2 failed, 1743 passed in 157.07s`. The 2 failures are in `tl-tui/tests/test_add_property.py` (`test_a_number_typed_stays_a_number_only_when_it_reads_back_the_same`, `test_the_tab_shows_a_held_ad_hoc_field_in_the_custom_section_labelled_custom`, RecordNotFoundError in `tests/fakes.py:576`); they fail the same on p2/w0 @656e54a with my changes stashed. Not touched.

## Open
4 Should the extension be approved without a second person (as built), or should the command stop at Approved for an admin? 4 Full-suite parity (Postgres) not run: `just gate-pg` is the next step.
