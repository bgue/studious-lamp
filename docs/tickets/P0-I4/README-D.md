# Increment plan — P0-I4 workstream D: Live TUI

Status: done
Supervisor session: 2026-10-10
Brief sections: §4 (embedded vs remote client), §5.3, §7.5, §10.2, §10.3
Branch: `p0/i4d` (integration branch `p0/i4`; trunk `claude/wizardly-allen-m2v96s`). Ticket branches `p0/i4d-t<nn>-<slug>`. Fanout: `docs/tickets/P0-I4/FANOUT.md`; the API it consumes: `README-C.md`; the query language and change feed: `README-A.md`.

## Objective
The same TUI runs against a SQLite file in this process (embedded, the default) or against a running API server (`tl tui --remote URL --token T`), and in both modes it shows other writers' changes within a second or two. `ClientInterface` gains `query_records` / `count_records` (orchestrator decision O3). A filter bar sends query-language text to the grid, shows the match count from `count_records`, and points at the character where the parser stopped. A change by someone else marks the row in the grid, refreshes an open record view with an "updated by" line, and, when it lands under an open edit form, shows a conflict banner and blocks the save (the ledger would refuse it anyway because the form sends `expected_version`). A lost server shows a "server unreachable" banner, not a crash, and the feed resumes from the last `seq` when the server returns. Out of scope: any role or permission model (human gate), conflict merging or three-way edit, offline queueing of commands, WebSocket, a head endpoint on the API (the remote feed finds the head by bisection).

## Demo
```
just demo P0-I4
```
`dev/demos/P0-I4.sh` starts `tl serve` on a free loopback port with a dev token, then drives a headless remote client (the same `RemoteClient` and `RemoteFeed` the TUI uses) and an in-process MCP client while an embedded writer (the CLI) changes a record. It prints the measured latency of each observer and fails above 2 s. The Textual Pilot tests (`packages/tl-tui/tests/test_live_remote_app.py`) prove the same on screen, with no terminal.

## Published interfaces (for later increments)
```python
# tl_tui.client.ClientInterface (additive, O3)
query_records(scope, q, *, limit=500, offset=0, order_by=None) -> list[dict]   # QuerySyntaxError(position) on bad text
count_records(scope, q) -> int
# tl_tui.live
class ChangeFeed(Protocol): follow(sink: FeedSink, stop: threading.Event) -> None;  close() -> None
class FeedSink(Protocol):   events(batch: list[Event]) -> None;  connection(state, detail="") -> None
EmbeddedFeed(ledger, bus, *, scope=None, interval_s=0.25)        # EmbeddedClient.change_feed(scope)
LiveUpdates(feed, target).start() / .stop()                      # a daemon thread; posts LiveEvents and ConnectionChanged
OwnWrites().note(CommandResult) / event_id in own_writes         # EmbeddedClient.own_writes, RemoteClient.own_writes
touched_record_ids(events), detect_conflict(record_id, opened_version, events), latest_by_record(events), describe_changes(events)
# tl_tui.remote
RemoteClient.connect(url, token) / RemoteClient(api, feed_api=...)   # .as_client(), .change_feed(scope), .connection_listener, .own_writes
RemoteFeed(make_api, *, scope=None)    # head by bisection (find_head), SSE from the cursor, backoff 0.25 s to 5 s, states live / reconnecting / unreachable
# tl_tui.main
make_app(remote=, token=, db=, project=, actor=) -> TlApp ; run(...) ; main(argv) ; env TL_REMOTE, TL_TOKEN, TL_PROJECT, TL_DB
```
Messages (`tl_tui.messages`): `LiveEvents`, `ConnectionChanged`, `FilterSubmitted`, `FilterClosed`. Grid: `apply_filter(text) -> FilterResult(ok, count, message, position)`, `refresh_live(ids)`, `is_marked(id)`, `filter_text`, `match_count`.

