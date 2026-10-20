# P1-I5-T03a — CorrespondenceProjector: the item events into the item and clearance tables

Status: ready
Tier: haiku
Labels: core, module
Depends on: — (the schema, names, `_common.py` and the generated DDL are in the tree at the branch point)
Branch: `p1/i5-t03a-correspondence-projector`

## Goal
`CorrespondenceProjector` writes `cur_correspondence_correspondence` and `cur_correspondence_clearance` from the eleven `Correspondence.*` events. `projectors/correspondence.py` has the class, its `name`, `handles` and `ddl` and the `_UPDATABLE` map written; `apply` and `reset` raise `NotImplementedError`. You implement them by their STEPS comments. One provided test file must pass on SQLite and on Postgres.

## Brief references (pasted)
> **Module storage rule (ADR-0010).** Every record of the module is a row of `cur_core_record` (the envelope: key, title, status, version) and a row of the module's own table, joined on `id`. `Record.Created` makes the envelope row; the module's first event (`Correspondence.Defined`) follows it in the same append and carries the typed fields. The subject of an item is the envelope title, and the workflow state is the envelope `status`: neither is written by this projector. A projector is deterministic: a row depends only on the events of its stream.
>
> **Confidentiality (ADR-0016).** `confidentiality` holds `internal`, `restricted` or `privileged`. `Correspondence.ClearanceGranted` and `...Withdrawn` keep the rows of `cur_correspondence_clearance` that name who may read a privileged item. The projector writes the value as it is in the event; the commands check it.

### Learnings that apply
> **L-P1-I1-6.** A parity run's count is not the SQLite count twice: a case that does not use the `db`/`new_db`/`engine` fixtures runs once. Every case of this ticket's test uses them, so the counts below are exact.
>
> **L-P1-I5-1.** Postgres cannot infer the type of a bare parameter in `CASE WHEN :p IS NOT NULL ...` (`could not determine data type of parameter $1`), and a Python bool is the portable value for a boolean column. Compute such choices in Python; run the test on both adapters before you report.
>
> **L-P0-I5-A8.** pg8000 re-raises every SQLSTATE class 23 error as `IntegrityError`; `text()` statements with named parameters behave the same on both adapters.

