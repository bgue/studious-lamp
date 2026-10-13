# Increment plan — P1-I2b Document controller role

Status: in-progress
Supervisor session: 2026-10-13
Brief sections: §8 (identity and auth), §9 M1, §25.2, §27
Branch: `p1/i2b` (from trunk `claude/wizardly-allen-m2v96s` at f0cc848)

## Objective
Owner request (2026-10-13): "make a doc controller role to wrap Phase 1". Add a third role, `document_controller`, that holds
the controlling acts of document control without being an admin. ADR-0013 records the decision, supersedes ADR-0011's
interim access table (the controlling acts were the admin's "until a document controller role exists") and amends
ADR-0008 decision 3 from two roles to three. The admin keeps every right; an agent can never hold the role and stays
propose-only; the engineering registry, link recovery and everything under `admin.*` stay the admin's.

The increment is small and security-sensitive, so the supervisor built all of it and relayed no implementer tickets.

## Demo
`just demo P1-I2b` (SQLite and Postgres), seven clauses:
1. a plain user prepares a revision and is refused issue and import `--apply`;
2. an admin grants `document_controller` (`tl admin user roles dora --add document_controller`); the event names the admin and the reason;
3. the controller issues the revision and a transmittal and applies an import with no admin session; the ledger names her;
4. the controller cannot list accounts, create one, change a role (hers included) or list tokens; an agent cannot hold the role;
5. the HTTP matrix of user, controller, admin and agent over the ten controlling commands, then the admin routes and link recovery for the controller;
6. the TUI: the accounts screen offers the role (`c`); the transmittal composer issues for a controller (`Ctrl+T`) and refuses a user;
7. the admin takes the role away and she is refused again; `demo` / `demo` still works.

`just demo P1-I2` still passes (its refusal text changed from "needs the admin role" to "needs the document_controller or admin role").

## Supervisor-built pieces (in order)
| # | Piece | Why supervisor-tier | Reviewer | Status |
|---|---|---|---|---|
| S1 | ADR-0013; notes in ADR-0008, 0009 (addendum), 0011; this plan | Auth and permission design (owner request) | orchestrator | done |
| S2 | Core: `Role`, `ROLES`, `Principal.is_controller`, `CONTROL_ACTION_PREFIX`, `RoleAuthorizer(controller_actions)`, agent and kind rules in `accounts`, `AccountRole` enum in `schema/core/auth.yaml` and `just gen` | Auth code (root rule: never a Haiku ticket); changes the frozen contract by owner request | security review | done |
| S3 | API: `controller` access level and `control.command.<Name>` action, `controller_actions()` into `create_app`, the ten documents commands, role list size in the admin routes; refusal wording in the module; tests (EXPECTED_ACCESS, HTTP matrix, admin routes, agent walk) | Auth and permission | security review | done |
| S4 | CLI: `require_controller` at eleven sites, `tl admin user roles --add/--remove`; tests for each site on both adapters | Auth and permission | security review | done |
| S5 | TUI: role key and form box, `is_controller` through the app, `Ctrl+T` draft and issue, embedded `_controller_gate`, `issue_transmittal` on the clients; tests and snapshots | Auth and permission (embedded gate) | security review | done |
| S6 | HTTP matrix of the role on both adapters (`test_api_document_controller.py`) | Auth tests | security review | done |
| S7 | Demo `dev/demos/P1-I2b.sh` and its driver; the P1-I2 demo text | Demo | orchestrator | done |
| S8 | Docs: runbooks (accounts-and-access, documents), module page, package READMEs and AGENTS.md, OpenAPI reference, LEARNINGS, APPROVALS lines | Docs | orchestrator | done |
| S9 | The documents module tests follow the new refusal wording (found by the full `just test`) | Tests | security review | done |
| S10 | Report `docs/reports/P1-I2b.md` | Report | orchestrator | done |
| S11 | Review fixes LOW-1 to LOW-4 (embedded gate tests and actor check, `action_for` fails closed, `expected_roles` against a stale role write) and two ADR tidies | Auth | security review | done |
| S12 | Report updated with the follow-up and the final gates | Report | orchestrator | done |

## Tickets
None. No piece was large and specifiable enough to pay for the ticket overhead: the pieces share one rule (who may call what) and each is a few dozen lines plus tests.

## Order of work
1. ADR and plan, then the core (everything else imports `Role`).
2. API, then CLI and TUI (independent of each other).
3. Demo, docs, report.
4. Gates on the final tree, alone: `just check`, `just test`, `just test-tui`, `just test-parity` (background, log file, L-P1-I1-10), both demos.

## Risks and escalation triggers
- A control action that is not in the controller list must fail closed (admin only): pinned by tests of the authorizer, the table and the HTTP matrix.
- The simulator's people keep the `user` role (dev tokens, ADR-0009 section 9), so the simulator does not issue. Giving them the role changes ADR-0009 section 9; not done, recorded in ADR-0013 and the report.
- A refusal text is pinned in tests and in the P1-I2 demo script; changing it means grepping `dev/demos` too.

## Blocked / Decision
None. Owner request recorded in ADR-0013.
