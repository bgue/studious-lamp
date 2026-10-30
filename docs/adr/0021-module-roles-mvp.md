# ADR-0021 — Module roles: viewer, user and superuser per project and module

Status: draft (proposed 2026-10-30 by the spec writer for Phase 2 wave 0; needs the owner's answers to Q1–Q4 of
`docs/build-spec/specs/roles-mvp.md` §12 and orchestrator acceptance; a role and access-level change is a human gate,
`08-phase2-plan.md` header)
Date: 2026-10-30
Deciders: repository owner (decision 1 of `module-designs/OWNER-DECISIONS-2026-10-30.md`); orchestrator (acceptance)
Brief sections: §8 (identity, permissions), §25.2, §25.5, §27
Amends: ADR-0009 §1 and the P1-I2b addendum (authorizer rule for listed `control.*` actions), ADR-0013 §1–§4 (the
document controller becomes a source of derived module roles), ADR-0010 addendum 2026-10-21 (`allowed_actions` holds
are scoped). Leaves ADR-0016 unchanged.

## Context
Phase 1 has three company-wide account roles (`admin`, `document_controller`, `user`) and one access word per command
(`user`, `controller`, `admin`, `company`). Phase 2 adds field work packaging, materials and requisitions, whose
controlling acts (IWP sign-off, issue to a foreman, inventory adjust, requisition approval) belong to different people
on different projects. One new company-wide role per module (the ADR-0013 mechanism) would multiply roles and still be
unable to say "Ana approves requisitions on P123 only". The owner decided an MVP: per module, three roles, granted per
project, with admin unchanged and the document controller mapped to `superuser` of documents, keeping a richer
project-role model possible by naming access words and keeping the role-to-word table as data.

## Decision
1. **Roles and words.** Each module has `viewer`, `user`, `superuser`. Commands keep their access word. The table
   `schema/settings/module-roles.yaml` maps roles to words (`viewer` → `read`; `user` → `read`, `user`;
   `superuser` → `read`, `user`, `controller`) and account roles to derived module roles. `admin` and `company` are
   platform words outside the table. A word or role the table does not know fails at start-up.
2. **Grants are account events.** `Account.ModuleRoleGranted` and `Account.ModuleRoleRevoked` on the account stream
   (internal, hidden and redacted as every account event), projected into `cur_account_module_role`. Only a human
   admin grants. Agents may hold `viewer` or `user` and still only propose.
3. **Resolution.** `tl_core.auth.module_roles.effective_roles(conn, holder, scope, module)`: admin → everything; at
   `company` scope → derived only; else explicit grants on `(project, module)`, then on `(project, "*")`, **replacing**
   the derived roles; else derived from the account roles (`user` → `user` everywhere; `document_controller` →
   `superuser` of documents, and, if the owner confirms, correspondence and schedule); else nothing. Service actors
   keep their declared access (ADR-0017 §7).
4. **One check, every entry point.** `require_command_access(conn, command, holder=...)` is called by the API command
   endpoint, the typed command runner, proposal accept, the CLI before every module handler call, and the embedded
   TUI client before every module handler call; `require_generic` checks the word `user` for module record types;
   `allowed_actions` passes module hooks a holds function scoped to the record's project and module. The
   `RoleAuthorizer` lets any non-agent principal with a role through a *listed* `control.*` action and the endpoint
   decides; an unlisted `control.*` action stays the admin's.
5. **No data migration.** Existing accounts derive their module roles from their account roles, so behaviour is
   unchanged until an admin grants. `document_controller` stays in `ROLES`.
6. **Confidentiality unchanged.** Clearance stays account-level (ADR-0016 §2); a module grant gives none.
7. **Reads unfiltered by module role** in this ADR. `read` is resolved and reported only.

## Consequences
- Contracts changed: `CommandSpec.module`, `ModuleSpec.command_words`, `require_generic(..., actor=)`,
  `RoleAuthorizer` semantics for listed `control.*` actions, `ClientInterface` gains five methods, `ApiClient.admin`
  four and `ApiClient.auth` one. New: `tl_core.auth.module_roles`, `module_grants`, the table file, two events, one
  projection, five routes, `tl admin roles`.
- CLI and embedded TUI: every module handler call is preceded by the gate (pinned by AST tests). A dev ledger file
  without a session passes the `user` word as today; `controller` still needs a session.
- Workflow `roles` guards are untouched; controlling acts stay commands with access words (R-P2-3).
- Error text: `<Name> needs the <word> access word for <module> on <project>` (403 `forbidden`).
- Gates: `schema/**` changes (human gate); security review of the wave covers every seam in spec §5.

## Alternatives considered
| Option | Why not |
|---|---|
| One company-wide role per module (ADR-0013 repeated) | Roles multiply; cannot scope to a project; the owner chose per-project grants |
| Role checks inside each module handler | Hundreds of call sites in module code; the entry points already decide access (ADR-0013 §4) |
| Data migration that writes grants for every existing account | Events for a derivation the table already expresses; derived roles cost nothing and can be overridden |
| Grants as project settings | Settings are not per account and are readable by every user; account events are already hidden |
| Module roles give `restricted` clearance | Changes ADR-0016, a separate human gate; left as owner Q2 |
| Filter reads by module role now | Touches every read path and the walking tests; belongs with the P3-I8 party scope |
