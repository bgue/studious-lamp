# P1-I6-T04a — Commercial items: raise, update, submit, review, return

Status: ready
Tier: haiku
Labels: module, handlers
Depends on: — (the schema, the projectors, the reads, the helpers and the test world are in the tree at the branch point; the handlers of T04b are in the tree)
Branch: `p1/i6-t04a-commercial-raise`

## Goal
`handlers/commercial.py` has the command models, the helpers (`require_controller_viewer`, `resolve_clause`, `_aware_on`, `_states_amount`) and the stubs of `create_commercial` (the one place a Commercial item is made, also used by the escalation of an RFI) and of `handle_raise_commercial`, `handle_update_commercial`, `handle_submit_commercial`, `handle_review_commercial`, `handle_return_commercial`. You implement them by their STEPS comments. A document controller raises a notice (an early warning, a change notice, a claim, a site instruction we received ...) whose time bar starts at once from the day the contractor became aware; edits it while it is a Draft or in commercial review; and sends it through review. One provided test file must pass on SQLite and on Postgres.

## Brief references (pasted)
> **§9 M10, Initial domains, Commercial.** "Time bars are hard clocks with escalating warnings. The register exports to the cost system as pending/approved changes (M11). Forecast impacts are visible to the future cost module." Data: contract clause, estimated value ($, hours, qty by cost code), schedule impact, entitlement basis, assessed value; links to RFIs, instructions, cost codes, activities.
>
> **Decided in the P1-I6 plan (ADR-0019).** A Commercial item is a record of its own type (`correspondence.CommercialItem`) with its own workflow, the class `restricted`, and **every Commercial command is a document controller's**: the handler calls `require_controller_viewer()` first (a viewer below that level is refused with `ForbiddenError` before anything is read or written). Money is a decimal text with two places, hours with one; the helpers of `handlers/domain.py` check them. The **time bar** is a clock of kind `time_bar` that starts when the item is made, counted from the day the contractor became aware (`aware_on`), and is met when the notice is issued; an item that names a contract clause takes the clause's length and day type. The workflow is in `schema/fixtures/workflows/correspondence-commercial.yaml`, the clocks in `schema/fixtures/correspondence/domains/commercial.yaml`.
>
> **Rules of the module (`packages/tl-modules/correspondence/AGENTS.md`, ADR-0016).** A handler runs inside an entered unit of work, appends through it and never commits; a failed check raises a `ServiceError` before anything is appended (the tests count the events). Read an item only through `registry`, `registry_domain`, `views`, `load_item`, `open_technical` or `open_commercial`: they apply the viewer's class filter, and a hidden item, a foreign item and an unknown id are the same "not found". The viewer defaults to the lowest clearance; a handler never sets one.
>
> **Command, handler and model docstrings are the contract.** Do not change a model, a field, a docstring, a name or a helper in a file you complete; only the function bodies that carry a STEPS comment are yours.

