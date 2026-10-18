"""Reading the correspondence tables: items, threads, clocks, parties, clauses, clearances.

Every function takes a connection (``uow.conn()`` inside a unit of work, a read transaction
elsewhere) and returns frozen rows read from the module's flat views (``v_correspondence_<class>``,
which join the typed table to the envelope in ``cur_core_record``). Nothing here writes. JSON
columns come back as Python values on both adapters, booleans as ``bool``.

**Confidentiality (ADR-0016).** An item the viewer may not read does not exist for them: ``get_*``
and ``find_*`` return ``None`` and the lists leave it out, so a caller answers "not found" and never
"hidden". A thread and a clock are readable only when their item is (the module's confidential
source names them as children). Parties and clauses carry no class.

A voided record is left out of a list unless a function says so; a ``get`` or ``find`` returns it
with ``voided`` set. A record that never moved is in its workflow's first state: ``state`` is that
state, not ``None``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, text
from tl_core import confidentiality

from tl_mod_correspondence.clocks import Fact
from tl_mod_correspondence.names import (
    CLAUSE_VIEW,
    CLEARANCE_TABLE,
    CLOCK_VIEW,
    CONTACT_TABLE,
    CORRESPONDENCE_VIEW,
    PARTY_VIEW,
    ST_DRAFT,
    THREAD_VIEW,
)


def _json(value: Any, default: Any) -> Any:
    """A JSON column as Python: text on SQLite and through the Postgres adapter."""
    if value is None:
        return default
    return json.loads(value) if isinstance(value, str) else value


def _hidden(conn: Connection, record_id: str) -> bool:
    return confidentiality.is_hidden(conn, record_id)


# --- items -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class ItemRow:
    id: str
    scope: str
    number: str
    subject: str
    state: str
    voided: bool
    version: int
    direction: str
    medium: str
    received_via: str
    external_ref: str | None
    message_id: str | None
    in_reply_to: str | None
    from_party_id: str | None
    from_name: str | None
    to: list[dict[str, Any]]
    cc: list[dict[str, Any]]
    sent_on: str | None
    received_on: str | None
    issued_on: str | None
    body: str | None
    confidentiality: str
    domain: str | None
    subtype: str | None
    thread_id: str | None
    responds_to_id: str | None
    superseded_by_id: str | None
    response_required: bool
    response_due: str | None
    responded_on: str | None
    triaged_on: str | None
    triaged_by: str | None
    rendition_file_id: str | None
    rendition_sha256: str | None
    delivery: str
    created_at: str
    updated_at: str

    @property
    def closed(self) -> bool:
        """True when the item takes no more changes (void, closed or superseded)."""
        return self.voided or self.state in ("Void", "Closed") or self.superseded_by_id is not None


_ITEM_COLUMNS = (
    "id, scope, number, title, status, voided, version, direction, medium, received_via, "
    "external_ref, message_id, in_reply_to, from_party_id, from_name, to_parties_json, "
    "cc_parties_json, sent_on, received_on, issued_on, body, confidentiality, domain, subtype, "
    "thread_id, responds_to_id, superseded_by_id, response_required, response_due, responded_on, "
    "triaged_on, triaged_by, rendition_file_id, rendition_sha256, delivery, created_at, updated_at"
)


def _item(row: Any) -> ItemRow:
    return ItemRow(
        id=row.id,
        scope=row.scope,
        number=row.number,
        subject=row.title,
        state=row.status or ST_DRAFT,
        voided=bool(row.voided),
        version=row.version,
        direction=row.direction,
        medium=row.medium,
        received_via=row.received_via,
        external_ref=row.external_ref,
        message_id=row.message_id,
        in_reply_to=row.in_reply_to,
        from_party_id=row.from_party_id,
        from_name=row.from_name,
        to=_json(row.to_parties_json, []),
        cc=_json(row.cc_parties_json, []),
        sent_on=row.sent_on,
        received_on=row.received_on,
        issued_on=row.issued_on,
        body=row.body,
        confidentiality=row.confidentiality,
        domain=row.domain,
        subtype=row.subtype,
        thread_id=row.thread_id,
        responds_to_id=row.responds_to_id,
        superseded_by_id=row.superseded_by_id,
        response_required=bool(row.response_required),
        response_due=row.response_due,
        responded_on=row.responded_on,
        triaged_on=row.triaged_on,
        triaged_by=row.triaged_by,
        rendition_file_id=row.rendition_file_id,
        rendition_sha256=row.rendition_sha256,
        delivery=row.delivery,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def get_item(conn: Connection, item_id: str) -> ItemRow | None:
    """The item with this id, or ``None`` when there is none or the viewer may not read it."""
    row = conn.execute(
        text(f"SELECT {_ITEM_COLUMNS} FROM {CORRESPONDENCE_VIEW} WHERE id = :id"), {"id": item_id}
    ).first()
    return None if row is None or _hidden(conn, item_id) else _item(row)


def find_item(conn: Connection, scope: str, number: str) -> ItemRow | None:
    """The item of this number in the scope, under the same rule as ``get_item``."""
    row = conn.execute(
        text(
            f"SELECT {_ITEM_COLUMNS} FROM {CORRESPONDENCE_VIEW} "
            "WHERE scope = :scope AND number = :number"
        ),
        {"scope": scope, "number": number},
    ).first()
    return None if row is None or _hidden(conn, row.id) else _item(row)


def find_by_message_id(conn: Connection, scope: str, message_id: str) -> ItemRow | None:
    """The item with this normalised Message-ID (email ingest refuses a repeat)."""
    row = conn.execute(
        text(
            f"SELECT {_ITEM_COLUMNS} FROM {CORRESPONDENCE_VIEW} "
            "WHERE scope = :scope AND message_id = :mid ORDER BY number LIMIT 1"
        ),
        {"scope": scope, "mid": message_id},
    ).first()
    return None if row is None or _hidden(conn, row.id) else _item(row)


def list_items(
    conn: Connection,
    scope: str,
    *,
    state: str | None = None,
    direction: str | None = None,
    domain: str | None = None,
    subtype: str | None = None,
    thread_id: str | None = None,
    untriaged: bool = False,
    awaiting_response: bool = False,
    received_from: str | None = None,
    received_to: str | None = None,
    include_void: bool = False,
    limit: int = 500,
    offset: int = 0,
) -> list[ItemRow]:
    """The items of a scope the viewer may read, newest number first.

    ``untriaged`` keeps items of state Received (the triage inbox). ``awaiting_response`` keeps
    items that need an answer and have none. A void item is left out unless asked.
    """
    sql = f"SELECT {_ITEM_COLUMNS} FROM {CORRESPONDENCE_VIEW} WHERE scope = :scope"
    params: dict[str, Any] = {"scope": scope, "limit": limit, "offset": offset}
    visible, visible_params = confidentiality.not_hidden("id")
    sql += f" AND {visible}"
    params.update(visible_params)
    for column, value in (
        ("direction", direction),
        ("domain", domain),
        ("subtype", subtype),
        ("thread_id", thread_id),
    ):
        if value is not None:
            sql += f" AND {column} = :{column}"
            params[column] = value
    if state is not None:
        sql += " AND COALESCE(status, 'Draft') = :state"
        params["state"] = state
    if untriaged:
        sql += " AND COALESCE(status, 'Draft') = 'Received'"
    if awaiting_response:
        sql += (
            " AND response_required = :yes AND responded_on IS NULL"
            " AND COALESCE(status, 'Draft') NOT IN ('Void', 'Closed', 'Responded')"
        )
        params["yes"] = True
    if received_from is not None:
        sql += " AND received_on >= :received_from"
        params["received_from"] = received_from
    if received_to is not None:
        sql += " AND received_on <= :received_to"
        params["received_to"] = received_to
    if not include_void:
        sql += " AND COALESCE(status, 'Draft') <> 'Void'"
    sql += " ORDER BY number DESC LIMIT :limit OFFSET :offset"
    return [_item(r) for r in conn.execute(text(sql), params).all()]


def items_of_thread(conn: Connection, thread_id: str) -> list[ItemRow]:
    """The items of a thread the viewer may read, oldest first."""
    sql = (
        f"SELECT {_ITEM_COLUMNS} FROM {CORRESPONDENCE_VIEW} WHERE thread_id = :tid AND "
        + confidentiality.not_hidden("id")[0]
        + " ORDER BY COALESCE(received_on, sent_on, issued_on, created_at), number"
    )
    params = {"tid": thread_id, **confidentiality.not_hidden("id")[1]}
    return [_item(r) for r in conn.execute(text(sql), params).all()]


@dataclass(frozen=True)
class ClearanceRow:
    record_id: str
    account: str
    granted_by: str
    granted_on: str


def clearances_of(conn: Connection, item_id: str) -> list[ClearanceRow]:
    """The accounts named on an item, by account. ``[]`` for an item the viewer may not read."""
    if _hidden(conn, item_id):
        return []
    rows = conn.execute(
        text(
            "SELECT record_id, account, granted_by, granted_on "
            f"FROM {CLEARANCE_TABLE} WHERE record_id = :id ORDER BY account"
        ),
        {"id": item_id},
    ).all()
    return [ClearanceRow(r.record_id, r.account, r.granted_by, r.granted_on) for r in rows]


# --- threads ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class ThreadRow:
    id: str
    scope: str
    number: str
    subject_key: str
    domain: str | None
    state: str
    governing_item_id: str | None
    item_count: int
    last_item_on: str | None
    voided: bool
    version: int


_THREAD_COLUMNS = (
    "id, scope, number, subject_key, domain, state, governing_item_id, item_count, last_item_on, "
    "voided, version"
)


def _thread(row: Any) -> ThreadRow:
    return ThreadRow(
        id=row.id,
        scope=row.scope,
        number=row.number,
        subject_key=row.subject_key,
        domain=row.domain,
        state=row.state,
        governing_item_id=row.governing_item_id,
        item_count=row.item_count,
        last_item_on=row.last_item_on,
        voided=bool(row.voided),
        version=row.version,
    )


def get_thread(conn: Connection, thread_id: str) -> ThreadRow | None:
    row = conn.execute(
        text(f"SELECT {_THREAD_COLUMNS} FROM {THREAD_VIEW} WHERE id = :id"), {"id": thread_id}
    ).first()
    return None if row is None or _hidden(conn, thread_id) else _thread(row)


def find_thread(conn: Connection, scope: str, number: str) -> ThreadRow | None:
    row = conn.execute(
        text(
            f"SELECT {_THREAD_COLUMNS} FROM {THREAD_VIEW} WHERE scope = :scope AND number = :number"
        ),
        {"scope": scope, "number": number},
    ).first()
    return None if row is None or _hidden(conn, row.id) else _thread(row)


def list_threads(
    conn: Connection, scope: str, *, state: str | None = None, limit: int = 500, offset: int = 0
) -> list[ThreadRow]:
    """The threads of a scope the viewer may read, newest number first."""
    visible, visible_params = confidentiality.not_hidden("id")
    sql = f"SELECT {_THREAD_COLUMNS} FROM {THREAD_VIEW} WHERE scope = :scope AND {visible}"
    params: dict[str, Any] = {"scope": scope, "limit": limit, "offset": offset, **visible_params}
    if state is not None:
        sql += " AND state = :state"
        params["state"] = state
    sql += " ORDER BY number DESC LIMIT :limit OFFSET :offset"
    return [_thread(r) for r in conn.execute(text(sql), params).all()]


def thread_candidates(conn: Connection, scope: str, subject_key: str) -> list[ThreadRow]:
    """Open threads of a scope whose normalised subject is ``subject_key`` (readable ones)."""
    visible, visible_params = confidentiality.not_hidden("id")
    sql = (
        f"SELECT {_THREAD_COLUMNS} FROM {THREAD_VIEW} WHERE scope = :scope AND "
        f"subject_key = :key AND state = 'open' AND {visible} ORDER BY number"
    )
    found = conn.execute(text(sql), {"scope": scope, "key": subject_key, **visible_params}).all()
    return [_thread(r) for r in found]


# --- clocks ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class ClockRow:
    id: str
    key: str  # <item number>-C<nn>
    scope: str
    item_id: str
    item_number: str
    label: str
    kind: str
    start_on: str
    duration_days: int
    day_type: str
    calendar: str
    warn_days: list[int]
    due_on: str
    state: str  # as stored: running, paused, met, cancelled or expired
    paused_on: str | None
    pause_reason: str | None
    closed_on: str | None
    closed_reason: str | None
    warned_level: int | None
    owner: str | None
    clause_id: str | None
    restarts: int
    voided: bool
    version: int


_CLOCK_COLUMNS = (
    "id, key, scope, item_id, item_number, label, kind, start_on, duration_days, day_type, calendar, "
    "warn_days_json, due_on, state, paused_on, pause_reason, closed_on, closed_reason, "
    "warned_level, owner, clause_id, restarts, voided, version"
)


def _clock(row: Any) -> ClockRow:
    return ClockRow(
        id=row.id,
        key=row.key,
        scope=row.scope,
        item_id=row.item_id,
        item_number=row.item_number,
        label=row.label,
        kind=row.kind,
        start_on=row.start_on,
        duration_days=row.duration_days,
        day_type=row.day_type,
        calendar=row.calendar,
        warn_days=[int(w) for w in _json(row.warn_days_json, [])],
        due_on=row.due_on,
        state=row.state,
        paused_on=row.paused_on,
        pause_reason=row.pause_reason,
        closed_on=row.closed_on,
        closed_reason=row.closed_reason,
        warned_level=row.warned_level,
        owner=row.owner,
        clause_id=row.clause_id,
        restarts=row.restarts,
        voided=bool(row.voided),
        version=row.version,
    )


def get_clock(conn: Connection, clock_id: str) -> ClockRow | None:
    row = conn.execute(
        text(f"SELECT {_CLOCK_COLUMNS} FROM {CLOCK_VIEW} WHERE id = :id"), {"id": clock_id}
    ).first()
    return None if row is None or _hidden(conn, clock_id) else _clock(row)


def find_clock(conn: Connection, scope: str, key: str) -> ClockRow | None:
    """The clock with this key (``<item number>-C<nn>``) in the scope, under the item's rule."""
    row = conn.execute(
        text(f"SELECT {_CLOCK_COLUMNS} FROM {CLOCK_VIEW} WHERE scope = :scope AND key = :key"),
        {"scope": scope, "key": key},
    ).first()
    return None if row is None or _hidden(conn, row.id) else _clock(row)


