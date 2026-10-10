# Report — P0-I8 workstream B: extension record type registry v0

Branch: `p0/i8b` (base `p0/i8`, merged in three times). Plan and decisions B1 to B14: `docs/tickets/P0-I8/README-B.md`. Demo: `just demo P0-I8-B`. Runbook: `docs/runbooks/extension-types.md`.

## Outcome
Objective met: yes, except the last planned ticket (below). A company can add a record type by putting a package of files in a directory. `tl types sync <root>` validates each package, registers it with one ledger event or quarantines it with a report, and does nothing the second time. A registered type works as a generic record type on every surface: `CreateRecord.record_type = "co.acme.LiftPlan"`; the query language filters its index fields; the CLI, the REST API, the MCP read tools and the TUI list, create, read and (for bodies) edit it. A managed type keeps its values in the ledger. An object-backed type keeps its body in the object store as a content-addressed, hash-verified document; a mismatch is quarantined, listed by `tl types quarantine ls`, refused on every surface and healed by storing the body again. Editing the files of a registered version is a reported `conflict` that never removes the registration.

**Open: the settings registration ticket.** Registering a package's `settings.yaml` through `tl_core.settings.register_definitions` waits on workstream A, which is not on `p0/i8` yet (the function exists on `p0/i8a`). `read_settings` already validates and returns the definitions (namespace rule, no secret keys). Plan for the ticket: when the type source refreshes, register each usable type's definitions with its type name as owner and unregister the types that left; at sync, quarantine a package whose keys clash with another owner's (`settings` issue). A clash while registering is logged and skips that type's settings.

Demo verified (`just demo P0-I8-B`, "P0-I8-B demo ok", run three times; it failed once in two before a `| head` under `pipefail` was removed, L-P0-I8B-13).

## Tickets
| ID | Outcome | Review rounds | Notes |
|---|---|---|---|
| T20 `tl types sync\|ls\|show\|validate\|lock\|deprecate\|watch` | merged | 1 | Supervisor fix: `sync` prints `conflict <ref> (kept <hash>)` (orchestrator ruling); `deprecate` moved to `registry.deprecate` after re-review |
| T21 API routes for types and bodies | merged | 1 | No findings |
| T22 MCP `list_record_types`, `get_record_type`, `get_record_body` | merged | 1 | Provided test corrected by supervisor (pyright, L-P0-I8B-7) |
| T23 `ApiClient` type and body methods | merged | 1 | Provided test corrected by supervisor (same) |
| T24 TUI grid columns from `form.yaml` | merged | 1 | No findings |
| T25 TUI generated new-record form | merged | 1 | Three open questions ruled (untouched bool omitted, `psets=None` for object-backed, stale Required mark fixed in `FieldEditor`) |
| T26 `tl types quarantine ls\|recheck` | merged | 1 | First implementer died (usage limit); second hit a red test on my base (L-P0-I8B-9); reviewed as review-only |
| T27 TUI edit form for an object-backed body | merged | 1 | Wired into `e` of the record view by the supervisor (S41); `record["id"]` confirmed with the embedded and the remote client |
| Settings registration | open | | Waits on workstream A |

Taken over: none. Abandoned: none. Supervisor pieces: S20 `schema/core/extension.yaml` and catalog updates; S21 package model, validator, compiler, example packages; S22 registry, projectors, loader, schema provider hook; S23 body store and quarantine; S24 forms, `type_detail`, watcher, API error rows; S25 stubs and provided tests; S26 to S32 review fixes (imports confined, per-package validation, loader re-verification, lost-race retry, hidden files locked, `registry.deprecate`); S33 `ClientInterface` growth, `EmbeddedClient`, fakes; S34, S37 tickets; S35 to S39 wiring and the S33 review fixes; S40 cross-surface test, demo, CLI help, deprecated-first status; S41 body edit wiring; S42 runbook and docs.

## Reviews
- Fresh-context review of S20 to S24: changes-requested (1 high, 2 medium, 3 low), fixed in S26 and S27, re-review passed. The high finding: a package could import outside itself and one bad package stopped a sync; imports are now confined and `validate_package` never raises.
- Review of S32 and S33: S32 clean; S33 changes-requested (1 high, 2 medium, 3 low), fixed in S35 and S38, re-review passed. The medium findings: the embedded client accepted an `agent:*` actor (now refused, as the API does) and a store `OSError` escaped as a crash (now a `ServiceError` without a path).
- Core-engine pieces (S21 to S24) were not merged by me into `p0/i8`; they are for the orchestrator's merge.

