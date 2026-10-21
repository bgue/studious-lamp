"""Which commands the viewer may run on a document, a revision or a transmittal now (P1-UX2-S1).

``RULES`` is the one source of the states in which each record type takes a command (the revision
and transmittal handlers read them with ``states_for``), of the access level (a test holds it equal
to the ``access`` of ``commands.API_COMMANDS``) and of the label a screen shows. The hooks
``document_actions``, ``revision_actions`` and ``transmittal_actions`` are pure functions of the
record's own rows and ``holds``.

A document is *open* until it is void or superseded (``DocumentRow.closed``, the property
``open_document`` uses): every command on a document, and on a revision that changes it, needs an
open document. An offer is advice; the handler still checks everything when the command runs.
Commands that need no record (register a document, upload) are not offers; creating a revision is
not either, because it is a form of its own.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from sqlalchemy import Connection
from tl_core.actions import ActionOffer, Holds, Level

from tl_mod_documents import registry
from tl_mod_documents.names import DOCUMENT, REVISION, TRANSMITTAL

#: A check on the revision that its state alone does not give. ``True`` keeps the offer.
Check = Callable[[registry.RevisionRow], bool]


def _no_check(rev: registry.RevisionRow) -> bool:
    return True


def _issued_and_current(rev: registry.RevisionRow) -> bool:
    """Only the current issued revision is superseded (``handle_supersede_revision``)."""
    return rev.is_current


@dataclass(frozen=True)
class Rule:
    """One command a screen may offer, with the states of each record type that take it.

    ``states`` is ``None`` for a document: the state does not matter, an open document does.
    ``in_open_document`` is ``False`` for a command that does not look at the revision's document
    (a transmittal of issued revisions is made whatever became of the document).
    """

    command: str  # the command model's class name, as in ``commands.API_COMMANDS``
    label: str  # plain words
    level: Level
    record_type: str
    states: tuple[str, ...] | None
    in_open_document: bool = True
    check: Check = field(default=_no_check)


#: Revision states that a transmittal may carry: issued, current or since superseded.
CARRIABLE = ("Issued", "Superseded")

RULES: tuple[Rule, ...] = (
    # a document
    Rule("SupersedeDocument", "Supersede", "controller", DOCUMENT, None),
    Rule("VoidDocument", "Void", "controller", DOCUMENT, None),
    # a revision
    Rule("IssueRevision", "Issue", "controller", REVISION, ("Draft",)),
    Rule(
        "SupersedeRevision",
        "Supersede",
        "controller",
        REVISION,
        ("Issued",),
        check=_issued_and_current,
    ),
    Rule(
        "CreateTransmittal",
        "Create transmittal",
        "user",
        REVISION,
        CARRIABLE,
        in_open_document=False,
    ),
    Rule("VoidRevision", "Void", "user", REVISION, ("Draft",)),
    # a transmittal
    Rule("IssueTransmittal", "Issue", "controller", TRANSMITTAL, ("Draft",)),
    Rule("RecordTransmittalResponse", "Record response", "user", TRANSMITTAL, ("Issued",)),
    Rule("CloseTransmittal", "Close", "user", TRANSMITTAL, ("Issued", "Acknowledged")),
    Rule("VoidTransmittal", "Void", "user", TRANSMITTAL, ("Draft",)),
)

_STATES: Mapping[tuple[str, str], tuple[str, ...]] = {
    (rule.command, rule.record_type): rule.states for rule in RULES if rule.states is not None
}


def states_for(command: str, record_type: str) -> tuple[str, ...]:
    """The states in which ``command`` takes a record of ``record_type`` (``KeyError`` for a pair
    the table does not hold: a handler asking for a rule that is not written is a bug)."""
    return _STATES[(command, record_type)]


def _offers(
    record_type: str,
    holds: Holds,
    state_ok: Callable[[Rule], bool],
    rev: registry.RevisionRow | None = None,
) -> list[ActionOffer]:
    offers: list[ActionOffer] = []
    for rule in RULES:
        if rule.record_type != record_type or not state_ok(rule) or not holds(rule.level):
            continue
        if rev is not None and not rule.check(rev):
            continue
        offers.append(ActionOffer(command=rule.command, label=rule.label))
    return offers


def document_actions(conn: Connection, record_id: str, holds: Holds) -> list[ActionOffer]:
    """The commands the viewer may run on this document now: none once it is void or superseded.

    The document is read as the handlers read it (one the viewer may not read has no actions).
    """
    doc = registry.get_document(conn, record_id)
    if doc is None or doc.closed:
        return []
    return _offers(DOCUMENT, holds, lambda rule: True)


def revision_actions(conn: Connection, record_id: str, holds: Holds) -> list[ActionOffer]:
    """The commands the viewer may run on this revision now, judged on its state and, for the
    commands that change it, on its document being open."""
    rev = registry.get_revision(conn, record_id)
    if rev is None or rev.voided:
        return []
    parent = registry.get_document(conn, rev.document_id)
    if parent is None:
        return []

    def state_ok(rule: Rule) -> bool:
        return (
            rule.states is not None
            and rev.state in rule.states
            and not (rule.in_open_document and parent.closed)
        )

    return _offers(REVISION, holds, state_ok, rev)


def transmittal_actions(conn: Connection, record_id: str, holds: Holds) -> list[ActionOffer]:
    """The commands the viewer may run on this transmittal now, by its state."""
    row = registry.get_transmittal(conn, record_id)
    if row is None or row.voided:
        return []
    return _offers(
        TRANSMITTAL, holds, lambda rule: rule.states is not None and row.state in rule.states
    )


__all__ = [
    "CARRIABLE",
    "RULES",
    "Rule",
    "document_actions",
    "revision_actions",
    "states_for",
    "transmittal_actions",
]