def clocks_of(conn: Connection, item_id: str) -> list[ClockRow]:
    """The clocks of one item, oldest first. ``[]`` when the viewer may not read the item."""
    visible, visible_params = confidentiality.not_hidden("id")
    sql = (
        f"SELECT {_CLOCK_COLUMNS} FROM {CLOCK_VIEW} "
        f"WHERE item_id = :item AND {visible} ORDER BY start_on, id"
    )
    return [_clock(r) for r in conn.execute(text(sql), {"item": item_id, **visible_params}).all()]


def list_clocks(
    conn: Connection,
    scope: str,
    *,
    open_only: bool = True,
    due_to: str | None = None,
    limit: int = 1000,
    offset: int = 0,
) -> list[ClockRow]:
    """The clocks of a scope the viewer may read, soonest due first.

    ``open_only`` keeps clocks that still count (running or paused, as stored: an expired one is a
    running clock past its date, and is kept). ``due_to`` keeps clocks due on or before a day.
    """
    visible, visible_params = confidentiality.not_hidden("id")
    sql = f"SELECT {_CLOCK_COLUMNS} FROM {CLOCK_VIEW} WHERE scope = :scope AND {visible}"
    params: dict[str, Any] = {"scope": scope, "limit": limit, "offset": offset, **visible_params}
    if open_only:
        sql += " AND state IN ('running', 'paused', 'expired')"
    if due_to is not None:
        sql += " AND due_on <= :due_to"
        params["due_to"] = due_to
    sql += " ORDER BY due_on, item_number, id LIMIT :limit OFFSET :offset"
    return [_clock(r) for r in conn.execute(text(sql), params).all()]


