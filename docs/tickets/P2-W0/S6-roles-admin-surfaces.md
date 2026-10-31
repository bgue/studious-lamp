# P2-W0-RM-S3 — Module roles: grant, revoke, list and effective roles on every admin surface, with the module roles log

Status: ready
Tier: sonnet
Kind: piece
Review: full
Labels: auth, security, api, cli, tui
Depends on: RM-S1 (merged, `module_grants.py`, `module_roles.py`); RM-S2 (merged; independent of this piece)
Branch: `p2/w0-rm-s3`
Approver (permission path): the orchestrator under P2-Q10 (line in `docs/reports/APPROVALS.md` at merge)

## Goal
An admin can grant, revoke and list module roles, and read a person's effective roles per module, through the API, the
`ApiClient`, the embedded and remote TUI clients, `tl admin roles ...` and the accounts screen; any signed-in person reads
their own roles. The TUI shows the explicit grants in the module roles log (rule 12: the old T1 ticket is folded in here).
No decision logic is added: every write calls the RM-S1 handlers, every read calls the RM-S1 resolver.

## Brief references
- Interface: `docs/build-spec/specs/roles-mvp.md` **§6 in full** (routes, names, views, CLI, TUI), authoritative except:
  1. **Scope (D8).** `project` is `company` or `project:<id>` (`module_grants._PROJECT_PATTERN`); the routes and the CLI take the
     same value (CLI `--project P1` means `project:P1`; `--project company` means `company`). A `company` grant for a module
     without `company_roles` answers `NoCompanyRolesError`.
  2. **Views.** Put `ModuleRoleGrantView {account_id, username, project, module, role, granted_by, granted_at}` and
     `EffectiveRoleView {module, roles: list[str], source}` and the two queries in a **new** `tl_core/auth/module_role_views.py`
     (`types.py` is a frozen contract; do not edit it). `list_module_roles(conn, *, project=None, module=None, account_id=None)`
     reads `cur_account_module_role`; `effective_role_views(conn, account_id, project)` calls `effective_roles` once per
     loaded module from a `Holder` built from the account row (`find_account`; the way `holder_for_actor` builds it).
     `source` is the resolver's (`grant`, `derived`, `admin`, `none`, ... as `Source` declares).
  3. **Errors.** `UnknownRoleError` 422 `unknown_role`, `UnknownModuleError` 422 `unknown_module`, `NoSuchGrantError` 404
     `no_such_grant`, `NoCompanyRolesError` 422 `no_company_roles` have no row in `tl_api/errors.py`; add the four.
  4. **Actions.** Grant and revoke use the new action `admin.accounts.module_roles`; the two admin GETs use the existing
     `admin.accounts.list`; `GET /auth/me/roles` uses `auth.me`. An agent is refused the admin ones by the default-deny list
     (check `AGENT_ACTIONS` in `provider.py` is untouched).
  5. **Reads are not module-role filtered** and the grant events stay hidden from non-admin `/events` (RM-S1 did that); do not
     change confidentiality.
- TUI layout: load the `tui-layout` skill before the log screen. Plain words (`Granted`, `Derived`, `Admin`), ids only in
  technical mode, one property line per module in the panel, 80 and 170 columns.

## Context (<= 10 files)
- `docs/build-spec/specs/roles-mvp.md` §3, §6; `docs/reports/P2-W0/RM-S1.md`, `RM-S2.md`
- `packages/tl-core/src/tl_core/auth/{module_grants.py,module_roles.py,queries.py}`; `packages/tl-api/src/tl_api/routes/{admin,auth}.py`, `tl_api/client/{admin,auth}.py`
- `packages/tl-cli/src/tl_cli/{admin.py,admin_user.py}` (the pattern for a CLI admin group); `packages/tl-tui/src/tl_tui/widgets/{admin_screen.py,log_screen.py}`, `tl_tui/admin_text.py`
may explore: `widgets/integration_screen.py` (a LogScreen with a row action and a host-key form), `widgets/action_form.py`, `tests/auth/authworld.py`

