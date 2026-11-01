# P2-WEB1 — Web client, increment 1: RFI, correspondence and document logs, record screen, full PDF preview

Status: in-progress (round 1). Plan: `docs/build-spec/specs/web-client-i1.md` (the spec; wins over this file), placement in
`docs/build-spec/specs/phase2-wave-plan.md` §2. Owner decisions 3 and 7–9: `docs/build-spec/module-designs/OWNER-DECISIONS-2026-10-30.md`.
Board and next steps: `STATE.md`. Trunk at start: `claude/wizardly-allen-m2v96s` @1b93a13 (P2-W0 merged, roles in `allowed_actions` and `run_command`).

## Objective
A person signs in at `/web/sign-in` on the server that already serves the API, opens the RFI, correspondence or document log
of a project, selects a row, sees the terminal's panel and offered actions, runs an offered action, opens the record screen
and reads any PDF in full in the browser. Increment 1 is view and act: no create forms. Pages are server-rendered from the
JSON routes' own functions and the terminal's pure text modules; the session token stays in an `HttpOnly` cookie. The web is
off in production until its security review passes (`TL_WEB`, owner answer 8). Browsers: current and previous Chrome, Edge,
Firefox, Safari (answer 9).

## Demo
`just demo P2-WEB1`: five clauses, spec §12 (`dev/demos/P2-WEB1.sh`, ticket T08). `just tour` is not used (no terminal change).

## Order of work
Process: tests deferred to one tests piece at C3 (owner policy); every piece and ticket leaves an acceptance script
`dev/accept/P2-WEB1/<id>.py` instead of the spec's "Tests added" files, which the tests piece S5 writes. One security review
at C4 (spec §11 Sec rows S1–S3, plus the offered-now check that moved to S4, D3). Haiku for every ticket passing `01-tiers.md` §6.
Registries (`tl_api/{auth,app,commands}.py`, root `pyproject.toml`, `uv.lock`, `openapi.json`): S1 and S2 merge first;
the later side regenerates, never hand-merges.

| Checkpoint | Meaning |
|---|---|
| C1 | S1 foundation, S2 runner, S3 server page 1 merged (sign-in works, shared runner, page-1 route) |
| C2 | S4 merged (reads, log standard, actions, RFI log) |
| C3 | T01–T05 merged; S5 tests piece merged and run |
| C4 | T06–T08 merged, full gate, demo, security review of S1–S4 |

## Pieces and tickets (file names)
| Spec id | File | Kind / review | Round |
|---|---|---|---|
| S1 foundation | `S1-foundation.md` | piece | 1 |
| S2 shared runner, `action_ui` (web `actions.py` moved to S4, D3) | `S2-run-command-action-ui.md` | piece | 1 |
| T6 vendored licence check | `T06-vendored-licence-check.md` | ticket, lite | 1 |
| S3 server page 1 (tl-api route and the web file mirror routes) | `S3-*.md` | piece | 2 (after S1) |
| S4 log standard, reads, actions, RFI log | `S4-*.md` | piece | 2 (after S1, S2) |
| T1 correspondence log, T2 document log | `T01-*.md`, `T02-*.md` | tickets, full | 3 |
| T3, T4 record screen; T5 PDF viewer | `T03-*.md`, `T04-*.md`, `T05-*.md` | tickets, full | 3–4 |
| S5 tests (recasts all "Tests added", D2) | `S5-*.md` | piece | C3 |
| T7 docs, T8 demo | `T07-*.md`, `T08-*.md` | tickets, lite | C3–C4 |
| Twin tickets for M3 and M4 logs (6) | `T09`–`T14` | tickets | after M3 and M4 C2 |

## Risks and escalation
Spec §13 (R1–R6). Stop and call the orchestrator for: a new dependency whose licence is not permissive (95 line); any change
to the JSON API's auth surface beyond the cookie fill in `AuthenticationMiddleware`; a read the pages need that no route function offers.