# --- parties and clauses ---------------------------------------------------------------------


@dataclass(frozen=True)
class ContactRow:
    contact_id: str
    party_id: str
    position: int
    name: str
    email: str | None
    title: str | None
    domain: str | None
    is_authorised: bool
    is_active: bool


@dataclass(frozen=True)
class PartyRow:
    id: str
    scope: str
    code: str
    name: str
    project_role: str
    email_domains: list[str]
    is_active: bool
    version: int


_PARTY_COLUMNS = "id, scope, code, title, project_role, email_domains_json, is_active, version"


def _party(row: Any) -> PartyRow:
    return PartyRow(
        id=row.id,
        scope=row.scope,
        code=row.code,
        name=row.title,
        project_role=row.project_role,
        email_domains=[str(d) for d in _json(row.email_domains_json, [])],
        is_active=bool(row.is_active),
        version=row.version,
    )


def get_party(conn: Connection, party_id: str) -> PartyRow | None:
    row = conn.execute(
        text(f"SELECT {_PARTY_COLUMNS} FROM {PARTY_VIEW} WHERE id = :id"), {"id": party_id}
    ).first()
    return None if row is None else _party(row)


def find_party(conn: Connection, scope: str, code: str) -> PartyRow | None:
    row = conn.execute(
        text(f"SELECT {_PARTY_COLUMNS} FROM {PARTY_VIEW} WHERE scope = :scope AND code = :code"),
        {"scope": scope, "code": code},
    ).first()
    return None if row is None else _party(row)