## Gates
| Gate | Result |
|---|---|
| `just check` | green at 3141bab |
| `just test` (includes `packages/tl-tui` and its 24 snapshots) | 4713 passed, 1 skipped |
| `just test-parity` (SQLite and Postgres) | 1856 passed |
| `just demo P0-I8-B` | ok |
| `uv run python dev/tools/audit_docs.py --strict` | 0 findings |

Cross-surface coverage (`tests/extypes/test_cross_surface.py`, 7 tests on a real SQLite ledger, filesystem store and loopback server): register with the CLI, create over HTTP, read over MCP and the embedded client, edit with the embedded client, create and edit in the remote TUI, a damaged body refused on all surfaces and healed, a retired type refused everywhere. `tests/extypes` also runs on Postgres (211 tests at the review fixes).

## Deviations from plan
- `store_body` gained one optional keyword, `expected_version`, so an editor holding an old version gets a 409; `store_record_body` was added next to it and the API route and the embedded client both call it.
- `BodyStoreUnavailableError` (503 `body_store_unavailable`) is new: a call that needs the object store when none is configured, or when the store fails.
- A retired version now reports `deprecated` even when its files changed (status is judged from the registry row before any file is read).
- The plan's demo text listed a SafetyObservation query; the shipped demo shows the object-backed path, MCP, the TUI client, quarantine and retirement instead.
- The stub docstrings of three CLI commands leaked into `--help`; rewritten (S40).

## Escalations and decisions
- Schema change for approval: `schema/core/extension.yaml`, `core.yaml`, `annotations.yaml` and the example packages under `schema/fixtures/types` (commits a6909f0, 82d9d5c); no schema file changed since.
- No new dependencies. No data migration (a ledger without the registry tables reads as "no types", and `tl init` adds them). Permission rules for who may register a type or write a body are not designed (ADR-0005): v0 applies the mechanism only.
- Orchestrator rulings applied: conflict output, imports confined, loader re-verification interval, retry on a lost race, agent guard on the embedded client, store errors as service errors, one body write path, a status-line warning for `--type`, and the T25 questions.

## Learnings
Appended: L-P0-I8B-1 to L-P0-I8B-13 (LinkML typing and logging, import cycles, copy of `schema/core` per compile, stub and provided-test process, `pkill -f`, docstrings that reach OpenAPI, CLI help and MCP, pyright over provided tests, a cache notified after the commit, full package suites before relaying, `FieldEditor` choice marks, the embedded client's missing refusals, demo pipes). No implementer proposal was declined.

## Docs
Created: `docs/runbooks/extension-types.md` (and the runbooks index), `docs/reports/P0-I8/P0-I8-T20.md` to `T27.md`, `docs/tickets/P0-I8/README-B.md` and tickets `T20` to `T27`. Updated: README.md and AGENTS.md of `tl-core`, `tl-cli`, `tl-mcp`, `tl-api`, `tl-tui`; the MCP server instructions. `audit_docs` reports no finding.

## Follow-ups filed
- Settings registration (above), after workstream A merges.
- Full ReDoS hardening of package patterns (a short pattern can still backtrack); the cap is 200 characters.
- `tl types watch` stops if `on_change` raises something unguarded (a database outage).
- `_store_errors` in the embedded client also wraps the unit of work, so a stray SQLite `OSError` would read as "object store unavailable"; `type_warning` calls `list_types` on the UI thread at mount (a remote call).
- An embedded body save returns no events, so the TUI shows the user's own body edit as a change by someone else; `store_record_body` would have to return the events.
- Directory-backed storage and external `incoming/` writers (D11); signing `type.lock` (D9); a change-classification gate between versions of one type (§27.5); activating `workflow.yaml`; proposable `store_body` for agents; an `s3://` package location; a TUI grid column for body-only slots.

## Cost notes
Eight Haiku tickets (one re-dispatch after a usage-limit death), five review requests, no taken-over tickets. A full `just test` takes about 15 minutes under shared load.
