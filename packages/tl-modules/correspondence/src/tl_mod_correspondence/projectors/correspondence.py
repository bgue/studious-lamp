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
