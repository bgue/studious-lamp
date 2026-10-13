# ADR-0013 — Document controller role

Status: accepted 2026-10-13 (owner request, recorded by the orchestrator; drafted by the P1-I2b supervisor). It supersedes the interim access table of ADR-0011 and amends ADR-0008 decision 3 from two roles to three. The security review of the commits listed in the P1-I2b report is pending.
Date: 2026-10-13
Deciders: repository owner ("make a doc controller role to wrap Phase 1", 2026-10-13), recorded by the orchestrator; supervisor draft
Brief sections: §8 (identity and auth), §9 M1, §25.2, §27

## Context
ADR-0008 decision 3 gave Phase 1 two roles, `admin` and `user`. ADR-0011 then made the controlling acts of document control (issuing, superseding, voiding, signed copies, transmittals, the two review corrections) the admin's, "until a document controller role exists". The cost it named was a team with many controllers waiting on the role: the only way to let someone issue a revision was to make them an admin, which also gave them accounts, roles, tokens and the engineering registry.

The owner asked for that role to close Phase 1. `packages/tl-core/src/tl_core/auth/types.py` was frozen for P1-I0; it changes here by that request.

## Decision

### 1. Three roles
`Role` is `admin`, `user` or `document_controller`. An account's roles are a list, stored in alphabetical order (the projection's order). A person may hold `user` and `document_controller`; the role may also stand alone, in which case the person has every `user` right as well (the authorizer opens everything outside `admin.*` and `control.*` to any account that has a role).

| Role | May |
|---|---|
| `user` | Everything except `admin.*` and `control.*` |
| `document_controller` | Everything a `user` may, and the controlling acts (section 2). Nothing under `admin.*` |
| `admin` | Everything, the controlling acts included |

The controller is **not an admin**: no accounts, roles, tokens, settings locks or engineering registry, and it has no part in the last-admin rule (`is_admin` and the active-admin count ignore the role).

### 2. The controlling acts move from `admin` to `controller`
The commands of ADR-0011's left column are `controller` commands, gated by the action `control.command.<Name>` in the API and by `require_controller` in the CLI:

`IssueRevision`, `SupersedeRevision`, `SupersedeDocument`, `VoidDocument`, `SetDocumentConfidentiality`, `RegisterSignedRendition`, `ReplaceSignedRendition`, `IssueTransmittal`, `RecordReviewOutcomeOnBehalf`, `OverrideReviewOutcome`, and `tl doc import --apply` (a bulk registration into the controlled register; the preview stays open to any signed-in person).

Everything else in ADR-0011 stands: the right column is open to any signed-in person, a reviewer answers for themselves, a signed copy is write-once for everyone but a controller, the system link sources cannot be claimed over the API, and `tests/` pins the table (`packages/tl-api/tests/test_api_documents.py`, `EXPECTED_ACCESS`, now `user` or `controller`).

### 3. What stays the admin's
| Stays admin | Why |
|---|---|
| `AdminFlagLink`, `AdminRetractLink` (link recovery) | They reach any link, including core and engineering links and links a module wrote by rule. That is repair of the ledger's graph, not document control. |
| `RecordTag`, `tl tag import --apply`, `tl tag create --allow-violation`, the registry commands (`RegisterCodeList`, `RegisterMnemonic`, `RegisterNumberingPattern`, `CloseStandard`, `DefineTagClass`, `ReviseTagClass`, `CloseTagClass`), `tl standards load` and the standards CLI gates | The engineering registry and the tag list are not document control (ADR-0010 addendum). The document numbering pattern is registry data too. |
| Everything under `admin.*`: accounts, roles, passwords, tokens | Granting the role is an admin's act. A controller cannot change any role, her own included. |

