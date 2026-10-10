# Increment plan — P0-I4 workstream A: Query language and change feed

Status: done
Supervisor session: 2026-10-09
Brief sections: §5.3, §7.5, §10.2, §18.2, §5.4
Branch: `p0/i4a` (integration branch `p0/i4`; trunk `claude/wizardly-allen-m2v96s`). Fanout: `docs/tickets/P0-I4/FANOUT.md`.

## Objective
One filter language for the TUI, REST API and MCP: `parse` turns text into the frozen AST (`tl_core/query/ast.py`), `run_query` and
`count_query` compile it to SQL built only from allow-lists and bound parameters over `cur_core_record`, `cur_pset_values` and
`cur_links`, and results are the same envelope dicts as `list_records`. A change feed delivers committed events to subscribers with
filters (scope, event-type glob, record ids), at-least-once and resumable from the last `seq`: an in-process path (bus) and an
out-of-process path (a seq-cursor poller) feed one subscription registry. Out of scope: `path(...)`, FTS (text search is `LIKE`),
saved-query subscriptions, `ClientInterface.query` (the orchestrator decides at C's start), Postgres execution (P0-I5).

## Demo
```
just demo P0-I4-A
```
Builds a temporary ledger, runs a dozen queries from the brief (status, pset, date, linked, count, missing, text) and prints the keys
they return, shows a syntax error with its caret position, then streams events through a poller and a resumed subscription.

## Published interfaces (for workstreams C and D)

Everything below is importable from the named module and is covered by tests. The AST and `QuerySpec` are the frozen contract
(`tl_core/query/ast.py`, `api.py`); the rest is new in this workstream.

```python
# --- query language ---------------------------------------------------------------------------------------
from tl_core.query import (parse, run_query, count_query, QuerySpec, QuerySyntaxError, to_text, use_clock)

parse(text: str) -> Expr | None            # blank -> None; raises QuerySyntaxError(message, position) only
to_text(expr: Expr | None) -> str          # AST back to text (filter bar, saved views); parse(to_text(e)) == e
run_query(uow, spec: QuerySpec) -> list[dict]     # envelope dicts, same as services.queries.list_records
count_query(uow, spec: QuerySpec) -> int          # ignores limit, offset, order_by
QuerySpec(scope, record_type=None, where=None, order_by=[(col_or_pset_path, "asc"|"desc")], limit=500, offset=0, include_voided=False)
use_clock(now: datetime | Callable | None = None, tz: tzinfo | str = UTC)   # context manager; resolves +7d / today
# ValueError: bad limit, offset, order_by column, direction, or empty scope.  QuerySyntaxError: bad text or hand-built AST
#   (position 0 when the AST was not parsed from text).
# order_by columns: id key type scope title description status version last_seq effective_schema_hash conformance created_at
#   updated_at, or psets.<pset>.<property> (numbers, then text, then booleans; empty values last either way); id breaks ties.

# --- change feed ------------------------------------------------------------------------------------------
from tl_core.changefeed import (SubscriptionFilter, SubscriptionRegistry, ChangePoller, fetch_changes, ChangePage,
                                SubscriptionOverflow, ANY)

SubscriptionFilter(scope: str|None=None, event_types: tuple[str,...]|None=None, record_ids: frozenset[str]|None=None)
SubscriptionFilter.of(scope=..., event_types=<iterable>, record_ids=<iterable>)      # empty collections raise ValueError
    .matches(event) -> bool       # event_types are exact names or globs ("Record.*", "*.Created"); a record id also matches
                                  # a link event whose payload from_ref / to_ref is that id

registry = SubscriptionRegistry(ledger: Ledger | None = None)    # pass the ledger to enable replay and "live from head"
registry.attach(bus) -> Subscription                              # feed from the in-process bus (close() to detach)
registry.dispatch(events: Sequence[Event]) -> None                # the one feed point (bus adapter and poller call it)
registry.subscribe(callback, flt=None, *, after_seq=None) -> RegistrySubscription     # .close()
    # after_seq=None: live only. after_seq=n: replay the ledger after n (needs the ledger), then live, no gap, no repeat.
    # Callbacks run on the dispatching thread under the registry lock: never block in one.
registry.subscribe_queue(flt=None, *, after_seq=None, maxsize=1000) -> QueueSubscription
    # .get(timeout=0.0) -> Event | None;  .get_many(limit=100, timeout=0.0) -> list[Event];  .last_seq;  .overflowed;  .close()
    # A consumer that falls maxsize behind is dropped: after it drains the queue, get() raises
    # SubscriptionOverflow(resume_seq); resubscribe with after_seq=resume_seq (the replay pages through the backlog).
registry.close(); len(registry); registry.high_water

ChangePoller(ledger, registry, *, after_seq=None, scope=None, interval_s=0.25, page_size=500)
    # after_seq=None starts at the ledger head; 0 replays everything.  .poll_once() -> int;  .start();  .stop(timeout=5.0)
    # .cursor;  .running;  .last_error;  usable as a context manager.

fetch_changes(ledger, *, after_seq=0, flt=None, limit=500) -> ChangePage(events, next_seq, has_more)
    # for GET /events?after=<seq> and SSE catch-up. next_seq also moves past events the filter rejected; it is always
    # safe to pass back as after_seq.  At most 20 ledger pages are scanned per call.
```

**SSE sketch for workstream C** (one process, writers in-process and elsewhere):
```python
registry = SubscriptionRegistry(ledger); registry.attach(bus)           # events written in this process
poller = ChangePoller(ledger, registry); poller.start()                  # events written by other processes
# per connection, resuming with the Last-Event-ID header (a seq):
page = fetch_changes(ledger, after_seq=last_id, flt=flt)                 # catch up in pages, send each event with id: <seq>
sub = registry.subscribe_queue(flt, after_seq=page.next_seq)             # then go live
while connected:
    try: events = sub.get_many(100, timeout=15)                          # [] after 15 s: send an SSE comment keep-alive
    except SubscriptionOverflow as o: sub = registry.subscribe_queue(flt, after_seq=o.resume_seq)
```
`Event` carries `seq`, `stream_id`, `stream_version` (conflict detection for D), `scope`, `event_type`, `payload`.

## Supervisor-built pieces (in order)
| # | Piece | Why supervisor-tier | Reviewer | Status |
|---|---|---|---|---|
| S1 | Parser (`query/parser.py`): grammar, precedence, positioned errors, value typing, limits | "Query-language parser and SQL compiler" (`01-tiers.md` §3) | Orchestrator | built; reviewed at ce41208: pass (low notes fixed in 34e109f) |
| S2 | SQL compiler (`query/compiler.py`, `fields.py`, `temporal.py`, `clock.py`): allow-lists, bound params, two-valued predicates, pset EXISTS, link EXISTS/COUNT, ordering | same | Orchestrator | built; 339 tests in `tests/query` incl. injection and fuzz; reviewed at ce41208: pass |
| S3 | `query/format.py` (`to_text`) | Round-trip partner of the parser; pins the grammar by property test | Orchestrator | built |
| S4 | `changefeed/filters.py`, `registry.py` (fan-out, dedupe by seq, replay, queue subscriptions, overflow protocol) | Delivery ordering and concurrency (L-P0-I1-9, L-P0-I1-11); consumed by C's SSE | Orchestrator | built; 54 tests with deterministic ordering seams; reviewed at ce41208: pass |
| S5 | Integration tests over the real SQLite ledger (bus + poller double feed, resume, restart): `tests/services/test_changefeed_integration.py` | Needs T01 and T02 merged | — | built (7 tests) |
| S6 | Demo `dev/demos/P0-I4-A.sh` (`just demo P0-I4-A`), README and AGENTS updates, report `docs/reports/P0-I4-A.md` | Closing work | — | built |

## Tickets
| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| P0-I4-T01 | `fetch_changes` pager (16 provided tests) | H | S4 | merged | pass, 1 round |
| P0-I4-T02 | `ChangePoller` (19 provided tests) | H | S4 | merged | pass, 1 round |
| P0-I4-T03 | Query language reference page `docs/reference/query-language.md` (examples are executed by a provided test) | H | S1, S2 | merged | pass after one blocked attempt (not a strike). Implementer blocked correctly: `just check` failed on an E501 I introduced in `api.py` (56bb651). Fixed on `p0/i4a`; branch merged with it; the supervisor added the `~` note; 97 tests |

Haiku-ability (`01-tiers.md` §6), all three: (1) at most 3 files to read; (2) every interface is in the repo, stubs included;
(3) each ships a provided test (T03's test executes the page's examples, so prose cannot drift from the parser); (4) diffs of 40 to
80 lines plus the copied test (T03: one page); (5) none is in the Sonnet-authored table (the parser, compiler and registry are
supervisor-built, these are the thin pager, the polling loop and the docs); (6) no schema, migration, dependency or public-interface
change; (7) a reviewer verifies from the diff and the commands. Each was verified with a discarded reference implementation
dropped over the stub (pager 16/16, poller 19/19 and stable over 25 runs, doc 78/78) with `ruff` and `pyright` clean.

## Order of work
1. S1 to S4 and the provided tests (done), plan, tickets (this file).
2. Batch 1: T01, T02, T03 in parallel (disjoint Allowed paths). Merge on a pass verdict; take over on a second failure.
3. Then S5 (integration tests), demo script, README and AGENTS polish, report, final `just check && just test`.

## Design decisions taken by the supervisor (within the plan's scope)
| # | Decision | Why |
|---|---|---|
| A1 | The parser is a hand-written recursive descent over characters; every error is `QuerySyntaxError(message, position)`; input is bounded (2000 characters, 32 levels, 200 terms) | Positions for the filter bar; no input may raise another exception, recurse deeply or build a huge SQL tree. Fuzzed with hypothesis |
| A2 | `:` and `=` both mean equals. `=` is exact (case-sensitive); `~` is "contains, ignoring case" (`LOWER ... LIKE ... ESCAPE`, ASCII folding on SQLite) | The AST has one `=`; brief examples use both |
| A3 | `x!=v` means `NOT (x = v)`: it also matches records with no value. Every compiled predicate is two-valued | Otherwise `-x:v` and `x!=v` would disagree and `NOT` would lose rows (L-P0-I4-A1) |
| A4 | Value typing: envelope text columns always take text; integer and boolean columns validate; `null` (unquoted) is "no value"; pset values infer number, decimal, boolean, relative date, else text, and quoting forces text; numbers with leading zeros stay text | The AST `Value` is typed and the parser knows column kinds but not pset types |
| A5 | An unknown field is a syntax error that suggests the nearest name. Phase 0 fields are the `cur_core_record` envelope columns (`fields.py`); `discipline`, `area`, `due` from the brief's example arrive with the envelope columns | Silently treating `foo:bar` as text would hide typos; `fields.py` is the single place to extend |
| A6 | Dates: `created_at` / `updated_at` take `YYYY-MM-DD`, an ISO date-time, `+Nd` / `-Nd` or `today`. A date is a day window in the project time zone (`=` inside, `<` before, `<=` before its end, `>` after its end, `>=` from its start); a date-time is a window of its own precision. Relative dates on pset values compare ISO text by day. The clock and zone are injectable (`use_clock`); the default is UTC until about:config supplies the project time zone | Contract: "RelativeDate resolves against an injectable clock" |
| A7 | Link terms count a link as live when its status is `active`, `stale` or `broken`. Suggested links do not count (brief 7.3: suggestions wait for acceptance) and retracted links never do. **Confirmed by the orchestrator (2026-10-09):** suggested links are excluded as well as retracted ones; the `api.py` docstring was updated to say so (documentation-only contract edit, approved). One constant (`LIVE_LINK_STATUSES` in `fields.py`) holds the rule | Suggestions are not links yet, and `cur_link_counts` reports them separately |
| A8 | `linked:T` matches the other end's `type` equal to `T` or ending in `.T`, ignoring case (`NCR` finds `quality.NCR`) | The AST says "record type or type alias"; no alias registry exists yet |
| A9 | Syntax beyond the contract's table: `linked(*)` any relation; bare `linked` any live link; `linked:T.cond` and `linked(r).cond` attach a condition on the linked record (`.(a b)` groups; `linked:quality.NCR.status:open` splits at the last segment, or at a segment named `psets`); `count(...)` takes `=`, `!=`, `<`, `<=`, `>`, `>=`; `missing(link)` / `missing(link(rel):T)`. `path(...)` is a syntax error | Needed so the `where` slot of `Linked` is reachable from text |
| A10 | `or`, `and`, `not` are case-insensitive keywords; a word that is a keyword is quoted to search for it | Users type lower case; quoting is the escape |
| A11 | Text search is `LIKE` over `key`, `title` and `description` with `\`, `%`, `_` escaped. FTS5 replaces it later | Contract; dialect-neutral |
| A12 | Ordering by a pset path uses a `LEFT JOIN` on `cur_pset_values` (unique per record and path): numbers, then text, then booleans, empty last | Closes the P0-I2 follow-up "sorting on pset columns waits for the query language" |
| A13 | `services/queries.py` gains the public `envelope_from_row` (additive) so the compiler returns exactly the `list_records` shape | pyright strict forbids importing the private `_envelope` |
| A14 | The change feed lives in `tl_core/changefeed/`, not `feed/` | `Feed.*` events and the feed projection are P0-I6's activity feed |
| A15 | One `SubscriptionRegistry` is the fan-out for both sources. A subscriber has a `seq` cursor; events at or below it are dropped, so the bus and the poller can both offer an event. Replay and registration share the registry lock with `dispatch`, so there is no gap and no repeat. Callbacks run under that lock; `subscribe_queue` is the non-blocking path and ends with `SubscriptionOverflow(resume_seq)` when the consumer lags | At-least-once with resume (brief 5.3) without letting a slow SSE client stall writers |
| A16 | A record-id filter also matches link events whose payload `from_ref` / `to_ref` is that record | A record view's Links tab hears about its links |
| A17 | `ChangePoller` starts at the ledger head by default (live) and advances its cursor only after `dispatch` returned | At-least-once; no loss on a crash |
| A18 | Saved-query and record-type subscription filters are not built: a type filter needs the record row for non-create events | Out of scope for this increment; `fetch_changes` plus `run_query` can serve them in P0-I5/I6 |

Performance check (20,000 records, SQLite, fixed queries): field and pset filters 10 to 20 ms for 500 rows; `linked`/`count`/`missing`
about 130 ms; sort by a pset 27 ms. The 100k-row target of §15 is re-measured in P0-I8.

## Risks and escalation triggers
- Postgres: the compiler is dialect-neutral but untested there until P0-I5; `LOWER` and `LIKE ... ESCAPE '\'` behave the same on both.
  The change-feed cursor assumes serial commits (L-P0-I4-A2); P0-I5 must handle out-of-order visibility.
- Escalate only if C or D need an AST or `QuerySpec` change (contract), or a decision on A7.

## Blocked / Decision
- T03 attempt 1 was `blocked` by a red `just check` caused by the supervisor's own docstring commit, not by the implementer. It does not count as a strike.
- Review notes at ce41208, all fixed in 34e109f: identifier and date regexes now end with `\Z` (a trailing newline used to pass `$`); `QueueSubscription.last_seq` starts at the subscribe point; `~` on numeric or boolean pset values never matches (documented on the reference page).
- A7 confirmed by the orchestrator (see decision A7). The Phase 0 gap (`discipline`, `due` rejected as unknown fields) is accepted; follow-up for when the envelope gains those columns (P1), to be listed in the report.