def list_parties(conn: Connection, scope: str, *, include_inactive: bool = False) -> list[PartyRow]:
    sql = f"SELECT {_PARTY_COLUMNS} FROM {PARTY_VIEW} WHERE scope = :scope"
    if not include_inactive:
        sql += " AND is_active = :yes"
    sql += " ORDER BY code"
    params: dict[str, Any] = {"scope": scope, "yes": True}
    return [_party(r) for r in conn.execute(text(sql), params).all()]


def contacts_of(
    conn: Connection, party_id: str, *, include_ended: bool = False
) -> list[ContactRow]:
    sql = (
        "SELECT contact_id, party_id, position, name, email, title, domain, is_authorised, "
        f"is_active FROM {CONTACT_TABLE} WHERE party_id = :pid"
    )
    params: dict[str, Any] = {"pid": party_id}
    if not include_ended:
        sql += " AND is_active = :yes"
        params["yes"] = True
    sql += " ORDER BY position"
    return [
        ContactRow(
            contact_id=r.contact_id,
            party_id=r.party_id,
            position=r.position,
            name=r.name,
            email=r.email,
            title=r.title,
            domain=r.domain,
            is_authorised=bool(r.is_authorised),
            is_active=bool(r.is_active),
        )
        for r in conn.execute(text(sql), params).all()
    ]