### 4. Mechanism (allow-list, typed, closed)
- **API.** `CommandSpec.access` is `Literal["admin", "controller", "company", "user"]` (the documents module's `Access` is `admin`, `controller` or `user`), so a typo is a type error. The action of a `controller` command is `control.command.<Name>`.
- **Authorizer.** `RoleAuthorizer.authorize` refuses a `control.*` action to an agent always; allows it to an admin; and allows it to a `document_controller` only when the action is in `controller_actions`, the exact set the API builds from its command table (`tl_api.commands.controller_actions()`, passed in `create_app`). The default set is empty. A `control.*` action that nobody listed (a typo, a new name) is therefore an admin's: it can only fail closed. The prefix has no "open to controllers" meaning on its own. A test pins the ten actions and a second proves that listing a non-`control.` name opens nothing.
- **CLI.** `tl_cli.session.require_controller(db)` is `require_session` plus `principal.is_controller` (an admin or a `document_controller`, never an agent). It replaces `require_admin` at the eleven sites (a test counts them). Like `require_admin` it checks the session's principal, not `--actor`.
- **TUI.** The accounts screen (admin only) has key `c` to give or take away the role (`r` keeps the other roles when it toggles `admin`), and the add-account form has a box for it. The document register passes `is_controller` (an admin or a controller) to the transmittal composer, which then offers `Ctrl+T` (draft and issue). The embedded client enforces the same gate as the server (`_controller_gate`: the actor must be the active account's own actor with one of the two roles); the remote client calls `POST /commands/IssueTransmittal`, which the server decides. The TUI never decides; hiding a key is a convenience.
- **Principal.** `Principal.is_controller` is true for an admin or a `document_controller` whose kind is not `agent`.

### 5. Who may hold the role
- An `agent` account can never hold `document_controller` (refused with `InvalidAccountError`, like `admin`); agents stay propose-only, and neither `AGENT_ACTIONS` nor `MCP_ACTIONS` may contain a `control.*` action (a test pins it).
- A `person` or a `sim` account may hold it. (Only `person` may hold `admin`.)
- Only an admin grants it: `PUT /admin/accounts/{id}/roles` (`admin.accounts.roles`), `tl admin user roles NAME --add document_controller [--reason ...]`, or the accounts screen. `tl admin user roles` also takes `--remove` and keeps `--role` (replace); `--role` and `--add/--remove` are exclusive.
- The grant is an `Account.RolesSet` event with the admin as actor and the reason. Account events stay internal: hidden from `/events` and `/stream` for everyone but a human admin, redacted in the lake, never delivered to webhooks (ADR-0009 section 1). Nothing about them changes.

## Consequences
- **Contracts changed.** `Role` and `ROLES` in `tl_core/auth/types.py` (frozen for P1-I0; changed here by owner request), `Principal.is_controller`, `CONTROL_ACTION_PREFIX`; `RoleAuthorizer(controller_actions=...)`; `Access` in `tl_api.commands` and in `tl_mod_documents.commands`; `ClientInterface.issue_transmittal` (TUI) and `DocumentsApi.issue_transmittal`. `schema/core/auth.yaml`: the `AccountRole` enum gains `document_controller` and two descriptions change (documentation only: `roles` is a JSON list of any strings; regenerated models and JSON schema, no DDL, no event shape, no migration).
- **ADR-0008 decision 3** now reads "three roles". **ADR-0009** sections 1 and 5 and the threat model's privilege row read with the third role; its rules are unchanged. **ADR-0011** keeps its context, the right column, the review rules and the known limits; its left column and the sentence "until a document controller role exists" are replaced by section 2 above.
- **Existing data.** None to migrate: `roles_json` is free text, an older role list stays valid, and no account holds the new role until an admin grants it. Admin behaviour is unchanged: an admin passes every controller check.
- **Error text.** The user-visible refusal changes from "needs the admin role" to "needs the document_controller or admin role" (CLI) and `control.command.<Name> needs the admin or document_controller role` (API 403 `forbidden`). Review-rule messages say "document controller".
- **Simulator.** Simulated people sign in with dev tokens, which carry the `user` role only (ADR-0009 section 9), so the simulator still registers and drafts but does not issue. Letting a simulated person issue needs either roles read from the account for a dev token (a change to ADR-0009 section 9) or a session sign-in for one identity; both are the orchestrator's call and are left as a follow-up. `just demo P1-I2b` exercises the role with real accounts instead.
- **Gates affected.** None. The security review that follows covers the commits that change roles, the authorizer, access levels and CLI gates (listed in the report).

## Known limits (Phase 1)
- **The role is company-wide.** There is no project-level assignment; a controller controls every project of the ledger. Entra groups (brief §27) can add that later without changing the commands: the gate is still one word per command.
- **No separation of duties.** A controller may issue a revision she drafted and may record or override review answers; ADR-0011 gave the same power to an admin. The events name who did it (`recorded_by`, the actor).
- **A controller may import.** `tl doc import --apply` registers documents only; it cannot issue, supersede or void. It was an admin's act in ADR-0011 because it was a bulk write; it is the controller's now because it is the document register.
- **`--actor` in a dev setup.** On a ledger file where `TL_ENV` is dev, test or ci the CLI still honours any `--actor` (the file's owner can write the file anyway, ADR-0009 section 7); `require_controller` checks the session's principal, as `require_admin` does.
- **The writer lock** still serialises two controllers issuing the same revision (ADR-0011).

## Alternatives considered
| Option | Why not |
|---|---|
| Keep the controlling acts admin-only | The owner asked for the role; the admin role is too wide to hand to a document controller |
| A prefix rule: every `control.*` action is open to a `document_controller` | A typo or a command added later would be opened to the role without anyone listing it; the explicit set built from the typed table fails closed |
| Make `document_controller` imply `user` in storage (always store both) | Hides a state the admin chose; the authorizer already treats any role as a person's right to the `user` actions |
| Let the controller also flag and retract links (`AdminFlagLink`, `AdminRetractLink`) | They repair any link, not only document links; widening them is a separate decision |
| Move the tag registry to the controller | The engineering registry is not document control; the owner's request is about documents |
| A project-level assignment of the role | No per-project role model in Phase 1 (ADR-0008 decision 3); left to the SSO increment |
| Read a dev token's roles from its account so the simulator can issue | Changes ADR-0009 section 9 (dev tokens are never more than `user`) and adds a privilege path from the token file; not decided here |
