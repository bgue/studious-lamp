# P0-I4-T01 — Change pager: `fetch_changes`

Status: ready
Tier: haiku
Labels: core
Depends on: — (the filter, registry and stub are on the base branch)
Branch: `p0/i4a-t01-change-pager`

## Goal
`tl_core.changefeed.pager.fetch_changes` returns one page of events after a `seq` cursor that pass a `SubscriptionFilter`, together
with the cursor to continue from and a `has_more` flag. The REST `/events?after=` endpoint and a reconnecting SSE client will call it.
The dataclass, constants and signature exist in the stub; the body of `fetch_changes` raises `NotImplementedError`. A provided test
file (16 tests) must pass.

## Brief references (pasted)
> **5.3 Realtime data access.** Change feed source (dev): in-process bus fed on commit; polling by `seq` for out-of-process readers.
> Delivery semantics: at-least-once, cursor-based (`seq`); clients resume from last `seq`. Subscriptions by scope, record type,
> record ID, or saved query.

### Specification (the provided test checks it)
`fetch_changes(ledger, *, after_seq=0, flt=None, limit=DEFAULT_LIMIT) -> ChangePage`

1. `limit < 1` raises `ValueError(f"limit must be at least 1, got {limit}")`; `after_seq < 0` raises
   `ValueError(f"after_seq must not be negative, got {after_seq}")`. Check `limit` first.
2. `flt=None` means `ANY` (import it from `tl_core.changefeed.filters`).
3. Keep `cursor = after_seq` and an empty `events` list. Repeat at most `MAX_SCAN_PAGES` times:
   - `page = ledger.read_after(cursor, scope=flt.scope, limit=PAGE)`.
   - For each `event` in `page`, in order:
     - if `flt.matches(event)`: if `events` already holds `limit` events, stop and return
       `ChangePage(events, events[-1].seq, True)` (the extra event is not consumed; the next call finds it again); otherwise append it.
     - then set `cursor = event.seq` (not for the extra event, which returned above).
   - If `len(page) < PAGE` the log has no more rows: return `ChangePage(events, cursor, False)`.
4. After the loop (the scan cap was reached with full pages) return `ChangePage(events, cursor, True)`.

So `next_seq` is the seq of the last event examined, which moves past rejected events, except when the page filled up: then it is the
last event returned. `has_more` is true only when the call stopped early (limit or scan cap).

Learnings that apply:
- Provided tests live in `docs/tickets/P0-I4/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copy.
- pyright is `strict` for `packages/tl-core/src`; ruff limits lines to 100 columns. Run `uv run ruff format` before committing.
  `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- The stub had its unused imports removed; add back the ones you use (`ANY`).
- Remove the `STUB (P0-I4-T01)` paragraph from the module docstring when you are done.
- Commit your report file (see Allowed paths); an uncommitted report cost earlier tickets a retry.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-core/src/tl_core/changefeed/pager.py (stub; names, constants and signature are final)
DEFAULT_LIMIT = 500
PAGE = 500  # rows read from the ledger per query
MAX_SCAN_PAGES = 20  # ledger pages examined per call; bounds the work for a very selective filter

@dataclass(frozen=True)
class ChangePage:
    events: list[Event]
    next_seq: int  # pass as ``after_seq`` to get the next page; never less than ``after_seq``
    has_more: bool  # True when more events may follow (limit or scan cap reached)

def fetch_changes(ledger: Ledger, *, after_seq: int = 0, flt: SubscriptionFilter | None = None,
                  limit: int = DEFAULT_LIMIT) -> ChangePage: ...
```
```python
# packages/tl-core/src/tl_core/changefeed/filters.py (exists)
@dataclass(frozen=True)
class SubscriptionFilter:
    scope: str | None = None
    event_types: tuple[str, ...] | None = None
    record_ids: frozenset[str] | None = None
    def matches(self, event: Event) -> bool: ...
ANY = SubscriptionFilter()
```
```python
# tl_core.ledger.Ledger (Protocol), the one method you call
def read_after(self, seq: int, *, scope: str | None = None, limit: int = 1000) -> list[Event]: ...
# events with seq > the argument, ascending, optionally only one scope, at most `limit`
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-core/src/tl_core/changefeed/pager.py`
- `docs/tickets/P0-I4/provided/test_changefeed_pager.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-core/src/tl_core/changefeed/pager.py` (edit)
- `packages/tl-core/tests/test_changefeed_pager.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I4/P0-I4-T01.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I4/provided/test_changefeed_pager.py.txt packages/tl-core/tests/test_changefeed_pager.py`
2. Implement `fetch_changes`; delete the STUB paragraph.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-core/tests/test_changefeed_pager.py -q
just check
just test
diff docs/tickets/P0-I4/provided/test_changefeed_pager.py.txt packages/tl-core/tests/test_changefeed_pager.py
```
Expected: 16 tests pass, `just check` and `just test` exit 0, `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus the decisive lines of the four acceptance commands. Commit the report file.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification.
- Stop rather than change any other file.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
