# P2-W0-RM-S2 — Module roles: one access function at every API-side entry point, fine words normalised once

Status: ready
Tier: sonnet
Kind: piece
Review: full
Labels: auth, security, api, core
Depends on: RM-S1 (merged, `module_roles.py`), W0-B1 (merged, `access_words.py`)
Branch: `p2/w0-rm-s2`
Approver (permission path): the orchestrator under P2-Q10 (line in `docs/memory/APPROVALS.md` at merge)

## Goal
After this piece every module command is decided by the module role table: `require_command_access` (RM-S1) is the **only**
access function and every API-side entry point calls it; fine access words (`awp.cwp.release`) are read as their table
word in **one** place, `command_index()`, and a module may declare one in `command_words` and in `CommandSpec.access`.
CLI and embedded-TUI gates are RM-S4's (it calls the same function); nothing here touches `tl_cli` or `tl_tui`.

## Brief references
Interface: `docs/build-spec/specs/roles-mvp.md` **§5 (seams table, read in full) and §4 last paragraph**, authoritative
except for these deltas (`specs/wave0.md` wins; plan check F1, F4, F7):
1. **Fine words (F1).** In `module_roles.command_index()` map every declared word once: `admin` and `company` (platform
   words) and the table words `read|user|controller` pass through unchanged; any other word goes through
   `tl_core.auth.access_words.table_word()` (unknown -> `AccessWordError`, a start-up failure, fail closed). So
   `require_command_access`, `holds_word` and every other reader of `command_index()` only ever see a table or platform
   word. `tl_api.commands.Access` accepts a fine word at declaration (type: the four literals or `str`; validated by
   `table_word()` in `CommandSpec.__post_init__`, so a typo is still a start-up error, not an open door). `action_for`,
   `controller_actions`, `RoleAuthorizer`, `access_of` (and every other reader of `CommandSpec.access`; grep
   `\.access\b` under `packages/` and list what you found in the report) use one helper `effective_access(spec)` that
   returns the normalised word; a fine word whose table word is `controller` is a `control.command.<Name>` action.
2. **One function.** `require_command_access` is not copied or re-implemented at a seam. Seams: `_make_endpoint`
   (inside the `ctx.backend(False)` block, before the handler, holder from `holder_for_principal`), `RoleAuthorizer`,
   `TableCommandRunner.run` (`user:`/`agent:` actors; `svc:` unchanged), `accept_proposal` (accepter's roles on the stored
   command's scope), `allowed_actions` + `scoped_holds`, and the 8 `require_generic` call sites (keyword `actor=`). The
   walk of `GET /records/{id}/actions` offers nothing the endpoint would refuse.
3. **`tl_mod_legacy/module.py` (F4).** This piece owns its `command_words` line; W0-B2 must not touch that file.
4. `CommandSpec.module` + `_module_specs("<m>", TUPLE)` as in the §5 row; `controller` with `module=None` is a start-up error
   unless the command is a core command already on a short explicit list in `commands.py` (find them; list in the report).
5. Reads are not filtered by module role; ADR-0016 is untouched; do not change `request_model` / `refuse_role_claim`.

## Consequential pins (rule 12; do not stop for these, update in this piece and list them)
`packages/tl-api/tests/test_api_document_controller.py:83-90`, `packages/tl-api/tests/test_api_schedule.py:285`,
`packages/tl-api/tests/test_commands.py:228-289`. They break because controlling acts are now decided by module role, not
by account role alone. Update each to the new rule and, where the old form still exists (an admin; a derived
`document_controller`), keep a counterpart that pins it. Any other test that breaks and is not in this list **stops the
piece** (*Blocked*, with the test id).

## Context (<= 10 files)
- `docs/build-spec/specs/roles-mvp.md` §4-§5; `specs/wave0.md` §2; `docs/reports/P2-W0/RM-S1.md`, `W0-B1.md` (interfaces in the tree)
- `packages/tl-core/src/tl_core/auth/{module_roles.py,access_words.py,provider.py}`; `packages/tl-core/src/tl_core/modules.py`
- `packages/tl-api/src/tl_api/commands.py`, `tl_api/routes/{actions,proposals}.py`; `packages/tl-core/src/tl_core/{actions.py,services/proposals.py}`
may explore: the seven `module.py` files, `tests/auth/authworld.py`

## Allowed paths
- `packages/tl-api/src/tl_api/commands.py`, `packages/tl-api/src/tl_api/routes/{actions,proposals}.py`
- `packages/tl-core/src/tl_core/{actions.py,modules.py}` (`require_generic` and the hook plumbing; no new `ModuleSpec` field), `auth/provider.py`, `auth/module_roles.py` (fine-word lookup and any helper it needs), `services/{proposals,records,psets,workflow,links}.py`, `files/service.py`, `integration/enrichers/layer.py` (the `require_generic` call sites only)
- `packages/tl-modules/*/src/*/module.py` (the `command_words` line only, one per module, built from that module's `API_COMMANDS`; includes `tl_mod_legacy/module.py`)
- the three consequential pins above; `docs/reference/openapi.json` only by `python -m tl_api.openapi` if `just check` says it drifted
- `dev/accept/P2-W0/RM-S2.py` (create), `docs/reports/P2-W0/RM-S2.md` (create)
Not allowed: `tl_cli/**`, `tl_tui/**`, `tl_mcp/**`, `schema/**`, `tl_mod_legacy` anything but `module.py`, other modules' files.

## Acceptance (run these, once; no pytest, no `just gate`)
```
just check
uv run python dev/accept/P2-W0/RM-S2.py
```
`dev/accept/P2-W0/RM-S2.py` (SQLite, temp ledger from the `tests/auth/authworld.py` pattern, exit 0, one `PASS <check>` per
check, and the **full matrix printed**): every command of every loaded module (from `command_index()`) x {viewer, user,
superuser, admin, agent} x {P1, P2}, driven through the API test client and compared with the table's words (the expected
cell is computed from `schema/settings/module-roles.yaml`, not copied from the code under test); a plain user with no grant
is refused a `controller` command on P2 and allowed a `user` command; `document_controller` derived acts in P1 and in P2;
the runner, proposal acceptance (accepter without the word -> 403) and `require_generic` each refuse one cross-scope
case per module; `GET /records/{id}/actions` offers a controller only the actions the endpoint accepts; a stand-in module
(patch `load_modules` in the script) declaring `awp.cwp.release` gives `command_index()[...] == (module, "controller")`
and `awp.view` gives `read`; an unknown fine word raises `AccessWordError`; `Access` accepts a fine word and rejects a typo
at `CommandSpec` construction.

## Tests for the end run (TA writes them; this piece writes none)
`packages/tl-api/tests/test_api_module_roles.py`, `packages/tl-core/tests/test_actions_scoped.py`,
`tests/services/test_module_role_seams.py`, a `command_words == API_COMMANDS` equality test per module, and a
`command_index()` fine-word test. Report the seam list (file:line of each `require_command_access` call) so TA can
place the mutants: `_make_endpoint` check removed -> walking test red; `RoleAuthorizer` any-role pass; normalisation
removed from `command_index()`.

## Report requirements
Standard piece report (<= 60 lines): deviations first; every reader of `.access` found and how it is normalised; the list
of consequential pins updated (test id, old form kept Y/N); the seam list; acceptance output (<= 5 lines per command).

## Escalation triggers
- *Blocked* if: a seam cannot call `require_command_access` without a schema or ledger change; a test outside the three
  pins breaks; a module command has no stable class name in `API_COMMANDS`; the table word of a fine word is `admin`.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