## Supervisor-built pieces (in order)
| # | Piece | Why supervisor-tier | Reviewer | Status |
|---|---|---|---|---|
| S20 | `query_records` / `count_records` (protocol, embedded, fake through the real parser); `errors.py` (`ApiError` in `CLIENT_ERRORS`, unreachable text); `RemoteClient` adapter (relations conversion, reachability states, own writes, signature test over every interface method) | Error contract and the seam between two transports | Orchestrator | built; 7 + 12 tests |
| S20 | Live-update subscription and its threading into Textual: `live.py` (`EmbeddedFeed`, `LiveUpdates`, `OwnWrites`), `RemoteFeed` with `find_head` and resume, `RecordGrid.refresh_live` (worker thread, `call_from_thread`, generation guard, coalescing), `TlApp` wiring, `ConnectionBanner` | Concurrency across three threads and the ordering guarantees of L-P0-I1-9 | Orchestrator | built; 10 + 12 + 11 + 4 tests, mutation-checked |
| S23 | Review fixes: feed hand-off, own-write ordering, ledger reset, mark retention, interactive timeout, token help | Concurrency findings of the fresh review | Orchestrator (re-review of the first two) | built; 8 + 3 + 1 tests, mutation-checked |
| S20 | Conflict detection: `detect_conflict` (a record-stream event past the version the form opened at) | Defines when a save is blocked | Orchestrator | rule built and tested; screen wiring in round 2 |
| S21 | Grid filter (`apply_filter`, `FilterResult`), `tl_tui.main` (`make_app`, `run`, `--remote`) | Ties the query contract to the grid | — | built; 5 tests |
| S24 | App wiring of the filter bar (`/`), "updated by" line and edit-form conflict (`detect_conflict`); demo `dev/demos/P0-I4.sh`; READMEs, AGENTS.md, runbook; report `docs/reports/P0-I4.md` | Closing work | — | built; 14 tests, mutation-checked |

