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
| F5 to F7 | Re-review fixes: dirty text in services, audit keys and counts, reserved hash slot, closed default filters, lake redaction without counts, the per-source sign-in limiter (`tl_api.ratelimit`), the runbook `accounts-and-access.md`, ADR-0009 accepted | Auth and permission code | same reviewer | done, awaiting final re-review |
| S8 | The admin API tests run on both adapters (`Harness.build(target=...)`, `parity_harness`); T04 report refreshed | Test infrastructure | — | done |
| F8 | Final re-review fixes: last header line and IPv6 /64 for the sign-in limiter, validation of the last three id and event inputs, a Postgres connection that saw an unencodable parameter is dropped, runbook and ADR notes | Auth and permission code | final re-review passed; these are its follow-ups | done |
| S11 | Base-red fixes: `tl tui` test expects `signed_in`, key map context Accounts, palette snapshot with F10 | Test upkeep | — | done |
| S12 | Security review of S3, S4 and 045c46e (changes requested, one MEDIUM): `--actor` checked on every value and by target (file versus server), exact admin gate, locked session file, OS user in the recovery audit, remote session ended on exit, plain-http warning; ADR-0009 section 7 states the rule | Auth and permission code | short re-review | done, awaiting re-review |
| S3 | CLI session module: private session file (0600), default `--actor` from the session (`user:dev` only in dev, test or ci), `tl init --dev`, `tl admin bootstrap\|unlock\|audit`; embedded only | Credential handling | fresh-context security review | done, awaiting review |
| S4 | TUI client: the ten admin calls on `ClientInterface`, the embedded implementation with its admin gate, `FakeClient` with a parity test, `EmbeddedAuthenticator` and `RemoteAuthenticator`, `main.py` sign-in flow, `F10` | Public interface; credential handling | fresh-context security review of the gate and the authenticators | done, awaiting review |
| S9 | Runbook `docs/runbooks/accounts-and-access.md` (written; to verify against the real commands), package READMEs and AGENTS.md, learnings | Docs definition of done | — | planned |

## Tickets
| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| P1-I0-T03 | `/auth/*` routes (sign-in, sign-out, me, own password) and API client methods | haiku | S2, F1 to F3 | merged (cdce513) | passed review first time; the ticket's client STEPS were the server's (L-P1-I0A-12) |
| P1-I0-T04 | `/admin/*` routes (accounts, roles, disable and enable, reset password, agent tokens) and API client methods | haiku | S2, F1 to F3, T03 | merged (634fe01) | first run blocked on T03 and a 101-column docstring (L-P1-I0A-11); passed review; the admin tests run on both adapters since S8 |
| P1-I0-T05 | (absorbed into F3: server start rules for the demo account, hidden account events) | — | — | abandoned | done by the supervisor in F3 |
| P1-I0-T06 | CLI `tl login`, `tl logout`, `tl whoami`; the default actor of every command follows the session (the hook is S3's) | haiku | S3 | merged | passed review first time | first run BLOCKED by a red base (L-P1-I0A-19), not by the ticket |
| P1-I0-T07 | CLI `tl admin user ls\|show\|add\|roles\|disable\|enable\|reset-password` and `tl admin token ls\|issue\|revoke` (the recovery commands `bootstrap`, `unlock`, `audit` and `tl init --dev` were built by the supervisor in S3: they must work with no admin signed in) | haiku | S3 | merged | passed review; supervisor change: `--days` default none, refused with `--no-expiry` | first run BLOCKED by the red base; supervisor change: `--days` default none, refused with `--no-expiry` |
| P1-I0-T08 | TUI sign-in screen (`SignInScreen`, `SignInApp`); the authenticators and `main.py` flow are S4 | haiku | T03, S4 | ready | |
| P1-I0-T09 | TUI accounts screen on `F10`: list, detail, disable and enable, admin role, agent token list; snapshots | haiku | T04, S4 | ready | |
| P1-I0-T09b | TUI forms on the accounts screen: add an account, reset a password, issue a token (shown once), revoke a token | haiku | T09 | planned (written after T09 merges) | split from T09 (Haiku-ability: more than five files and 400 lines) |
| P1-I0-T10 | MCP authenticates by `TL_AGENT_TOKEN`; `--actor` removed | haiku | S2 | planned | |
| P1-I0-T11 | Simulator: seeded `user:sim-*` accounts and the assistant's agent token; `just seed` seeds `demo` | haiku | T10 | planned | |
| P1-I0-T12 | Parity tests for the account projections on both adapters | supervisor | S2 | planned | |

## Haiku-ability check (01-tiers section 6) for T06 to T09
| Ticket | Files read | Interfaces in repo | Test file or acceptance | Diff | Sonnet-authored table | Schema, deps, public interface | Verifiable from the diff |
|---|---|---|---|---|---|---|---|
| T06 | 6 | yes (S3) | 20 cases provided | 1 module of about 60 lines, 1 test copy, report | glue over supervisor-built credential code (reviewer checks secrets first) | none | yes |
| T07 | 6 | yes (S3, `tl_core.auth`) | 47 cases provided | 2 modules of about 250 lines, 2 test copies, report | same | none | yes |
| T08 | 4 | yes (S4: authenticators, `main.py`) | 14 cases and 2 snapshots provided | 4 bodies of about 25 lines, 1 test copy, 2 snapshots, report | none | none (the layout is final in the stub) | yes |
| T09 | 5 | yes (S4: client calls, fake, `F10`) | 22 cases and 3 snapshots provided | 2 modules of about 150 lines, 2 test copies, 3 snapshots, report | none | none | yes |
All four were verified against an out-of-repo reference implementation (all provided tests pass) and mutation-checked (a dozen
deliberate faults per ticket, each caught by a provided test). T09 was split: forms for adding accounts, resetting passwords and
issuing or revoking tokens are T09b, because the whole would have changed more than five files and 400 lines.

## Held until a dependency merges
- `test_f10_opens_the_accounts_screen_for_an_admin` (F10 pushes `AdminScreen`) is added to `packages/tl-tui/tests/test_app_admin.py`
  after T09 merges (the text is in `docs/tickets/P1-I0/held/test_f10_opens.py.txt`): with the stub in place it would fail (L-P1-I0A-11 applied to supervisor tests too).

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
