# P2-WEB1 report: web client wave 1

Status: done at C4 (checkpoint), pending the wave-close whole-suite gate on the integrated branch. Branch `p2/web1`, trunk `claude/wizardly-allen-m2v96s`. Spec `docs/build-spec/specs/web-client-i1.md`. Board and decisions D1-D46: `docs/tickets/P2-WEB1/STATE.md`.

## Objective
A server-rendered web client under `/web` (`TL_WEB`) that shows the same logs, record screens and plain-word text as the terminal, through the same command and read contracts as the API (no new business logic). Hidden records answer as missing (ADR-0016).

## What shipped
| Area | Items | Pages |
|---|---|---|
| Foundation | S1, S2, S3, S4 | sign-in, cookie session, CSRF, `WebLog`, `/do` actions, read mirrors, PDF vendoring (htmx, pdf.js, licence manifest) |
| Core pages | T15, T01, T02, T05 | RFI log, correspondence register, document log, PDF viewer |
| Record screen | S6, T03, T04 | Details, Properties, History, Links, Trace, Thread, Files tabs |
| M3 twins | T09, T09b, T10, T11, T16 | CWP register, CWA register, WBS tree, packages, path |
| M4 twins | T12, T12b, T13, T13b, T14, T14b | stock, movements, receipts, MTO lines, items, locations |
| Support | S5, T06, T08, T17, T18, T19, T20, T07 | tests piece, licence check, demo script, materials seed, digit-string tidy, stock Location fix, demo clauses 6-7, docs |
11 twin pages and 15 core web screens are in the owner screenshot gallery (wave1 tour). Docs: `packages/tl-web/README.md`, `docs/runbooks/web-client.md`, AGENTS row.

## Gates
| Gate | Result |
|---|---|
| Demo `just demo P2-WEB1` | 7/7 clauses, sqlite and postgres, rc0 (`.gate/demo-c4.log`) |
| tl-web tests | 481/481 at T19 |
| Per-item gates and reviews | all merged items passed (see board) |
| Whole-suite `just gate`, `gate-pg` | not run here; run once at wave close on the integrated branch (trunk + p2/i1 + p2/i3 + p2/web1) by the orchestrator, owner capacity |

## Security
First-wave review: F1 MD login CSRF, F2 LO guard default-on, F3 LO rate-limit tests; all fixed in SECFIX (`b817341`, merge `0118cb0`). Milestone review SEC-C4 (`da07d37..904dfb0`, twins): 9 none. Twins add no write route. Report: `docs/reports/P2-WEB1/SEC-C4.md`.

## Notable decisions
- D3/D26: S5 one tests piece for every merged item; tests live in `packages/tl-web/tests`.
- D16/D19: S6 moved record logic into Textual-free `tl_tui` text modules so tabs could be Haiku tickets.
- D30/D38/D43: supervisor registry seams in `reads.py` (mirrors 24 to 42), disclosed over the 50-line cap.
- D34/D39: twins split one page each (01-tiers 6 item 4).
- D41: `WebLog.row_open_key` lets M4 rows carry no Open link.
- T20 (orchestrator): an unknown well-formed project answers an empty 200, like every log and the API (roles-mvp 7); a malformed name stays 404.

## Follow-ups
- D46: locations page looks flat (HTML collapses the depth indent); `white-space:pre` on the Subject cell would fix it.
- P3-I8: unknown or non-member project answers one 404 on web and JSON API; `item_projects` and `items.projects` need the membership filter in the view.
- Q4: `seed_hidden_world` fails on Postgres (AttachFile needs the user access word), so `just gate-pg packages/tl-web` errors at baseline; needs a web test seed on Postgres.
- Stream-test flake seen under load (passes alone); not quarantined.
- Q3: awp twins walk at route level only (no awp seeder); Q8: M4 rows have no web record pages.
- D20: document revision and transmittal actions stay terminal-only.

## Learnings
L-P2-WEB1-1 to 3 appended to `docs/memory/LEARNINGS.md`.
