# Spec: module roles MVP (viewer, user, superuser per project and module)
Owner answers of 2026-10-30 and the wave-0 build plan are in `specs/wave0.md`; where they differ, `wave0.md` wins.

Status: draft v0.1, 2026-10-30, planner tier. Source: owner decision 1 (`module-designs/OWNER-DECISIONS-2026-10-30.md`).
ADR: `docs/adr/0021-module-roles-mvp.md` (draft). Builds on ADR-0009, ADR-0011, ADR-0013 (+ P1-SEC1 addendum), ADR-0016,
ADR-0010 addendum 2026-10-21 (`ModuleSpec.actions`), ADR-0017 §7 (service actors). Lines marked **(proposed)** go beyond
the decision and the designs; the owner may strike them without breaking the rest.

## 1. What exists after this spec is built
- Every module has three roles: `viewer` (read), `user` (create and work records), `superuser` (approve, sign off,
  configure, void), granted **per project and per module** by an admin, as ledgered account events.
- Commands keep their **access word** (`CommandSpec.access`, unchanged literals `user`, `controller`, `admin`,
  `company`). Which role holds which word is a **data table** (`schema/settings/module-roles.yaml`), not code.
- Every entry point that decides a command (API, command runner, proposal accept, CLI, embedded TUI) and the
  allowed-actions query ask one core function, `tl_core.auth.module_roles`. Admin keeps its platform-wide powers.
- Today's accounts keep working with **no data migration**: module roles are **derived** from today's account roles
  until an admin grants explicitly.