## Tickets
| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| P0-I4-T60 | Filter bar widget (12 provided tests) | H | S21 | merged | pass, 1 round (reported blocked by the supervisor's flaky outage test, see S23; its own tests and `just check` were clean) |
| P0-I4-T61 | `tl serve` and `tl tui` (8 provided tests) | H | S21 | merged | pass, 1 round; the supervisor changed the `--token` help text afterwards (review ruling 6) |
| P0-I4-T62 | Record view "updated by" line (5 provided tests) | H | S20 | merged | pass, 1 round |
| P0-I4-T63 | Edit form conflict banner (5 provided tests) | H | S20 | merged | pass, 1 round |

Haiku-ability (`01-tiers.md` §6), all four: (1) three or four files to read; (2) the stubs, the messages, `FilterResult` and `tl_tui.main.run` are in the repository; (3) each ships a provided test (12, 8, 5, 5 tests) verified against a scratch reference (kept in `/home/user/wt/p0-i4d-refs/` until the tickets merge) with `ruff` and `pyright` clean; (4) diffs of 20 to 90 lines plus the copied test; (5) none is in the Sonnet-authored table (a widget, two thin CLI commands, two small additions to existing widgets); (6) no schema, migration, dependency or public-interface change (the workspace dependency lines are committed on the base); (7) a reviewer verifies from the diff and the commands.

## Order of work
1. Round 1 (done): plan, S20 and S21, stubs, provided tests and tickets T60 to T63.
2. Round 2 (done): review fixes S23; merge batch 1; wire the filter bar, the "updated by" line and the conflict banner into `TlApp` with tests; `dev/demos/P0-I4.sh`; READMEs, AGENTS.md, runbook; gates; report.

## Design decisions taken by the supervisor (within the plan's scope)
| # | Decision | Why |
|---|---|---|
| D1 | A feed is a blocking `follow(sink, stop)` run on a daemon thread; the sink posts Textual messages with `post_message` | `post_message` is the thread-safe entry that never blocks the feed and never waits on a loop that may have stopped. A worker that has a result to apply (the grid refresh) uses `call_from_thread`, with the generation guard of L-P0-I2-B5 |
| D2 | `EmbeddedClient.for_sqlite` keeps one `SqliteUowFactory` (engine, ledger, in-process bus). The embedded feed is the bus (own writes at once) plus a `ChangePoller` (other processes), one registry | The same arrangement the API uses; the registry dedupes by `seq` |
| D3 | Own writes are told from others' by event id (`OwnWrites`), not by actor | Two TUIs run by the same user must still see each other's changes |
| D4 | The remote feed finds the ledger head by bisection over `GET /events?limit=1`, then streams after it | The API has no head endpoint (contract C is final). The first connection is thereby live with no gap and no race, and a drop before the first event still resumes from a cursor |
| D5 | `RemoteFeed` uses `stream_events(reconnect=False)` and its own loop | The client's built-in reconnect hides an outage; the TUI must show it. The probe before each resume (`events_after(cursor, limit=1)`) proves the server is back and feeds the banner |
| D6 | The feed has its own connection pool (`feed_api` factory), so `close()` can abort a blocked read and the main pool is never held by the stream | A read blocked on keep-alive (15 s) must not delay shutdown |
| D7 | A mark means "someone else changed this row in the last 4 s" and does not depend on what an earlier read showed | An outage refresh and a replayed event can both read the same version (found by the restart test) |
| D8 | The filter does not restrict the record type (`ClientInterface.query_records` has no `record_type`, O3); say `type:...` in the text. A blank filter returns to the grid's type | Contract O3 is final; the reference page documents `type` |
| D9 | The filter bar is hidden until `/` and takes no space; a filter in force keeps it visible | Existing layouts and snapshots are unchanged |
| D10 | The remote header shows `--actor` (default `user:dev`); the server records the token's actor | The client cannot learn the token's actor from the API |
| D11 | An open record view re-reads on the UI thread when a foreign event touches it | Its tabs fetch synchronously today (also when the user opens a record); moving that to workers is a follow-up |
| D12 | `tl-tui` depends on `tl-api` and `httpx2`; `tl-cli` depends on `tl-tui` (workspace packages; httpx2 is BSD-3-Clause, already in the lock) | The remote client is the API client; `tl tui` and `tl serve` live in the CLI |
| D13 | The feed's cursor is taken before the grid's first read: `TlApp.__init__` calls `feed.head()`, and `follow` starts after that seq (embedded: registry replay and poller `after_seq`; remote: `RemoteFeed.cursor`). The first "live" state also triggers one refresh as a safety net | An event committed between the first read and the thread start used to be lost (review of S20) |
| D14 | While a command of this client is in flight, events on its stream are `pending` (`OwnWrites.in_flight`, cap 2 s); the app holds them until the response has been noted, then drops the own ones and marks the rest | The SSE event can beat the HTTP response (review of S20) |
| D15 | After a drop, `RemoteFeed` compares the server's head with its cursor; a lower head resets the cursor, tells the app (`LedgerReset`), which reads everything again and shows a banner for 8 s | A replaced or restored ledger would otherwise leave the feed waiting for seqs that never come |
| D16 | Remote calls on the UI thread time out after 3 s (`INTERACTIVE_TIMEOUT_S`); the unreachable banner explains the freeze. Moving the grid load, record view and filter calls to workers is a P0-I8 hardening follow-up | Accepted by the orchestrator for P0-I4 |
| D17 | A mark is forgotten only when it has been applied; a failed read keeps it, a result dropped after a sort marks the rows now shown, and an unexpected error in a refresh is logged, reported in the footer and resets the busy flag | Review of S20 |

## Risks and escalation triggers
- A feed callback that blocks would stall writers; callbacks only enqueue (`subscribe_queue`) and post messages.
- Postgres: the embedded feed is SQLite-only today (`SqliteUowFactory`); the remote feed works against any backend the API serves.
- Escalate for: a change to `Event`, `QuerySpec` or the SSE contract; any role or permission rule (human gate).

## Blocked / Decision
(none)
