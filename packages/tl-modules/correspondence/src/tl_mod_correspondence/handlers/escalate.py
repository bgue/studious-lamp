"""Escalate an answered RFI to the Commercial domain (brief 9, M10, "Cross-domain behaviour").

An answer that says it costs money or time is the start of a commercial matter: the contractor has
to give notice within the time bar. ``EscalateTechnical`` makes the Commercial item (an early
warning unless told otherwise) from the answered Technical item:

* the new item is **derived from** the RFI (a ``derived_from`` link the module writes as its own,
  which a person cannot retract) and takes the day of the answer as the day the contractor became
  aware, so its time bar counts from the answer;
* it is a Draft with the Commercial domain's class (``restricted``), or the RFI's class when that
  is higher, and it names the readers of a privileged RFI;
* **nothing is written on the RFI's stream**: the RFI shows who escalated it only to a reader who
  may read the new item, through the link (ADR-0016: an event on the RFI that named a restricted
  item would hand its number to every reader of the RFI).

The command is a document controller's, like every Commercial command. A rule (P1-I7, propose
mode) proposes it when an answer says ``yes`` to cost or schedule impact; a person accepts it.
"""

from __future__ import annotations

from pydantic import ConfigDict, Field, field_validator
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import RecordNotFoundError
from tl_core.uow import UnitOfWork

from tl_mod_correspondence import catalog, registry_domain
from tl_mod_correspondence.errors import InvalidItemError, ItemStateError
from tl_mod_correspondence.handlers.commercial import (
    RaiseCommercial,
    create_commercial,
    require_controller_viewer,
)
from tl_mod_correspondence.handlers.common import correlated, require_project
from tl_mod_correspondence.handlers.confidentiality import inherited_class
from tl_mod_correspondence.handlers.models import non_blank
from tl_mod_correspondence.limits import MAX_BODY, MAX_NUMBER, MAX_TEXT
from tl_mod_correspondence.names import DOMAIN_COMMERCIAL
from tl_mod_correspondence.textcheck import clean_body, clean_optional_text, clean_text


class EscalateTechnical(Command):
    """Make a Commercial item from an answered Technical item (a document controller's act).

    ``subtype`` is the kind of notice (``early_warning`` by default). ``subject`` and ``body``
    default to words that name the RFI and the answer. ``clause`` is ``<contract>/<number>`` of
    the contract clause the notice is given under. The new item is a Draft whose time bar counts
    from the day of the answer.
    """

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    subtype: str = Field(default="early_warning", min_length=1, max_length=MAX_NUMBER)
    subject: str | None = Field(default=None, min_length=1, max_length=MAX_TEXT)
    body: str | None = Field(default=None, max_length=MAX_BODY)
    clause: str | None = Field(default=None, max_length=MAX_NUMBER)

    @field_validator("subject")
    @classmethod
    def _subject(cls, value: str | None) -> str | None:
        return None if value is None else clean_text(non_blank(value))

    @field_validator("body")
    @classmethod
    def _body(cls, value: str | None) -> str | None:
        return None if value is None else clean_body(value)

    @field_validator("clause")
    @classmethod
    def _clause(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


def handle_escalate_technical(uow: UnitOfWork, cmd: EscalateTechnical) -> CommandResult:
    """Make the Commercial item (``create_commercial``) with a ``derived_from`` link to the RFI.

    Raises ``ForbiddenError`` (the viewer is below a document controller), ``RecordNotFoundError``
    (the item is unknown, foreign, hidden or not a Technical item), ``ItemStateError`` (it has no
    answer yet), ``InvalidItemError`` (it was escalated already, to an item the viewer can read)
    and the errors of ``create_commercial``.
    """
    require_controller_viewer()
    require_project(cmd)
    cmd = correlated(cmd)
    found = registry_domain.get_technical(uow.conn(), cmd.stream_id)
    if found is None or found.item.scope != cmd.scope:
        raise RecordNotFoundError(f"no record {cmd.stream_id!r}")
    item, data = found.item, found.data
    if data.answered_on is None:
        raise ItemStateError(f"item {item.number} has no answer yet; there is nothing to escalate")
    earlier = registry_domain.derived_from_commercial(uow.conn(), item.id)
    live = [e.item.number for e in earlier if e.item.state != "Void"]
    if live:
        raise InvalidItemError(f"item {item.number} was escalated already, as {', '.join(live)}")
    definition = catalog.check_subtype(cmd.scope, DOMAIN_COMMERCIAL, cmd.subtype)
    named, clearances = inherited_class(uow, item, cmd.actor)
    if named == "internal":  # the domain's own class applies, never lower
        named, clearances = definition.confidentiality_default, []
    chosen = definition.subtype(cmd.subtype)
    assert chosen is not None  # check_subtype ran
    raised = RaiseCommercial(
        actor=cmd.actor,
        source=cmd.source,
        scope=cmd.scope,
        correlation_id=cmd.correlation_id,
        causation_id=cmd.causation_id,
        subtype=cmd.subtype,
        subject=cmd.subject or f"{chosen.label}: {item.subject}"[:MAX_TEXT],
        body=cmd.body
        or (
            f"{item.number} was answered on {data.answered_on}"
            f" with cost impact {data.answer_cost_impact} and schedule impact"
            f" {data.answer_schedule_impact}.\n\nQuestion: {data.question}"
        )[:MAX_BODY],
        clause=cmd.clause,
        aware_on=data.answered_on,
        entitlement_basis=f"Answer to {item.number} of {data.answered_on}",
    )
    return create_commercial(
        uow,
        raised,
        definition=definition,
        derived_from=item,
        confidentiality_class=named,
        clearances=clearances,
    )
