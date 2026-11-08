# P2-INT-S1 — Event intent: model, column, hash extension, archive, restore, lake bronze

Status: ready
Tier: sonnet
Kind: piece
Review: full
Labels: core, adapter, ledger, human-gate
Depends on: wave 2 close (`p2/wave2-close`)
Branch: `p2/int-s1-event-intent`  (from p2/int at the r1 state commit)
Approver: orchestrator, with an APPROVALS line (core interface change, hash extension, migration-free nullable column)

## Goal
The ledger can store and attest an intent, and nothing yet writes one. After this piece: the `Intent` model exists; `Command`, `NewEvent`, `Event` and
both adapters' `append`/`append_in` carry it; `events.intent` (nullable TEXT, SQLite and Postgres) exists in fresh and existing databases; `event_hash`
takes an optional last part present only when an intent exists; the archive dumps, restores and verifies it; lake bronze has the column. Until S2 merges the
command boundary refuses any non-null intent with `intent_invalid`. Chains, segments and restores made before this piece verify and re-seal unchanged.

## Brief references
> ADR-0025 Decision 1 and 3, answers F4 (dump intent only when set; read the Parquet column only when present; a pre-change segment re-seals byte-identical),
> F5 (no migration runner: idempotent ADD COLUMN per adapter, in restore and in lake bronze; TEXT, not JSONB), F6 (refuse non-null intent until S2), F14
> (normalise `{}` and all-null to None; hash the canonical JSON of the validated model with `exclude_none`). Brief 5.1 (hash chain). AGENTS.md rule 3 (events immutable): the new column is added, never updated.

## Interfaces (names are the contract S2 and the faces call)
```python
# tl_core/intent.py (create). Fields as ADR-0025 d1; extra="forbid"; all optional.
class IntentRef(BaseModel): command: str | None = None; target: str | None = None; text: str | None = None   # next item: {command,target} or {text}
class IntentToward(BaseModel): target: str; state: str | None = None; condition: str | None = None             # state xor condition
class Intent(BaseModel): why: str | None; next: list[IntentRef] = []; toward: IntentToward | None; goal_ref: str | None
def intent_json(intent: Intent | None) -> str | None     # None when intent is None or empty; else canonical_json(model_dump(mode="json", exclude_none=True)) with an empty `next` list dropped
class IntentInvalid(ValueError): code = "intent_invalid"
def check_intent(command) -> None                        # S1 body: raise IntentInvalid("intent_invalid") if command.intent is not None. S2 replaces the body. ONE function.
# Command.intent: Intent | None = None   (tl_core/services/commands.py; NOT counted in the NUL scan twice)
# NewEvent.intent: Intent | None = None;  Event.intent: Intent | None = None   (ledger/types.py)
# hashing.py:  event_hash(..., recorded_at_iso, intent_canonical_json: str | None = None)   # parts.append(intent_canonical_json) only when not None
# append / append_in (Ledger Protocol, AppendInLedger, both adapters): reads NewEvent.intent; stores intent_json; passes it to event_hash.
```
Shape rules: the validated `Intent` (S2 adds the checks) serialises to the stored text by one function only (`intent_json`); the adapters, `recomputed_hash`,
the sealer and restore all call it or read the stored text, never their own dump. An all-empty intent gives `None` before anything is hashed.

## Context (read these, nothing else)
- `packages/tl-core/src/tl_core/ledger/types.py`, `hashing.py`, `services/commands.py` (Command only)
- `packages/tl-adapters/src/tl_adapters/sqlite/ledger.py` (`append_in`, `_row_to_event`), `sqlite/schema.sql`, `postgres/ledger.py`, `postgres/ddl.py` (`EVENTS_DDL`)
- `packages/tl-core/src/tl_core/archive/segments.py` (`EVENT_COLUMNS`, `event_line`, `recomputed_hash`, `event_row`, `encode_parquet`, `parquet_rows`, `parquet_matches`, `decode_ndjson`), `archive/sealer.py`
- `packages/tl-adapters/src/tl_adapters/_restore.py` (`_INSERT`, `_params`), `restore.py`
- `packages/tl-lake/src/tl_lake/schema.py` (bronze `Column(...)` list, ~line 59), `sync.py` (`_redacted` ~line 143, `insert_rows`)
may explore: `tl_adapters/db.py` (where schema is applied at open), `tests/` for archive and parity fixtures.

