# P0-I5-T24 — Webhook worker loop

Status: ready
Tier: haiku
Labels: core
Depends on: — (the dispatcher, the delivery engine, the stub and the provided test are on the base branch)
Branch: `p0/i5b-t24-webhook-worker`

## Goal
`tl_core.webhooks.worker.WebhookWorker` runs the dispatcher and the delivery engine on a loop: each cycle turns new outbox rows into
deliveries, claims the head of every subject's queue and sends them on a thread pool, and `start` / `stop` run the cycles on a daemon
thread. The dataclass `CycleResult` and every signature exist in the stub; all method bodies raise `NotImplementedError`. A provided test
file (10 tests) must pass. Signing, ordering and retries are already in the engine; this ticket only schedules them.

## Brief references (pasted)
> **18.4 Outbound webhooks.** Delivery: Transactional **outbox** written with the event, then delivered by workers. At-least-once delivery,
> ordered per subject (record), parallel across subjects.

### Specification (the provided test checks it)
- `__init__(dispatcher, engine, *, threads=4, claim_limit=16, interval_s=0.5)`: raise `ValueError` for `threads < 1`, `claim_limit < 1`
  or `interval_s <= 0`. Store the arguments; create `self._stop = threading.Event()`, `self._thread: threading.Thread | None = None` and
  `self._error: Exception | None = None`.
- `running`: the thread exists and `is_alive()`. `last_error`: `self._error`.
- `run_cycle()`: `created = self._dispatcher.run_until_idle().created`; `claims = self._engine.claim(self._claim_limit)`; build
  `CycleResult(dispatched=created, claimed=len(claims))`. If there are claims, deliver them concurrently:
  `with ThreadPoolExecutor(max_workers=min(self._threads, len(claims)), thread_name_prefix="tl-webhook") as pool:` and for each
  `settled` in `pool.map(self._engine.deliver, claims)` add one to `delivered` when `settled.state == "delivered"`, to `retried` when
  `"retry"`, to `dead` when `"dead"`, and add `settled.disabled_subscription` to `disabled`. Return the result. The claims of one cycle
  are the heads of different subjects (the engine guarantees it), so sending them together never reorders a subject.
- `drain(*, max_cycles=1000)`: run up to `max_cycles` cycles, summing every counter into one `CycleResult`; stop after the first cycle whose
  `idle` is true (that cycle is included in the sum).
- `start()`: `RuntimeError("the worker is already running")` if `running`; otherwise clear the stop event and start a daemon thread named
  `tl-webhook-worker` running a private `_run`.
- `_run()`: `while not self._stop.is_set()`: `idle = True`; `try:` `idle = self.run_cycle().idle` and set `self._error = None`;
  `except Exception as exc:` store it in `self._error` and `log.warning("webhook cycle failed: %s", exc)` (the loop must go on);
  then, only when `idle` is true, `self._stop.wait(self._interval)`. A busy cycle loops again at once.
- `stop(timeout=10.0)`: no thread means return; otherwise set the stop event, `join(timeout)`, and drop `self._thread` once it has finished.
  Twice is harmless; after `stop`, `start` works again. `__enter__` starts and returns `self`; `__exit__` stops.
- Add `log = logging.getLogger(__name__)`.

Learnings that apply:
- Provided tests live in `docs/tickets/P0-I5/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copy.
- Threads in tests are daemon threads with timeouts so a regression fails instead of hanging; keep the loop thread a daemon.
- pyright is `strict` for `packages/tl-core/src`; ruff limits lines to 100 columns; run `uv run ruff format` before committing. `uv`
  prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into another command.
- A fresh worktree has no workspace packages installed: run `uv sync --all-packages` once before the first test.
- The test imports `from world import World`: `tests/webhooks/conftest.py` puts its directory on `sys.path`, so the copy must live in
  `tests/webhooks/`.
- Remove the `STUB (P0-I5-T24)` paragraph from the module docstring when you are done.
- Commit your report file (see Allowed paths); an uncommitted report cost earlier tickets a retry.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-core/src/tl_core/webhooks/delivery.py (use as is)
class DeliveryEngine:
    def claim(self, limit: int = 10) -> list[Claim]: ...
    def deliver(self, claim: Claim) -> Settled: ...      # attempt + settle; thread safe
@dataclass(frozen=True)
class Settled:
    delivery_id: str; state: str   # "delivered" | "retry" | "dead" | "lost"
    attempt: int = 0; status: int | None = None; next_attempt_at: datetime | None = None
    dead_reason: str | None = None; disabled_subscription: bool = False
```
```python
# packages/tl-core/src/tl_core/webhooks/dispatch.py (use as is)
class Dispatcher:
    def run_until_idle(self, *, limit: int = 500) -> DispatchStats: ...   # .created = deliveries created
```
```python
# packages/tl-core/src/tl_core/webhooks/worker.py (stub; names and signatures are final)
@dataclass
class CycleResult:
    dispatched: int = 0; claimed: int = 0; delivered: int = 0; retried: int = 0; dead: int = 0; disabled: int = 0
    @property
    def idle(self) -> bool: ...          # already written

class WebhookWorker:
    def __init__(self, dispatcher: Dispatcher, engine: DeliveryEngine, *, threads: int = 4,
                 claim_limit: int = 16, interval_s: float = 0.5) -> None: ...
    @property
    def running(self) -> bool: ...
    @property
    def last_error(self) -> Exception | None: ...
    def run_cycle(self) -> CycleResult: ...
    def drain(self, *, max_cycles: int = 1000) -> CycleResult: ...
    def start(self) -> None: ...
    def stop(self, timeout: float = 10.0) -> None: ...
    def __enter__(self) -> WebhookWorker: ...
    def __exit__(self, *exc: object) -> None: ...
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-core/src/tl_core/webhooks/worker.py`
- `docs/tickets/P0-I5/provided/test_webhook_worker.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-core/src/tl_core/webhooks/worker.py` (edit)
- `tests/webhooks/test_worker.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I5/P0-I5-T24.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I5/provided/test_webhook_worker.py.txt tests/webhooks/test_worker.py`
2. Implement the class; delete the STUB paragraph.
3. Run the acceptance commands (the worker test file three times), write the report, commit the code and the report.

## Acceptance
```
uv run pytest tests/webhooks/test_worker.py -q
just check
just test
diff docs/tickets/P0-I5/provided/test_webhook_worker.py.txt tests/webhooks/test_worker.py
```
Expected: 10 tests pass (every time of three runs), `just check` and `just test` exit 0, `diff` prints nothing.

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
