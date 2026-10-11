# Fanout plan: P1-I0 (authentication, admin module, Postgres for the services)

Status: active. Both workstreams start now from `p1/i0`.
Orchestrator session: 2026-10-11
Owner decisions: ADR-0008 (read it first). Brief sections: §18 (security), §11 (API, MCP), §10 (TUI), §16 Phase 1.

## Objective
Real sign-in replaces the ADR-0005 dev stub. It provides:
- username and password authentication behind an identity seam that Entra ID can replace later;
- two roles, `admin` and `user`;
- an admin module for accounts, roles and agent tokens, from the CLI, API and TUI;
- a `demo`/`demo` account seeded in dev and demo setups only;
- service tokens for MCP agents.

In parallel, the API server, the TUI and the operator commands run on Postgres as well as SQLite. GitHub Actions is deferred (ADR-0008 decision 9).

## Exit criteria
- [ ] **Contract.** The `tl_core/auth/types.py` contract is implemented. Passwords are hashed with a memory-hard KDF from the standard library (`hashlib.scrypt`) or from a permissively licensed dependency.
  - Sessions are opaque bearer tokens, stored hashed, with an expiry and a sign-out.
  - Lockout follows repeated failed sign-ins, with the same error for an unknown user and a wrong password.
  - No secret (password, hash, token) appears in the ledger, archive, lake, webhooks, logs or error text.
- [ ] **API.** The API has `POST /auth/sign-in`, `POST /auth/sign-out`, `GET /auth/me`, and `/admin/*` routes for accounts, roles, passwords and agent tokens.
  - Every route authorizes through the `Authorizer`. A `user` gets 403 `forbidden` on `admin.*`.
  - Agents keep 403 `agent_must_propose`.
  - The dev token file still works when `TL_ENV` is `dev` or `test`, so existing tests keep passing, and is refused when `TL_ENV=prod`.
- [ ] **TUI.** The TUI shows a sign-in screen, both embedded and remote, and an admin screen for admins only (accounts, roles, reset password, disable or enable, issue or revoke agent tokens).
- [ ] **CLI.** `tl login` and `tl logout` keep a session in a 0600 file under the user config directory. The admin commands are `tl admin user add|ls|roles|disable|enable|reset-password` and `tl admin token issue|ls|revoke`. `tl admin bootstrap` creates the first admin when none exists, locally only.
- [ ] **MCP.** The MCP server authenticates with an agent token (`TL_AGENT_TOKEN`) instead of `--actor`. The simulator provisions seeded `user:sim-*` accounts and an agent token for its assistant.
- [ ] **Demo account.** `demo`/`demo` (role `admin`, so the admin module can be shown) is created by `just seed` and `tl init --dev`. It is never created when `TL_ENV=prod`. A server bound to a non-loopback address refuses to start while it exists and is enabled. A warning is logged at start while it exists.
- [ ] **Postgres.** `tl serve`, `tl tui`, `tl webhook`, `tl lake`, `tl file` and the embedded feed accept a `postgresql://` URL wherever they accept a SQLite path, through one backend factory. Parity tests cover the new paths.
- [ ] **Demo.** `just demo P1-I0` covers the following, and passes on SQLite and on Postgres:
  - demo signs in (TUI headless and API) and creates a record;
  - a `user` is refused an admin action;
  - an admin creates a user and issues an agent token, and the agent proposes over MCP;
  - repeated bad passwords lock an account;
  - the demo account refuses a non-loopback bind.

## Workstreams
| WS | Name | Branch · worktree | Base | Supervisor builds | Implementer tickets (summary) |
|---|---|---|---|---|---|
| A | Identity and admin | `p1/i0a` · `/home/user/wt/p1-i0a` | `p1/i0` | T01 auth ADR (hashing, session format, lockout policy, password policy, Entra seam, threat model); T02 account store, hashing, sessions, lockout, Authorizer, admin services, operational tables | T03 API auth and admin routes plus error rows; T04 TUI sign-in and admin screen, CLI `tl login` and `tl admin`; T05 MCP agent tokens and simulator accounts; demo |
| B | Postgres for the services | `p1/i0b` · `/home/user/wt/p1-i0b` | `p1/i0` | one backend factory from a URL or path (`open_backend`), and the server and embedded feed wiring | each CLI group and the TUI on the factory; parity tests; runbook updates |

## Shared contracts
- `packages/tl-core/src/tl_core/auth/types.py` (A).
- B does not touch auth. A does not touch backend selection. Both edit `tl_api/main.py` and `tl_cli/main.py`; B merges after A and resolves the conflicts.

## Orchestrator decisions
| # | Decision |
|---|---|
| D1 | The ledger records accounts and token metadata as events. All secrets live in operational tables excluded from archive, lake and webhooks. A restore from archive therefore restores accounts without passwords: they get a forced reset, the same rule as webhook secrets after a restore. |
| D2 | The `guard()` seam stays. Its token lookup becomes `IdentityProvider.principal_for_bearer`, and `authorize` becomes the `Authorizer`. The route signatures do not change. |
| D3 | The embedded TUI signs in against the local account store. The trust boundary in embedded mode is file access to the database, and the docs say so. |
| D4 | The last active admin cannot be disabled or demoted (`last_admin`). |
| D5 | Prefer no new dependency. If one is needed (for example argon2-cffi, MIT), name its licence; the licence gate decides. |
| D6 | Every review of A's supervisor pieces is a security review in fresh context: credential handling, timing-safe comparisons, enumeration, lockout bypass, token entropy and storage, secret leakage. |

## Merge order and conflict owner
A then B. B writes nothing in the demo. A writes `dev/demos/P1-I0.sh` and `docs/reports/P1-I0.md` after B merges, so the demo can run on Postgres. Merge commits only.

## Human gates
All delegated under ADR-0008 decision 6. Log each auth design approval in APPROVALS.md.
