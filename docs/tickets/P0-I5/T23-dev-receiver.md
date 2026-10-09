# P0-I5-T23 — Dev webhook receiver

Status: ready
Tier: haiku
Labels: core, tests
Depends on: — (signing, the stub and the provided test are on the base branch)
Branch: `p0/i5b-t23-dev-receiver`

## Goal
`tl_core.webhooks.receiver.DevReceiver` is a small HTTP server on 127.0.0.1 that plays the part of a customer's webhook endpoint in
development, tests and the demo: it verifies the Standard Webhooks signature of every POST, answers 200 for a good message and 401 for a
bad one, records both, treats a repeated `webhook-id` as a duplicate (still 200), and can be told to fail the next requests with chosen
statuses. The dataclass `Received` and all signatures exist in the stub; every method body raises `NotImplementedError`. A provided test
file (9 tests) must pass. There is no outbound internet here, so this server is how every webhook test reaches a real socket.

## Brief references (pasted)
> **18.4 Outbound webhooks.** Security: HMAC-SHA256 signatures (Standard Webhooks headers: id, timestamp, signature). Secret rotation with
> overlap. Replay: replay by `seq` range, time range, or DLQ selection. Receivers dedupe on the event `id`. Testing: "Send test event"
> with sample payload from the catalog; local tunnel support in dev.

### Specification (the provided test checks it)
- `__init__(secrets=(), *, host="127.0.0.1", port=0, tolerance_s=300, clock=time.time)`: wrap each secret string in `SigningSecret`;
  keep a `threading.Lock`/`Condition` for shared state; nothing is bound yet.
- `start()`: `RuntimeError("the receiver is already running")` if running. Otherwise create a `ThreadingHTTPServer((host, port), Handler)`
  and run `serve_forever` in a daemon thread named `tl-dev-receiver`. `port` (property) is the bound port (`server_address[1]`) and
  raises `RuntimeError("the receiver is not running")` while stopped. `url` is `f"http://{host}:{port}/hook"`.
- `stop()`: no server means return; otherwise `shutdown()`, `server_close()`, join the thread (timeout 5 s), forget both. Calling it twice
  is fine. `__enter__` starts and returns `self`; `__exit__` stops.
- The handler answers **POST** on any path. Read `Content-Length` bytes as the body (decode UTF-8, `errors="replace"`), lower-case the header
  names into a dict, and call one private method, `_handle(path, headers, body) -> (status, answer_dict)`, which does everything under the
  lock and then the handler writes `json.dumps(answer)` with `Content-Type: application/json` and the right `Content-Length`. Silence
  `log_message`.
- `_handle`: `verified` is true when `verify(headers, body, self._secrets, now=self._clock(), tolerance_s=self._tolerance)` returns, false
  when it raises `SignatureError`. `message_id = headers.get("webhook-id", "")`.
  1. If a scripted status is waiting (`fail_next`), pop the first one, record a `Received(..., verified=<as computed>, duplicate=False)` in
     the **rejected** list, notify waiters and answer `(status, {"ok": False, "scripted": True})`.
  2. Else if not verified: record in the rejected list and answer `(401, {"ok": False, "error": "bad signature"})`.
  3. Else: `duplicate = message_id in seen`; add the id to `seen`; append a `Received(..., verified=True, duplicate=duplicate)` to the accepted
     list; notify waiters; answer `(200, {"ok": True, "duplicate": duplicate})`.
- `fail_next(statuses)` appends to the script. `set_secrets(secrets)` replaces the secrets (so a rotation overlap with two secrets accepts
  either). `messages()` / `rejected()` return **copies** of the lists; `unique()` is the accepted messages with `duplicate` false.
- `wait_for(count, timeout_s=10.0)`: wait on the condition until `len(accepted) >= count`; return `False` when the timeout passes.
- `clear()` empties accepted, rejected, script and seen.

Learnings that apply:
- Provided tests live in `docs/tickets/P0-I5/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copy.
- Threads in tests are daemon threads joined with a timeout so a regression fails instead of hanging; keep the server thread a daemon.
- pyright is `strict` for `packages/tl-core/src`; ruff limits lines to 100 columns; run `uv run ruff format` before committing. `uv`
  prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into another command.
- A fresh worktree has no workspace packages installed: run `uv sync --all-packages` once before the first test.
- Ruff wants `# noqa: N802` on the `do_POST` method name and `# noqa: A002` on a `format` parameter that shadows the builtin.
- Remove the `STUB (P0-I5-T23)` paragraph from the module docstring when you are done.
- Commit your report file (see Allowed paths); an uncommitted report cost earlier tickets a retry.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-core/src/tl_core/webhooks/signing.py (use as is)
class SignatureError(Exception): ...
@dataclass(frozen=True)
class SigningSecret:
    value: str            # "whsec_<base64>"
def verify(headers: Mapping[str, str], body: str | bytes, secrets: Iterable[SigningSecret], *,
           now: float | None = None, tolerance_s: int = 300) -> str: ...   # returns webhook-id or raises SignatureError
```
```python
# packages/tl-core/src/tl_core/webhooks/receiver.py (stub; names and signatures are final)
@dataclass(frozen=True)
class Received:
    path: str; webhook_id: str; body: str; headers: dict[str, str]; verified: bool; duplicate: bool
    def event(self) -> dict[str, Any]: ...        # already written

class DevReceiver:
    def __init__(self, secrets: Sequence[str] = (), *, host: str = "127.0.0.1", port: int = 0,
                 tolerance_s: int = 300, clock: Callable[[], float] = time.time) -> None: ...
    @property
    def port(self) -> int: ...
    @property
    def url(self) -> str: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def __enter__(self) -> DevReceiver: ...
    def __exit__(self, *exc: object) -> None: ...
    def fail_next(self, statuses: Sequence[int]) -> None: ...
    def set_secrets(self, secrets: Sequence[str]) -> None: ...
    def messages(self) -> list[Received]: ...
    def rejected(self) -> list[Received]: ...
    def unique(self) -> list[Received]: ...
    def wait_for(self, count: int, timeout_s: float = 10.0) -> bool: ...
    def clear(self) -> None: ...
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-core/src/tl_core/webhooks/receiver.py`
- `packages/tl-core/src/tl_core/webhooks/signing.py`
- `docs/tickets/P0-I5/provided/test_webhook_receiver.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-core/src/tl_core/webhooks/receiver.py` (edit)
- `packages/tl-core/tests/test_webhook_receiver.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I5/P0-I5-T23.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I5/provided/test_webhook_receiver.py.txt packages/tl-core/tests/test_webhook_receiver.py`
2. Implement the class; delete the STUB paragraph.
3. Run the acceptance commands (the receiver test file three times), write the report, commit the code and the report.

## Acceptance
```
uv run pytest packages/tl-core/tests/test_webhook_receiver.py -q
just check
just test
diff docs/tickets/P0-I5/provided/test_webhook_receiver.py.txt packages/tl-core/tests/test_webhook_receiver.py
```
Expected: 9 tests pass (every time of three runs), `just check` and `just test` exit 0, `diff` prints nothing.

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
