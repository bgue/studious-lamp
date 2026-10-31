# Report — P2-W0-RM-S2 (module roles at every API-side entry point; fine words read once)

Branch: `p2/w0-rm-s2`   Commit(s): see `git log p2/w0..p2/w0-rm-s2` (one build commit, this report included)

## Deviations
1. **Owner policy: no pytest, no `just gate`, no mutants.** Every pin below is updated by reading, not run.
2. **Pin list is incomplete (predicted, not run).** Same cause as the pins, fixed here: `test_commands.py::test_a_command_with_no_body_is_a_422_not_a_500` (controller commands are now 422, admin stays 403) and `test_api_document_controller.py::test_taking_the_role_away_closes_the_commands_at_once` (needs a valid body). **Not touched, will go red at the end run** (outside Allowed paths): `tests/auth/test_document_controller.py::test_a_user_is_refused_every_control_action` (a listed `control.*` action now passes a plain user at the authorizer, as the spec says). At risk, unaudited: tests that run a generic command on a module record as an actor with no account (`user:dev` in `tl_cli`/embedded TUI), `packages/tl-sim`, `tests/auth/test_authorizer_and_seed.py`. See Open questions 1-2.
3. **Opt-in `holder`.** `accept_proposal`/`accept_or_fail` and `allowed_actions` take `holder: Holder | None = None`; the API routes pass `holder_for_principal(principal)`. With none (CLI, embedded TUI, MCP, sim), behaviour is as before; RM-S4 wires them. A dev ledger actor has no account row, so a default `holder_for_actor` would refuse every CLI accept.
4. **Proposal accept is AND, not replace.** The account-role check (`holds("controller")`) still runs; the module check is added (spec: "also"). A `superuser` grant without the `document_controller` account role cannot accept a controller proposal. Refusal is `ProposalAccessError` (403 `proposal_access`), proposal stays pending.
5. Acceptance matrix uses real endpoints with a loose body and a stub handler (a valid body per command is not derivable; a 200 is "the gate let it through").
6. Added `normalise_word` and `require_word` to `module_roles.py` (the one fine-word lookup, and the shared refusal `require_command_access` and `require_generic` both call). `addable.py` (read-side offer) and `tl_mod_legacy/source_layer.py` call `require_generic` without `actor`: not in the 8, not in Allowed paths.

## Changed files
- `tl_api/commands.py` — `Access` accepts `str`; `CommandSpec.module` + `__post_init__` (fine word via `normalise_word`, controller needs a module); `effective_access`, `_module_specs`, `check_command_words` (run in `build_router`), `CORE_CONTROLLER_COMMANDS` (empty); `action_for`/`controller_actions`/`access_of`/`run` use `effective_access`
- `tl_api/routes/{actions,proposals}.py` — pass `holder_for_principal`; `tl_core/{actions,modules}.py` — `holder` in `allowed_actions`, `actor=` in `require_generic`
- `tl_core/auth/{module_roles,provider}.py` — `command_index()` normalises; `RoleAuthorizer` lets a listed `control.*` action through to the endpoint (agents refused, unlisted = admin)
- `tl_core/services/{proposals,records,psets,workflow,links}.py`, `files/service.py`, `integration/enrichers/layer.py` — module check / `actor=cmd.actor`
- 7 `module.py` — `command_words={c.model.__name__: c.access for c in API_COMMANDS}`; legacy `command_words={}` (no API commands)
- pins: `test_api_document_controller.py`, `test_api_schedule.py`, `test_commands.py`; `docs/reference/openapi.json` (regenerated, one description); `dev/accept/P2-W0/RM-S2.py`

## Readers of `.access` (`grep '\.access\b' packages`)
`CommandSpec.access`: `commands.py` (all through `effective_access`: `action_for`, `controller_actions`, `_make_endpoint` company test, `access_of`, `run`; `__post_init__`). Not touched, RM-S4's: `tl_tui/embedded.py:1146,1168,1170,1510` read the raw word (a fine word there is not yet normalised; none is declared today). Other hits are unrelated `access` (rules, endpoints, enrichers, `ProposableCommand.access`, `item.access` in proposals/CLI/TUI text). Controller commands with `module=None`: none (`CORE_CONTROLLER_COMMANDS` is empty).

## Pins updated (old form kept?)
- `test_api_document_controller.py::test_a_user_is_refused_every_controlling_command_by_the_module_role` (was `..._naming_its_action`): Y, derived controller + admin test kept; new `test_a_superuser_grant_opens_...`
- `test_api_schedule.py::test_a_user_is_refused_the_controlling_commands_by_the_module_role`: Y (dora, boss kept)
- `test_commands.py::test_an_unknown_access_value_is_refused_when_the_spec_is_built_so_it_fails_closed`: Y (admin/user/company actions kept); added `test_a_controller_command_with_no_module_is_a_start_up_error`

## Seam list (`require_command_access` / `require_word`)
`commands.py:330` `_make_endpoint` (in `ctx.backend(False)`, before the handler) | `commands.py:440` `TableCommandRunner.run` (person/agent module commands; ForbiddenError -> CommandAccessError; `svc:` unchanged) | `proposals.py:845` (`_require_module_access`) | `actions.py:92` `scoped_holds` | `modules.py:411` `_require_user_word` via `require_generic(..., actor=)` at `records.py:320,367`, `psets.py:149`, `workflow.py:178`, `links.py:222,387`, `files/service.py:380`, `enrichers/layer.py:59` | `provider.py:121` `_may_control` | `module_roles.py:362` `command_index()` normalisation.

## Commands and output
```
$ just check
ruff 0 | format 1869 files ok | pyright 0 errors | generated up to date (639) | openapi ok | licences ok
$ uv run python dev/accept/P2-W0/RM-S2.py     # exit 0, 21 PASS lines, matrix printed
PASS matrix: 115 commands x 5 roles x 2 projects equals the role table
PASS proposal accept: 10 refused 403 for an accepter without the word on the stored scope, 8 let through, ...
PASS require_generic: the word `user` refused on P2, held on P1, for 6 modules
PASS a stand-in module's awp.cwp.release reads as controller and awp.view as read
```

## Tests added
None (end run). Hand to TA: mutants `commands.py:330` removed; `provider.py` `_may_control` any-role pass; `normalise_word` removed from `command_index()`; `modules.py:411`; `proposals.py:845`.

## Learnings (proposed)
- A route that reads the project from the body cannot refuse before body validation: an empty-body walk is 422 for everyone now; walking tests need valid bodies.
- A module record made by `Record.Created` alone is hidden (ADR-0016) to every viewer but `system_view()`.

## Open questions / Blocked
1. `require_generic(actor=)` refuses an actor with no account (`user:dev`): does RM-S4 add a dev-file rule in core, or should the 8 callers fall back for `TL_ENV` dev/test/ci?
2. A `document_controller`-only account (no `user` role) now has no `user` word outside documents, correspondence, schedule (CreateTag 403). Add `derive` rows, or require `user` with it?
3. Proposal accept AND vs replace (deviation 4).
