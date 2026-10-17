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

_INSERT_SQL = text(
    f"INSERT INTO {CORRESPONDENCE_TABLE} (id, scope, number, direction, medium, received_via, "
    "external_ref, message_id, in_reply_to, from_party_id, from_name, to_parties_json, "
    "cc_parties_json, sent_on, received_on, body, confidentiality, domain, subtype, "
    "responds_to_id, response_required, "
    "response_due, last_seq) VALUES (:id, :scope, :number, :direction, :medium, :received_via, "
    ":external_ref, :message_id, :in_reply_to, :from_party_id, :from_name, :to_parties_json, "
    ":cc_parties_json, :sent_on, :received_on, :body, :confidentiality, :domain, :subtype, "
    ":responds_to_id, "
    ":response_required, :response_due, :last_seq)"
)
_TRIAGED_SQL = text(
    f"UPDATE {CORRESPONDENCE_TABLE} SET domain = :domain, subtype = :subtype, "
    "triaged_on = :triaged_on, triaged_by = :triaged_by, last_seq = :last_seq WHERE id = :id"
)
_RECLASSIFIED_SQL = text(
    f"UPDATE {CORRESPONDENCE_TABLE} SET domain = :domain, subtype = :subtype, "
    "last_seq = :last_seq WHERE id = :id"
)
_THREAD_SQL = text(
    f"UPDATE {CORRESPONDENCE_TABLE} SET thread_id = :thread_id, "
    "responds_to_id = COALESCE(:responds_to_id, responds_to_id), last_seq = :last_seq "
    "WHERE id = :id"
)
_ISSUED_SQL = text(
    f"UPDATE {CORRESPONDENCE_TABLE} SET issued_on = :issued_on, rendition_file_id = :file_id, "
    "rendition_sha256 = :sha256, delivery = :delivery, last_seq = :last_seq WHERE id = :id"
)
_RESPONDED_SQL = text(
    f"UPDATE {CORRESPONDENCE_TABLE} SET responded_on = :responded_on, last_seq = :last_seq "
    "WHERE id = :id"
)
_SUPERSEDED_SQL = text(
    f"UPDATE {CORRESPONDENCE_TABLE} SET superseded_by_id = :by, last_seq = :last_seq WHERE id = :id"
)
_CLASS_SQL = text(
    f"UPDATE {CORRESPONDENCE_TABLE} SET confidentiality = :to_class, last_seq = :last_seq "
    "WHERE id = :id"
)
_GRANT_SQL = text(
    f"INSERT INTO {CLEARANCE_TABLE} (clearance_id, scope, record_id, account, granted_by, "
    "granted_on, last_seq) VALUES (:cid, :scope, :record_id, :account, :granted_by, :granted_on, "
    ":last_seq)"
)
_WITHDRAW_SQL = text(
    f"DELETE FROM {CLEARANCE_TABLE} WHERE record_id = :record_id AND account = :account"
)
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
        payload: dict[str, Any] = event.payload
        et = event.event_type
        base = {"id": event.stream_id, "last_seq": event.seq}
        if et == CORR_DEFINED:
            conn.execute(
                _INSERT_SQL,
                {
                    **base,
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
                },
            )
        elif et == CORR_UPDATED:
            changes: dict[str, list[Any]] = payload.get("changes") or {}
            fields = [name for name in _UPDATABLE if name in changes]
            params: dict[str, Any] = {}
            for name in fields:
                new = changes[name][1]
                params[_UPDATABLE[name]] = json_text(new or []) if name in _JSON_FIELDS else new
            sets = "".join(f"{column} = :{column}, " for column in params)
            statement = (
                f"UPDATE {CORRESPONDENCE_TABLE} SET {sets}last_seq = :last_seq WHERE id = :id"
            )
            self._require(conn.execute(text(statement), {**params, **base}).rowcount, event)
        elif et == CORR_TRIAGED:
            self._require(
                conn.execute(
                    _TRIAGED_SQL,
                    {
                        **base,
                        "domain": payload["domain"],
                        "subtype": payload["subtype"],
                        "triaged_on": payload["triaged_on"],
                        "triaged_by": event.actor,
                    },
                ).rowcount,
                event,
            )
        elif et == CORR_RECLASSIFIED:
            self._require(
                conn.execute(
                    _RECLASSIFIED_SQL,
                    {**base, "domain": payload["domain"], "subtype": payload["subtype"]},
                ).rowcount,
                event,
            )
        elif et == CORR_THREAD_ASSIGNED:
            self._require(
                conn.execute(
                    _THREAD_SQL,
                    {
                        **base,
                        "thread_id": payload["thread_id"],
                        "responds_to_id": payload.get("responds_to_id"),
                    },
                ).rowcount,
                event,
            )
        elif et == CORR_ISSUED:
            self._require(
                conn.execute(
                    _ISSUED_SQL,
                    {
                        **base,
                        "issued_on": payload["issued_on"],
                        "file_id": payload["rendition_file_id"],
                        "sha256": payload["rendition_sha256"],
                        "delivery": payload["delivery"],
                    },
                ).rowcount,
                event,
            )
        elif et == CORR_RESPONDED:
            self._require(
                conn.execute(
                    _RESPONDED_SQL, {**base, "responded_on": payload["responded_on"]}
                ).rowcount,
                event,
            )
        elif et == CORR_SUPERSEDED:
            self._require(
                conn.execute(_SUPERSEDED_SQL, {**base, "by": payload["superseded_by_id"]}).rowcount,
                event,
            )
        elif et == CORR_CLASS_CHANGED:
            self._require(
                conn.execute(_CLASS_SQL, {**base, "to_class": payload["to_class"]}).rowcount, event
            )
        elif et == CORR_CLEARANCE_GRANTED:
            conn.execute(
                _GRANT_SQL,
                {
                    "cid": f"{event.stream_id}:{payload['account']}",
                    "scope": event.scope,
                    "record_id": event.stream_id,
                    "account": payload["account"],
                    "granted_by": event.actor,
                    "granted_on": payload["granted_on"],
                    "last_seq": event.seq,
                },
            )
        elif et == CORR_CLEARANCE_WITHDRAWN:
            conn.execute(
                _WITHDRAW_SQL, {"record_id": event.stream_id, "account": payload["account"]}
            )
        else:
            raise ValueError(f"CorrespondenceProjector cannot apply event type: {et}")
        touch_record(conn, event)

    @staticmethod
    def _require(rowcount: int, event: Event) -> None:
        if rowcount == 0:
            raise LookupError(f"no {CORRESPONDENCE_TABLE} row for stream {event.stream_id}")

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {CLEARANCE_TABLE}"))
        conn.execute(text(f"DELETE FROM {CORRESPONDENCE_TABLE}"))
