"""Which commands the viewer may run on an item now: the table and the hook (P1-UX2-S1).

``RULES`` is the one source for three things that must not drift apart: the states in which an item
of each type takes a command (the handlers read them with ``states_for`` in their ``require_state``
calls), the access level of the command (a test holds it equal to the ``access`` of
``commands.API_COMMANDS``), and the label a screen shows for it. ``item_actions`` is the hook the
module gives ``ModuleSpec.actions``; it is a pure function of the item's own rows and ``holds``.

An offer is advice. The handler still checks the state, the access word and everything the data
needs (a recipient, a reason) when the command runs, and a refusal is shown as it is. What the
table cannot say (a letter we received is never issued; an RFI is escalated once, after an answer)
is a ``check`` on the rule, read from the same rows the handler reads.

Commands that need no record (register, create, raise) are not offers. A Commercial item is changed
by controllers only, whatever the access word of the command (ADR-0019 section 3), so every rule on
a Commercial item asks for ``controller`` at least.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from sqlalchemy import Connection
from tl_core.actions import ActionOffer, Holds, Level

from tl_mod_correspondence import registry, registry_domain
from tl_mod_correspondence.names import (
    COMMERCIAL,
    CORRESPONDENCE,
    ST_ACCEPTED,
    ST_AGREED,
    ST_ANSWERED,
    ST_AWAITING_ASSESSMENT,
    ST_AWAITING_RESPONSE,
    ST_COMMERCIAL_REVIEW,
    ST_DISPUTED,
    ST_DRAFT,
    ST_INTERNAL_REVIEW,
    ST_ISSUED,
    ST_PARTLY_AGREED,
    ST_PM_APPROVAL,
    ST_RECEIVED,
    ST_REJECTED,
    ST_RESPONDED,
    ST_TRIAGED,
    TECHNICAL,
)

#: A check on the item that the state alone does not give. ``True`` keeps the offer.
Check = Callable[[Connection, registry.ItemRow], bool]


def _no_check(conn: Connection, item: registry.ItemRow) -> bool:
    return True


def _letter_we_wrote(conn: Connection, item: registry.ItemRow) -> bool:
    """Only a letter we wrote is issued (``handle_issue_correspondence``)."""
    return item.direction == "out"


def _answered_and_not_escalated(conn: Connection, item: registry.ItemRow) -> bool:
    """The RFI has an answer and no live Commercial item was raised from it already
    (``handle_escalate_technical``): both are read as that handler reads them."""
    found = registry_domain.get_technical(conn, item.id)
    if found is None or found.data.answered_on is None:
        return False
    earlier = registry_domain.derived_from_commercial(conn, item.id)
    return not [e for e in earlier if e.item.state != "Void"]


@dataclass(frozen=True)
class Rule:
    """One command a screen may offer: its label, the access it asks for, and the item states in
    which each record type takes it (``None``: the state does not matter, ``check`` decides)."""

    command: str  # the command model's class name, as in ``commands.API_COMMANDS``
    label: str  # plain words
    level: Level
    states: Mapping[str, tuple[str, ...]] | None
    #: ``False`` for a command that does not use ``open_item``/``open_technical``: it also works on
    #: an item that is closed.
    needs_open: bool = True
    check: Check = field(default=_no_check)


#: Both voids offer the same word: the first rule that applies wins (see ``item_actions``), so a
#: Draft shows the person's own void and a Received item the controller's.
_UNISSUED_TECHNICAL = (ST_DRAFT, ST_INTERNAL_REVIEW)
_UNISSUED_COMMERCIAL = (ST_DRAFT, ST_COMMERCIAL_REVIEW, ST_PM_APPROVAL)

RULES: tuple[Rule, ...] = (
    # letters and minutes (the core item)
    Rule("ConfirmTriage", "Triage", "user", {CORRESPONDENCE: (ST_RECEIVED,)}),
    Rule(
        "RecordResponse",
        "Record response",
        "user",
        {CORRESPONDENCE: (ST_RECEIVED, ST_TRIAGED, ST_ISSUED)},
    ),
    Rule(
        "CloseCorrespondence",
        "Close",
        "user",
        {CORRESPONDENCE: (ST_TRIAGED, ST_ISSUED, ST_RESPONDED)},
    ),
    Rule(
        "IssueCorrespondence",
        "Issue",
        "controller",
        {CORRESPONDENCE: (ST_DRAFT,)},
        check=_letter_we_wrote,
    ),
    # Technical items: RFI, technical query, deviation request
    Rule("SubmitTechnical", "Submit for review", "user", {TECHNICAL: (ST_DRAFT,)}),
    Rule("ReturnTechnical", "Return to draft", "user", {TECHNICAL: (ST_INTERNAL_REVIEW,)}),
    Rule("IssueTechnical", "Issue", "controller", {TECHNICAL: (ST_INTERNAL_REVIEW,)}),
    Rule("AnswerTechnical", "Answer", "user", {TECHNICAL: (ST_AWAITING_RESPONSE,)}),
    Rule("ReviewTechnicalAnswer", "Review answer", "user", {TECHNICAL: (ST_ANSWERED,)}),
    Rule("ReissueTechnical", "Reissue", "user", {TECHNICAL: (ST_REJECTED,)}),
    Rule(
        "CloseTechnical",
        "Close",
        "user",
        {TECHNICAL: (ST_AWAITING_RESPONSE, ST_ACCEPTED, ST_REJECTED)},
    ),
    Rule(
        "EscalateTechnical",
        "Escalate",
        "controller",
        None,
        needs_open=False,
        check=_answered_and_not_escalated,
    ),
    # Commercial items: controllers only
    Rule("SubmitCommercial", "Submit for review", "controller", {COMMERCIAL: (ST_DRAFT,)}),
    Rule("ReviewCommercial", "Approve review", "controller", {COMMERCIAL: (ST_COMMERCIAL_REVIEW,)}),
    Rule(
        "ReturnCommercial",
        "Return to draft",
        "controller",
        {COMMERCIAL: (ST_COMMERCIAL_REVIEW, ST_PM_APPROVAL)},
    ),
    Rule("IssueCommercial", "Issue", "controller", {COMMERCIAL: (ST_PM_APPROVAL,)}),
    Rule(
        "AssessCommercial",
        "Record assessment",
        "controller",
        {COMMERCIAL: (ST_AWAITING_ASSESSMENT,)},
    ),
    Rule(
        "CloseCommercial",
        "Close",
        "controller",
        {COMMERCIAL: (ST_AGREED, ST_PARTLY_AGREED, ST_DISPUTED)},
    ),
    Rule("ReferCommercialToLegal", "Refer to legal", "controller", {COMMERCIAL: (ST_DISPUTED,)}),
    # last: a void is the one act that cannot be undone
    Rule(
        "VoidDraft",
        "Void",
        "user",
        {
            CORRESPONDENCE: (ST_DRAFT,),
            TECHNICAL: _UNISSUED_TECHNICAL,
            COMMERCIAL: _UNISSUED_COMMERCIAL,
        },
    ),
    Rule(
        "VoidCorrespondence",
        "Void",
        "controller",
        {
            CORRESPONDENCE: (ST_DRAFT, ST_RECEIVED),
            TECHNICAL: _UNISSUED_TECHNICAL,
            COMMERCIAL: _UNISSUED_COMMERCIAL,
        },
    ),
)

#: The states a command takes on a record type, for the handlers' ``require_state``. Two rules of
#: one command never share a record type, so this is a plain lookup.
_STATES: dict[tuple[str, str], tuple[str, ...]] = {
    (rule.command, record_type): states
    for rule in RULES
    for record_type, states in (rule.states or {}).items()
}


def states_for(command: str, record_type: str) -> tuple[str, ...]:
    """The states in which ``command`` takes an item of ``record_type`` (``KeyError`` for a pair
    the table does not hold: a handler asking for a rule that is not written is a bug)."""
    return _STATES[(command, record_type)]


_RANK: dict[Level, int] = {"user": 0, "controller": 1, "admin": 2}


def effective_level(rule: Rule, record_type: str) -> Level:
    """The access the command needs on this record type: a Commercial item asks for a controller
    whatever the command's own word."""
    if record_type == COMMERCIAL and _RANK[rule.level] < _RANK["controller"]:
        return "controller"
    return rule.level


def item_actions(conn: Connection, record_id: str, holds: Holds) -> list[ActionOffer]:
    """The commands the viewer may run on this item now, in the order of ``RULES``.

    The item is read as the handlers read it (``registry.get_item``: the viewer's class filter
    applies; an item the viewer may not read has no actions). A word that two rules share is
    offered once.
    """
    item = registry.get_item(conn, record_id)
    if item is None:
        return []
    offers: list[ActionOffer] = []
    seen: set[str] = set()
    for rule in RULES:
        if rule.states is not None:
            states = rule.states.get(item.record_type)
            if states is None or item.state not in states:
                continue
        elif item.record_type != TECHNICAL:
            continue  # a rule with no states is the escalation of an RFI
        if rule.needs_open and item.closed:
            continue
        if rule.label in seen or not holds(effective_level(rule, item.record_type)):
            continue
        if not rule.check(conn, item):
            continue
        seen.add(rule.label)
        offers.append(ActionOffer(command=rule.command, label=rule.label))
    return offers


__all__ = ["RULES", "Rule", "effective_level", "item_actions", "states_for"]