### Learnings that apply
> **L-P1-I5-2.** The viewer (ADR-0016) defaults to the lowest clearance, so a helper that reads a record in a test reads nothing unless the test set a viewer (`use_viewer(...)`, `as_controller()`). Do not widen the default to get a test green.
>
> **L-P1-I3-5.** A test that only passes with the whole module in place is the module's test: run the provided file as it is; do not add helpers to it or to the shared test support (`tl_mod_correspondence/testing.py`).
>
> **L-P1-I1-6.** A parity run's count is not the SQLite count twice: a case that does not use the `db`/`new_db`/`engine`/`world` fixtures runs once. The counts in *Acceptance* are exact.
>
> **L-P0-I1-6.** ruff's `E501` applies to docstrings and comments at 100 columns, and pyright strict flags `@contextmanager` functions annotated `Iterator[X]`. Wrap prose.
>
> **L-P0-I6C-8.** Write files with the Write tool, not a long `cat > file <<'EOF'` inside a `&&` chain (it hung until the timeout), and never `pkill -f <pattern>` (it kills your own shell): kill only a PID you started.
>
> **L-P1-I3B-6.** Copy the provided test byte for byte (`cp`), run `ruff` and `pyright` on the tree, and do not edit the copy: if it cannot pass, stop and report *Blocked*.
>
> **L-P1-I4-9.** A first `just check` in a fresh worktree takes over two minutes and the Postgres run of a module suite can take longer: give the shell tool `timeout` 600000, or run it in the background and wait for it. Run `ruff format <your file>` first, because the format check rewrites a hand-wrapped line.
>
> **L-P1-I5-4.** Give a provided test only the helpers its own handlers and the merged ones provide: `CorrWorld.forge_item`, `forge_party`, `forge_clause`, `forge_technical` and `forge_commercial` write a record with raw events, so a test of one command does not depend on another ticket's command.
>
> **L-P1-I3B-5.** Keep the exact messages that tests compare as they are written in the STEPS: do not paraphrase a message; copy it. A comment that wraps a quoted message is one message.
>
> **L-P1-I6-1.** Pyright strict does not narrow an attribute through a boolean local computed from it (`late = x is not None and ...; if late:` leaves `x` as `T | None`). Where a STEPS line says "when `late`", write the `is not None` check again in the code and say so in the report.
>
> **L-P1-I6-2.** The first `just check` in a fresh worktree can end with a bare exit 247 at the pyright step and no output; run it again once before you read it as a type error.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/commercial.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401, F841
"""Raise, edit, submit and review a Commercial item: an early warning, a change notice, a claim ...

A Commercial item (brief 9, M10) is a notice or a claim under the contract. It is a record of the
type ``correspondence.CommercialItem`` with its own workflow (``correspondence.commercial``) and
the class ``restricted`` (commercial roles and the project manager; the nearest the platform has
is the document controller and admin, ADR-0016). So **every Commercial command is a document
controller's**: a person who cannot read a restricted item cannot make one, and a handler refuses
a viewer below that level before it writes anything.

* ``RaiseCommercial``: a Draft numbered by kind (``P123-EW-0001``) with the contract clause, the
  day the contractor became aware, the estimated value and hours, the effect by cost code, the
  schedule impact and the entitlement basis. The **time bar** of the subtype starts counting at
  once, from the awareness day, so the clock runs while the notice is written and reviewed. A
  site instruction (received) is logged and waits for our assessment instead.
* ``UpdateCommercial``: changes the money, the text and the recipients while the item is a Draft
  or in commercial review. The clause and the awareness day are fixed (the time bar was counted
  from them); correct them by voiding the item and raising it again.
* ``SubmitCommercial``: Draft to Commercial review. Some subtypes need data first (a claim needs
  its basis and its clause).
* ``ReviewCommercial``: Commercial review to PM approval. ``ReturnCommercial``: back to Draft.

``create_commercial`` is the one place an item is made; ``RaiseCommercial`` and the escalation of
an answered RFI (``escalate.py``) both call it.

STUB (P1-I6-T04a): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
"""

from __future__ import annotations

from typing import Any

from pydantic import ConfigDict, Field, field_validator, model_validator
from tl_core import confidentiality
from tl_core.auth.errors import ForbiddenError
from tl_core.ledger import Event, NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import NoChangesError
from tl_core.services.links import AddLink, handle_add_link
from tl_core.uow import UnitOfWork

from tl_mod_correspondence import catalog, registry
from tl_mod_correspondence.domains import DomainDefinition
from tl_mod_correspondence.errors import InvalidItemError
from tl_mod_correspondence.handlers.common import (
    append,
    changes_of,
    correlated,
    plausible_date,
    require_project,
    require_state,
    today,
    transition,
)
from tl_mod_correspondence.handlers.create import check_body, check_recipients, create_item
from tl_mod_correspondence.handlers.domain import (
    CostCodeImpact,
    ReferenceList,
    check_currency,
    check_hours,
    check_impacts,
    check_money,
    check_references,
    kind_numbering,
    link_references,
    open_commercial,
    start_domain_clocks,
)
from tl_mod_correspondence.handlers.models import Recipient, non_blank
from tl_mod_correspondence.limits import (
    MAX_BODY,
    MAX_IMPACTS,
    MAX_NUMBER,
    MAX_REASON,
    MAX_RECIPIENTS,
    MAX_TEXT,
)
from tl_mod_correspondence.names import (
    COMM_DEFINED,
    COMM_UPDATED,
    COMMERCIAL,
    CORR_UPDATED,
    DOMAIN_COMMERCIAL,
    ST_COMMERCIAL_REVIEW,
    ST_DRAFT,
    ST_PM_APPROVAL,
)
from tl_mod_correspondence.textcheck import clean_body, clean_optional_text, clean_text

#: Data a subtype needs before it can go to review: the names of ``CommercialData`` fields.
REQUIRED_TO_SUBMIT: dict[str, tuple[str, ...]] = {
    "change_notice": ("entitlement_basis",),
    "claim_notice": ("entitlement_basis", "contract_clause_id"),
    "detailed_claim": (
        "entitlement_basis",
        "contract_clause_id",
        "estimated_value",
        "cost_code_impacts",
    ),
}
_UPDATABLE = (
    "currency",
    "estimated_value",
    "estimated_hours",
    "cost_code_impacts",
    "schedule_impact_days",
    "schedule_impact_note",
    "entitlement_basis",
)