def party_by_email(conn: Connection, scope: str, email: str) -> PartyRow | None:
    """The active party that has a contact with this email, else the one that owns its domain."""
    address = email.strip().lower()
    row = conn.execute(
        text(
            f"SELECT p.id FROM {CONTACT_TABLE} c JOIN {PARTY_VIEW} p ON p.id = c.party_id "
            "WHERE c.scope = :scope AND c.email = :email AND c.is_active = :yes "
            "AND p.is_active = :yes ORDER BY p.code LIMIT 1"
        ),
        {"scope": scope, "email": address, "yes": True},
    ).first()
    if row is not None:
        return get_party(conn, row.id)
    domain = address.rpartition("@")[2]
    for party in list_parties(conn, scope):
        if domain and domain in party.email_domains:
            return party
    return None


@dataclass(frozen=True)
class ClauseRow:
    id: str
    scope: str
    contract: str
    clause_number: str
    time_bar_days: int | None
    time_bar_day_type: str | None
    notice_requirements: str | None
    required_recipients: list[str]
    service_method: str | None
    contract_document_id: str | None
    domains: list[str]
    is_active: bool
    version: int


_CLAUSE_COLUMNS = (
    "id, scope, contract, clause_number, time_bar_days, time_bar_day_type, notice_requirements, "
    "required_recipients_json, service_method, contract_document_id, domains_json, is_active, "
    "version"
)


