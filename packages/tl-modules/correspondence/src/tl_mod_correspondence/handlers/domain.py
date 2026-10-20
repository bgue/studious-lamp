"""What the Technical and Commercial handlers share (P1-I6).

* **Value checks** for the fields of the domain tables: the yes/no/unknown flags, money as a decimal
  text with two places (never a float), hours with one place, a currency code, cost-code impacts.
  They are pydantic validators of the command models, so an API client, the CLI and a proposal
  meet the same rules.
* ``kind_numbering``: the ``kind`` field of the domain's numbering pattern (``RFI``, ``EW``).
* ``start_domain_clocks``: the clocks a subtype starts on a trigger (``awareness`` at the raise of a
  Commercial item, ``issue`` when it is issued), with the two rules that make a clock follow the
  item rather than the template: a time bar takes its length and day type from the contract clause
  the item names, and an item with a ``required_by`` date is answered by that date.
* ``link_references``: the records an item refers to, linked ``references`` (a document with a
  pinned revision, say).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text
from tl_core import confidentiality
from tl_core.ledger import Event
from tl_core.services.commands import Command
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.links import AddLink, handle_add_link
from tl_core.uow import UnitOfWork

from tl_mod_correspondence import registry, registry_domain
from tl_mod_correspondence.domains import DomainDefinition
from tl_mod_correspondence.errors import InvalidClockError, InvalidItemError, ItemStateError
from tl_mod_correspondence.handlers.clocks import start_clock
from tl_mod_correspondence.handlers.common import today_date
from tl_mod_correspondence.limits import (
    MAX_IMPACTS,
    MAX_NUMBER,
    MAX_REFERENCES,
    MAX_TEXT,
)
from tl_mod_correspondence.names import YES_NO_UNKNOWN
from tl_mod_correspondence.textcheck import clean_optional_text, clean_text

_MONEY = re.compile(r"[0-9]{1,13}(\.[0-9]{1,2})?")
_HOURS = re.compile(r"[0-9]{1,9}(\.[0-9])?")
_QUANTITY = re.compile(r"[0-9]{1,12}(\.[0-9]{1,3})?")
_CURRENCY = re.compile(r"[A-Z]{3}")
_COST_CODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_RECORD_SQL = text("SELECT id, scope, type FROM cur_core_record WHERE id = :id")


def check_flag(value: str, what: str) -> str:
    """``value`` when it is ``yes``, ``no`` or ``unknown``; otherwise ``ValueError``."""
    if value not in YES_NO_UNKNOWN:
        raise ValueError(f"{what} is one of {', '.join(YES_NO_UNKNOWN)}")
    return value


def check_money(value: str | None, what: str) -> str | None:
    """A decimal text with at most two places, written with exactly two (``12500`` is
    ``12500.00``); ``None`` stays ``None``. A float, a sign, an exponent, a separator or a digit
    that is not ``0`` to ``9`` is refused (L-P1-I4-1)."""
    if value is None:
        return None
    if _MONEY.fullmatch(value) is None:
        raise ValueError(f"{what} is an amount with at most two decimal places, such as 12500.00")
    return str(Decimal(value).quantize(Decimal("0.01")))


def check_hours(value: str | None, what: str) -> str | None:
    """A decimal text with at most one place, written with one (``240`` is ``240.0``)."""
    if value is None:
        return None
    if _HOURS.fullmatch(value) is None:
        raise ValueError(f"{what} is a number of hours with at most one decimal place")
    return str(Decimal(value).quantize(Decimal("0.1")))


def check_currency(value: str | None) -> str | None:
    if value is not None and _CURRENCY.fullmatch(value) is None:
        raise ValueError("currency is a three-letter upper-case code such as USD")
    return value


class CostCodeImpact(BaseModel):
    """The effect of an event on one cost code: money, hours, a quantity, or any of them."""

    model_config = ConfigDict(extra="forbid")

    cost_code: str = Field(min_length=1, max_length=64)
    amount: str | None = None
    hours: str | None = None
    quantity: str | None = None
    uom: str | None = Field(default=None, max_length=16)

    @field_validator("cost_code")
    @classmethod
    def _code(cls, value: str) -> str:
        if _COST_CODE.fullmatch(value) is None:
            raise ValueError("a cost code is letters, digits and . _ -")
        return value

    @field_validator("amount")
    @classmethod
    def _amount(cls, value: str | None) -> str | None:
        return check_money(value, "amount")

    @field_validator("hours")
    @classmethod
    def _hours(cls, value: str | None) -> str | None:
        return check_hours(value, "hours")

    @field_validator("quantity")
    @classmethod
    def _quantity(cls, value: str | None) -> str | None:
        if value is not None and _QUANTITY.fullmatch(value) is None:
            raise ValueError("quantity is a number with at most three decimal places")
        return value

    @field_validator("uom")
    @classmethod
    def _uom(cls, value: str | None) -> str | None:
        return clean_optional_text(value)

    def as_payload(self) -> dict[str, str | None]:
        return {
            "cost_code": self.cost_code,
            "amount": self.amount,
            "hours": self.hours,
            "quantity": self.quantity,
            "uom": self.uom,
        }


def check_impacts(impacts: Sequence[CostCodeImpact]) -> list[dict[str, str | None]]:
    """The payload of cost-code impacts: bounded, and a cost code appears once."""
    if len(impacts) > MAX_IMPACTS:
        raise InvalidItemError(f"at most {MAX_IMPACTS} cost codes per notice")
    codes = [i.cost_code for i in impacts]
    if len(set(codes)) != len(codes):
        raise InvalidItemError("a cost code is named once in a notice")
    return [i.as_payload() for i in impacts]


class Reference(BaseModel):
    """A record the item refers to; ``pin`` pins a link to a document at a revision label."""

    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(min_length=1, max_length=MAX_NUMBER)
    pin: str | None = Field(default=None, max_length=MAX_NUMBER)
    note: str | None = Field(default=None, max_length=MAX_TEXT)

    @field_validator("pin", "note")
    @classmethod
    def _clean(cls, value: str | None) -> str | None:
        return None if value is None else clean_text(value)


ReferenceList = Annotated[list[Reference], Field(max_length=MAX_REFERENCES)]


def kind_numbering(definition: DomainDefinition, subtype: str) -> dict[str, str]:
    """The ``kind`` field of the pattern for ``subtype`` (``{"kind": "RFI"}``)."""
    chosen = definition.subtype(subtype)
    if chosen is None or chosen.number_code is None:
        raise InvalidItemError(f"subtype {subtype!r} of {definition.code!r} has no number code")
    return {"kind": chosen.number_code}


def check_references(
    uow: UnitOfWork, cmd: Command, references: Sequence[Reference], own_id: str | None
) -> None:
    """Each referenced record is in the scope and readable by the viewer (the same
    ``RecordNotFoundError`` for an unknown, a foreign and a hidden record), once each."""
    ids = [r.record_id for r in references]
    if len(set(ids)) != len(ids):
        raise InvalidItemError("a record can be referenced only once")
    for record_id in ids:
        row = uow.conn().execute(_RECORD_SQL, {"id": record_id}).first()
        hidden = row is not None and confidentiality.is_hidden(uow.conn(), record_id)
        if row is None or row.scope != cmd.scope or hidden:
            raise RecordNotFoundError(f"no record {record_id!r}")
        if record_id == own_id:
            raise InvalidItemError("an item cannot refer to itself")


def link_references(
    uow: UnitOfWork, cmd: Command, item_id: str, references: Sequence[Reference]
) -> list[Event]:
    """Link ``item_id`` to each referenced record with a ``references`` link (the person's own:
    it can be retracted like any link the person made). Returns the link events."""
    events: list[Event] = []
    for reference in references:
        done = handle_add_link(
            uow,
            AddLink(
                actor=cmd.actor,
                source=cmd.source,
                scope=cmd.scope,
                correlation_id=cmd.correlation_id,
                causation_id=cmd.causation_id,
                from_id=item_id,
                to_id=reference.record_id,
                relation="references",
                pin=reference.pin,
                link_source="manual",
                note=reference.note,
            ),
        )
        events.extend(done.events)
    return events


_SAME_LINK_SQL = text(
    "SELECT 1 FROM cur_links WHERE from_id = :from_id AND to_id = :to_id "
    "AND relation = 'references'"
)


def link_if_new(
    uow: UnitOfWork, cmd: Command, from_id: str, to_id: str, note: str | None
) -> list[Event]:
    """Link ``from_id`` to ``to_id`` with a ``references`` link unless one is there already (a
    link of any status counts: a retracted link is not made again behind someone's back)."""
    found = uow.conn().execute(_SAME_LINK_SQL, {"from_id": from_id, "to_id": to_id}).first()
    if found is not None:
        return []
    return link_references(uow, cmd, from_id, [Reference(record_id=to_id, note=note)])


def start_domain_clocks(
    uow: UnitOfWork,
    cmd: Command,
    item: registry.ItemRow,
    definition: DomainDefinition,
    trigger: str,
    start_on: str,
    *,
    clause_id: str | None = None,
    answer_by: str | None = None,
) -> tuple[list[str], list[Event]]:
    """Start the clocks of the item's subtype whose trigger is ``trigger``; return ids and events.

    * A ``time_bar`` clock of an item that names a contract clause cites the clause and, when the
      clause has a time bar, takes its length and day type (the contract decides, not the
      template).
    * A ``response_from_them`` clock of an item with an ``answer_by`` date counts calendar days to
      that date (at least one), so the clock ends when the raiser said an answer is needed.
    * Warnings later than the clock is long are dropped.
    Raises ``InvalidClockError`` for a clause that is not an active clause of the scope.
    """
    chosen = definition.subtype(item.subtype or "")
    if chosen is None:
        return [], []
    clause = None
    if clause_id is not None:
        clause = registry.get_clause(uow.conn(), clause_id)
        if clause is None or clause.scope != item.scope or not clause.is_active:
            raise InvalidClockError(f"clause {clause_id!r} is not an active clause of {item.scope}")
    ids: list[str] = []
    events: list[Event] = []
    for template in chosen.clocks:
        if template.trigger != trigger:
            continue
        days, day_type, bar_clause = template.duration_days, template.day_type, None
        if template.kind == "time_bar" and clause is not None:
            bar_clause = clause.id
            if clause.time_bar_days:
                days = clause.time_bar_days
                day_type = clause.time_bar_day_type or template.day_type
        if template.kind == "response_from_them" and answer_by is not None:
            left = (date.fromisoformat(answer_by) - date.fromisoformat(start_on)).days
            if left < 1:
                raise InvalidClockError(
                    f"the answer is needed by {answer_by}, which is not after {start_on}"
                )
            days, day_type = left, "calendar"
        made = start_clock(
            uow,
            cmd,
            item=item,
            label=template.label,
            kind=template.kind,
            duration_days=days,
            day_type=day_type,
            warn_days=[w for w in template.warn_days if w <= days],
            start_on=start_on,
            trigger=trigger,
            clause_id=bar_clause,
        )
        ids.append(made.stream_id)
        events.extend(made.events)
    return ids, events


def not_after_today(value: str | None, what: str) -> str | None:
    """``value`` (an ISO date) when it is today or earlier; otherwise ``InvalidItemError``."""
    if value is not None and date.fromisoformat(value) > today_date():
        raise InvalidItemError(f"{what} {value} is after today ({today_date().isoformat()})")
    return value


def _closed_message(item: registry.ItemRow) -> str:
    return (
        f"item {item.number} is {item.state}"
        + (f", replaced by {item.superseded_by_id}" if item.superseded_by_id else "")
        + " and takes no more changes"
    )


def open_technical(uow: UnitOfWork, cmd: Command, item_id: str) -> registry_domain.TechnicalRow:
    """The Technical item in the command's scope that the viewer may read and that still takes
    changes. A missing item, one of another scope, a hidden one and an item of another kind all
    raise the same ``RecordNotFoundError`` (ADR-0016); a closed one raises ``ItemStateError``."""
    found = registry_domain.get_technical(uow.conn(), item_id)
    if found is None or found.item.scope != cmd.scope:
        raise RecordNotFoundError(f"no record {item_id!r}")
    if found.item.closed:
        raise ItemStateError(_closed_message(found.item))
    return found


def open_commercial(uow: UnitOfWork, cmd: Command, item_id: str) -> registry_domain.CommercialRow:
    """Like ``open_technical`` for a Commercial item."""
    found = registry_domain.get_commercial(uow.conn(), item_id)
    if found is None or found.item.scope != cmd.scope:
        raise RecordNotFoundError(f"no record {item_id!r}")
    if found.item.closed:
        raise ItemStateError(_closed_message(found.item))
    return found


def feed_fields(definition: DomainDefinition, *, full: str, minimal: str) -> dict[str, str]:
    """The ``feed_policy`` and ``feed_text`` keys an event carries so that the feed shows what the
    domain's policy allows (``tl_core.feed.cards``): the line ``full`` for policy full, the line
    ``minimal`` for policy minimal, and no card at all for policy none. The policy is fixed when
    the event is written, so a rebuild of the feed never depends on a file that changed later."""
    policy = definition.feed_policy
    if policy == "none":
        return {"feed_policy": "none"}
    return {"feed_policy": policy, "feed_text": full if policy == "full" else minimal}
