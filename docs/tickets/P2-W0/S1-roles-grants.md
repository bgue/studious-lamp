# P2-W0-RM-S1 — Module roles: role table, grants, resolver, company grants

Status: ready
Tier: sonnet
Kind: piece
Review: full
Labels: schema, auth, core
Depends on: —
Branch: `p2/w0-rm-s1`
Approver (schema): the orchestrator under P2-Q10 (line in `docs/memory/APPROVALS.md` at merge)

## Goal
After this piece, an admin can grant and revoke a module role (`viewer`, `user`, `superuser`) for an account on a
project and module, as ledgered `Account.*` events projected to `cur_account_module_role`; the role-to-word table is data
(`schema/settings/module-roles.yaml`); and one resolver, `tl_core.auth.module_roles`, answers "what roles and words does
this holder have here" (precedence 1-7) and `require_command_access`. A grant with project `company` is accepted only for
a module that declares `company_roles`. No entry point calls the resolver yet (RM-S2 wires them).

## Brief references
The interface is `docs/build-spec/specs/roles-mvp.md` **§2 (role table), §3 (grants), §4 (resolver)**, read in full
(about 110 lines) and authoritative except for the deltas below. Owner answers: `specs/wave0.md` §2.

**Deltas (wave0.md wins over roles-mvp.md)**
1. Closed owner questions: `document_controller` derives `superuser` of `documents`, `correspondence` and `schedule` (the
   "(proposed)" marks go; it is the table's `derive` block as written). A superuser grant gives no restricted read
   (ADR-0016 unchanged). Module roles do not filter reads. Only active human admins grant and revoke.
2. **Company grants** (answer 14). `GrantModuleRole.project` / `RevokeModuleRole.project` accept `company` as well as
   `project:<id>` (pattern `^(company|project:[A-Za-z0-9_.-]+)$`). A `company` grant is accepted only when `module` names
   a loaded module whose `ModuleSpec.company_roles` is true; otherwise `NoCompanyRolesError` (422 code
   `no_company_roles`; `module="*"` with `company` is refused the same way). Precedence step 3 becomes: command scope
   `company` -> explicit `company` grants for that module when it declares `company_roles`, else derived only (registry
   and schema commands unchanged). A `project:<id>` command never reads a `company` grant.
3. `ModuleSpec` (`tl_core/modules.py`) gains exactly two fields, both after `actions`: `command_words: Mapping[str, str]`
   (command class name -> access word; empty default) and `company_roles: bool = False`. No module fills them in this piece
   (RM-S2 does); no other change to `ModuleSpec` or `modules.py`.
4. Fine access words (`schema/settings/access-words.yaml`, `tl_core.auth.access_words`) are W0-B1's, built in parallel on
   another branch. **Do not import or read them.** `command_index()` returns each word exactly as declared; RM-S2 later
   normalises fine -> table word inside it. `require_command_access` treats the word it gets as a table word.
5. The role table's `words` are `read`, `user`, `controller`; `admin` and `company` are platform words, as in §2.
6. Do not touch `tl_api`, `tl_cli`, `tl_tui`, any `module.py`, `settings` or any test outside the two pinned lists.

## Interfaces (key signatures; full text in roles-mvp.md §3-§4)
```python
# tl_core/auth/module_grants.py (Command subclasses, scope always "company")
class GrantModuleRole(Command):      # RevokeModuleRole has the same fields
    account_id: str
    project: str = Field(pattern=r"^(company|project:[A-Za-z0-9_.-]+)$")
    module: str            # a loaded module name or "*"
    role: str              # a role of the table
    reason: str = Field(min_length=1, max_length=500)
def grant_module_role(uow, cmd: GrantModuleRole) -> CommandResult: ...
def revoke_module_role(uow, cmd: RevokeModuleRole) -> CommandResult: ...
# errors (tl_core/auth/errors.py, ServiceError subclasses): UnknownRoleError, UnknownModuleError, NoSuchGrantError,
#   NoCompanyRolesError, RoleTableError (table load); reuse ForbiddenError, AccountNotFoundError, InvalidAccountError.
# tl_core/auth/module_roles.py: Holder, holder_for_principal, holder_for_actor, EffectiveRoles, load_role_table,
#   effective_roles, holds_word, scoped_holds, require_command_access, command_index  (signatures in roles-mvp.md §4)
# events (schema/core/events.yaml, payload classes): Account.ModuleRoleGranted / Account.ModuleRoleRevoked
#   {account_id, project, module, role, reason}; stream account:<id>, stream type core.Account, scope company.
# projection (schema/core/auth.yaml, tl:current_state): AccountModuleRole -> cur_account_module_role
#   account_id, project, module, role, granted_by, granted_at, seq; key (account_id, project, module, role); tl:ix_scope: project,module
```
Checks in `grant_module_role`, in order: actor active human admin (`ForbiddenError`); account exists
(`AccountNotFoundError`); role in table (`UnknownRoleError`); `company` project -> module has `company_roles`
(`NoCompanyRolesError`); module loaded or `*` (`UnknownModuleError`); agent account and role not in `agent_roles`
(`InvalidAccountError`). Already held -> append nothing, `changed: false`. Revoke of a grant not held -> `NoSuchGrantError`.

## Context (<= 10 files)
- `docs/build-spec/specs/roles-mvp.md` §2-§4; `docs/adr/0021-module-roles-mvp.md` (draft; do not edit)
- `packages/tl-core/src/tl_core/auth/{accounts.py,projector.py,errors.py,types.py,provider.py}` (the grant commands copy `accounts.py`'s command/event pattern; the projector gains the two events)
- `packages/tl-core/src/tl_core/modules.py` (`ModuleSpec`, `load_modules`)
- `schema/core/auth.yaml`, `schema/core/events.yaml` (add beside the Account classes)
- `packages/tl-schema/tests/test_ddl.py`, `test_generate.py` (pinned lists you must update)
may explore: `packages/tl-core/src/tl_core/services/commands.py` (Command base), `tests/auth/authworld.py` (a ready ledger with accounts, for the acceptance script)

## Allowed paths
- `schema/core/auth.yaml`, `schema/core/events.yaml`, `schema/settings/module-roles.yaml` (create)
- `packages/tl-schema/src/tl_schema/generated/**` (only by `just gen`; commit the output)
- `packages/tl-core/src/tl_core/auth/{module_roles.py,module_grants.py}` (create), `auth/{projector.py,errors.py,__init__.py}`
- `packages/tl-core/src/tl_core/modules.py` (the two `ModuleSpec` fields and nothing else)
- `packages/tl-schema/tests/test_ddl.py`, `packages/tl-schema/tests/test_generate.py` (pinned lists only; consequential pins, list them in the report)
- `dev/accept/P2-W0/RM-S1.py` (create), `docs/reports/P2-W0/RM-S1.md` (create)

## Acceptance (run these, once; no pytest, tests are deferred to TA and the end run)
```
just gen
just check
uv run python dev/accept/P2-W0/RM-S1.py
```
`dev/accept/P2-W0/RM-S1.py` (SQLite, a temp ledger, exit 0, one `PASS <check>` line per check) proves: the table loads
and an unknown word / role / account role in a bad copy is a `RoleTableError`; ada (admin) grants alice `superuser` of
documents on P1 -> events appended, projection row present, repeat is `changed: false`; revoke works, a second revoke is
`NoSuchGrantError`; unknown role / module / agent-with-superuser / non-admin granter are refused with the named errors;
precedence 1-7 by a table of holders (disabled, inexact actor, admin, scope company, explicit grant replaces derived,
`*` grant, derived `document_controller` -> superuser of documents / correspondence / schedule, none, agent capped at
`agent_roles`, `svc:` held access); a `company` grant for a stand-in `ModuleSpec(company_roles=True)` is accepted and
read at command scope `company`, and for a module without `company_roles` is refused `NoCompanyRolesError`; the two
events are stream type `core.Account`, scope `company`. Print the precedence table (holder x result) in the output.

## Tests to add
None in this piece (owner: tests deferred). TA writes `packages/tl-core/tests/auth/test_module_role_table.py`,
`test_module_roles_resolve.py`, `test_module_grants.py`, `test_company_grants.py`. Update only the pinned lists above.

## Mutation guards (run by TA, named here so the code is written to be killable)
Precedence 4 over 6 (explicit replaces derived); agent superuser refused; unknown word in the table fails closed; scope
`company` ignores `project:` grants and `project:` ignores `company` grants; `company` grant for a module without
`company_roles` refused. Report in 3 lines which guard sits where (file:line).

## Report requirements
Standard piece report (<= 60 lines): deviations first; the pinned-list changes; the acceptance output; candidate learnings.

## Escalation triggers
- Stop and report *Blocked* if: a core `schema/**` change beyond the two classes and the table is needed; the projector
  cannot take the events without touching the ledger or hash chain; `ModuleSpec` must change beyond the two fields; the
  precedence in §4 contradicts delta 2.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
