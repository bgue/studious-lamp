# P0-I4-T02 — Change poller: `ChangePoller`

Status: ready
Tier: haiku
Labels: core
Depends on: — (the registry and stub are on the base branch)
Branch: `p0/i4a-t02-change-poller`

## Goal
`tl_core.changefeed.poller.ChangePoller` reads `Ledger.read_after` from a `seq` cursor and hands each page to a
`SubscriptionRegistry`, either on demand (`poll_once`) or on a daemon thread (`start` / `stop`). A process that shares the database
with a writer but not its in-process bus (the API server, a CLI watcher) uses it to hear about changes. The class, its docstrings and
all signatures exist in the stub; seven bodies raise `NotImplementedError`. A provided test file (19 tests) must pass.

## Brief references (pasted)
> **5.3 Realtime data access.** Change feed source (dev): in-process bus fed on commit; polling by `seq` for out-of-process readers.
> Delivery semantics: at-least-once, cursor-based (`seq`); clients resume from last `seq`. Every open TUI screen subscribes to the
> records it shows; rows update live.

### Specification (the provided test checks it)
- `__init__`: validate first (`after_seq` given and negative, `interval_s <= 0`, `page_size < 1` each raise `ValueError` with a
  message that names the argument). Store the arguments. The cursor starts at `ledger.head_seq()` when `after_seq is None`, else at
  `after_seq`. Create `self._error: Exception | None = None`, `self._stop = threading.Event()` and `self._thread: threading.Thread | None = None`.
- `cursor` returns the cursor; `last_error` returns `self._error`; `running` is true while the thread exists and `is_alive()`.
- `poll_once()`: loop `page = ledger.read_after(cursor, scope=self._scope, limit=page_size)`; an empty page ends the loop; otherwise call
  `registry.dispatch(page)`, **then** set the cursor to `page[-1].seq` and add `len(page)` to the total; a page shorter than `page_size`
  ends the loop (no further read). Return the total. Exceptions from the ledger propagate and leave the cursor where it was.
  (The registry catches subscriber errors itself; the cursor moves only after `dispatch` returned, so a crash repeats events, which
  the registry drops for subscribers that saw them.)
- `start()`: raise `RuntimeError("the poller is already running")` if `running`; otherwise clear the stop event and start a daemon
  `threading.Thread(target=self._run, name="tl-change-poller", daemon=True)`.
- `_run()` (private helper you add): `while not self._stop.is_set()`: try `self.poll_once()` and set `self._error = None`; on
  `Exception` store it in `self._error` and `log.warning("change-feed poll failed: %s", exc)`; then `self._stop.wait(self._interval)`.
- `stop(timeout=5.0)`: no thread means return; otherwise set the stop event, `join(timeout)`, and drop `self._thread` once it has
  finished. Calling it twice is fine. After `stop`, `start` works again.

Learnings that apply:
- Provided tests live in `docs/tickets/P0-I4/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copy.
- Threads in tests are daemon threads joined with a timeout so a regression fails instead of hanging; keep that in mind for `_run`.
- pyright is `strict` for `packages/tl-core/src`; ruff limits lines to 100 columns. Run `uv run ruff format` before committing.
  `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- The stub had its unused imports removed; add back the ones you use (`threading`). `log` is defined and used by `_run`.
- Remove the `STUB (P0-I4-T02)` paragraph from the module docstring when you are done.
- Commit your report file (see Allowed paths); an uncommitted report cost earlier tickets a retry.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-core/src/tl_core/changefeed/poller.py (stub; the class and signatures are final)
class ChangePoller:
    def __init__(self, ledger: Ledger, registry: SubscriptionRegistry, *, after_seq: int | None = None,
                 scope: str | None = None, interval_s: float = 0.25, page_size: int = 500) -> None: ...
    @property
    def cursor(self) -> int: ...
    @property
    def running(self) -> bool: ...
    @property
    def last_error(self) -> Exception | None: ...
    def poll_once(self) -> int: ...
    def start(self) -> None: ...
    def stop(self, timeout: float = 5.0) -> None: ...
    def __enter__(self) -> ChangePoller: ...      # already written: calls start()
    def __exit__(self, exc_type, exc, tb) -> None: ...   # already written: calls stop()
```
```python
# packages/tl-core/src/tl_core/changefeed/registry.py (exists; the only method you call)
class SubscriptionRegistry:
    def dispatch(self, events: Sequence[Event]) -> None: ...   # filters and delivers; never raises for subscriber errors
```
```python
# tl_core.ledger.Ledger (Protocol), the two methods you call
def read_after(self, seq: int, *, scope: str | None = None, limit: int = 1000) -> list[Event]: ...
def head_seq(self) -> int: ...
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-core/src/tl_core/changefeed/poller.py`
- `docs/tickets/P0-I4/provided/test_changefeed_poller.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-core/src/tl_core/changefeed/poller.py` (edit)
- `packages/tl-core/tests/test_changefeed_poller.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I4/P0-I4-T02.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I4/provided/test_changefeed_poller.py.txt packages/tl-core/tests/test_changefeed_poller.py`
2. Implement the seven bodies and `_run`; delete the STUB paragraph.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-core/tests/test_changefeed_poller.py -q
just check
just test
diff docs/tickets/P0-I4/provided/test_changefeed_poller.py.txt packages/tl-core/tests/test_changefeed_poller.py
```
Expected: 19 tests pass, `just check` and `just test` exit 0, `diff` prints nothing. Run the poller test file three times; it must
pass every time.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive lines of the acceptance commands. Commit the report file.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification.
- Stop rather than change any other file.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
