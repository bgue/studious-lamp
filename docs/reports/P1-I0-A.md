# Report — P1-I0 workstream A: Identity and admin

Branch `p1/i0a` (base `p1/i0`), supervisor session 2026-10-11. Plan: `docs/tickets/P1-I0/README-A.md`. Design: `docs/adr/0009-authentication.md` (accepted). Operations: `docs/runbooks/accounts-and-access.md`.

## Outcome
Objective met: yes for workstream A. Real sign-in replaces the ADR-0005 dev stub in the library, API, CLI, TUI and MCP: accounts, two roles (`admin`, `user`), sessions, lockout, admin-issued agent tokens, an identity seam for Entra ID. The dev token file survives only where `TL_ENV` is dev, test or ci. The demo (`dev/demos/P1-I0.sh`) and the increment report are written after workstream B merges (they need the combined branch); they are not part of this report.

## Tickets
| ID | Outcome | Review rounds | Notes |
|---|---|---|---|
| S1 (ADR-0009) | merged, accepted | 3 (two changes-requested, then pass) | design: scrypt, token formats, lockout, enumeration, restore, threat model |
| S2a (`schema/core/auth.yaml`) | merged | with S2b | two projections, four operational tables, seven events; schema approvals logged by the orchestrator |
| S2b, S2c (`tl_core.auth`, `guard()`) | merged | 3 | F1 to F8 are the review fixes: recovery from a held lock, demo gating, hashing outside write transactions, hidden account events, dirty input, a reserved hash slot, closed filters, lake redaction, the per-source limiter, Postgres pool guard |
| T03 `/auth/*` routes and client | merged (cdce513) | 1 | |
| T04 `/admin/*` routes and client | merged (634fe01) | 1 | first run blocked on T03 (L-P1-I0A-11); tests run on both adapters (S8) |
| T05 server start rules, hidden account events | abandoned | n/a | done by the supervisor in F3 |
| S3, S4 (CLI session, TUI client admin calls, authenticators) | merged | 2 | review: one MEDIUM (`--actor` bypassed sign-in) and five LOW, all fixed in S12 |
| T06 `tl login`, `logout`, `whoami` | merged (cf05a90) | 1 | first run blocked by a red base (L-P1-I0A-19) |
| T07 `tl admin user ...`, `tl admin token ...` | merged (7a44abd) | 1 | supervisor change: `--days` defaults to none and is refused with `--no-expiry` |
| T08 TUI sign-in screen | merged (9dfa978) | 1 | first run blocked by my provided test (pyright; L-P1-I0A-21) |
| T09 TUI accounts screen (`F10`) | merged (0ed4d44) | 1 | |
| T09b TUI forms: add, password, issue and revoke a token | merged (dd114f1) | 1 | split from T09 (Haiku-ability) |
| T10 MCP `TL_AGENT_TOKEN`, checked on every call | built by the supervisor | 1 (pass, four LOW fixed in S19) | explicit MCP action allow-list |
| T11 simulator: agent token on the dev ledger | built by the supervisor | 1 (pass) | `just seed` end to end: 530 checks |
| T12 projection parity on both adapters | built by the supervisor | with T10 | |

No ticket was taken over after two failed reviews. Every Haiku ticket passed its review on the first attempt once its block (a red base or a defect in a provided test, both mine) was removed.

## Gates (final tree, `p1/i0a`)
| Gate | Result |
|---|---|
| `just check` | clean |
| `just test` (run in shards: tl-cli, tl-sim, tl-mcp / tl-tui / tl-api / tl-core, tl-adapters, tl-lake, tl-schema and `tests/`) | 1223 + 704 (34 snapshots) + 532 + 3482 passed, 0 failed |
| `just test-tui` | 704 passed, 34 snapshots |
| `just test-parity` | see the relay NOTE (run on the final tree) |
| Security reviews (fresh context) | D6 (S2b, S2c) three rounds; S3, S4 and the sign-in wiring (changes requested, fixed, re-review); T10 to T12 (pass) |

## Deviations from plan
- T05 was absorbed into F3. T10 to T12 were built by the supervisor instead of Haiku tickets: T10 and T11 are auth and provisioning code, T12 is a parity test.
- T09 was split into T09 and T09b. S5b to S19 are supervisor commits that were not in the first plan (review fixes, base repairs, layout for T09b).
- Four supervisor mistakes cost an implementer round each; all are in `docs/memory/LEARNINGS.md`: the T04 dependency (L-P1-I0A-11), the T03 client steps (12), a red base (19) and a provided test that failed pyright (21).

## Escalations and decisions
- ADR-0009 section 7 amended twice by ruling: the CLI and TUI sessions; and the rule that an explicit `--actor` is honoured only for the session's own actor, or in a dev, test or ci setup on a ledger file (a `scheme://` target always needs a session).
- Rulings applied: the per-source limiter, the MEDIUM `--actor` rule, `--days`/`--no-expiry`, the MCP allow-list, the rotating token set of the simulator.
- Workstream B interface: `tl_cli.session.is_local_target` and `current_principal` assume a ledger file; when B's `tl_adapters.db.is_postgres` and `as_target` merge, switch the predicate and give sessions a key for URL targets. `tl_cli/main.py`, `tl_api/main.py` and `justfile` are touched by both workstreams.

## Learnings
`L-P1-I0A-1` to `L-P1-I0A-22` (security, process, tooling). Implementer proposals declined: none.

## Docs
- ADR: `docs/adr/0009-authentication.md`. Runbooks: `docs/runbooks/accounts-and-access.md` (new), `docs/runbooks/lake-sync.md`, `docs/runbooks/tui-dev.md`, `docs/runbooks/README.md`.
- Package READMEs and AGENTS.md: tl-core, tl-api, tl-cli, tl-tui, tl-mcp, tl-sim, tl-adapters (AGENTS only); root `AGENTS.md`.
- Ticket reports: `docs/reports/P1-I0/P1-I0-T03.md` and T04, T06 to T09b.

## Follow-ups filed
- After B merges: the demo `dev/demos/P1-I0.sh`, the increment report `docs/reports/P1-I0.md`, the `is_local_target` switch above.
- Not built, by decision: Entra ID (the seam is `IdentityProvider`), per-record permissions, a front-door rate limiter (a release gate in the runbook), password change in the TUI.

## Cost notes
Implementer runs: 8 tickets, 10 attempts (two re-runs after a base or provided-test defect). Reviewer runs: 4 security reviews and 8 ticket reviews.
