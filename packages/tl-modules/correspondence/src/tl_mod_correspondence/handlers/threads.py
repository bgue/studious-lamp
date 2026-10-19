"""Threads: group the items of one exchange, and replace an item by another (brief 9 M10).

A **thread** is opened by its first item (``CorrespondenceThread.Defined``, numbered from the
``THR`` pattern) and grows by ``ItemAdded``. ``assign_thread`` decides where an item belongs using
the pure rules of ``threading.match_thread``: the message ids of the email headers first, then the
item numbers written in the subject or text, then the normalised subject of an open thread. An item
that matches nothing opens a thread of its own. Only items and threads the viewer may read are
candidates: a hidden thread is never joined (ADR-0016).

``AssignThread`` is the manual form (a person moves an item to a thread, or says what it answers).
``SupersedeCorrespondence`` replaces an item by another (a corrected letter); the old item stays in
the register, marked superseded, and a ``supersedes`` link says which replaced which.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import ConfigDict, Field, field_validator
from tl_core.ledger import Event, NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import NoChangesError, RecordNotFoundError
from tl_core.services.links import AddLink, handle_add_link
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork

from tl_mod_correspondence import registry
from tl_mod_correspondence.errors import InvalidItemError, ItemStateError, ThreadNotFoundError
from tl_mod_correspondence.handlers.common import (
    append,
    correlated,
    load_item,
    open_item,
    today,
)
from tl_mod_correspondence.handlers.confidentiality import inherit_from_matches
from tl_mod_correspondence.handlers.models import non_blank
from tl_mod_correspondence.limits import MAX_NUMBER, MAX_REASON
from tl_mod_correspondence.names import (
    CORR_SUPERSEDED,
    CORR_THREAD_ASSIGNED,
    CORRESPONDENCE,
    THREAD,
    THREAD_DEFINED,
    THREAD_ITEM_ADDED,
)
from tl_mod_correspondence.threading import (
    KnownItem,
    ThreadFacts,
    ThreadMatch,
    find_item_numbers,
    match_thread,
    normalise_message_id,
    normalise_subject,
)

#: The type codes of the item numbers the text is searched for (``P123-COR-0042``).
ITEM_TYPE_CODES = ("COR",)


class AssignThread(Command):
    """Move an item to a thread, or open a new thread for it, and say what it answers.

    With ``thread_id`` the item joins that thread (which must be readable). Without it a new
    thread is opened with this item as its first. ``responds_to_id`` names the item it answers.
    """

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    thread_id: str | None = Field(default=None, max_length=MAX_NUMBER)
    responds_to_id: str | None = Field(default=None, max_length=MAX_NUMBER)


class SupersedeCorrespondence(Command):
    """Replace an item by another item (a document controller's act).

    The old item is marked superseded by the new one and takes no more changes; a reason is
    required.
    """

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    superseded_by_id: str = Field(max_length=MAX_NUMBER)
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return non_blank(value)


def thread_facts_for(item: registry.ItemRow, references: Sequence[str] = ()) -> ThreadFacts:
    """What the item says about where it belongs: its headers, subject key and item numbers."""
    project = item.scope.removeprefix("project:")
    text = f"{item.subject}\n{item.body or ''}"
    own = {item.number}
    numbers = [n for n in find_item_numbers(text, project, ITEM_TYPE_CODES) if n not in own]
    return ThreadFacts(
        in_reply_to=normalise_message_id(item.in_reply_to),
        references=[r for r in (normalise_message_id(x) for x in references) if r],
        subject_key=normalise_subject(item.subject),
        numbers=numbers,
    )


def find_match(
    uow: UnitOfWork, item: registry.ItemRow, references: Sequence[str] = ()
) -> ThreadMatch | None:
    """Where ``item`` belongs according to the readable items and threads of its scope."""
    conn = uow.conn()
    if item.responds_to_id is not None:
        answered = registry.get_item(conn, item.responds_to_id)
        if answered is not None and answered.id != item.id:
            return ThreadMatch(answered.thread_id, answered.id, "manual")
    facts = thread_facts_for(item, references)
    by_message_id: dict[str, KnownItem] = {}
    message_ids = [*facts.references, *([facts.in_reply_to] if facts.in_reply_to else [])]
    for message_id in message_ids:
        found = registry.find_by_message_id(conn, item.scope, message_id)
        if found is not None and found.id != item.id:
            by_message_id[message_id] = KnownItem(found.id, found.thread_id)
    by_number: dict[str, KnownItem] = {}
    for number in facts.numbers:
        known = registry.find_item(conn, item.scope, number)
        if known is not None and known.id != item.id:
            by_number[number] = KnownItem(known.id, known.thread_id)
    subjects: dict[str, str] = {}
    for thread in registry.thread_candidates(conn, item.scope, facts.subject_key):
        subjects.setdefault(thread.subject_key, thread.id)
    return match_thread(facts, by_message_id, by_number, subjects)


def _open_thread(
    uow: UnitOfWork, cmd: Command, governing: registry.ItemRow
) -> tuple[str, list[Event]]:
    """A new thread whose first item is ``governing``. Returns its id and its events."""
    made = create_module_record(uow, cmd, record_type=THREAD, title=governing.subject, key=None)
    defined = append(
        uow,
        cmd,
        made.stream_id,
        THREAD,
        [
            NewEvent(
                event_type=THREAD_DEFINED,
                payload={
                    "number": made.key,
                    "subject_key": normalise_subject(governing.subject),
                    "domain": governing.domain,
                    "governing_item_id": governing.id,
                    "item_on": governing.received_on or governing.sent_on or today(),
                },
            )
        ],
        expected=made.version,
    )
    return made.stream_id, [*made.events, *defined.events]


def _join(
    uow: UnitOfWork,
    cmd: Command,
    thread_id: str,
    item: registry.ItemRow,
    responds_to_id: str | None,
    matched_by: str,
    *,
    first: bool = False,
) -> list[Event]:
    """``ItemAdded`` on the thread and ``ThreadAssigned`` on the item.

    ``first=True`` is the item that opened the thread: ``Defined`` counted it already, so only
    the item gets an event.
    """
    added: list[Event] = []
    if not first:
        added = append(
            uow,
            cmd,
            thread_id,
            THREAD,
            [
                NewEvent(
                    event_type=THREAD_ITEM_ADDED,
                    payload={
                        "item_id": item.id,
                        "item_on": item.received_on or item.sent_on or today(),
                    },
                )
            ],
        ).events
    assigned = append(
        uow,
        cmd,
        item.id,
        CORRESPONDENCE,
        [
            NewEvent(
                event_type=CORR_THREAD_ASSIGNED,
                payload={
                    "thread_id": thread_id,
                    "responds_to_id": responds_to_id,
                    "matched_by": matched_by,
                },
            )
        ],
    )
    return [*added, *assigned.events]


def assign_thread(
    uow: UnitOfWork, cmd: Command, item: registry.ItemRow, references: Sequence[str] = ()
) -> list[Event]:
    """Put ``item`` in the thread it belongs to, opening one when nothing matches.

    Returns the events appended. An item that already has a thread is left alone (``[]``).
    """
    if item.thread_id is not None:
        return []
    match = find_match(uow, item, references)
    if match is None:
        thread_id, events = _open_thread(uow, cmd, item)
        return [*events, *_join(uow, cmd, thread_id, item, None, "manual", first=True)]
    events: list[Event] = []
    matched_thread = match.thread_id
    if matched_thread is None:
        earlier = registry.get_item(uow.conn(), match.responds_to_id or "")
        if earlier is None:
            thread_id, events = _open_thread(uow, cmd, item)
            return [*events, *_join(uow, cmd, thread_id, item, None, "manual", first=True)]
        thread_id, events = _open_thread(uow, cmd, earlier)
        events += _join(uow, cmd, thread_id, earlier, None, match.matched_by, first=True)
    else:
        thread_id = matched_thread
    events += _join(uow, cmd, thread_id, item, match.responds_to_id, match.matched_by)
    return [*events, *_inherit(uow, cmd, item, thread_id, match.responds_to_id)]


def _inherit(
    uow: UnitOfWork, cmd: Command, item: registry.ItemRow, thread_id: str, answers: str | None
) -> list[Event]:
    """The item takes the class of what it answers and of the thread's first item."""
    thread = registry.get_thread(uow.conn(), thread_id)
    opened_by = thread.governing_item_id if thread is not None else None
    return inherit_from_matches(uow, cmd, item, [answers, opened_by])


def with_thread(uow: UnitOfWork, cmd: Command, made: CommandResult) -> CommandResult:
    """``made`` (a new item) once the item is in its thread: the events are added to the result."""
    item = registry.get_item(uow.conn(), made.stream_id)
    if item is None:
        return made
    events = assign_thread(uow, cmd, item)
    current = registry.get_item(uow.conn(), item.id)
    return CommandResult(
        stream_id=made.stream_id,
        key=made.key,
        version=current.version if current else made.version,
        events=[*made.events, *events],
    )


def handle_assign_thread(uow: UnitOfWork, cmd: AssignThread) -> CommandResult:
    """Join ``stream_id`` to a thread by hand (or open a new one).

    Raises ``RecordNotFoundError`` (item or answered item unknown, foreign or hidden),
    ``ThreadNotFoundError`` (no readable thread of that id in the scope), ``ItemStateError`` (the
    item is void) and ``NoChangesError`` (it is in that thread already).
    """
    cmd = correlated(cmd)
    item = load_item(uow, cmd, cmd.stream_id)
    if item.voided or item.state == "Void":
        raise ItemStateError(f"item {item.number} is void")
    if cmd.responds_to_id is not None:
        answered = registry.get_item(uow.conn(), cmd.responds_to_id)
        if answered is None or answered.scope != cmd.scope:
            raise RecordNotFoundError(f"no record {cmd.responds_to_id!r}")
        if answered.id == item.id:
            raise InvalidItemError("an item cannot answer itself")
    events: list[Event] = []
    if cmd.thread_id is None:
        thread_id, events = _open_thread(uow, cmd, item)
    else:
        thread = registry.get_thread(uow.conn(), cmd.thread_id)
        if thread is None or thread.scope != cmd.scope:
            raise ThreadNotFoundError(f"no thread {cmd.thread_id!r} in scope {cmd.scope!r}")
        if item.thread_id == thread.id and cmd.responds_to_id in (None, item.responds_to_id):
            raise NoChangesError(f"item {item.number} is already in thread {thread.number}")
        thread_id = thread.id
    events += _join(
        uow,
        cmd,
        thread_id,
        item,
        cmd.responds_to_id,
        "manual",
        first=cmd.thread_id is None,
    )
    if cmd.thread_id is not None:
        events += _inherit(uow, cmd, item, thread_id, cmd.responds_to_id)
    current = registry.get_item(uow.conn(), item.id)
    return CommandResult(
        stream_id=item.id,
        key=item.number,
        version=current.version if current else item.version,
        events=events,
    )


def handle_supersede_correspondence(uow: UnitOfWork, cmd: SupersedeCorrespondence) -> CommandResult:
    """Append ``Correspondence.Superseded`` and a ``supersedes`` link from the new item.

    Raises ``RecordNotFoundError`` (either item unknown, foreign or hidden), ``ItemStateError``
    (the old item is closed, or the new one is void) and ``InvalidItemError`` (an item cannot
    replace itself).
    """
    cmd = correlated(cmd)
    old = open_item(uow, cmd, cmd.stream_id)
    new = load_item(uow, cmd, cmd.superseded_by_id)
    if new.id == old.id:
        raise InvalidItemError("an item cannot supersede itself")
    if new.voided or new.state == "Void":
        raise ItemStateError(f"item {new.number} is void and cannot replace another")
    done = append(
        uow,
        cmd,
        old.id,
        CORRESPONDENCE,
        [
            NewEvent(
                event_type=CORR_SUPERSEDED,
                payload={"superseded_by_id": new.id, "reason": cmd.reason},
            )
        ],
        expected=cmd.expected_version or old.version,
    )
    linked = handle_add_link(
        uow,
        AddLink(
            actor=cmd.actor,
            source=cmd.source,
            scope=cmd.scope,
            correlation_id=cmd.correlation_id,
            causation_id=cmd.causation_id,
            from_id=new.id,
            to_id=old.id,
            relation="supersedes",
            link_source="rule",
            note=cmd.reason,
        ),
        by_module=True,
    )
    return CommandResult(
        stream_id=old.id,
        key=old.number,
        version=done.new_version,
        events=[*done.events, *linked.events],
    )
