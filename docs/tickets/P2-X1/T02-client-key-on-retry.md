# P2-X1-T02 — Client sends a key on a command and retries once with it

Status: ready
Tier: haiku   kind: ticket   review: full
Labels: api, tests
Depends on: T01 (merged)
Branch: `p2/x1-t02-client-key`   Worktree: `/home/user/wt/x1/t02`

## Goal
`ApiClientBase._send` gives every `POST /commands/<name>` a key (the caller's if the body already has one), and sends that request a second time, with the same key, when the first fails with a connection reset or a timeout. Server replay (S1, T01) makes the second send safe. GETs and all other POSTs stay as they are.

## Brief references (pasted)
> Plan P2-X1: "A retry after a timeout never files a second proposal or creates a second record." Key: printable ASCII 0x21-0x7E, 1..128, no space. Header `Idempotency-Key` and body field `idempotency_key` are both accepted; if both are sent they must be equal (else 422). Two sends of one key with one body: one event set, second answer equals first. Embedded and CLI paths pass no key (not this ticket).

## Interfaces (verbatim, `packages/tl-api/src/tl_api/client/base.py`)
```python
_RESET = (httpx2.ReadError, httpx2.WriteError, httpx2.CloseError, httpx2.RemoteProtocolError)

def _send(self, method, path, *, params=None, json=None, content=None, headers=None) -> httpx2.Response:
    attempts = 2 if method.upper() == "GET" else 1
    response = self._attempt(attempts, method, path, params, json, content, headers)
    ...
def _attempt(self, attempts, method, path, params, json, content, headers) -> httpx2.Response:
    # loops `attempts` times; `except _RESET` retries, `except httpx2.TransportError` raises ApiUnavailableError
def _command(self, name: str, command: Command) -> CommandResult:
    body = command.model_dump(mode="json", exclude={"actor"})
    return CommandResult.model_validate(self._post_json(f"/commands/{name}", body))
```

## Context (read these, nothing else)
- `packages/tl-api/src/tl_api/client/base.py`
- `packages/tl-api/tests/test_client_base.py` (existing pins: a GET timeout is not retried; keep them green)
- `packages/tl-api/tests/test_client_idempotency.py` (provided, red)

## Allowed paths
- `packages/tl-api/src/tl_api/client/base.py`
- `packages/tl-api/tests/test_client_idempotency.py` (provided; do not edit: it must stay byte-identical to `docs/tickets/P2-X1/provided/test_client_idempotency.py`)
- `docs/reports/P2-X1/T02.md`

## Steps
1. In `_send`: when `method.upper() == "POST"` and `path` starts with `/commands/` and `json` is a dict: if `idempotency_key` is absent or `None` in it, copy the dict and set `idempotency_key` to a fresh `uuid.uuid4().hex`. Generate once per `_send` call, before any attempt, so both attempts carry the same key. A key already in the body is never replaced.
2. For that request `attempts = 2`, and a `httpx2.TimeoutException` is retried like `_RESET` (a retry on timeout applies only to this keyed request; a GET timeout stays unretried, a plain POST stays single-send).
3. Two failures raise `ApiUnavailableError` with the last cause, as now. An error status answer (400+) is never retried.
4. No change to `_command` unless needed; no change to other files.

## Acceptance
```
just check
just gate packages/tl-api/tests/test_client_idempotency.py packages/tl-api/tests/test_client_base.py packages/tl-api/tests/test_client_records.py packages/tl-api/tests/test_client_proposals.py
```
Expected: all pass.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report. State: the key format used; the exact retry rule; that the provided test is byte-identical (101).

## Escalation triggers
- A test outside Allowed paths breaks (e.g. one that counts requests on a POST /commands/ failure): list it and stop.
- The remote TUI or another caller sets its own header `Idempotency-Key`: stop and report.
