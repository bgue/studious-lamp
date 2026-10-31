# Report — P2-W0-RM-S1 (module roles: table, grants, resolver, company grants)

Branch: `p2/w0-rm-s1`   Commit(s): see `git log p2/w0..p2/w0-rm-s1` (code commit, then this report)

## Deviations
1. The `Account.ModuleRole*` payload classes sit in `schema/core/auth.yaml` beside the Account payloads (that is
   where `AccountEventPayload` lives); `schema/core/events.yaml` is unchanged.
2. `AccountModuleRole` has no single-column identifier (the generator supports none for a composite key); the key is
   the unique index `ux_cur_account_module_role_grant` over the four key columns, plus `ix_..._scope (project, module)`.
3. `CommandResult` has no `changed`, so the commands return `ModuleRoleResult(CommandResult)` with `changed: bool`.
4. Event-type constants are in `auth/projector.py` (`types.py` is a frozen contract); `auth/__init__.py` is unchanged.
5. A revoke checks only admin, account, and "held" (it skips the role-table, module, company and agent checks of a
   grant), so a grant made under an older table stays revocable. Owner policy: no pytest, no `just gate`, no mutants run.

## Changed files
- `schema/core/auth.yaml` — class `AccountModuleRole`, payloads `AccountModuleRole{Granted,Revoked}Payload`
- `schema/settings/module-roles.yaml` — the role table (data)
- `packages/tl-schema/src/tl_schema/generated/**` — `just gen` output only
- `packages/tl-core/src/tl_core/auth/module_roles.py` — table loader, Holder, resolver (precedence 1-7), `require_command_access`
- `packages/tl-core/src/tl_core/auth/module_grants.py` — `GrantModuleRole`, `RevokeModuleRole`, handlers
- `packages/tl-core/src/tl_core/auth/{projector,errors}.py` — two events in the projector; five errors
- `packages/tl-core/src/tl_core/modules.py` — `ModuleSpec.command_words`, `company_roles` (after `actions`)
- `packages/tl-schema/tests/{test_ddl,test_generate}.py` — pinned lists, see below
- `dev/accept/P2-W0/RM-S1.py` — acceptance script

## Pinned-list changes
`ddl/postgres/cur_account_module_role.sql` and `ddl/sqlite/cur_account_module_role.sql` added, after `cur_account.sql`, in both files
(4 lines). Other pins may move at the end run (event-catalog counts, `tests/auth/test_projection_parity.py`); not touched.

## Commands and output
```
$ just gen            -> wrote 639 files
$ just check          -> 0 errors, 0 warnings; generated files are up to date (639 files); licences ok
$ uv run python dev/accept/P2-W0/RM-S1.py   -> exit 0, 18 PASS lines, e.g.
PASS precedence 1-7: disabled, inexact, admin, company scope, grant, '*', derived, none
PASS company grant accepted for company_roles module, read at scope company only
PASS company grant for a module without company_roles refused: NoCompanyRolesError
bob, explicit viewer replaces derived user   project:P1 documents  viewer     granted
dora (document_controller)                   project:P1 schedule   superuser  derived
```
The script prints the full holder x result table.

## Mutation guard sites (for TA)
- Precedence 4 over 6: `module_roles.py` `effective_roles`, `roles = _grants(..., scope, module)` then `if not roles: roles = _derived(...)`.
- Agent cap: `module_roles.py` `roles &= frozenset(table.agent_roles)`; grant refusal `module_grants.py` `_check_grant` (`kind == "agent"`).
- Unknown word fails closed: `module_roles.py` `parse_role_table` (`unknown = sorted(set(listed) - set(words))`).
- Scope isolation: `effective_roles` `if scope == COMPANY` branch vs the `else` branch (project reads `scope`, company reads `COMPANY`).
- Company grant refused: `module_grants.py` `_check_grant` (`not spec.company_roles`).

## Tests added
None (owner: deferred to TA). Acceptance script only.

## Learnings (proposed)
- The DDL generator has no composite primary key; a `unique_keys` entry is the way to express one.
- `Principal` for a dev token has `account_id = "dev:<actor>"`; the resolver trusts it without a row.

## Open questions / Blocked
none. For RM-S2: `holder_for_principal` trusts the principal's roles (not re-read from `cur_account`); the resolver checks only that the account is active and the actor exact.