## 2. The role table (data)
File `schema/settings/module-roles.yaml` (a `schema/**` change: human gate). Loaded once per process by
`load_role_table()`; any unknown word, role or account role in it is a `RoleTableError` at start-up (fail closed).
```yaml
version: 1
words:                      # the grantable access words; CommandSpec.access values other than admin/company
  read: Read the module's records          # reported, not yet enforced on reads (section 7)
  user: Create and work records            # = today's access word "user"
  controller: Approve, sign off, issue, configure, void   # = today's access word "controller"
roles:                      # role -> words it holds; order = display order
  viewer: [read]
  user: [read, user]
  superuser: [read, user, controller]
agent_roles: [viewer, user] # roles an agent account may be granted (agents still only propose)
derive:                     # account role -> implied module roles, used only where no explicit grant applies
  user: [{module: "*", role: user}]
  document_controller:
    - {module: documents, role: superuser}
    - {module: correspondence, role: superuser}   # (proposed) keeps today's controller acts, owner Q1
    - {module: schedule, role: superuser}         # (proposed) idem
```
Platform words are not in the table and cannot be granted: `admin` (an active human admin only) and `company`
(`admin` when the command's scope is `company`, else the word `user`). A `CommandSpec` whose access is outside
`words ∪ {admin, company}` fails the app's start-up (test).

## 3. Grants: events, projection, commands
- Events (payload classes in `schema/core/events.yaml`; stream `account:<account_id>`, stream type `core.Account`,
  scope `company`, so ADR-0009 §1 hiding, lake redaction and the webhook exclusion apply unchanged):
  `Account.ModuleRoleGranted {account_id, project, module, role, reason}` and
  `Account.ModuleRoleRevoked {account_id, project, module, role, reason}`.
- Projection `cur_account_module_role` (LinkML class `AccountModuleRole` in `schema/core/auth.yaml`,
  `tl:current_state`): `account_id, project, module, role, granted_by, granted_at, seq`; key
  `(account_id, project, module, role)`; `tl:ix_scope: project,module`. Written by `tl_core.auth.projector`.
- Commands in `tl_core/auth/module_grants.py` (Command subclasses, `scope` always `company`):
```python
class GrantModuleRole(Command):     # also RevokeModuleRole, same fields
    account_id: str
    project: str = Field(pattern=r"^project:[A-Za-z0-9_.-]+$")
    module: str                     # a loaded module name (load_modules()) or "*" (every module of the project)
    role: str                       # a role of the table
    reason: str = Field(min_length=1, max_length=500)
def grant_module_role(uow, cmd: GrantModuleRole) -> CommandResult: ...
def revoke_module_role(uow, cmd: RevokeModuleRole) -> CommandResult: ...
```
  Checks, in order: actor is an active human admin (`ForbiddenError`); account exists (`AccountNotFoundError` 404);
  role in table (`UnknownRoleError` 422 `unknown_role`); module loaded or `*` (`UnknownModuleError` 422
  `unknown_module`); agent account and role not in `agent_roles` (`InvalidAccountError` 422). Granting a role already
  held appends nothing and answers `changed: false`; revoking one not held is `NoSuchGrantError` 404 `no_such_grant`.
  Several roles may be held for one `(project, module)` (the hook for section 8); the MVP's three are nested.

## 4. The resolver (`tl_core/auth/module_roles.py`, builder piece)
```python
@dataclass(frozen=True)
class Holder:                     # who is asking; never read from a request body
    actor: str; kind: AccountKind | Literal["service"]; account_id: str | None; account_roles: tuple[str, ...]
def holder_for_principal(p: Principal) -> Holder                  # API (dev-token principals have no account rows)
def holder_for_actor(conn: Connection, actor: str) -> Holder       # CLI, embedded, runner: from cur_account, exact actor
@dataclass(frozen=True)
class EffectiveRoles:
    roles: frozenset[str]; words: frozenset[str]
    source: Literal["admin", "granted", "granted_all_modules", "derived", "service", "none"]
def effective_roles(conn, holder: Holder, *, scope: str, module: str) -> EffectiveRoles
def holds_word(conn, holder, *, scope, module, word: str) -> bool
def scoped_holds(conn, holder, *, scope, module, base: Holds) -> Holds      # for ModuleSpec.actions hooks
def require_command_access(conn, command: Command, *, holder: Holder | None = None) -> None   # ForbiddenError
def command_index() -> Mapping[str, tuple[str, str]]   # command name -> (module, word), from ModuleSpec.command_words
```
Precedence for `effective_roles` (first that applies wins):
1. Disabled, missing or inexact account (actor ≠ `actor_for(kind, username)`): `none`.
2. Active human `admin`: every role and word, plus `admin`; source `admin`.
3. Scope `company` (registry and schema commands): derived only (today's behaviour); explicit grants never apply.
4. Explicit grants for `(account, project, module)`: those roles (an explicit grant **replaces** the derived roles, so
   an admin can lower a person to `viewer` on one project); source `granted`.
5. Explicit grants for `(account, project, "*")`: source `granted_all_modules`.
6. Derived from `account_roles` through `derive`: source `derived`.
7. Otherwise `none`. An agent holds at most `agent_roles`; a `svc:*` actor keeps its declared access
   (`held_access`, ADR-0017 §7: `user` → word `user`, `controller` → words `user`, `controller`), source `service`.

`require_command_access` looks the command's class name up in `command_index()` (a name in two modules is a
`ModuleLoadError`), takes `scope` and `actor` from the command, and raises
`ForbiddenError("<Name> needs the <word> access word for <module> on <project>")`. Core commands with no module
are unchanged. Every handler already refuses a record outside `cmd.scope` (e.g. `tl_mod_documents/handlers/common.py`),
so the scope on the command is the project the check uses; a test pins one refusal per module.

## 5. How the seams consult it (verified against the trunk at 88d037a)
| Seam | Today | After |
|---|---|---|
| `tl_api.commands.CommandSpec` | `access`; module tuples splatted | adds `module: str \| None`; module tuples wrapped by `_module_specs("<m>", TUPLE)`; `controller` with `module=None` is a start-up error |
| `_make_endpoint` | authorizer by action prefix, then handler | inside the `ctx.backend(False)` block, before the handler: `require_command_access(conn, command, holder=holder_for_principal(principal))` |
| `RoleAuthorizer` (`tl_core/auth/provider.py`) | `control.*` in `controller_actions` only for `document_controller` | a listed `control.*` action passes for **any non-agent principal with a role**; the endpoint's scoped check decides. Unlisted `control.*` stays admin-only; agents still refused |
| `TableCommandRunner.run` | `require_access(conn, actor, needed)` | `user:`/`agent:` actors: `require_command_access`; `svc:` actors: unchanged `require_access` |
| `accept_proposal` (`tl_core/services/proposals.py`) | `_require_access(row.command_type, holds)` | also `require_command_access` for the accepting person on the stored command's scope (module from `ModuleSpec.proposable`) |
| `allowed_actions` (`tl_core/actions.py`) | hook gets the route's `holds` | reads the record's `scope`; passes `scoped_holds(conn, holder, scope, module, base=holds)`: `admin` from `base`, `user`/`controller` from the table. Hook signature unchanged |
| `require_generic` (`tl_core/modules.py`, 8 call sites) | type allow-list + guard | adds keyword `actor: str \| None = None`; when given and the type is a module's, needs the word `user` there; all 8 call sites pass `cmd.actor` |
| `ModuleSpec` | — | adds `command_words: Mapping[str, str]` (command name → access word), each module filled from its own `API_COMMANDS` in one line; a test holds them equal |
| CLI (`tl_cli.session`) | `require_controller(db)` at the controller sites, nothing at `user` sites | `require_command(db, cmd)` immediately before every `tl_mod_*` handler call (139 calls). On a dev ledger file without a session (`TL_ENV` dev/test/ci) the `user` word passes as today; `controller` still needs a session |
| Embedded TUI (`tl_tui/embedded.py`) | `_controller_gate(uow)` | `_command_gate(uow, cmd)` before each of its 35 module handler calls; same dev-file rule |
| MCP | write tools create proposals | unchanged (agents propose; the accepter's roles apply) |
| Workflow `roles` guards (`workflow_roles`) | account roles | **unchanged**: controlling acts are commands with access words (R-P2-3), not role guards |

## 6. Surfaces: grant, revoke, list
- API (`tl_api/routes/admin.py`, admin only): `POST /admin/accounts/{account_id}/module-roles` (grant, 201) and
  `POST /admin/accounts/{account_id}/module-roles/revoke`, body `{project, module, role, reason}`, action
  `admin.accounts.module_roles`; `GET /admin/module-roles?project=&module=&account_id=` (explicit grants,
  `ModuleRoleGrantView`); `GET /admin/accounts/{account_id}/effective-roles?project=` (one
  `EffectiveRoleView{module, roles, source}` per loaded module). Caller's own: `GET /auth/me/roles?project=` (action
  `auth.me`). `ApiClient.admin` gains the four calls; `ApiClient.auth.my_roles`.
- `ClientInterface` (+ embedded with `_admin_gate`, remote, fake): `list_module_roles(project)`,
  `effective_roles(account_id, project)`, `grant_module_role(...)`, `revoke_module_role(...)`, `my_roles(project)`.
- CLI: `tl admin roles grant USER --project P --module M --role R --reason TEXT`, `tl admin roles revoke ...`,
  `tl admin roles ls [--project P] [--module M] [--user U]`, `tl admin roles effective USER --project P`.
- TUI: on the accounts screen (admin only) key `m` opens `ModuleRolesLog` (a `LogScreen`) for the current project:
  columns Account, Module, Role, Granted by, Since; panel = identity line (account display name), state line
  (`Admin`, `Granted`, `Derived`), section **Effective roles** (one property line per module: `Documents  superuser
  (granted)`); row action `r` Revoke (reason form); host key `n` New grant (`ActionFormScreen`: account, module, role,
  reason). Plain words; ids only in technical mode.
- Web: none in web increment 1 (admin work stays in the terminal) **(proposed)**.

## 7. Confidentiality, reads, automation (what does not change)
- **ADR-0016 is unchanged.** Clearance stays account-level: `viewer_for(principal)` gives `restricted` to an admin or a
  `document_controller` account. A module grant of `superuser` gives no clearance, and lowering a controller to
  `viewer` on a project lowers no clearance (owner Q2). A superuser without clearance cannot act on a restricted
  record: `require_visible` answers it as missing, before any role check.
- **Reads are not filtered by module role in the MVP.** The `read` word is resolved and reported (`/auth/me/roles`)
  so screens can say "view only", but lists and gets stay governed by ADR-0016 alone. A project-membership read filter
  belongs with the party scope of external parties (P3-I8) **(proposed)**, owner Q3.
- Service actors, the job worker, projectors and the sealer are unchanged. `held_access` keeps its meaning.
- `document_controller` stays in `ROLES`; the accounts screen key `c` and `tl admin user roles` still set it.

## 8. The hook for the richer role model
Later roles (planner, cost controller, QA/QC inspector, external party) are new rows under `roles:` (and, when a
command needs a finer word such as `sign_off`, a new word under `words:` plus that command's `access` value and a
`Literal` widening in the module's `Access`). Grants store the role **name**, validated against the table at command
time, so a new role needs no schema or event change; several roles per `(project, module)` are already allowed and
their words are unioned. A new derivation source (Entra groups, ADR-0009 §12) adds a `Holder.account_roles` source in
`holder_for_*` and nothing else. Granting by module superusers (delegation) is a later decision (owner Q4).

## 9. Pieces and tickets
Wave 0 of Phase 2 (`08-phase2-plan.md` §0.2), registry owner for `tl_api/commands.py`. IDs `P2-RM-*`.
| ID | Kind | Review | Depends | Allowed paths | Tests added |
|---|---|---|---|---|---|
| S1 grants, table, resolver | piece (schema, human gate) | full | — | `schema/core/auth.yaml`, `schema/core/events.yaml`, `schema/settings/module-roles.yaml`, `packages/tl-schema/src/tl_schema/generated/**` (by `just gen`), `packages/tl-core/src/tl_core/auth/{module_roles,module_grants,projector,errors,__init__}.py`, `packages/tl-core/src/tl_core/modules.py` (`command_words` field only), pinned lists `packages/tl-schema/tests/test_ddl.py`, `test_generate.py` | `packages/tl-core/tests/auth/test_module_role_table.py`, `test_module_roles_resolve.py` (precedence 1–7), `test_module_grants.py` (checks, idempotence, events hidden from `/events` for non-admins) |
| S2 API, runner, proposals, actions | piece (security) | full | S1 | `packages/tl-api/src/tl_api/commands.py`, `routes/actions.py`, `routes/proposals.py`, `packages/tl-core/src/tl_core/{actions,modules}.py`, `auth/provider.py`, `services/proposals.py`, `services/{records,psets,workflow,links}.py` and `files/service.py`, `integration/enrichers/layer.py` (the `require_generic` call sites only), each `packages/tl-modules/*/src/*/module.py` (`command_words` line) | `packages/tl-api/tests/test_api_module_roles.py` (walks every module command × viewer, user, superuser, admin, agent; plain user with no grant on project B refused there), `packages/tl-core/tests/test_actions_scoped.py`, `tests/services/test_module_role_seams.py` (runner, proposal accept, `require_generic`, cross-scope refusal per module) |
| S3 admin surfaces | piece (auth) | full | S1 | `packages/tl-api/src/tl_api/routes/{admin,auth}.py`, `tl_api/client/{admin,auth}.py`, `tl_api/errors.py`, `docs/reference/openapi.json` (generated), `packages/tl-tui/src/tl_tui/{client,embedded,remote}.py` and the fake, `packages/tl-cli/src/tl_cli/admin_roles.py`, `tl_cli/main.py` (one line) | `packages/tl-api/tests/test_api_admin_module_roles.py`, `packages/tl-cli/tests/test_cli_admin_roles.py`, `packages/tl-tui/tests/test_client_module_roles.py` |
| S4 gate sweep CLI + embedded | piece (one area, rule 12) | full | S2 | `packages/tl-cli/src/tl_cli/**` (gate calls only), `tl_cli/session.py`, `packages/tl-tui/src/tl_tui/embedded.py` (gate calls only); consequential pins listed in the report | `packages/tl-cli/tests/test_cli_module_words.py` (AST: every `tl_mod_*` handler call is preceded by `require_command`), `packages/tl-tui/tests/test_embedded_module_words.py` (same AST rule), updates `test_cli_controller_gates.py` |
| T1 module roles log | ticket (tui) | full | S3 | `packages/tl-tui/src/tl_tui/widgets/module_roles_log.py`, `tl_tui/admin_text.py`, `widgets/admin_screen.py` (key `m`) | `packages/tl-tui/tests/test_module_roles_log.py` (3 rows, revoke refusal in status line, 80/170 snapshots, plain walk entry) |
| T2 docs | ticket | lite | S3, S4 | `docs/runbooks/accounts-and-access.md`, `docs/reference/access-words.md` (new), `packages/tl-core/README.md` | none (docs) |
| T3 demo | ticket | lite | T1 | `dev/demos/P2-RM.sh` | the demo is its test |

Mutation guards (S1, S2; sentinel + ≤ 5): precedence 4 over 6 (explicit replaces derived); agent superuser refused;
unknown word in the table fails closed; the `_make_endpoint` check removed → walking test red; `scope=company` ignores
grants. S2 and S4 are on the wave-0 security review (`Sec`).

## 10. Demo clauses (`just demo P2-RM`)
1. Seeded ledger: `alice` (user), `dora` (document_controller), `ada` (admin). Without any grant, alice registers a
   document in P1 and cannot issue it (403); dora issues it (derived superuser).
2. `tl admin roles grant alice --project P1 --module documents --role superuser --reason demo` → alice issues a
   revision in P1; in P2 she is still refused.
3. `tl admin roles grant dora --project P2 --module documents --role viewer --reason demo` → dora is refused
   `RegisterDocument` in P2 and still issues in P1; `GET /records/{id}/actions` in P2 offers her nothing.
4. `tl admin roles effective alice --project P1` lists every module with source; `GET /events` as alice shows no
   grant events; as ada it does.
5. An agent proposal of `IssueRevision` in P1 accepted by alice runs; accepted by bob (plain user) is 403.

## 11. Risks
- **R1 bypass by a missed entry point** (HIGH): a sixth path that runs a module handler without the check. Mitigation:
  the API walking test, the two AST pins, the runner and proposal tests; the security review reads `git grep handle_`.
- **R2 dev workflows break** (MD): tests that run as `user:dev` with no account. Mitigation: the dev-file rule; S4
  lists every consequential pin.
- **R3 authorizer widening** (MD): opening listed `control.*` actions to any person moves the decision into the
  endpoint. Mitigation: start-up error for a controller command with no module; walking test asserts 403 for a plain
  user on every controller command.
- **R4 table drift** (LO): a module adds an access word not in the table → start-up error, caught by `just gate`.

## 12. Owner questions
- **Q1** Should `document_controller` also derive `superuser` of correspondence and schedule (today it runs their
  `controller` commands)? Default here: yes, so nothing a controller does today stops working.
- **Q2** Should a per-project `superuser` of documents or correspondence also read `restricted` records of that project?
  Default here: no (ADR-0016 unchanged; clearance stays the account's).
- **Q3** When should module roles filter reads (a person with no role on a project sees nothing of it)? Default:
  with the party scope in P3-I8.
- **Q4** May a module `superuser` grant `viewer`/`user` of that module on that project, or only an admin? Default: admin only.
