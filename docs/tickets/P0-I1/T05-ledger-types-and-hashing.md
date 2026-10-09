# P0-I1-T05 — Ledger types and hashing

Status: draft (ready when T01 merges)
Tier: haiku
Labels: core
Depends on: P0-I1-T01
Branch: `p0/i1-t05-ledger-types`

## Goal
The ledger's value types (`NewEvent`, `Event`, `AppendResult`, `ConcurrencyError`), the `Ledger` Protocol, canonical
JSON serialisation, UTC timestamp formatting, and the per-scope hash-chain function, with fixed test vectors, plus two
tiny shared helpers (`utcnow`, `new_ulid`). Nothing stores anything yet.

## Brief references (pasted)
> Every write is a command validated by the service layer, which emits one or more events in a single transaction. Fields: `seq` global monotonic; `event_id` ULID; `stream_id`; `stream_type`; `stream_version` per-record, optimistic concurrency; `event_type`; `schema_version`; `scope` `company` or `project:{id}`; `payload` JSON; `actor`; `recorded_at` system time; `effective_at` business time; `correlation_id`/`causation_id`; `source`; `prev_hash`/`hash` hash chain per scope for tamper evidence. (§5.1)
> No updates, no deletes on the event table. Corrections are explicit events. (§5.2)

Learnings that apply: `uv` prints a harmless "UV_NATIVE_TLS is deprecated" warning on every call. Run commands with
`export PATH="$HOME/.local/bin:$PATH"`.

## Interfaces (verbatim)

`packages/tl-core/src/tl_core/ledger/types.py` (create exactly this; add a module docstring):
```python
from __future__ import annotations
from datetime import datetime
from typing import Any, Protocol, Sequence
from pydantic import BaseModel

class NewEvent(BaseModel):
    """What a command handler emits. The ledger fills seq, stream_version, hashes, recorded_at."""
    event_type: str                 # e.g. "Record.Created"
    schema_version: int = 1
    payload: dict[str, Any]
    effective_at: datetime | None = None   # defaults to recorded_at

class Event(BaseModel):
    """A stored event: NewEvent's fields (effective_at required) plus the ledger-assigned ones."""
    event_type: str
    schema_version: int = 1
    payload: dict[str, Any]
    seq: int
    event_id: str                   # ULID
    stream_id: str
    stream_type: str
    stream_version: int
    scope: str                      # "company" | "project:<id>"
    actor: str                      # "user:<id>" | "svc:<name>" | "agent:<id>" (+ on_behalf_of in payload)
    recorded_at: datetime
    effective_at: datetime
    correlation_id: str
    causation_id: str | None
    source: str
    prev_hash: str | None
    hash: str

class AppendResult(BaseModel):
    events: list[Event]
    new_version: int
    last_seq: int

class ConcurrencyError(Exception):
    """expected_version did not match the stream's current version."""

class Ledger(Protocol):
    def append(
        self,
        *,
        stream_id: str,
        stream_type: str,
        scope: str,
        expected_version: int,          # 0 for a new stream
        events: Sequence[NewEvent],
        actor: str,
        source: str,
        correlation_id: str,
        causation_id: str | None = None,
    ) -> AppendResult: ...
    def read_stream(self, stream_id: str, *, from_version: int = 1) -> list[Event]: ...
    def read_after(self, seq: int, *, scope: str | None = None, limit: int = 1000) -> list[Event]: ...
    def head_seq(self) -> int: ...
    def stream_version(self, stream_id: str) -> int: ...   # 0 if absent
```
Note: `Event` deliberately does not subclass `NewEvent` (pyright strict rejects narrowing `effective_at` in a subclass).
The field names and types are the same as in `docs/build-spec/03-repo-and-toolchain.md` §7. Copy the block as written.

`packages/tl-core/src/tl_core/ledger/hashing.py` (create):
```python
def canonical_json(payload: Mapping[str, Any]) -> str:
    """json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)"""

def iso_utc(moment: datetime) -> str:
    """Timezone-aware datetimes only (raise ValueError for naive). Convert to UTC and return
    moment.astimezone(UTC).isoformat(timespec="microseconds"), e.g. '2026-01-01T00:00:00.000000+00:00'.
    Use `from datetime import UTC`."""

def event_hash(prev_hash: str | None, event_id: str, stream_id: str, stream_version: int,
               event_type: str, payload_canonical_json: str, recorded_at_iso: str) -> str:
    """SHA-256 hex over the concatenation with '\n' separators; prev_hash '' when None.
    Chain is per scope: prev_hash is the hash of the previous event in the same scope."""
```
Hash input string, joined with `"\n"`, in this order: `prev_hash or ""`, `event_id`, `stream_id`, `str(stream_version)`,
`event_type`, `payload_canonical_json`, `recorded_at_iso`. Encode as UTF-8. Output: lowercase hex SHA-256.

