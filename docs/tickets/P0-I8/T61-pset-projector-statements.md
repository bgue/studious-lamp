# P0-I8-T61 — PsetProjector: one insert per record, no reads for a new record

Status: ready
Tier: haiku
Labels: core
Depends on: P0-I8-S62 (base of this branch)
Branch: `p0/i8d-t61-pset-projector-statements`

## Goal
`PsetProjector` writes the `cur_pset_values` rows of a record with one multi-row `INSERT` instead of one `INSERT` per value, and projects `Record.Created` without reading the record back or deleting rows that cannot exist. A new record with five pset values costs two statements instead of nine. The rows written are identical; the provided test `packages/tl-core/tests/test_pset_projector_statements.py` pins both the budget and the rows.

## Why (numbers)
The P0-I8 bench rebuilds 10,000 records (36,179 events) in 52.9 s on SQLite; `pset_values` is 7.2 s of the 47 s spent in projectors. On Postgres a statement costs about 0.5 ms (a pure-Python driver and a round trip), so the projector's nine statements per record dominate a rebuild and a bulk load. Fewer statements is the fix; the data stays the same.

## Brief references (pasted)
> **Current-state rule (brief §5.4):** a projector is deterministic and idempotent; a rebuild replays the ledger into empty tables and must give the same rows. `cur_pset_values` is always a function of `psets_json`: after any event that changes the psets of a record its rows are rebuilt from the new JSON, keeping the units already recorded for unchanged paths.

## Interfaces (verbatim from repo at the branch point)
Existing constants and entry points of `packages/tl-core/src/tl_core/projection/pset.py` (the lines this ticket changes):
```python
_UNITS_SQL = text(
    "SELECT path, unit FROM cur_pset_values WHERE record_id = :id AND unit IS NOT NULL"
)
_DELETE_SQL = text("DELETE FROM cur_pset_values WHERE record_id = :id")
_INSERT_SQL = text(
    "INSERT INTO cur_pset_values (record_id, scope, path, pset, property_name, layer, value_type, "
    "value_text, value_num, value_bool, value_json, unit, last_seq, updated_at) VALUES "
    "(:record_id, :scope, :path, :pset, :property_name, :layer, :value_type, "
    ":value_text, :value_num, :value_bool, :value_json, :unit, :last_seq, :updated_at)"
)

    def apply(self, conn: Connection, event: Event) -> None:
        if event.event_type == VALUES_SET:
            self._values_set(conn, event)
            return
        if event.event_type == "Record.Created":
            touched = "psets" in event.payload
        else:
            touched = "psets" in event.payload.get("changes", {})
        if touched:
            self._sync(conn, event, {})

    def _sync(
        self,
        conn: Connection,
        event: Event,
        new_units: dict[str, str],
        psets: dict[str, Any] | None = None,
    ) -> None:
        """Rebuild this record's ``cur_pset_values`` rows and promoted columns from its psets."""
        if psets is None:
            psets = self._load(conn, event)
        kept = {r.path: r.unit for r in conn.execute(_UNITS_SQL, {"id": event.stream_id})}
        conn.execute(_DELETE_SQL, {"id": event.stream_id})
        stamp = iso_utc(event.recorded_at)
        for segments, value in flatten(psets):
            path = "psets." + ".".join(segments)
            pset, prop, layer = classify(segments)
            conn.execute(
                _INSERT_SQL,
                {
                    "record_id": event.stream_id,
                    "scope": event.scope,
                    "path": path,
                    "pset": pset,
                    "property_name": prop,
                    "layer": layer,
                    "unit": new_units.get(path, kept.get(path)),
                    "last_seq": event.seq,
                    "updated_at": stamp,
                    **typed_columns(value),
                },
            )
        self._update_promoted(conn, event.stream_id, psets)
```
`flatten`, `classify`, `typed_columns`, `_update_promoted` stay as they are. `Record.Created` carries the whole value set in `event.payload["psets"]` (a dict, possibly empty), and `RecordProjector` stored the same dict canonically in `cur_core_record.psets_json`.

## Context (read these, nothing else)
- `packages/tl-core/src/tl_core/projection/pset.py` (the file to change)
- `packages/tl-core/tests/test_pset_projector_statements.py` (provided; the spec: read every assertion; do not edit)
- `packages/tl-core/tests/test_pset_projector.py` (existing behaviour tests; must keep passing; do not edit)
may explore: (none)

## Allowed paths
- `packages/tl-core/src/tl_core/projection/pset.py`

## Steps
1. Replace the single-row `_INSERT_SQL` with a helper that inserts many rows with one statement: build `INSERT INTO cur_pset_values (<the 14 columns>) VALUES (:c_0, ...), (:c_1, ...)` with numbered bound parameters (`record_id_0`, `record_id_1`, ...), never splicing a value into the SQL text. Insert in chunks of 500 rows so a record with thousands of values stays under the engines' limits on bound parameters. The text is plain portable SQL: it must run on SQLite and Postgres unchanged.
2. Use the helper in `_sync` (the path for `Pset.ValuesSet` and for `Record.Updated`/`Record.Corrected`) in place of the loop; keep the `_UNITS_SQL` read and the `_DELETE_SQL` there, because those events change a record that already has rows.
3. In `apply`, for `Record.Created` add a path `_create` that takes the value set from `event.payload.get("psets") or {}`, inserts its rows with the helper (units are all `None`: a new record has none), then calls `_update_promoted(conn, event.stream_id, psets)` exactly as `_sync` does. It must not read `cur_core_record` and must not run the units read or the delete.
4. Everything else (row contents, column order of the rows, `typed_columns`, `classify`, the promoted-column update) stays byte for byte the same.

## Acceptance
```
uv run pytest packages/tl-core/tests/test_pset_projector_statements.py packages/tl-core/tests/test_pset_projector.py -q --adapters sqlite,postgres
uv run pytest tests/property -q -k projection
just check
```
Expected: all pass on both adapters (Postgres must be reachable at `TL_PG_URL`; `sudo pg_ctlcluster 16 main start` if not); `just check` clean.

## Tests to add
None: the provided test file is the spec. Do not edit it.

## Report requirements
Standard report. Paste the statement counts the provided test asserts (the two budget tests) and the pytest summary lines of all three commands.

## Learnings to apply (from the project memory)
- Run `just check` before you report: it lints `dev/` as well as the package, and a one-line E501 failed a whole batch once.
- A docstring that holds a backslash must escape it (`\\s`), or the module warns at import.

## Escalation triggers
- Stop and report *Blocked* if an existing test in `test_pset_projector.py` fails after the change and the fix would need an edit outside `pset.py`.
- Stop if Postgres rejects the multi-row insert (for example "could not determine data type of parameter"): report the error text; do not add a cast per dialect.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
