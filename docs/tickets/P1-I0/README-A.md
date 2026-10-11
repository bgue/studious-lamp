# Increment plan — P1-I0 workstream A: Identity and admin

Status: in-progress
Supervisor session: 2026-10-11
Brief sections: §8 (identity and auth), §11.1 (auth), §11.3 (MCP), §18.12, §18.13, §10 (TUI)
Branch: `p1/i0a` (base `p1/i0`; fanout plan `FANOUT.md`; owner decisions ADR-0008; design ADR-0009)

## Objective
Real sign-in replaces the ADR-0005 dev stub. Accounts, two roles (`admin`, `user`), sessions, lockout and admin-issued agent
tokens live behind an identity seam that Entra ID can replace. The admin module is reachable from the API, the CLI and the TUI.
The seeded `demo`/`demo` admin exists in dev and demo setups only. MCP agents authenticate with `TL_AGENT_TOKEN`. Secrets
never enter the ledger, the archive, the lake or webhooks. Workstream B (Postgres for the services) works in parallel and owns
backend selection; this workstream does not touch backend factories.

## Demo
Written after workstream B merges, so it can run on SQLite and on Postgres: `just demo P1-I0` (`dev/demos/P1-I0.sh`).
It shows `demo` signing in to the TUI (headless) and the API and creating a record, a `user` refused an admin action, an admin
creating a user and issuing an agent token that proposes over MCP, repeated bad passwords locking an account, and the demo
account refusing a non-loopback bind.

## Supervisor-built pieces (in order)
| # | Piece | Why supervisor-tier | Reviewer | Status |
|---|---|---|---|---|
| S1 (T01) | ADR-0009: KDF, token formats, lockout, password policy, enumeration, Entra seam, restore, threat model | Auth design (§25.5) | orchestrator approves | done, awaiting approval |
| S2a | `schema/core/auth.yaml`: two projections, four operational tables, seven catalogued events; generated artefacts | Schema (`schema/**` approval) | orchestrator | done, awaiting approval |
| S2b (T02) | `tl_core.auth`: scrypt and policy, sessions, lockout, accounts, agent tokens, `PasswordIdentityProvider`, `RoleAuthorizer`, `seed_demo`, `bootstrap_admin`; account events kept out of the feed and webhooks; restore warning; credential tables denied to the dev MCP | Auth and permission code | fresh-context security review (D6) | done, awaiting review |
| S2c | `guard()` resolves a principal and runs the Authorizer; dev tokens only when `TL_ENV` is dev, test or ci; error rows | Auth and permission code | fresh-context security review (D6) | done, awaiting review |
| F1 to F3 | Fixes from the D6 review of S2b and S2c (eight items: recovery from a held lock and the audit table, demo outside dev, hashing outside write transactions, stream re-check, hidden account events, NUL and surrogate input, blocklist, hardening) | Auth and permission code | same reviewer re-reviews | done, awaiting re-review |
| S3 | CLI session module: session file (0600), `default_actor()`, remote or embedded sign-in | Credential handling | fresh-context security review | planned |
| S4 | Runbook `docs/runbooks/accounts-and-access.md`, package READMEs and AGENTS.md, learnings | Docs definition of done | — | planned |

## Tickets
| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| P1-I0-T03 | `/auth/*` routes (sign-in, sign-out, me, own password) and API client methods | haiku | S2, F1 to F3 | ready (`T03-api-auth.md`, 31 + 10 cases) | |
| P1-I0-T04 | `/admin/*` routes (accounts, roles, disable and enable, reset password, agent tokens) and API client methods | haiku | S2, F1 to F3 | ready (`T04-api-admin.md`, 39 + 6 cases) | |
| P1-I0-T05 | (absorbed into F3: server start rules for the demo account, hidden account events) | — | — | abandoned | done by the supervisor in F3 |
| P1-I0-T06 | CLI `tl login`, `tl logout`, `tl whoami`; the default actor of every command follows the session | haiku | S3 | planned | |
| P1-I0-T07 | CLI `tl admin user ...`, `tl admin token ...`, `tl admin bootstrap` (resets and unlocks an existing admin), `tl admin unlock`, `tl admin audit`; `tl init --dev` seeds `demo` | haiku | S3 | planned | |
| P1-I0-T08 | TUI sign-in screen, embedded and remote | haiku | T03 | planned | |
| P1-I0-T09 | TUI admin screen (accounts, roles, reset, disable and enable, agent tokens) with snapshots | haiku | T04, T08 | planned | |
| P1-I0-T10 | MCP authenticates by `TL_AGENT_TOKEN`; `--actor` removed | haiku | S2 | planned | |
| P1-I0-T11 | Simulator: seeded `user:sim-*` accounts and the assistant's agent token; `just seed` seeds `demo` | haiku | T10 | planned | |
| P1-I0-T12 | Parity tests for the account projections on both adapters | supervisor | S2 | planned | |

## Order of work
1. S1, S2 now; request the security review of both (D6) before any ticket is built on them.
2. Batches of at most two tickets (usage limits, L-P0-I8-O1): T03 and T04, then T05 and S3 work, T06 and T07, T08 and T09, T10 and T11.
3. Merge only on a `pass` verdict; the supervisor takes over a ticket after two review failures.
4. Docs, learnings, the demo and the report after workstream B has merged.

## Risks and escalation triggers
- The auth ADR and the security review may change the token formats or the lockout rules; tickets quote the code, so they are built after the review.
- `tl_api/main.py` and `tl_cli/main.py` are edited by both workstreams; B merges after A and resolves the conflicts.
- The embedded CLI and TUI trust the file owner (D3); the runbook and ADR say so.
- Escalate if the contract in `tl_core/auth/types.py` has to change, or the same engine fails its gates twice.

## Blocked / Decision
(none)