`packages/tl-core/src/tl_core/util.py` (create):
```python
def utcnow() -> datetime:
    """Current time, timezone-aware UTC: datetime.now(UTC)."""
def new_ulid() -> str:
    """A new ULID as a 26-character string, using python-ulid: str(ULID())."""
```

`packages/tl-core/src/tl_core/ledger/__init__.py` re-exports: `NewEvent, Event, AppendResult, ConcurrencyError, Ledger,
canonical_json, iso_utc, event_hash` with an `__all__`.

Style: the pasted blocks are shown compactly. If ruff reports import order or `typing.Sequence` (UP035), run
`uv run ruff check --fix` and `uv run ruff format` on your new files; that is not a deviation. Add a one-line docstring to
each new module.

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-core/src/tl_core/__init__.py`
- `packages/tl-core/pyproject.toml` (to confirm `pydantic` and `python-ulid` are already dependencies; do not edit it)

## Allowed paths
- `packages/tl-core/src/tl_core/ledger/__init__.py` (create)
- `packages/tl-core/src/tl_core/ledger/types.py` (create)
- `packages/tl-core/src/tl_core/ledger/hashing.py` (create)
- `packages/tl-core/src/tl_core/util.py` (create)
- `packages/tl-core/tests/test_ledger_types.py`, `packages/tl-core/tests/test_hashing.py` (create)

## Acceptance
```
just check
uv run pytest packages/tl-core/tests/test_ledger_types.py packages/tl-core/tests/test_hashing.py -q
```
Expected: all pass; pyright strict clean for `tl_core` (`just check` prints `0 errors`).

## Tests to add
- `test_hashing.py`:
  - vector 1: `event_hash(None, "01J00000000000000000000000", "s1", 1, "Record.Created", '{"a":1}', "2026-01-01T00:00:00.000000+00:00")`
    equals the literal `69d2a9ba6e245b32d4fb2ab928026347dfd99bbb0ef866c11faf19256a84469d`.
  - vector 2: the same call with `prev_hash` set to vector 1's value equals the literal
    `aadeb1f9ad0da9535605bbf2ed35c6fd7cc3b63fe85775fe6ccdca22936e1eb5`.
  - the same two calls also equal a recomputation in the test using `hashlib.sha256("\n".join([...]).encode("utf-8")).hexdigest()`.
  - `canonical_json` is stable under key order and for nested dicts (`{"b":1,"a":{"d":1,"c":2}}` gives `{"a":{"c":2,"d":1},"b":1}`); non-ASCII is preserved (`{"k":"é"}` gives `{"k":"é"}`, not an escape).
  - `iso_utc` formats `datetime(2026,1,1,tzinfo=UTC)` as `2026-01-01T00:00:00.000000+00:00`; converts `+02:00` input to UTC; raises `ValueError` for a naive datetime.
- `test_ledger_types.py`:
  - `NewEvent` requires `event_type` and `payload` (pydantic `ValidationError`); `schema_version` defaults to 1; `effective_at` defaults to `None`.
  - `Event` rejects a missing `hash` (`ValidationError`); a fully constructed `Event` round-trips through `model_dump_json` and `model_validate_json`.
  - `AppendResult.new_version` equals the last event's `stream_version` in a constructed example with two events.
  - `ConcurrencyError` is an `Exception` subclass.
  - `utcnow()` is timezone-aware with `utcoffset() == timedelta(0)`; `new_ulid()` returns 26 characters, and two calls differ.

## Report requirements
Standard report. Paste the two vector hex values as your tests assert them.

## Escalation triggers
- Stop if the pasted interface conflicts with anything already under `packages/tl-core/src/tl_core/ledger/`.
- Stop if pyright strict rejects an interface line; do not add ignores or change the interface.

## Blocked

## Decision