class _CommercialFields(Command):
    """The fields a notice states, with their checks (shared by raising and updating)."""

    model_config = ConfigDict(extra="forbid")

    currency: str | None = Field(default=None, max_length=3)
    estimated_value: str | None = Field(default=None, max_length=20)
    estimated_hours: str | None = Field(default=None, max_length=20)
    cost_code_impacts: list[CostCodeImpact] | None = Field(default=None, max_length=MAX_IMPACTS)
    schedule_impact_days: int | None = Field(default=None, ge=-3650, le=3650)
    schedule_impact_note: str | None = Field(default=None, max_length=MAX_REASON)
    entitlement_basis: str | None = Field(default=None, max_length=MAX_REASON)

    @field_validator("currency")
    @classmethod
    def _currency(cls, value: str | None) -> str | None:
        return check_currency(value)

    @field_validator("estimated_value")
    @classmethod
    def _value(cls, value: str | None) -> str | None:
        return check_money(value, "estimated_value")

    @field_validator("estimated_hours")
    @classmethod
    def _hours(cls, value: str | None) -> str | None:
        return check_hours(value, "estimated_hours")

    @field_validator("schedule_impact_note", "entitlement_basis")
    @classmethod
    def _text(cls, value: str | None) -> str | None:
        return None if value is None else clean_body(value)


class RaiseCommercial(_CommercialFields):
    """Raise a Commercial item as a Draft (a document controller's act).

    ``subtype`` is one of the Commercial domain's (``early_warning``, ``change_notice``,
    ``site_instruction`` ...). ``clause`` is ``<contract>/<clause number>`` of an active contract
    clause: its time bar sets the length of the notice clock. ``aware_on`` is the day the
    contractor became aware of the event (today by default, never later); the time bar counts
    from it. ``currency`` is needed when any amount is stated. ``references`` are records the
    item refers to (RFIs, instructions, photos, daily records).
    """

    subtype: str = Field(min_length=1, max_length=MAX_NUMBER)
    subject: str = Field(min_length=1, max_length=MAX_TEXT)
    body: str | None = Field(default=None, max_length=MAX_BODY)
    clause: str | None = Field(default=None, max_length=MAX_NUMBER)
    aware_on: str | None = Field(default=None, max_length=10)
    to: list[Recipient] = Field(default_factory=list, max_length=MAX_RECIPIENTS)
    cc: list[Recipient] = Field(default_factory=list, max_length=MAX_RECIPIENTS)
    references: ReferenceList = Field(default_factory=list)

    @field_validator("subject")
    @classmethod
    def _subject(cls, value: str) -> str:
        return clean_text(non_blank(value))

    @field_validator("body")
    @classmethod
    def _body(cls, value: str | None) -> str | None:
        return None if value is None else clean_body(value)

    @field_validator("clause")
    @classmethod
    def _clause(cls, value: str | None) -> str | None:
        return clean_optional_text(value)

    @model_validator(mode="after")
    def _currency_for_amounts(self) -> RaiseCommercial:
        if _states_amount(self.estimated_value, self.cost_code_impacts) and self.currency is None:
            raise ValueError("state the currency of the amounts")
        return self


class UpdateCommercial(_CommercialFields):
    """Change a Commercial item that is a Draft or in commercial review (a controller's act).

    A field you leave out stays as it is; ``null`` clears an optional one. The clause and the
    awareness day cannot be changed. Give a ``reason`` when you change an item that is in review.
    """

    stream_id: str
    expected_version: int | None = None
    subject: str | None = Field(default=None, min_length=1, max_length=MAX_TEXT)
    body: str | None = Field(default=None, max_length=MAX_BODY)
    to: list[Recipient] | None = Field(default=None, max_length=MAX_RECIPIENTS)
    cc: list[Recipient] | None = Field(default=None, max_length=MAX_RECIPIENTS)
    reason: str | None = Field(default=None, max_length=MAX_REASON)

    @field_validator("subject")
    @classmethod
    def _subject(cls, value: str | None) -> str | None:
        return None if value is None else clean_text(non_blank(value))

    @field_validator("body")
    @classmethod
    def _body(cls, value: str | None) -> str | None:
        return None if value is None else clean_body(value)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


