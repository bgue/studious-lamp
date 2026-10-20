"""CorrespondenceProjector: the ``Correspondence.*`` events into the item and clearance tables.

``Correspondence.Defined`` inserts the item row; the other events move single columns (triage,
reclassification, thread, issue, answer, supersession, confidentiality); ``ClearanceGranted`` and
``ClearanceWithdrawn`` add and remove the rows that name who may read a privileged item
(ADR-0016). The subject is the envelope title and the workflow state is the envelope ``status``;
neither is written here. Deterministic: a row depends only on the events of its stream. Register
it after ``RecordProjector``.
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
        payload = event.payload
        et = event.event_type

        if et == CORR_DEFINED:
            conn.execute(
                text(
                    f"INSERT INTO {CORRESPONDENCE_TABLE} "
                    "(id, scope, number, direction, medium, received_via, external_ref, "
                    "message_id, in_reply_to, from_party_id, from_name, to_parties_json, "
                    "cc_parties_json, sent_on, received_on, body, confidentiality, domain, "
                    "subtype, responds_to_id, response_required, response_due, last_seq) "
                    "VALUES (:id, :scope, :number, :direction, :medium, :received_via, "
                    ":external_ref, :message_id, :in_reply_to, :from_party_id, :from_name, "
                    ":to_parties_json, :cc_parties_json, :sent_on, :received_on, :body, "
                    ":confidentiality, :domain, :subtype, :responds_to_id, :response_required, "
                    ":response_due, :last_seq)"
                ),
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "number": payload["number"],
                    "direction": payload["direction"],
                    "medium": payload["medium"],
                    "received_via": payload["received_via"],
                    "external_ref": payload.get("external_ref"),
                    "message_id": payload.get("message_id"),
                    "in_reply_to": payload.get("in_reply_to"),
                    "from_party_id": payload.get("from_party_id"),
                    "from_name": payload.get("from_name"),
                    "to_parties_json": json_text(payload.get("to") or []),
                    "cc_parties_json": json_text(payload.get("cc") or []),
                    "sent_on": payload.get("sent_on"),
                    "received_on": payload.get("received_on"),
                    "body": payload.get("body"),
                    "confidentiality": payload["confidentiality"],
                    "domain": payload.get("domain"),
                    "subtype": payload.get("subtype"),
                    "responds_to_id": payload.get("responds_to_id"),
                    "response_required": bool(payload.get("response_required", False)),
                    "response_due": payload.get("response_due"),
                    "last_seq": event.seq,
                },
            )
        elif et == CORR_UPDATED:
            changes = payload.get("changes") or {}
            assignments: list[str] = []
            values: dict[str, Any] = {}
            for name, column in _UPDATABLE.items():
                if name not in changes:
                    continue
                value = changes[name][1]
                if name in _JSON_FIELDS:
                    value = json_text(value or [])
                assignments.append(f"{column} = :{column}")
                values[column] = value
            self._update(conn, event, assignments, values)
        elif et == CORR_TRIAGED:
            self._update(
                conn,
                event,
                [
                    "domain = :domain",
                    "subtype = :subtype",
                    "triaged_on = :triaged_on",
                    "triaged_by = :triaged_by",
                ],
                {
                    "domain": payload["domain"],
                    "subtype": payload["subtype"],
                    "triaged_on": payload["triaged_on"],
                    # triaged_by is the actor of the event, not a payload field.
                    "triaged_by": event.actor,
                },
            )
        elif et == CORR_RECLASSIFIED:
            self._update(
                conn,
                event,
                ["domain = :domain", "subtype = :subtype"],
                {"domain": payload["domain"], "subtype": payload["subtype"]},
            )
        elif et == CORR_THREAD_ASSIGNED:
            self._update(
                conn,
                event,
                [
                    "thread_id = :thread_id",
                    "responds_to_id = COALESCE(:responds_to_id, responds_to_id)",
                ],
                {
                    "thread_id": payload["thread_id"],
                    "responds_to_id": payload.get("responds_to_id"),
                },
            )
        elif et == CORR_ISSUED:
            self._update(
                conn,
                event,
                [
                    "issued_on = :issued_on",
                    "rendition_file_id = :rendition_file_id",
                    "rendition_sha256 = :rendition_sha256",
                    "delivery = :delivery",
                ],
                {
                    "issued_on": payload["issued_on"],
                    "rendition_file_id": payload["rendition_file_id"],
                    "rendition_sha256": payload["rendition_sha256"],
                    "delivery": payload["delivery"],
                },
            )
        elif et == CORR_RESPONDED:
            self._update(
                conn,
                event,
                ["responded_on = :responded_on"],
                {"responded_on": payload["responded_on"]},
            )
        elif et == CORR_SUPERSEDED:
            self._update(
                conn,
                event,
                ["superseded_by_id = :superseded_by_id"],
                {"superseded_by_id": payload["superseded_by_id"]},
            )
        elif et == CORR_CLASS_CHANGED:
            self._update(
                conn,
                event,
                ["confidentiality = :confidentiality"],
                {"confidentiality": payload["to_class"]},
            )
        elif et == CORR_CLEARANCE_GRANTED:
            conn.execute(
                text(
                    f"INSERT INTO {CLEARANCE_TABLE} "
                    "(clearance_id, scope, record_id, account, granted_by, granted_on, last_seq) "
                    "VALUES (:clearance_id, :scope, :record_id, :account, :granted_by, "
                    ":granted_on, :last_seq)"
                ),
                {
                    "clearance_id": f"{event.stream_id}:{payload['account']}",
                    "scope": event.scope,
                    "record_id": event.stream_id,
                    "account": payload["account"],
                    "granted_by": event.actor,
                    "granted_on": payload["granted_on"],
                    "last_seq": event.seq,
                },
            )
        elif et == CORR_CLEARANCE_WITHDRAWN:
            # A DELETE on a projection table is allowed; the event itself is never deleted.
            conn.execute(
                text(
                    f"DELETE FROM {CLEARANCE_TABLE} "
                    "WHERE record_id = :record_id AND account = :account"
                ),
                {"record_id": event.stream_id, "account": payload["account"]},
            )
        else:
            raise ValueError(f"CorrespondenceProjector cannot apply event type: {et}")

        touch_record(conn, event)

    def _update(
        self,
        conn: Connection,
        event: Event,
        assignments: list[str],
        values: dict[str, Any],
    ) -> None:
        # The assignments name columns of this module only; values are bound parameters.
        sets = ", ".join([*assignments, "last_seq = :last_seq"])
        result = conn.execute(
            text(f"UPDATE {CORRESPONDENCE_TABLE} SET {sets} WHERE id = :id"),
            {"id": event.stream_id, "last_seq": event.seq, **values},
        )
        self._require(result.rowcount, event)

    @staticmethod
    def _require(rowcount: int, event: Event) -> None:
        if rowcount == 0:
            raise LookupError(f"no {CORRESPONDENCE_TABLE} row for stream {event.stream_id}")

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {CLEARANCE_TABLE}"))
        conn.execute(text(f"DELETE FROM {CORRESPONDENCE_TABLE}"))
