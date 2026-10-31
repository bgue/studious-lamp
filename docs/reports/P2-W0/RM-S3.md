# Report — P2-W0-RM-S3 (module roles on every admin surface; the module roles log)

Branch: `p2/w0-rm-s3`   Commit(s): see `git log p2/w0..p2/w0-rm-s3` (one build commit, this report included)

## Deviations
1. **Blocked on one pin outside Allowed paths (predicted, no pytest by policy).** `packages/tl-api/tests/test_auth_review.py::test_every_route_action_is_decided_for_agents` fails until `"admin.accounts.module_roles"` is added to `AGENT_MAY_NOT` (next to `"admin.accounts.state"`, ~line 377). It is not a pin class the spec lists and the file is not allowed, so I stopped there (spec: *Blocked*, test id). Everything else is built and accepted.
2. `effective_role_views(conn, account_id, project, *, holder=None)`: one optional keyword beyond the spec, so `GET /auth/me/roles` can pass `holder_for_principal(me)` (a dev-token principal has no account row).
3. `module_role_views.PROJECT_PATTERN` repeats the private `module_grants._PROJECT_PATTERN`. 4. `main.py`: the `add_typer` line plus its entry in the import list. `remote.py` needed no change (the five calls pass through `__getattr__`; signatures equal `AdminApi`/`AuthApi`).
5. `AdminScreen` reads the project from `getattr(self.app, "scope", "company")`, so `app.py` (not allowed) is unchanged. `keymap.py` (not allowed) has no `m` row (`test_keymap` only checks documented keys exist).

## Changed files
- `tl_core/auth/module_role_views.py` (new) — views, `list_module_roles`, `effective_role_views`
- `tl_api/routes/{admin,auth}.py`, `client/{admin,auth}.py`, `errors.py` (4 rows), `docs/reference/openapi.json` (regenerated)
- `tl_tui/{client,embedded}.py` (five methods), `tests/fakes_admin.py` (the fake, five methods + `seed_module_role`, `me_account_id`)
- `tl_cli/admin_roles.py` (new), `main.py`
- `tl_tui/widgets/module_roles_log.py` (new), `admin_text.py`, `widgets/admin_screen.py` (key `m`, hint)
- `dev/accept/P2-W0/RM-S3.py` (new)

## Routes and actions
| Route | Action | Who |
|---|---|---|
| `POST /admin/accounts/{id}/module-roles` (201) | `admin.accounts.module_roles` | admin |
| `POST /admin/accounts/{id}/module-roles/revoke` | `admin.accounts.module_roles` | admin |
| `GET /admin/module-roles?project&module&account_id` | `admin.accounts.list` | admin |
| `GET /admin/accounts/{id}/effective-roles?project` | `admin.accounts.list` | admin |
| `GET /auth/me/roles?project` | `auth.me` | any signed-in (agents too) |
`AGENT_ACTIONS` untouched. Errors added: `unknown_role` 422, `unknown_module` 422, `no_such_grant` 404, `no_company_roles` 422.

## Pins (by reading) and snapshots expected to change
- Text pin to add: see Deviation 1.
- `AdminScreen.KEY_HINTS` gained `m module roles` (78 cells; `KEY_HINTS_MORE` and its 76 pin untouched). Snapshots expected to change (do not regenerate): `test_admin_screen.py::test_the_accounts_snapshot_120x40`, `::test_the_accounts_snapshot_80x24`, `::test_the_agent_tokens_snapshot_120x40`; the modals over it may too: `test_account_forms.py::test_the_add_form_snapshot_120x40`, `::test_the_password_form_with_an_error_snapshot_80x24`, `::test_the_token_shown_once_snapshot_120x40`.
- `test_plain_walk.py`: `m` is a VIEW_KEY.
- `tests/api/test_error_table.py` (before this piece): `RoleTableError` (RM-S1) has no row; the spec names four rows only.

## Guard sites (for TA mutants)
- Admin check on grant/revoke routes: `routes/admin.py:295` and `:316` (`actor: ModuleRoleSetter`, guard at `:51`); the handler's own `_require_admin` at `module_grants.py:166`, `:182`. Reads: `Lister` on `list_roles`, `effective_roles_of`.
- `_admin_gate` on the embedded calls: `embedded.py:1789` (list), `:1796` (effective), `:1803` (grant), `:1821` (revoke); none in `my_roles` (`:1835`).
- `my_roles` principal binding: `routes/auth.py:142` (`me.account_id`, `holder_for_principal(me)`; no account-id parameter); embedded `:1838` (`holder_for_actor(self.actor)`).
- CLI: `require_admin(ctx.obj)` first line of each command in `admin_roles.py`. TUI: `admin_screen.py:294` (`is_admin` check for `m`).

## Commands and output
```
$ just check
ruff, format, pyright 0 errors, generated, openapi, licences: ok (exit 0)
$ uv run python dev/accept/P2-W0/RM-S3.py     # exit 0, 26 PASS lines, ALL PASS
PASS admin: revoke again is 404 no_such_grant | PASS the embedded client and the fake answer the five calls alike
PASS CLI: grant, grant again, ls, ls filtered, effective, revoke, revoke again refused
PASS module roles log at 80 columns: 3 rows, panel, refusal in the status line   (also 170)
PASS key m opens nothing for a non-admin (F10 refuses; no module role call was made)
```
The script also prints the embedded/fake answers, each CLI command, and the log at 80 and 170 columns.

## Tests added
None (end run, TA writes the four files the spec names).

## Learnings (proposed)
- `LogScreen` rows with no `Subject`/`Title` column need `keep_columns()` set to every column, or a constant column (one module) is hidden.

## Open questions / Blocked
Blocked on the one-line pin in Deviation 1 (supervisor adds it, or widens Allowed paths to that file). Also: map `RoleTableError` in `errors.py`?