def _clause(row: Any) -> ClauseRow:
    return ClauseRow(
        id=row.id,
        scope=row.scope,
        contract=row.contract,
        clause_number=row.clause_number,
        time_bar_days=row.time_bar_days,
        time_bar_day_type=row.time_bar_day_type,
        notice_requirements=row.notice_requirements,
        required_recipients=[str(r) for r in _json(row.required_recipients_json, [])],
        service_method=row.service_method,
        contract_document_id=row.contract_document_id,
        domains=[str(d) for d in _json(row.domains_json, [])],
        is_active=bool(row.is_active),
        version=row.version,
    )


def get_clause(conn: Connection, clause_id: str) -> ClauseRow | None:
    row = conn.execute(
        text(f"SELECT {_CLAUSE_COLUMNS} FROM {CLAUSE_VIEW} WHERE id = :id"), {"id": clause_id}
    ).first()
    return None if row is None else _clause(row)


def find_clause(
    conn: Connection, scope: str, contract: str, clause_number: str
) -> ClauseRow | None:
    row = conn.execute(
        text(
            f"SELECT {_CLAUSE_COLUMNS} FROM {CLAUSE_VIEW} WHERE scope = :scope AND "
            "contract = :contract AND clause_number = :number"
        ),
        {"scope": scope, "contract": contract, "number": clause_number},
    ).first()
    return None if row is None else _clause(row)


def list_clauses(
    conn: Connection, scope: str, *, include_inactive: bool = False
) -> list[ClauseRow]:
    sql = f"SELECT {_CLAUSE_COLUMNS} FROM {CLAUSE_VIEW} WHERE scope = :scope"
    params: dict[str, Any] = {"scope": scope}
    if not include_inactive:
        sql += " AND is_active = :yes"
        params["yes"] = True
    sql += " ORDER BY contract, clause_number"
    return [_clause(r) for r in conn.execute(text(sql), params).all()]


def clock_facts(conn: Connection, clock_id: str) -> list[Fact]:
    """The clock events of one clock stream in ledger order, as the engine reads them.

    Reads through ``conn`` so a handler sees the events its own unit of work appended. It does no
    access check: callers read the clock row first (``get_clock``), which applies it.
    """
    rows = conn.execute(
        text(
            "SELECT event_type, payload FROM events WHERE stream_id = :s "
            "AND event_type LIKE 'ResponseClock.%' ORDER BY stream_version"
        ),
        {"s": clock_id},
    ).all()
    return [
        Fact(r.event_type, json.loads(r.payload) if isinstance(r.payload, str) else r.payload)
        for r in rows
    ]
