"""What the API, the CLI, the TUI and MCP show of correspondence: pydantic views over the registry.

Every function takes a connection and the scope, reads through ``registry`` (which applies the
viewer's confidentiality: ADR-0016) and returns plain models. An item the viewer may not read is
left out of a list and answers ``ItemNotFoundError`` for a single read, with the same message as an
item that does not exist. Nothing here writes.

The **master register** is one list: the correspondence items plus the lines of the register
sources the domains name (``documents.transmittal``: the I2 transmittals, as Document-control
items). A clock's *days left* and *effective state* depend on today's date, so they are computed
here from the clock's events and its calendar (``clocks.replay``), never stored.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Connection

from tl_mod_correspondence import catalog, registry, sources
from tl_mod_correspondence.clocks import days_left, effective_state, replay
from tl_mod_correspondence.errors import ItemNotFoundError, PartyNotFoundError, ThreadNotFoundError
from tl_mod_correspondence.handlers.common import today_date
from tl_mod_correspondence.suggest import suggest


class RecipientView(BaseModel):
    name: str | None = None
    email: str | None = None
    party_id: str | None = None


class ClearanceView(BaseModel):
    account: str
    granted_by: str
    granted_on: str


class ClockView(BaseModel):
    id: str
    key: str
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
    state: str  # as stored: running, paused, met, cancelled or expired (the sweep recorded it)
    effective_state: str  # as of today: a running clock past its date is expired
    days_left: int | None  # counted in the clock's own day type; negative once overdue
    warned_level: int | None
    paused_on: str | None
    closed_on: str | None
    closed_reason: str | None
    owner: str | None
    clause_id: str | None
    restarts: int
    problem: str | None = None  # why the figures could not be recomputed, when they could not


class ItemView(BaseModel):
    id: str
    number: str
    subject: str
    state: str
    direction: str
    medium: str
    received_via: str
    external_ref: str | None
    from_name: str | None
    from_party_id: str | None
    to: list[RecipientView]
    cc: list[RecipientView]
    sent_on: str | None
    received_on: str | None
    issued_on: str | None
    body: str | None
    confidentiality: str
    domain: str | None
    subtype: str | None
    thread_id: str | None
    thread_number: str | None
    responds_to_id: str | None
    responds_to_number: str | None
    superseded_by_id: str | None
    response_required: bool
    response_due: str | None
    responded_on: str | None
    triaged_on: str | None
    triaged_by: str | None
    delivery: str
    rendition_file_id: str | None
    version: int
    clocks: list[ClockView] = []
    clearances: list[ClearanceView] = []


class RegisterLineView(BaseModel):
    kind: str  # item or transmittal
    id: str
    number: str
    subject: str
    domain: str | None
    subtype: str | None
    direction: str
    state: str
    on: str | None
    counterparty: str | None
    response_due: str | None
    confidentiality: str
    thread_id: str | None = None


class ThreadView(BaseModel):
    id: str
    number: str
    subject_key: str
    state: str
    domain: str | None
    item_count: int
    last_item_on: str | None
    governing_item_id: str | None
    items: list[RegisterLineView] = []


class ContactView(BaseModel):
    position: int
    name: str
    email: str | None
    title: str | None
    domain: str | None
    is_authorised: bool
    is_active: bool


class PartyView(BaseModel):
    id: str
    code: str
    name: str
    project_role: str
    email_domains: list[str]
    is_active: bool
    contacts: list[ContactView] = []


class ClauseView(BaseModel):
    id: str
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


class ClockTemplateView(BaseModel):
    label: str
    trigger: str
    kind: str
    duration_days: int
    day_type: str
    warn_days: list[int]
    clause: str | None


class SubtypeView(BaseModel):
    code: str
    label: str
    response_required: bool
    clocks: list[ClockTemplateView]


class DomainView(BaseModel):
    code: str
    name: str
    semver: str
    scope: str
    description: str | None
    default_subtype: str
    confidentiality_default: str
    item_source: str | None
    subtypes: list[SubtypeView]
    templates: list[str]


class SuggestionView(BaseModel):
    domain: str | None
    subtype: str | None
    score: int
    reasons: list[str]
    scores: dict[str, int]


# --- items -----------------------------------------------------------------------------------


def _recipients(values: list[dict[str, Any]]) -> list[RecipientView]:
    return [RecipientView(**{k: v.get(k) for k in ("name", "email", "party_id")}) for v in values]


def _number_of(conn: Connection, item_id: str | None) -> str | None:
    if item_id is None:
        return None
    found = registry.get_item(conn, item_id)
    return found.number if found else None


def _thread_number(conn: Connection, thread_id: str | None) -> str | None:
    if thread_id is None:
        return None
    found = registry.get_thread(conn, thread_id)
    return found.number if found else None


def clock_view(conn: Connection, row: registry.ClockRow, today: date | None = None) -> ClockView:
    """One clock with its figures as of ``today`` (the module's today by default).

    The dates, state and days left are recomputed from the clock's events and its calendar; when
    that fails (the calendar file is gone, an event does not fit the engine) the stored values are
    shown and ``problem`` says why, so a damaged clock is visible, not hidden.
    """
    day = today or today_date()
    state, left, problem = row.state, None, None
    due, warned, paused, closed = row.due_on, row.warned_level, row.paused_on, row.closed_on
    try:
        calendar = catalog.calendar_for(row.calendar, row.scope)
        figures = replay(registry.clock_facts(conn, row.id), calendar)
        state = effective_state(figures.state, figures.due_on, day)
        left = days_left(calendar, figures, day)
        due = figures.due_on.isoformat()
        warned = figures.warned_level
        paused = figures.paused_on.isoformat() if figures.paused_on else None
        closed = figures.closed_on.isoformat() if figures.closed_on else None
    except Exception as exc:  # noqa: BLE001 - any failure shows the stored figures and says why
        problem = str(exc) or type(exc).__name__
        state = effective_state(row.state, date.fromisoformat(row.due_on), day)
    return ClockView(
        id=row.id,
        key=row.item_number,
        item_id=row.item_id,
        item_number=row.item_number,
        label=row.label,
        kind=row.kind,
        start_on=row.start_on,
        duration_days=row.duration_days,
        day_type=row.day_type,
        calendar=row.calendar,
        warn_days=row.warn_days,
        due_on=due,
        state=row.state,
        effective_state=state,
        days_left=left,
        warned_level=warned,
        paused_on=paused,
        closed_on=closed,
        closed_reason=row.closed_reason,
        owner=row.owner,
        clause_id=row.clause_id,
        restarts=row.restarts,
        problem=problem,
    )


def item_view(conn: Connection, scope: str, number: str) -> ItemView:
    """One item with its clocks and (for a privileged item) the accounts named on it.

    Raises ``ItemNotFoundError`` for an unknown number and for an item the viewer may not read,
    with the same message.
    """
    row = registry.find_item(conn, scope, number)
    if row is None:
        raise ItemNotFoundError(f"no correspondence item {number!r} in scope {scope!r}")
    return _item(conn, row)


def item_view_by_id(conn: Connection, scope: str, item_id: str) -> ItemView:
    row = registry.get_item(conn, item_id)
    if row is None or row.scope != scope:
        raise ItemNotFoundError(f"no correspondence item {item_id!r} in scope {scope!r}")
    return _item(conn, row)


def _item(conn: Connection, row: registry.ItemRow) -> ItemView:
    return ItemView(
        id=row.id,
        number=row.number,
        subject=row.subject,
        state=row.state,
        direction=row.direction,
        medium=row.medium,
        received_via=row.received_via,
        external_ref=row.external_ref,
        from_name=row.from_name,
        from_party_id=row.from_party_id,
        to=_recipients(row.to),
        cc=_recipients(row.cc),
        sent_on=row.sent_on,
        received_on=row.received_on,
        issued_on=row.issued_on,
        body=row.body,
        confidentiality=row.confidentiality,
        domain=row.domain,
        subtype=row.subtype,
        thread_id=row.thread_id,
        thread_number=_thread_number(conn, row.thread_id),
        responds_to_id=row.responds_to_id,
        responds_to_number=_number_of(conn, row.responds_to_id),
        superseded_by_id=row.superseded_by_id,
        response_required=row.response_required,
        response_due=row.response_due,
        responded_on=row.responded_on,
        triaged_on=row.triaged_on,
        triaged_by=row.triaged_by,
        delivery=row.delivery,
        rendition_file_id=row.rendition_file_id,
        version=row.version,
        clocks=[clock_view(conn, c) for c in registry.clocks_of(conn, row.id)],
        clearances=[
            ClearanceView(account=c.account, granted_by=c.granted_by, granted_on=c.granted_on)
            for c in registry.clearances_of(conn, row.id)
        ],
    )


def _line(row: registry.ItemRow) -> RegisterLineView:
    when = row.issued_on if row.direction == "out" and row.issued_on else None
    counterparty = row.from_name
    if row.direction == "out" and row.to:
        counterparty = str(row.to[0].get("name") or row.to[0].get("email") or "") or None
    return RegisterLineView(
        kind=sources.KIND_ITEM,
        id=row.id,
        number=row.number,
        subject=row.subject,
        domain=row.domain,
        subtype=row.subtype,
        direction=row.direction,
        state=row.state,
        on=when or row.received_on or row.sent_on,
        counterparty=counterparty,
        response_due=row.response_due,
        confidentiality=row.confidentiality,
        thread_id=row.thread_id,
    )


def register(
    conn: Connection,
    scope: str,
    *,
    state: str | None = None,
    direction: str | None = None,
    domain: str | None = None,
    subtype: str | None = None,
    awaiting_response: bool = False,
    include_void: bool = False,
    include_sources: bool = True,
    limit: int = 500,
    offset: int = 0,
) -> list[RegisterLineView]:
    """The master register: items the viewer may read plus the lines of the domains' sources.

    Newest first (by date, then number). ``state`` and ``awaiting_response`` apply to items; a
    source line is kept when ``domain`` (and ``subtype``, ``direction``, ``state``) match it.
    """
    items = registry.list_items(
        conn,
        scope,
        state=state,
        direction=direction,
        domain=domain,
        subtype=subtype,
        awaiting_response=awaiting_response,
        include_void=include_void,
        limit=limit + offset,
    )
    lines = [_line(i) for i in items]
    if include_sources and not awaiting_response:
        names = {d.item_source for d in catalog.domain_set().for_scope(scope) if d.item_source}
        for name in sorted(names):
            source = sources.SOURCES.get(name)
            if source is None:
                continue
            for line in source(conn, scope, limit + offset):
                if (
                    (domain is None or line.domain == domain)
                    and (subtype is None or line.subtype == subtype)
                    and (direction is None or line.direction == direction)
                    and (state is None or line.state == state)
                ):
                    lines.append(
                        RegisterLineView.model_validate({**line.__dict__, "id": line.record_id})
                    )
    lines.sort(key=lambda ln: (ln.on or "", ln.number), reverse=True)
    return lines[offset : offset + limit]


# --- threads, clocks, parties, clauses, domains ----------------------------------------------


def thread_view(conn: Connection, scope: str, number: str) -> ThreadView:
    row = registry.find_thread(conn, scope, number)
    if row is None:
        raise ThreadNotFoundError(f"no thread {number!r} in scope {scope!r}")
    return ThreadView(
        id=row.id,
        number=row.number,
        subject_key=row.subject_key,
        state=row.state,
        domain=row.domain,
        item_count=row.item_count,
        last_item_on=row.last_item_on,
        governing_item_id=row.governing_item_id,
        items=[_line(i) for i in registry.items_of_thread(conn, row.id)],
    )


def thread_views(conn: Connection, scope: str, *, state: str | None = None) -> list[ThreadView]:
    return [
        ThreadView(
            id=t.id,
            number=t.number,
            subject_key=t.subject_key,
            state=t.state,
            domain=t.domain,
            item_count=t.item_count,
            last_item_on=t.last_item_on,
            governing_item_id=t.governing_item_id,
        )
        for t in registry.list_threads(conn, scope, state=state)
    ]


def clock_views(
    conn: Connection,
    scope: str,
    *,
    open_only: bool = True,
    due_to: str | None = None,
    overdue_only: bool = False,
    today: date | None = None,
) -> list[ClockView]:
    """The clocks of a scope the viewer may read, soonest due first, as of today.

    ``overdue_only`` keeps those whose effective state is expired.
    """
    day = today or today_date()
    rows = registry.list_clocks(conn, scope, open_only=open_only, due_to=due_to)
    views = [clock_view(conn, r, day) for r in rows]
    if overdue_only:
        views = [v for v in views if v.effective_state == "expired"]
    return views


def clock_view_by_id(conn: Connection, scope: str, clock_id: str) -> ClockView:
    row = registry.get_clock(conn, clock_id)
    if row is None or row.scope != scope:
        raise ItemNotFoundError(f"no clock {clock_id!r} in scope {scope!r}")
    return clock_view(conn, row)


def party_views(conn: Connection, scope: str, *, include_inactive: bool = False) -> list[PartyView]:
    out: list[PartyView] = []
    for party in registry.list_parties(conn, scope, include_inactive=include_inactive):
        out.append(_party(conn, party))
    return out


def _party(conn: Connection, party: registry.PartyRow) -> PartyView:
    return PartyView(
        id=party.id,
        code=party.code,
        name=party.name,
        project_role=party.project_role,
        email_domains=party.email_domains,
        is_active=party.is_active,
        contacts=[
            ContactView(
                position=c.position,
                name=c.name,
                email=c.email,
                title=c.title,
                domain=c.domain,
                is_authorised=c.is_authorised,
                is_active=c.is_active,
            )
            for c in registry.contacts_of(conn, party.id, include_ended=True)
        ],
    )


def party_view(conn: Connection, scope: str, code: str) -> PartyView:
    found = registry.find_party(conn, scope, code)
    if found is None:
        raise PartyNotFoundError(f"no party {code!r} in scope {scope!r}")
    return _party(conn, found)


def clause_views(
    conn: Connection, scope: str, *, include_inactive: bool = False
) -> list[ClauseView]:
    return [
        ClauseView(
            id=c.id,
            contract=c.contract,
            clause_number=c.clause_number,
            time_bar_days=c.time_bar_days,
            time_bar_day_type=c.time_bar_day_type,
            notice_requirements=c.notice_requirements,
            required_recipients=c.required_recipients,
            service_method=c.service_method,
            contract_document_id=c.contract_document_id,
            domains=c.domains,
            is_active=c.is_active,
        )
        for c in registry.list_clauses(conn, scope, include_inactive=include_inactive)
    ]


def domain_views(scope: str) -> list[DomainView]:
    """The domain definitions in force for a project (one per code)."""
    out: list[DomainView] = []
    for d in catalog.domain_set().for_scope(scope):
        out.append(
            DomainView(
                code=d.code,
                name=d.name,
                semver=d.semver,
                scope=d.scope,
                description=d.description,
                default_subtype=d.default_subtype,
                confidentiality_default=d.confidentiality_default,
                item_source=d.item_source,
                subtypes=[
                    SubtypeView(
                        code=s.code,
                        label=s.label,
                        response_required=s.response_required,
                        clocks=[
                            ClockTemplateView(
                                label=c.label,
                                trigger=c.trigger,
                                kind=c.kind,
                                duration_days=c.duration_days,
                                day_type=c.day_type,
                                warn_days=list(c.warn_days),
                                clause=c.clause,
                            )
                            for c in s.clocks
                        ],
                    )
                    for s in d.subtypes
                ],
                templates=[t.code for t in d.templates],
            )
        )
    return out


def suggestion_for_item(conn: Connection, scope: str, number: str) -> SuggestionView:
    """The engine's proposal for an item the viewer may read (a read, available to every reader;
    it proposes, a person confirms)."""
    row = registry.find_item(conn, scope, number)
    if row is None:
        raise ItemNotFoundError(f"no correspondence item {number!r} in scope {scope!r}")
    return suggestion_for_text(scope, row.subject, row.body)


def suggestion_for_text(scope: str, subject: str, body: str | None = None) -> SuggestionView:
    found = suggest(catalog.domain_set().for_scope(scope), subject=subject, body=body)
    return SuggestionView(
        domain=found.domain,
        subtype=found.subtype,
        score=found.score,
        reasons=list(found.reasons),
        scores=found.scores,
    )
