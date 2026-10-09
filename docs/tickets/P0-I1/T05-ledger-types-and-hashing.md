# P0-I1-T05 — Ledger types and hashing

Status: ready
Tier: haiku
Labels: core
Depends on: P0-I1-T01
Branch: `p0/i1/t05-ledger-types`

## Goal
The ledger's value types (`NewEvent`, `Event`, `AppendResult`, `ConcurrencyError`), the `Ledger` Protocol, canonical
JSON serialisation, and the per-scope hash-chain function, with test vectors. Nothing stores anything yet.

## Brief references (pasted)
> Every write is a command validated by the service layer, which emits one or more events in a single transaction. Fields: `seq` global monotonic; `event_id` ULID; `stream_id`; `stream_type`; `stream_version` per-record, optimistic concurrency; `event_type`; `schema_version`; `scope` `company` or `project:{id}`; `payload` JSON; `actor`; `recorded_at` system time; `effective_at` business time; `correlation_id`/`causation_id`; `source`; `prev_hash`/`hash` hash chain per scope for tamper evidence. (§5.1)
> No updates, no deletes on the event table. Corrections are explicit events. (§5.2)

## Interfaces (verbatim)
Implement exactly the classes and signatures in `docs/build-spec/03-repo-and-toolchain.md` §7 blocks
`ledger/types.py` and `ledger/hashing.py`. Canonical JSON: `json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`.
`recorded_at_iso`: ISO 8601 UTC with microseconds and `+00:00`.

Hash input string, joined with `\n`, in this order: `prev_hash or ""`, `event_id`, `stream_id`, `str(stream_version)`,
`event_type`, `payload_canonical_json`, `recorded_at_iso`. Output: lowercase hex SHA-256.

## Context (read these, nothing else)
- `AGENTS.md`
- `docs/build-spec/03-repo-and-toolchain.md` §7 (first three code blocks only)
- `packages/tl-core/src/tl_core/__init__.py`

## Allowed paths
- `packages/tl-core/src/tl_core/ledger/__init__.py` (create, re-export the public names)
- `packages/tl-core/src/tl_core/ledger/types.py` (create)
- `packages/tl-core/src/tl_core/ledger/hashing.py` (create: `canonical_json`, `event_hash`)
- `packages/tl-core/tests/test_ledger_types.py`, `test_hashing.py` (create)

## Acceptance
```
just check
uv run pytest packages/tl-core/tests/test_ledger_types.py packages/tl-core/tests/test_hashing.py -q
```
Expected: all pass; pyright strict clean for `tl_core`.

## Tests to add
- `test_hashing.py`:
  - vector 1: `event_hash(None, "01J00000000000000000000000", "s1", 1, "Record.Created", '{"a":1}', "2026-01-01T00:00:00.000000+00:00")` equals the SHA-256 you compute in the test with `hashlib` from the documented input string (assert against the recomputation, and pin the literal hex in a comment).
  - vector 2: same with `prev_hash` = vector 1 output differs from vector 1.
  - `canonical_json` is stable under key order and nested dicts; non-ASCII preserved.
- `test_ledger_types.py`:
  - `NewEvent` requires `event_type` and `payload`; `schema_version` defaults to 1.
  - `Event` rejects a missing `hash`; `AppendResult.new_version` equals last event's `stream_version` in a constructed example.
  - `ConcurrencyError` is an `Exception` subclass.

## Report requirements
Standard report. Paste the two vector hex values.

## Escalation triggers
- Stop if the pasted interface conflicts with anything already under `packages/tl-core/src/tl_core/ledger/`.

## Blocked

## Decision