## Allowed paths
- `packages/tl-core/src/tl_core/auth/module_role_views.py` (create); `packages/tl-core/src/tl_core/auth/__init__.py` only if it re-exports sibling modules today
- `packages/tl-api/src/tl_api/routes/{admin,auth}.py`, `tl_api/client/{admin,auth}.py`, `tl_api/errors.py`, `docs/reference/openapi.json` (by `python -m tl_api.openapi`)
- `packages/tl-tui/src/tl_tui/{client,embedded,remote}.py` (the five `ClientInterface` methods; embedded uses `_admin_gate` for the admin four, none for `my_roles`); the in-memory fake `packages/tl-tui/tests/fakes_admin.py` (a fake, not a test: it must implement the five methods so `FakeClient` conforms)
- `packages/tl-cli/src/tl_cli/admin_roles.py` (create), `packages/tl-cli/src/tl_cli/main.py` (one `add_typer` line, beside `user`/`token`)
- `packages/tl-tui/src/tl_tui/widgets/module_roles_log.py` (create), `tl_tui/admin_text.py`, `widgets/admin_screen.py` (key `m` opens the log, admin only), `widgets/action_form.py` only if the new-grant form needs a field kind it lacks
- `dev/accept/P2-W0/RM-S3.py` (create), `docs/reports/P2-W0/RM-S3.md` (create)
Not allowed: `schema/**`, `module_roles.py`, `module_grants.py`, `provider.py` (the resolver and handlers are RM-S1's), `tl_cli/session.py`, any other CLI file, `tl_mcp/**`.

## Consequential pins (rule 12; update by reading, no pytest, list them)
Tests that enumerate `ClientInterface` methods, the accounts screen footer/help text or its snapshots may break because the
interface and screen gain things. Update text pins; **do not regenerate snapshots** (end run, Q4-style; list the snapshot
test ids you expect to change). Any other breaking test outside these stops the piece (*Blocked*, test id).

## Acceptance (run these, once; no pytest, no `just gate`)
```
just check
uv run python dev/accept/P2-W0/RM-S3.py
```
`dev/accept/P2-W0/RM-S3.py` (SQLite temp ledger from the `tests/auth/authworld.py` pattern, exit 0, one `PASS <check>` per
check, output printed): API as admin: grant 201, repeat `changed: false`, revoke, revoke again 404 `no_such_grant`, unknown
role and module 422, company grant for a module without `company_roles` 422, agent account with `superuser` 422; as a
plain user: every admin route 403, `GET /auth/me/roles` answers their own derived roles; `GET /admin/module-roles` filters by
project, module and account; `effective-roles` lists one entry per loaded module with the source; a non-admin `/events` shows
no grant event, an admin's does; the embedded client and the fake answer the five calls alike (print both); CLI
through `CliRunner` against a temp ledger, signed in as admin: `tl admin roles grant alice --project P1 --module documents
--role superuser --reason demo`, `ls`, `effective alice --project P1`, `revoke` (print the output of each); the module
roles log under Pilot at 80 and 170 columns with 3 rows (print the rendered text of the table and the panel), a revoke
refusal shown in the status line, key `m` absent for a non-admin.

## Tests for the end run (TA writes them; this piece writes none)
`packages/tl-api/tests/test_api_admin_module_roles.py`, `packages/tl-cli/tests/test_cli_admin_roles.py`,
`packages/tl-tui/tests/test_client_module_roles.py`, `packages/tl-tui/tests/test_module_roles_log.py` (3 rows, revoke refusal in
the status line, 80/170 snapshots, plain walk entry). Report the guard sites (file:line) of: admin check on grant/revoke
routes, `_admin_gate` on the embedded calls, the `my_roles` principal binding, so TA can place mutants.

## Report requirements
Standard piece report (<= 60 lines): deviations first; changed files; routes and actions added (table); the pins updated
and snapshot ids expected to change; guard sites; acceptance output (<= 5 lines per command).

## Escalation triggers
- *Blocked* if: a route cannot be written without editing `module_grants.py` or `module_roles.py`; the accounts screen has no
  host key `m` free; a test outside the pin classes above breaks.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