> **L-P0-I1-6.** ruff's `E501` applies to docstrings and comments at 100 columns, and pyright strict flags `@contextmanager` functions annotated `Iterator[X]`. Wrap prose.
>
> **L-P0-I6C-8 / L-P1-I0B-3.** Write files with the Write tool, not a long `cat > file <<'EOF'` inside a `&&` chain, and never `pkill -f`: kill only a PID you started.
>
> **L-P1-I3B-6.** Copy the provided test byte for byte (`cp`), run `ruff` and `pyright` on the tree, and do not edit the copy: if it cannot pass, stop and report *Blocked*.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-modules/correspondence/src/tl_mod_correspondence/projectors/correspondence.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401, F841
"""CorrespondenceProjector: the ``Correspondence.*`` events into the item and clearance tables.

``Correspondence.Defined`` inserts the item row; the other events move single columns (triage,
reclassification, thread, issue, answer, supersession, confidentiality); ``ClearanceGranted`` and
``ClearanceWithdrawn`` add and remove the rows that name who may read a privileged item
(ADR-0016). The subject is the envelope title and the workflow state is the envelope ``status``;
neither is written here. Deterministic: a row depends only on the events of its stream. Register
it after ``RecordProjector``.

STUB (P1-I5-T03a): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_correspondence.names import (
    CLEARANCE_TABLE,
    CORR_CLASS_CHANGED,
    CORR_CLEARANCE_GRANTED,
    CORR_CLEARANCE_WITHDRAWN,
    CORR_DEFINED,
    CORR_ISSUED,
    CORR_RECLASSIFIED,
    CORR_RESPONDED,
    CORR_SUPERSEDED,
    CORR_THREAD_ASSIGNED,
    CORR_TRIAGED,
    CORR_UPDATED,
    CORRESPONDENCE_TABLE,
    CORRESPONDENCE_VIEW,
)
from tl_mod_correspondence.projectors._common import ddl_for, json_text, touch_record

#: Register fields a ``Correspondence.Updated`` may change, with the column each one writes.
_UPDATABLE = {
    "external_ref": "external_ref",
    "from_name": "from_name",
    "from_party_id": "from_party_id",
    "medium": "medium",
    "sent_on": "sent_on",
    "received_on": "received_on",
    "body": "body",
    "response_required": "response_required",
    "response_due": "response_due",
    "to": "to_parties_json",
    "cc": "cc_parties_json",
}
_JSON_FIELDS = frozenset({"to", "cc"})


class CorrespondenceProjector:
    name = "correspondence_item"
    handles = frozenset(
        {
            CORR_DEFINED,
            CORR_UPDATED,
            CORR_TRIAGED,
            CORR_RECLASSIFIED,
            CORR_THREAD_ASSIGNED,
            CORR_ISSUED,
            CORR_RESPONDED,
            CORR_SUPERSEDED,
            CORR_CLASS_CHANGED,
            CORR_CLEARANCE_GRANTED,
            CORR_CLEARANCE_WITHDRAWN,
        }
    )

    def ddl(self, dialect: str) -> list[str]:
        return (
            ddl_for(CORRESPONDENCE_TABLE, dialect)
            + ddl_for(CLEARANCE_TABLE, dialect)
            + ddl_for(CORRESPONDENCE_VIEW, dialect)
        )

    def apply(self, conn: Connection, event: Event) -> None:
        # STEPS
        # 1. `payload = event.payload`, `et = event.event_type`, `base = {"id": event.stream_id,
        #    "last_seq": event.seq}`. Every statement is `conn.execute(text(sql), params)` with
        #    named parameters. Table names come from the constants imported above, never from the
        #    event or the payload.
        # 2. CORR_DEFINED: INSERT a row into CORRESPONDENCE_TABLE. Required payload keys (use
        #    `payload[...]`): number, direction, medium, received_via, confidentiality. Optional
        #    (use `payload.get`): external_ref, message_id, in_reply_to, from_party_id, from_name,
        #    sent_on, received_on, body, domain, subtype, responds_to_id, response_due. Also write
        #    id, scope (`event.scope`) and last_seq. `to_parties_json` is
        #    `json_text(payload.get("to") or [])` and `cc_parties_json` the same for `"cc"`.
        #    `response_required` is `bool(payload.get("response_required", False))`. Other columns
        #    keep their defaults.
        # 3. CORR_UPDATED: `changes = payload.get("changes") or {}` maps a field to [old, new]. For
        #    each name in `_UPDATABLE` that is a key of `changes`, set the column `_UPDATABLE[name]`
        #    to the new value `changes[name][1]`; for a name in `_JSON_FIELDS` store `json_text(new
        #    or [])`. Build the SET clause from the columns of `_UPDATABLE` only (never from the
        #    keys of `changes`) and always add `last_seq = :last_seq`. If `changes` names none of
        #    them the statement still runs and sets `last_seq`.
        # 4. CORR_TRIAGED: UPDATE domain, subtype and triaged_on from the payload (all three are
        #    required keys), `triaged_by` = `event.actor`, and last_seq.
        # 5. CORR_RECLASSIFIED: UPDATE domain and subtype from the payload (required) and last_seq.
        # 6. CORR_THREAD_ASSIGNED: UPDATE thread_id (required key) and last_seq, and set
        #    `responds_to_id` to the payload's `responds_to_id` when that is not None, else keep the
        #    value the row has: `responds_to_id = COALESCE(:responds_to_id, responds_to_id)`.
        # 7. CORR_ISSUED: UPDATE issued_on, `rendition_file_id` (payload key `rendition_file_id`),
        #    `rendition_sha256`, delivery (all required keys) and last_seq.
        # 8. CORR_RESPONDED: UPDATE responded_on (required key) and last_seq.
        # 9. CORR_SUPERSEDED: UPDATE `superseded_by_id` from the payload key `superseded_by_id`, and
        #    last_seq.
        # 10. CORR_CLASS_CHANGED: UPDATE confidentiality = the payload's `to_class`, and last_seq.
        # 11. CORR_CLEARANCE_GRANTED: INSERT into CLEARANCE_TABLE: clearance_id =
        #    `f"{event.stream_id}:{payload['account']}"`, scope = `event.scope`, record_id =
        #    `event.stream_id`, account, granted_by = `event.actor`, granted_on, last_seq.
        # 12. CORR_CLEARANCE_WITHDRAWN: DELETE from CLEARANCE_TABLE where record_id =
        #    `event.stream_id` and account = `payload["account"]`. (A DELETE on a projection table
        #    is allowed; an event is never deleted.)
        # 13. Any other event type: `raise ValueError(f"CorrespondenceProjector cannot apply event
        #    type: {et}")`.
        # 14. Every UPDATE branch checks its row count with `self._require(rowcount, event)`. After
        #    the branches call `touch_record(conn, event)`.
        raise NotImplementedError

    @staticmethod
    def _require(rowcount: int, event: Event) -> None:
        if rowcount == 0:
            raise LookupError(f"no {CORRESPONDENCE_TABLE} row for stream {event.stream_id}")

    def reset(self, conn: Connection) -> None:
        # STEPS
        # 1. Delete every row of CLEARANCE_TABLE, then of CORRESPONDENCE_TABLE (`DELETE FROM
        #    <table>`).
        raise NotImplementedError
```

`tl_core.ledger.Event` (read-only; the fields a projector uses):
```python
class Event(BaseModel):
    event_type: str          # "Correspondence.Defined"
    payload: dict[str, Any]
    seq: int                 # ledger sequence; goes into the row's last_seq
    stream_id: str           # the record id (cur_core_record.id)
    scope: str               # "project:P123"
    actor: str               # "user:amy"
    recorded_at: datetime
```

`tl_mod_correspondence/projectors/_common.py` (read-only):
```python
from tl_mod_engineering.projectors._common import ddl_for, json_text, touch_record
# json_text(value) -> canonical JSON text (sorted keys, no spaces)
# touch_record(conn, event) -> moves cur_core_record.version/last_seq/updated_at; raises
#   LookupError when the stream has no envelope row. Every projector calls it last.
```

`packages/tl-schema/src/tl_schema/generated/ddl/sqlite/cur_correspondence_correspondence.sql` (the stub you complete; the whole file):
```sql
CREATE TABLE IF NOT EXISTS cur_correspondence_correspondence (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  number TEXT NOT NULL,
  direction TEXT NOT NULL,
  medium TEXT NOT NULL,
  received_via TEXT NOT NULL,
  external_ref TEXT,
  message_id TEXT,
  in_reply_to TEXT,
  from_party_id TEXT,
  from_name TEXT,
  to_parties_json TEXT NOT NULL DEFAULT '{}',
  cc_parties_json TEXT NOT NULL DEFAULT '{}',
  sent_on TEXT,
  received_on TEXT,
  issued_on TEXT,
  body TEXT,
  confidentiality TEXT NOT NULL DEFAULT 'internal',
  domain TEXT,
  subtype TEXT,
  thread_id TEXT,
  responds_to_id TEXT,
  superseded_by_id TEXT,
  response_required INTEGER NOT NULL DEFAULT 0,
  response_due TEXT,
  responded_on TEXT,
  triaged_on TEXT,
  triaged_by TEXT,
  rendition_file_id TEXT,
  rendition_sha256 TEXT,
  delivery TEXT NOT NULL DEFAULT 'none',
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_correspondence_message_id ON cur_correspondence_correspondence (scope, message_id);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_correspondence_scope_class ON cur_correspondence_correspondence (scope, confidentiality);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_correspondence_scope_direction ON cur_correspondence_correspondence (scope, direction);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_correspondence_scope_domain ON cur_correspondence_correspondence (scope, domain);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_correspondence_scope_due ON cur_correspondence_correspondence (scope, response_due);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_correspondence_scope_received ON cur_correspondence_correspondence (scope, received_on);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_correspondence_thread ON cur_correspondence_correspondence (thread_id);
```

`packages/tl-schema/src/tl_schema/generated/ddl/sqlite/cur_correspondence_clearance.sql` (the stub you complete; the whole file):
```sql
CREATE TABLE IF NOT EXISTS cur_correspondence_clearance (
  clearance_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  record_id TEXT NOT NULL,
  account TEXT NOT NULL,
  granted_by TEXT NOT NULL,
  granted_on TEXT NOT NULL,
  last_seq INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_correspondence_clearance_record_account ON cur_correspondence_clearance (record_id, account);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_clearance_account ON cur_correspondence_clearance (account);
```

The event type constants (`tl_mod_correspondence/names.py`) are imported in the stub; `CORR_*` are the eleven event types, `CORRESPONDENCE_TABLE` and `CLEARANCE_TABLE` the tables.

## Context (read these, nothing else)
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/projectors/correspondence.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/names.py`
- `packages/tl-schema/src/tl_schema/generated/ddl/sqlite/cur_correspondence_correspondence.sql`
- `docs/tickets/P1-I5/provided/t03a-test_projector_correspondence.py.txt`
- `docs/templates/haiku-report.md`
may explore: (none)

## Allowed paths
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/projectors/correspondence.py`
- `packages/tl-modules/correspondence/tests/test_projector_correspondence.py (create: the provided test, byte for byte)`
- `docs/reports/P1-I5/P1-I5-T03a.md` (create: your report; commit it)

## Steps
1. Copy the provided test: `cp docs/tickets/P1-I5/provided/t03a-test_projector_correspondence.py.txt packages/tl-modules/correspondence/tests/test_projector_correspondence.py`. Do not edit the copy.
2. Implement `CorrespondenceProjector.apply` and `reset` by their STEPS comments.
3. Delete the `STUB` paragraph of the module docstring, every `# STEPS` comment and the `# ruff: noqa` line at the top of each stub file you completed.
4. Run the acceptance commands, write the report, commit with `P1-I5-T03a: <imperative summary>`.

## Acceptance
```
just check
uv run pytest packages/tl-modules/correspondence/tests/test_projector_correspondence.py -q
TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test TL_REQUIRE_POSTGRES=1 uv run pytest packages/tl-modules/correspondence/tests/test_projector_correspondence.py -q --adapters sqlite,postgres
```
Expected: `just check` clean; 13 passed on SQLite; 26 passed with both adapters (every case runs once per adapter).

## Tests to add
- `packages/tl-modules/correspondence/tests/test_projector_correspondence.py` is provided; it is the whole test of this ticket. Add no other test file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), saved to `docs/reports/P1-I5/P1-I5-T03a.md` and committed. State the SQLite count and the both-adapters count you got, and say whether the `STUB` paragraph, the STEPS comments and the `ruff: noqa` line are gone.

## Escalation triggers
- A column the STEPS name does not exist in the DDL pasted above, or an event key the STEPS name is missing from a test.
- The provided test cannot pass without editing it, a file outside *Allowed paths*, or a pasted interface.
- Two attempts at the same failing test have not passed it.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
