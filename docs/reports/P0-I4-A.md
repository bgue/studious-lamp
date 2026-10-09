# Report — P0-I4 workstream A: Query language and change feed

Written 2026-10-09. Workstream branch `p0/i4a` (integration branch `p0/i4`; trunk `claude/wizardly-allen-m2v96s`). Plan, published
signatures and decisions A1 to A18: `docs/tickets/P0-I4/README-A.md`. Not merged into `p0/i4` and not pushed.

## Outcome
Objective met: yes. Text parses to the frozen AST, compiles to SQL built only from allow-lists and bound parameters, and runs over
`cur_core_record`, `cur_pset_values` and `cur_links`. Committed events reach filtered subscribers from the in-process bus and from a
seq-cursor poller through one registry, at-least-once and resumable from the last `seq`. Demo path verified: `just demo P0-I4-A`
prints "P0-I4-A demo ok" (13 queries with exact expected key sets, a positioned syntax error, a hostile value found as data, bus plus
poller delivery without repeats, paged resume, queue overflow with a resume point). WS-A's exit criterion in the fanout plan
("`parse` + `run_query` cover the AST except `path(...)`, with SQL from allow-lists and bound params only") is met.

## Tickets
| ID | Outcome | Review rounds | Notes |
|---|---|---|---|
| P0-I4-T01 `fetch_changes` pager | merged | 1, pass | 16 provided tests |
| P0-I4-T02 `ChangePoller` | merged | 1, pass | 19 provided tests, stable over repeated runs |
| P0-I4-T03 query reference page | merged | 1, pass (attempt 1 blocked by the supervisor's own E501, not a strike) | 97 tests; the page's 64 examples and 12 error examples are executed by the provided test; the supervisor added the `~` note and applied two advisory fixes in the merge |

Supervisor-built, reviewed by a fresh reviewer at ce41208 (pass; SQL safety, injection probes, NULL semantics, precedence, limits, a
20-consumer 3000-event stress run, mutations killed): parser, compiler, `fields.py`, `temporal.py`, `clock.py`, `format.py`
(`to_text`), `changefeed/filters.py`, `changefeed/registry.py`. Low notes fixed in 34e109f. Taken over: none. Abandoned: none.
Dispatch rounds: 1 batch of 3 tickets, plus one fix relay.

## Gates
| Gate | Result |
|---|---|
| `just check` (ruff, ruff format, pyright strict on `tl_core`, codegen drift) | green on `p0/i4a` |
| `just test` | 1730 passed |
| `just test-parity`, `just test-tui` | not applicable: no adapter, ledger or TUI change |
| Query tests | parser 148; `tests/query` 339 (seeded-ledger matrix, injection, hypothesis properties: parser never raises anything but `QuerySyntaxError`, `parse(to_text(e)) == e`, compiled SQL always runs, `x` and `-x` partition the records) |
| Change-feed tests | filters 28; registry 26 (deterministic ordering seams); pager 16; poller 19; integration over SQLite 7 |
| Schema classification, contract tests | not applicable (`schema/**` untouched) |
| Demo `just demo P0-I4-A` | clean |
| Performance (20,000 records, SQLite, 500-row pages) | field and pset filters 10 to 20 ms, `linked`/`count`/`missing` about 130 ms, sort by a pset 27 ms; the 100k target is P0-I8 |

Mutation checks run by the supervisor: splicing a value into SQL (16 injection tests fail), dropping the NULL guard (the `NOT`
partition property fails), removing the registry lock or the seq dedupe (ordering and dedupe tests fail).

## Deviations from plan
- **Contract edit (orchestrator-approved, documentation only):** `api.py` docstring now says suggested links are excluded from link terms as well as retracted ones (A7). `ast.py` is untouched; `api.py` bodies were filled in with lazy imports (the exception class is defined there and the parser imports it).
- **Additive change outside the package:** `tl_core.services.queries.envelope_from_row` is public so the compiler returns exactly the `list_records` shape (A13). `docs/reference/` is a new docs directory (row added to `AGENTS.md`).
- **Added beyond the plan:** `to_text` (AST to query text, for the filter bar and saved views), `use_clock`, the `fetch_changes` pager for `/events?after=`, queue subscriptions with an overflow protocol (for SSE), syntax extensions needed to reach `Linked.where` from text (A9).
- **Not built:** `path(...)` (syntax error, as the contract says), FTS (text search is `LIKE`), saved-query and record-type subscription filters (A18), `ClientInterface.query` (orchestrator decides at C's start).

## Escalations and decisions
- A7 (suggested links do not count as links): raised in round 1, confirmed by the orchestrator.
- Phase 0 gap accepted by the orchestrator: the brief's example fields `discipline` and `due` are rejected as unknown fields, because the record envelope has no such columns.
- No unresolved *Blocked* entries.

## Learnings
Appended: L-P0-I4-A1 (two-valued predicates), L-P0-I4-A2 (the seq-dedupe invariant and the Postgres out-of-order risk for P0-I5), L-P0-I4-A3 (run `just check` on the tip after every supervisor commit). Implementer proposals declined: T02's "`just check | grep` hides the exit status" (the ticket already says not to pipe it), "`just test` prints two summaries" (harness behaviour) and "the Context list omits files the provided test imports" (the file needed no change); T03's observations are reflected in the page and the decision note.

## Docs
- `packages/tl-core/README.md` and `AGENTS.md`: query and change-feed interface rows and rules. `docs/reference/query-language.md` (new, test-checked). `docs/tickets/P0-I4/README-A.md` (published signatures for C and D, SSE sketch). `AGENTS.md`: reference-docs row.
- Demo: `dev/demos/P0-I4-A.sh`. Ticket reports: `docs/reports/P0-I4/P0-I4-T01..T03.md`. Provided tests: `docs/tickets/P0-I4/provided/`.
- Runbook: none added; the poller and SSE endpoint are operated by workstream C, which owns their runbook.

## Follow-ups filed
- **P1, when the record envelope gains `discipline`, `area`, `due` and similar columns:** add them to `ENVELOPE_FIELDS` in `query/fields.py` (the parser, compiler and reference page follow from that table) so the brief's example `status:open discipline:PIP ... due<+7d` parses.
- **P0-I5:** run the compiler and the registry/poller against Postgres; the poller must tolerate out-of-order commit visibility (L-P0-I4-A2); `LOWER` folds only ASCII on SQLite.
- **Workstream C:** wire `fetch_changes`, `registry.attach(bus)`, `ChangePoller` and `subscribe_queue` into `/events` and SSE (sketch in README-A); decide `ClientInterface.query(spec)` with D.
- **Later:** project time zone from about:config into `use_clock`; `~` on numeric pset values (matches text values only, documented); `path(...)`; FTS5; saved-query subscriptions; a `linked` index on `cur_links(status)` if the 100k measurement needs it.

## Cost notes
Supervisor effort went to the parser, compiler and registry plus their tests and reference-checked provided tests, which gave first-round passes for all three tickets. Three implementer runs, three reviewer runs and one supervisor-pieces review.