class SubmitCommercial(Command):
    """Send a Draft to commercial review. A claim needs its basis and its clause first."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None


class ReviewCommercial(Command):
    """Pass an item in commercial review to the project manager's approval."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    note: str | None = Field(default=None, max_length=MAX_REASON)

    @field_validator("note")
    @classmethod
    def _note(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


class ReturnCommercial(Command):
    """Send an item in commercial review or PM approval back to its author. A reason is required."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return clean_text(non_blank(value))


def _states_amount(value: str | None, impacts: list[CostCodeImpact] | None) -> bool:
    return value is not None or any(i.amount is not None for i in impacts or [])


def require_controller_viewer() -> None:
    """Refuse a viewer below a document controller: Commercial items are ``restricted``."""
    if confidentiality.current_viewer().level < 1:
        raise ForbiddenError("commercial items are for the document_controller and admin roles")


def resolve_clause(uow: UnitOfWork, cmd: Command, ref: str | None) -> str | None:
    """The record id of the active clause ``<contract>/<number>``, or ``None`` for none.

    Raises ``InvalidItemError`` for a reference that is not that shape or names no active clause
    of the scope.
    """
    if ref is None:
        return None
    contract, _, number = ref.partition("/")
    found = registry.find_clause(uow.conn(), cmd.scope, contract, number) if number else None
    if found is None or not found.is_active:
        raise InvalidItemError(f"{ref!r} is not an active contract clause of {cmd.scope}")
    return found.id


def _aware_on(value: str | None) -> str:
    try:
        found = plausible_date(value, "aware_on") or today()
    except ValueError as exc:
        raise InvalidItemError(str(exc)) from exc
    if found > today():
        raise InvalidItemError(f"aware_on {found} is after today ({today()})")
    return found


def create_commercial(
    uow: UnitOfWork,
    cmd: RaiseCommercial,
    *,
    definition: DomainDefinition,
    derived_from: registry.ItemRow | None = None,
    confidentiality_class: str | None = None,
    clearances: list[str] | None = None,
) -> CommandResult:
    """Make the item: ``Record.Created``, ``Correspondence.Defined``, ``Commercial.Defined``, the
    links, the awareness clocks and (for an item we receive) the move to Awaiting assessment.

    ``derived_from`` is the item this one was escalated from (a ``derived_from`` link is written
    as the module's own, which a person cannot retract); ``confidentiality_class`` and
    ``clearances`` override the domain's default class when the source asks for a higher one. A
    Python-only path: no field of ``RaiseCommercial`` can set them.
    """
    # STEPS
    # 1. `require_controller_viewer()`; `chosen = definition.subtype(cmd.subtype)` and
    #    `assert chosen is not None`.
    # 2. `clause_id = resolve_clause(uow, cmd, cmd.clause)`; `aware_on =
    #    _aware_on(cmd.aware_on)`; `impacts = check_impacts(cmd.cost_code_impacts or [])`;
    #    `check_references(uow, cmd, cmd.references, None)`. All of these raise before
    #    anything is written.
    # 3. `direction = chosen.direction or "out"`.
    # 4. `made = create_item(uow, cmd, ...)` with: `subject=cmd.subject`,
    #    `direction=direction`, `medium="other"`, `received_via="manual"`, `to=cmd.to`,
    #    `cc=cmd.cc`, `received_on=today() if direction == "in" else None`,
    #    `body=cmd.body`, `confidentiality=confidentiality_class or
    #    definition.confidentiality_default`, `clearances=clearances or []`,
    #    `response_required=chosen.response_required`, `domain=DOMAIN_COMMERCIAL`,
    #    `subtype=cmd.subtype`, `record_type=COMMERCIAL`,
    #    `numbering=kind_numbering(definition, cmd.subtype)`.
    # 5. Also pass `domain_events=[NewEvent(event_type=COMM_DEFINED, payload={...})]`; the
    #    payload keys are exactly: `contract_clause_id` (`clause_id`), `aware_on`,
    #    `derived_from_id` (`derived_from.id` or `None`), `currency`, `estimated_value`,
    #    `estimated_hours` (from `cmd`), `cost_code_impacts` (`impacts`),
    #    `schedule_impact_days`, `schedule_impact_note`, `entitlement_basis` (from `cmd`).
    # 6. `events: list[Event] = list(made.events)`; `version = made.version`; `item =
    #    registry.get_item(uow.conn(), made.stream_id)` and `assert item is not None` (the
    #    controller viewer reads what it made).
    # 7. If `derived_from` is not None, add the events of `handle_add_link(uow,
    #    AddLink(actor=cmd.actor, source=cmd.source, scope=cmd.scope,
    #    correlation_id=cmd.correlation_id, causation_id=cmd.causation_id,
    #    from_id=item.id, to_id=derived_from.id, relation="derived_from",
    #    link_source="rule", note=f"escalated from {derived_from.number}"),
    #    by_module=True).events`.
    # 8. `events += link_references(uow, cmd, item.id, cmd.references)`.
    # 9. `_, clock_events = start_domain_clocks(uow, cmd, item, definition, "awareness",
    #    aware_on, clause_id=clause_id)`; `events += clock_events`.
    # 10. If `direction == "in"` (an instruction that arrived waits for our assessment):
    #    `moved = transition(uow, cmd, item.id, "receive")`, add `moved.events` and set
    #    `version = moved.version`.
    # 11. Return `CommandResult(stream_id=item.id, key=item.number, version=version,
    #    events=events)`.
    raise NotImplementedError


def handle_raise_commercial(uow: UnitOfWork, cmd: RaiseCommercial) -> CommandResult:
    """Make a Commercial item (``create_commercial``).

    Raises ``ForbiddenError`` (the viewer is below a document controller),
    ``CorrespondenceScopeError``, ``UnknownDomainError`` (no such subtype), ``InvalidItemError``
    (an unknown clause, a day after today, a party, a text, a repeated reference),
    ``RecordNotFoundError`` (a reference that is unknown, foreign or hidden),
    ``InvalidClockError`` and ``CalendarUnavailableError`` (the time bar cannot be counted), and
    the numbering errors of the core.
    """
    # STEPS
    # 1. `require_controller_viewer()`, `require_project(cmd)`, `cmd = correlated(cmd)`.
    # 2. `definition = catalog.check_subtype(cmd.scope, DOMAIN_COMMERCIAL, cmd.subtype)`.
    # 3. Return `create_commercial(uow, cmd, definition=definition)`.
    raise NotImplementedError


def handle_update_commercial(uow: UnitOfWork, cmd: UpdateCommercial) -> CommandResult:
    """Append ``Record.Updated`` (the subject), ``Correspondence.Updated`` (recipients and text)
    and ``Commercial.Updated`` (the notice's own fields).

    Raises ``ForbiddenError``, ``RecordNotFoundError`` (unknown, foreign, hidden, or not a
    Commercial item), ``ItemStateError`` (not a Draft or in commercial review),
    ``InvalidItemError`` (a text, a party, an amount without a currency) and ``NoChangesError``.
    """
    # STEPS
    # 1. `require_controller_viewer()`; `cmd = correlated(cmd)`; `row =
    #    open_commercial(uow, cmd, cmd.stream_id)`; `item, data = row.item, row.data`;
    #    `require_state(item, ST_DRAFT, ST_COMMERCIAL_REVIEW)`; `given =
    #    cmd.model_fields_set`.
    # 2. `old` is a dict of the seven notice fields as they are now, from `data`:
    #    `currency`, `estimated_value`, `estimated_hours`, `cost_code_impacts`,
    #    `schedule_impact_days`, `schedule_impact_note`, `entitlement_basis`. `new = {}`;
    #    for `name` in `_UPDATABLE` that is in `given`: `value = getattr(cmd, name)`; for
    #    `cost_code_impacts` replace it by `check_impacts(value or [])` (a `null` clears
    #    the list); `new[name] = value`.
    # 3. `after = {**old, **new}`. `stated` is true when `after["estimated_value"] is not
    #    None` or any impact in `after["cost_code_impacts"]` has `i.get("amount") is not
    #    None`. If `stated` and `after["currency"] is None` raise `InvalidItemError("state
    #    the currency of the amounts")`.
    # 4. `register_old = {"to": item.to, "cc": item.cc}` and `register_new = {}`. For
    #    `name` in `("to", "cc")` that is in `given`: `value = getattr(cmd, name)`; if it
    #    is `None` raise `InvalidItemError(f"{name} is a list; send [] to clear it")`;
    #    call `check_recipients(uow, cmd, value)`; set `register_new[name] =
    #    [r.as_payload() for r in value]`. If `"body"` is in `given`:
    #    `register_old["body"], register_new["body"] = item.body, check_body(cmd.body)`.
    # 5. `domain = changes_of(old, new)`; `register = changes_of(register_old,
    #    register_new)`; `envelope = changes_of({"title": item.subject}, {"title":
    #    cmd.subject} if cmd.subject else {})`. If all three are empty raise
    #    `NoChangesError(f"no field of item {item.number} differs from the request")`.
    # 6. `events` in this order, each only when its changes are not empty:
    #    `NewEvent(event_type="Record.Updated", payload={"changes": envelope})`;
    #    `NewEvent(event_type=CORR_UPDATED, payload={"changes": register, "reason":
    #    cmd.reason})`; `NewEvent(event_type=COMM_UPDATED, payload={"changes": domain,
    #    "reason": cmd.reason})`.
    # 7. `done = append(uow, cmd, item.id, item.record_type, events,
    #    expected=cmd.expected_version or item.version)`; return
    #    `CommandResult(stream_id=item.id, key=item.number, version=done.new_version,
    #    events=list(done.events))`.
    raise NotImplementedError


def handle_submit_commercial(uow: UnitOfWork, cmd: SubmitCommercial) -> CommandResult:
    """Move a Draft to Commercial review.

    Raises ``ForbiddenError``, ``RecordNotFoundError``, ``ItemStateError`` (not a Draft) and
    ``InvalidItemError`` (no recipient, or data the subtype needs is missing).
    """
    # STEPS
    # 1. `require_controller_viewer()`; `cmd = correlated(cmd)`; `row =
    #    open_commercial(uow, cmd, cmd.stream_id)`; `item, data = row.item, row.data`;
    #    `require_state(item, ST_DRAFT)`.
    # 2. `missing: list[str] = []`. If `item.direction == "out"` and `item.to` is empty
    #    append `"a recipient"`. For `name` in `REQUIRED_TO_SUBMIT.get(item.subtype or "",
    #    ())`: if `getattr(data, name)` is falsy (None, empty text or empty list) append
    #    `name`.
    # 3. If `missing` is not empty raise `InvalidItemError(f"item {item.number} needs {',
    #    '.join(missing)} before review")`.
    # 4. Return `transition(uow, cmd, item.id, "submit", expected=cmd.expected_version)`.
    raise NotImplementedError


def handle_review_commercial(uow: UnitOfWork, cmd: ReviewCommercial) -> CommandResult:
    """Move an item in commercial review to PM approval.

    Raises ``ForbiddenError``, ``RecordNotFoundError`` and ``ItemStateError`` (not in review).
    """
    # STEPS
    # 1. `require_controller_viewer()`; `cmd = correlated(cmd)`; `row =
    #    open_commercial(uow, cmd, cmd.stream_id)`; `require_state(row.item,
    #    ST_COMMERCIAL_REVIEW)`.
    # 2. Return `transition(uow, cmd, row.item.id, "review", reason=cmd.note,
    #    expected=cmd.expected_version)`.
    raise NotImplementedError


def handle_return_commercial(uow: UnitOfWork, cmd: ReturnCommercial) -> CommandResult:
    """Move an item in commercial review or PM approval back to Draft, with the reason.

    Raises ``ForbiddenError``, ``RecordNotFoundError`` and ``ItemStateError``.
    """
    # STEPS
    # 1. `require_controller_viewer()`; `cmd = correlated(cmd)`; `row =
    #    open_commercial(uow, cmd, cmd.stream_id)`; `require_state(row.item,
    #    ST_COMMERCIAL_REVIEW, ST_PM_APPROVAL)`.
    # 2. Return `transition(uow, cmd, row.item.id, "return", reason=cmd.reason,
    #    expected=cmd.expected_version)`.
    raise NotImplementedError
```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/common.py` (read-only; abridged to the names used):
```python
def require_project(cmd: Command) -> None:
    ...

def correlated[C: Command](cmd: C) -> C:
    """``cmd`` with a correlation id, so every event of the command carries the same one."""
    ...

def today() -> str:
    """Today's date, ISO, from ``now``."""
    ...

def plausible_date(value: str | None, what: str) -> str | None:
    """``check_date``, and the day is at most a year ahead and 50 years back of today."""
    ...

def resolve_date(value: str | None, reason: str | None, what: str) -> tuple[str, str | None]:
    """``(date, reason)`` for an act's date: today by default, never in the future.

    A date before today is a back-dated entry and needs a non-blank ``reason``, which the event
    keeps: the record says when something really happened and why it was entered later.
    """
    ...

def append(
    uow: UnitOfWork,
    cmd: Command,
    stream_id: str,
    stream_type: str,
    events: list[NewEvent],
    *,
    expected: int | None = None,
) -> AppendResult:
    """Append ``events`` to a stream at its current version (or ``expected``)."""
    ...

def transition(
    uow: UnitOfWork,
    cmd: Command,
    stream_id: str,
    name: str,
    *,
    reason: str | None = None,
    expected: int | None = None,
) -> CommandResult:
    """Run workflow transition ``name`` on a record of this module (at ``expected`` or now)."""
    ...

def require_state(item: registry.ItemRow, *states: str) -> None:
    """Raise ``ItemStateError`` unless the item is in one of ``states``."""
    ...

def changes_of(old: dict[str, Any], new: dict[str, Any]) -> dict[str, list[Any]]:
    """``{field: [old, new]}`` for each field of ``new`` that differs."""
    ...
```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/domain.py` (read-only; abridged to the names used):
```python
def check_impacts(impacts: Sequence[CostCodeImpact]) -> list[dict[str, str | None]]:
    """The payload of cost-code impacts: bounded, and a cost code appears once."""
    ...

def kind_numbering(definition: DomainDefinition, subtype: str) -> dict[str, str]:
    """The ``kind`` field of the pattern for ``subtype`` (``{"kind": "RFI"}``)."""
    ...

def check_references(
    uow: UnitOfWork, cmd: Command, references: Sequence[Reference], own_id: str | None
) -> None:
    """Each referenced record is in the scope and readable by the viewer (the same
    ``RecordNotFoundError`` for an unknown, a foreign and a hidden record), once each."""
    ...

def link_references(
    uow: UnitOfWork, cmd: Command, item_id: str, references: Sequence[Reference]
) -> list[Event]:
    """Link ``item_id`` to each referenced record with a ``references`` link (the person's own:
    it can be retracted like any link the person made). Returns the link events."""
    ...

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
    ...

def open_commercial(uow: UnitOfWork, cmd: Command, item_id: str) -> registry_domain.CommercialRow:
    """Like ``open_technical`` for a Commercial item."""
    ...
```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/create.py` (read-only; abridged to the names used):
```python
def check_recipients(uow: UnitOfWork, cmd: Command, recipients: Sequence[Recipient]) -> None:
    """Each named party exists in the command's scope; the list is bounded."""
    ...

def check_body(body: str | None) -> str | None:
    ...

def create_item(
    uow: UnitOfWork,
    cmd: Command,
    *,
    subject: str,
    direction: str,
    medium: str,
    received_via: str,
    to: Sequence[Recipient] = (),
    cc: Sequence[Recipient] = (),
    external_ref: str | None = None,
    message_id: str | None = None,
    in_reply_to: str | None = None,
    from_party_id: str | None = None,
    from_name: str | None = None,
    sent_on: str | None = None,
    received_on: str | None = None,
    body: str | None = None,
    confidentiality: str = "internal",
    clearances: Sequence[str] = (),
    responds_to_id: str | None = None,
    response_required: bool = False,
    response_due: str | None = None,
    domain: str | None = None,
    subtype: str | None = None,
    received: bool = False,
    record_type: str = CORRESPONDENCE,
    numbering: Mapping[str, str] | None = None,
    domain_events: Sequence[NewEvent] = (),
) -> CommandResult:
    """Create an item: ``Record.Created``, ``Correspondence.Defined`` and, for ``received=True``,
    the move to Received. ``direction`` is in, out or internal.

    ``record_type`` is the type of the item: the core item for General and Document control, the
    Technical or Commercial type for those domains (their commands pass it, with ``numbering``
    holding the ``kind`` field of the domain's pattern and ``domain_events`` the events that
    write the domain row). The domain and subtype must belong to that record type.

    Raises ``InvalidItemError`` (a date, a party, a text, a vocabulary word),
    ``UnknownDomainError`` and the numbering errors of the core (``NoNumberingPatternError``).
    """
    ...
```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/registry_domain.py` (read-only; the data of the item as the handlers read it; abridged to the names used):
```python
@dataclass(frozen=True)
class CommercialData:
    contract_clause_id: str | None
    aware_on: str | None
    derived_from_id: str | None
    currency: str | None
    estimated_value: str | None
    estimated_hours: str | None
    cost_code_impacts: list[dict[str, Any]]
    schedule_impact_days: int | None
    schedule_impact_note: str | None
    entitlement_basis: str | None
    assessed_value: str | None
    assessed_on: str | None
    assessment_status: str | None
    assessment_note: str | None

@dataclass(frozen=True)
class CommercialRow:
    """A Commercial item: the item and its domain data."""

    item: ItemRow
    data: CommercialData
```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/catalog.py` (read-only; raises `UnknownDomainError`; abridged to the names used):
```python
def check_subtype(scope: str, domain: str, subtype: str) -> DomainDefinition:
    """The definition, once ``subtype`` is known to belong to ``domain``."""
    ...
```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/testing.py` (read-only; what the provided test calls, abridged):
```python
class CorrWorld:
    def raise_commercial(self, subject="Early warning: routing change", subtype="early_warning", **more) -> CommandResult: ...
    def update_commercial(self, item_id: str, **more) -> CommandResult: ...
    def submit_commercial(self, item_id: str, **more) -> CommandResult: ...
    def review_commercial(self, item_id: str, **more) -> CommandResult: ...
    def return_commercial(self, item_id: str, reason="figures missing", **more) -> CommandResult: ...
    def commercial(self, number: str) -> CommercialRow: ...                    # a read; needs a controller viewer
    def forge_commercial(self, number="P123-EW-0001", *, subject=..., state="Draft", subtype="early_warning",
                         confidentiality="restricted", scope=PROJECT, **data) -> str: ...  # raw events; returns the id
    def forge_clause(self, contract="CT-1", number="20.1") -> str: ...        # an active clause with a 28-day time bar
    def forge_technical(...) -> str: ...
    def forge_party(self, code="MER", name="Meridian Energy") -> str: ...
    def events_of(self, stream_id: str) -> list[tuple[str, dict]]: ...
    def clocks(self, number: str) -> list[ClockRow]: ...

def as_controller() -> ContextManager[None]: ...   # the viewer of a document controller
def frozen_today(day) -> ContextManager[None]: ... # the day the module calls today

```

## Context (read these, nothing else)
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/commercial.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/common.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/domain.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/create.py`
- `docs/tickets/P1-I6/provided/t04a-test_commercial.py.txt`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/testing.py`
- `docs/templates/haiku-report.md`
may explore: (none)

## Allowed paths
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/commercial.py` (complete)
- `packages/tl-modules/correspondence/tests/test_commercial.py` (create: a byte-for-byte copy of the provided file)
- `docs/reports/P1-I6/P1-I6-T04a.md` (create: your report)

## Steps
1. `cp docs/tickets/P1-I6/provided/t04a-test_commercial.py.txt packages/tl-modules/correspondence/tests/test_commercial.py` and do not edit it.
2. Replace the body of each function that has a STEPS comment (`create_commercial`, `handle_raise_commercial`, `handle_update_commercial`, `handle_submit_commercial`, `handle_review_commercial`, `handle_return_commercial`) by the steps of its comment; delete the STEPS comments, the `STUB` paragraph of the module docstring and the `ruff: noqa` line.
3. Run the commands below and keep their output.

## Acceptance
```
uv run ruff format packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/commercial.py
uv run pytest packages/tl-modules/correspondence/tests/test_commercial.py -q
uv run pytest packages/tl-modules/correspondence/tests/test_commercial.py -q --adapters sqlite,postgres
just check
uv run pytest packages/tl-modules/correspondence -q
```
Expected: 65 passed on SQLite; 130 passed with both adapters (every case uses the `world` fixture, so each runs twice); `just check` clean (ruff, format, pyright, no codegen drift); the package suite passes. `TL_PG_URL` is exported by the session hook; if Postgres is not running, `sudo pg_ctlcluster 16 main start`.

## Tests to add
- `packages/tl-modules/correspondence/tests/test_commercial.py` (provided, 65 tests): the restricted Draft with its figures (money and hours as exact texts, cost-code impacts); the time bar that starts at once from `aware_on` (default today, not later), the clause that sets its length and is cited, the clauses that are refused; a site instruction we received (direction in, Awaiting assessment); numbering by kind; the references that become links; every refusal before any write (a wrong subtype, an amount without a currency, a bad amount, a bad currency, a repeated cost code, a bad reference, a scope that is not a project, a plain viewer); the update (fields kept and changed, `null` clears, the currency rule, the clause and the awareness day that cannot change, recipients, no-change, the states that take a change, a stale version, an unreadable item); submit (a recipient, and the data each subtype needs); review; return; a party that is not of the project; every command refuses a plain viewer and an unknown item; a plain viewer is refused before anything else is looked at; `create_commercial` called on its own (the link, the class and the readers of an item made from another).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), saved as `docs/reports/P1-I6/P1-I6-T04a.md` and committed with the ticket. Deviations first. Paste the decisive lines of every acceptance command. Say which lines of the STEPS you found unclear, if any.

## Escalation triggers
- Stop and report *Blocked* if the pasted interface and the repo disagree, a command in *Acceptance* fails for a reason outside *Allowed paths*, or the provided test cannot pass without editing it.
- Stop if you find yourself changing a model, a field, a docstring or a name that this ticket does not own.
- Stop if a STEPS line and the provided test disagree.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