## Allowed paths
- `packages/tl-core/src/tl_core/intent.py` (create), `ledger/types.py`, `ledger/hashing.py`, `ledger/__init__.py` (export), `services/commands.py` (field only), `archive/segments.py`
- `packages/tl-adapters/src/tl_adapters/sqlite/ledger.py`, `sqlite/schema.sql` (fresh table gets the column), `postgres/ledger.py`, `postgres/ddl.py`, `_restore.py`, `_unit.py` (Protocol signature only)
- `packages/tl-lake/src/tl_lake/schema.py`, `sync.py` (intent column, redaction rule below)
- `packages/tl-core/tests/`, `packages/tl-adapters/tests/`, `packages/tl-lake/tests/` (new test files)
- `dev/accept/P2-INT/S1.py` (create), `docs/reports/P2-INT/S1.md` (create)
Consequential pins (rule 12): a test that pins the `events` column list, `EVENT_COLUMNS`, the event line keys or the bronze column list and breaks only for the new name is updated and listed. No schema/** (LinkML) change, no payload change, no handler change.

## Steps
1. `intent.py` models and `intent_json`; `Command.intent`, `NewEvent.intent`, `Event.intent`; `check_intent` refusing non-null (called by the dispatcher in S2; S1 calls it from `run_command` in `tl_api/commands.py`: ONE added line, allowed).
2. `event_hash` optional part. Table-test: no intent gives the exact old digest for 3 pinned vectors taken from existing tests; with intent differs and is stable.
3. Column. Fresh databases: add `intent TEXT` to `schema.sql` and `EVENTS_DDL`. Existing: an idempotent ensure step run where each adapter opens (SQLite: probe `PRAGMA table_info(events)` then `ALTER TABLE events ADD COLUMN intent TEXT`; Postgres: `ALTER TABLE events ADD COLUMN IF NOT EXISTS intent TEXT`). The append-only triggers stay; ALTER ADD COLUMN touches no row. `INSERT` lists `intent` always (NULL when none); `_row_to_event` reads it by `row.get`.
4. Archive: `event_line` dumps `intent` only when set (the line bytes of an event without intent stay identical to today: exclude the key, do not emit `null`); `Event.model_validate` of an old line still works; `recomputed_hash` passes `intent_json(event.intent)`. Parquet: `intent` is the last of `EVENT_COLUMNS`, written only when any event in the segment has one; `parquet_rows`/`parquet_matches` read the column only when the file has it (probe `DESCRIBE`/schema), a segment without it yields None. A segment with no intent is byte-identical to a pre-change one.
5. Restore: `_INSERT` and `_params` add `intent` (text as sealed). Restore into a database whose `events` lacks the column runs the ensure step first.
6. Lake bronze: add `Column("intent", "VARCHAR")`, with the ALTER ADD COLUMN pattern already used at `sync.py` ~321 for an existing bronze table. Redaction (ADR-0025 d5): for a redacted or hidden event row the intent is dropped (`None`), exactly where the payload is; for a visible row of a non-internal record it is kept.
7. `intent_invalid` text is fixed: `intent not accepted`. No echo of the content.

## Acceptance (run once, named gate paths only; the supervisor runs nothing)
```
just check
just gate packages/tl-core/tests packages/tl-adapters/tests packages/tl-lake/tests
just gate-pg packages/tl-adapters/tests
uv run python dev/accept/P2-INT/S1.py --keep .accept/p2-int.db
```
`dev/accept/P2-INT/S1.py` (create) appends with and without intent through both adapters, seals, restores, verifies, and prints one PASS line per check.

## Tests to add (pytest; the piece owns them)
- `packages/tl-core/tests/test_event_hash_intent.py`: old vectors unchanged; intent changes the hash; `{}`/all-null normalise to None before hashing.
- `packages/tl-core/tests/test_archive_intent_compat.py`: **a segment sealed from events without intent, built from a committed fixture or a fresh seal with the pre-change code path, re-seals byte-identical (ndjson, parquet, manifest hashes); a segment with intents verifies and round-trips; a pre-change parquet (no `intent` column) reads as None.**
- `packages/tl-adapters/tests/test_events_intent_column.py` (both adapters, parity): fresh and pre-existing DB (create without the column, open, column exists, rerun idempotent), append stores text, `read_stream` returns the model, hash matches `recomputed_hash`, UPDATE still refused.
- `packages/tl-adapters/tests/test_restore_intent.py`: seal, restore, re-verify with intents.
- `packages/tl-lake/tests/test_bronze_intent.py`: column present on new and old bronze; hidden row drops intent.
- `packages/tl-api/tests/test_command_refuses_intent_until_s2.py` (removed by S2): a command with non-null intent answers `intent_invalid`, nothing appended.

## Mutants (builder, own worktree, report 3 lines)
Sentinel plus at most 5: drop the intent part from `event_hash`; emit `intent: null` in the line; read the Parquet column unconditionally; skip the ensure step in restore; keep intent on a redacted bronze row.

## Report requirements
Standard report (`docs/templates/haiku-report.md` style, ≤ 60 lines) plus the list of consequential pins and the three pinned old hash vectors. Candidate learning: the optional-part hash rule.

## Escalation triggers
- Stop and report *Blocked* if a pre-change segment does not re-seal byte-identical, if `schema/**` or a handler needs a change, or if any adapter path other than the two ledgers builds an `events` insert.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
