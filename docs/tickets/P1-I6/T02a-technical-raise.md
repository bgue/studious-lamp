# P1-I6-T02a — Technical items: raise, update, submit, return

Status: ready
Tier: haiku
Labels: module, handlers
Depends on: — (the schema, the projectors, the reads, the helpers and the test world are in the tree at the branch point; the handlers of T02b are in the tree and one provided test uses `issue_technical`)
Branch: `p1/i6-t02a-technical-raise`

## Goal
`handlers/technical.py` has the four command models (`RaiseTechnical`, `UpdateTechnical`, `SubmitTechnical`, `ReturnTechnical`) and the helper `_required_by`; the four `handle_*` functions raise `NotImplementedError`. You implement them by their STEPS comments. They are the raiser's side of an RFI, a technical query or a deviation request: a Draft is made with the question, edited while it is a Draft or in internal review, sent to review and sent back. One provided test file must pass on SQLite and on Postgres.

## Brief references (pasted)
> **§9 M10, Initial domains, Technical / RFI.** Subtypes: RFI, Technical Query (TQ), Deviation/Concession request. Workflow: Draft → Internal review → Issued → Awaiting response → Answered → (Accepted / Rejected → re-issue) → Closed. Data: question, proposed solution, discipline, required-by, cost/schedule impact flags, answer, answering document revision. "The RFI record is a Technical-domain correspondence item. It feeds AWP constraints (IWP blocked until answered). If the answer flags cost or schedule impact, a rule proposes a linked Commercial item."
>
> **Decided in the P1-I6 plan (ADR-0019).** A Technical item is a record of its own type (`correspondence.TechnicalItem`) with its own workflow: the raiser's side (raise, update, submit, return, answer, review, reissue, close) is any signed-in person's; issuing and escalating are a document controller's. The item is a row of the item table (number, parties, dates, class, register text) and a row of the Technical table (the question, the answer, the flags). The question is the register text and the date an answer is needed is the register's response date.
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
`packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/technical.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401, F841
"""Raise, edit, submit and return a Technical item: an RFI, a technical query, a deviation request.

A Technical item (brief 9, M10) is a question to the designer or the client, or a request to
deviate from the design. It is a record of the type ``correspondence.TechnicalItem`` with its own
workflow (``correspondence.technical``): the raiser writes a Draft, submits it to internal review,
and a document controller issues it (``technical_flow.py``). These four commands are the raiser's
side; any signed-in person may run them. Each handler runs inside an entered unit of work,
appends through it and never commits; a failed check raises a ``ServiceError`` before anything is
appended.

* ``RaiseTechnical``: a Draft numbered by kind (``P123-RFI-0001``), with the question, what is
  proposed, the discipline, the date an answer is needed, the raiser's own cost and schedule
  flags, the recipients, and the records it refers to (a document pinned at a revision, say).
* ``UpdateTechnical``: changes those fields while the item is a Draft or in internal review.
* ``SubmitTechnical``: Draft to Internal review; it needs a recipient and a date for the answer.
* ``ReturnTechnical``: Internal review back to Draft, with a reason.

STUB (P1-I6-T02a): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
"""

from __future__ import annotations

from typing import Any

from pydantic import ConfigDict, Field, field_validator
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import NoChangesError
from tl_core.uow import UnitOfWork

from tl_mod_correspondence import catalog
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
    ReferenceList,
    check_flag,
    check_references,
    kind_numbering,
    link_references,
    open_technical,
)
from tl_mod_correspondence.handlers.models import Recipient, non_blank
from tl_mod_correspondence.limits import (
    MAX_BODY,
    MAX_NUMBER,
    MAX_REASON,
    MAX_RECIPIENTS,
    MAX_TEXT,
)
from tl_mod_correspondence.names import (
    CORR_UPDATED,
    DOMAIN_TECHNICAL,
    ST_DRAFT,
    ST_INTERNAL_REVIEW,
    TECH_DEFINED,
    TECH_UPDATED,
    TECHNICAL,
)
from tl_mod_correspondence.textcheck import clean_body, clean_optional_text, clean_text


class RaiseTechnical(Command):
    """Raise an RFI, a technical query or a deviation request as a Draft.

    ``subtype`` is ``rfi``, ``tq`` or ``deviation``. ``required_by`` is the date an answer is
    needed (today or later). ``potential_cost_impact`` and ``potential_schedule_impact`` are the
    raiser's own flags (``yes``, ``no`` or ``unknown``) before there is an answer. ``references``
    are records the item refers to; a ``pin`` pins the link to a document at a revision label.
    The question is also the text of the item in the register.
    """

    model_config = ConfigDict(extra="forbid")

    subtype: str = Field(min_length=1, max_length=MAX_NUMBER)
    subject: str = Field(min_length=1, max_length=MAX_TEXT)
    question: str = Field(min_length=1, max_length=MAX_BODY)
    proposed_solution: str | None = Field(default=None, max_length=MAX_BODY)
    discipline: str | None = Field(default=None, max_length=32)
    required_by: str | None = Field(default=None, max_length=10)
    potential_cost_impact: str = Field(default="unknown", max_length=7)
    potential_schedule_impact: str = Field(default="unknown", max_length=7)
    to: list[Recipient] = Field(default_factory=list, max_length=MAX_RECIPIENTS)
    cc: list[Recipient] = Field(default_factory=list, max_length=MAX_RECIPIENTS)
    references: ReferenceList = Field(default_factory=list)

    @field_validator("subject")
    @classmethod
    def _subject(cls, value: str) -> str:
        return clean_text(non_blank(value))

    @field_validator("question")
    @classmethod
    def _question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return clean_body(value)

    @field_validator("proposed_solution")
    @classmethod
    def _solution(cls, value: str | None) -> str | None:
        return None if value is None else clean_body(value)

    @field_validator("discipline")
    @classmethod
    def _discipline(cls, value: str | None) -> str | None:
        return clean_optional_text(value)

    @field_validator("potential_cost_impact")
    @classmethod
    def _cost_flag(cls, value: str) -> str:
        return check_flag(value, "potential_cost_impact")

    @field_validator("potential_schedule_impact")
    @classmethod
    def _schedule_flag(cls, value: str) -> str:
        return check_flag(value, "potential_schedule_impact")


class UpdateTechnical(Command):
    """Change a Technical item that is a Draft or in internal review.

    A field you leave out stays as it is; ``null`` clears ``proposed_solution``, ``discipline``
    and ``required_by`` (the question, the subject and the flags cannot be cleared). The number
    and the subtype never change. Give a ``reason`` when you change an item that is in review.
    """

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    subject: str | None = Field(default=None, min_length=1, max_length=MAX_TEXT)
    question: str | None = Field(default=None, min_length=1, max_length=MAX_BODY)
    proposed_solution: str | None = Field(default=None, max_length=MAX_BODY)
    discipline: str | None = Field(default=None, max_length=32)
    required_by: str | None = Field(default=None, max_length=10)
    potential_cost_impact: str | None = Field(default=None, max_length=7)
    potential_schedule_impact: str | None = Field(default=None, max_length=7)
    to: list[Recipient] | None = Field(default=None, max_length=MAX_RECIPIENTS)
    cc: list[Recipient] | None = Field(default=None, max_length=MAX_RECIPIENTS)
    reason: str | None = Field(default=None, max_length=MAX_REASON)

    @field_validator("subject")
    @classmethod
    def _subject(cls, value: str | None) -> str | None:
        return None if value is None else clean_text(non_blank(value))

    @field_validator("question")
    @classmethod
    def _question(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError("must not be blank")
        return clean_body(value)

    @field_validator("proposed_solution")
    @classmethod
    def _solution(cls, value: str | None) -> str | None:
        return None if value is None else clean_body(value)

    @field_validator("discipline", "reason")
    @classmethod
    def _one_line(cls, value: str | None) -> str | None:
        return clean_optional_text(value)

    @field_validator("potential_cost_impact", "potential_schedule_impact")
    @classmethod
    def _flag(cls, value: str | None) -> str | None:
        return None if value is None else check_flag(value, "the flag")


class SubmitTechnical(Command):
    """Send a Draft to internal review. It needs a recipient and a date for the answer."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None


class ReturnTechnical(Command):
    """Send an item in internal review back to its raiser. A reason is required."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return clean_text(non_blank(value))


def _required_by(value: str | None) -> str | None:
    """``value`` as a plausible date that is not before today; ``InvalidItemError`` otherwise."""
    try:
        found = plausible_date(value, "required_by")
    except ValueError as exc:
        raise InvalidItemError(str(exc)) from exc
    if found is not None and found < today():
        raise InvalidItemError(f"required_by {found} is before today ({today()})")
    return found


def handle_raise_technical(uow: UnitOfWork, cmd: RaiseTechnical) -> CommandResult:
    """Append ``Record.Created``, ``Correspondence.Defined`` and ``Technical.Defined``; link the
    references.

    The item is a Draft, outgoing, ``internal`` (the domain's default class), numbered by kind
    and answer-required. Raises ``CorrespondenceScopeError`` (not a project scope),
    ``UnknownDomainError`` (no such subtype), ``InvalidItemError`` (a date before today, a party,
    a text, a repeated reference), ``RecordNotFoundError`` (a reference that is unknown, foreign
    or hidden) and the numbering errors of the core.
    """
    # STEPS
    # 1. `require_project(cmd)`, then `cmd = correlated(cmd)`.
    # 2. `definition = catalog.check_subtype(cmd.scope, DOMAIN_TECHNICAL, cmd.subtype)`
    #    (it raises `UnknownDomainError`), then `chosen = definition.subtype(cmd.subtype)`
    #    and `assert chosen is not None`.
    # 3. `required_by = _required_by(cmd.required_by)` and `check_references(uow, cmd,
    #    cmd.references, None)`: both raise before anything is written.
    # 4. `made = create_item(uow, cmd, ...)` with these keyword arguments:
    #    `subject=cmd.subject`, `direction="out"`, `medium="other"`,
    #    `received_via="manual"`, `to=cmd.to`, `cc=cmd.cc`, `body=cmd.question`,
    #    `confidentiality=definition.confidentiality_default`,
    #    `response_required=chosen.response_required`, `response_due=required_by`,
    #    `domain=DOMAIN_TECHNICAL`, `subtype=cmd.subtype`, `record_type=TECHNICAL`,
    #    `numbering=kind_numbering(definition, cmd.subtype)`.
    # 5. Also pass `domain_events=[NewEvent(event_type=TECH_DEFINED, payload={...})]` to
    #    `create_item`; the payload has exactly these keys: `question`,
    #    `proposed_solution`, `discipline` (each from `cmd`), `required_by` (the checked
    #    `required_by`), `potential_cost_impact`, `potential_schedule_impact` (from
    #    `cmd`).
    # 6. `linked = link_references(uow, cmd, made.stream_id, cmd.references)`.
    # 7. Return `CommandResult(stream_id=made.stream_id, key=made.key,
    #    version=made.version, events=[*made.events, *linked])`.
    raise NotImplementedError


def handle_update_technical(uow: UnitOfWork, cmd: UpdateTechnical) -> CommandResult:
    """Append ``Record.Updated`` (the subject), ``Correspondence.Updated`` (recipients, the text
    and the answer date as the register shows them) and ``Technical.Updated`` (the domain fields).

    Raises ``RecordNotFoundError`` (unknown, foreign, hidden, or not a Technical item),
    ``ItemStateError`` (not a Draft or in internal review), ``InvalidItemError`` (a date before
    today, a party, a text) and ``NoChangesError`` (nothing differs).
    """
    # STEPS
    # 1. `cmd = correlated(cmd)`; `row = open_technical(uow, cmd, cmd.stream_id)`; `item,
    #    data = row.item, row.data`; `require_state(item, ST_DRAFT, ST_INTERNAL_REVIEW)`;
    #    `given = cmd.model_fields_set`.
    # 2. `old` is a dict of the six domain fields as they are now: `question`,
    #    `proposed_solution`, `discipline`, `required_by`, `potential_cost_impact`,
    #    `potential_schedule_impact` (from `data`). Build `new` from the names of `old`
    #    that are in `given`: `value = getattr(cmd, name)`; if `value is None` and `name`
    #    is `question`, `potential_cost_impact` or `potential_schedule_impact`, raise
    #    `InvalidItemError(f"{name} cannot be cleared")`; else `new[name] = value`.
    # 3. If `"required_by"` is in `new`, replace it by `_required_by(new["required_by"])`
    #    (a plausible date that is not before today).
    # 4. `register_old = {"to": item.to, "cc": item.cc}` and `register_new = {}`. For
    #    `name` in `("to", "cc")` that is in `given`: `value = getattr(cmd, name)`; if it
    #    is `None` raise `InvalidItemError(f"{name} is a list; send [] to clear it")`;
    #    call `check_recipients(uow, cmd, value)`; set `register_new[name] =
    #    [r.as_payload() for r in value]`.
    # 5. The register shows the question as the text of the item: if `"question"` is in
    #    `new`, set `register_old["body"], register_new["body"] = item.body,
    #    check_body(new["question"])`. It shows the answer date as the date an answer is
    #    due: if `"required_by"` is in `new`, set `register_old["response_due"],
    #    register_new["response_due"] = item.response_due, new["required_by"]`.
    # 6. `domain = changes_of(old, new)`; `register = changes_of(register_old,
    #    register_new)`; `envelope = changes_of({"title": item.subject}, {"title":
    #    cmd.subject} if cmd.subject else {})`. If all three are empty raise
    #    `NoChangesError(f"no field of item {item.number} differs from the request")`.
    # 7. `events` in this order, each only when its changes are not empty:
    #    `NewEvent(event_type="Record.Updated", payload={"changes": envelope})`;
    #    `NewEvent(event_type=CORR_UPDATED, payload={"changes": register, "reason":
    #    cmd.reason})`; `NewEvent(event_type=TECH_UPDATED, payload={"changes": domain,
    #    "reason": cmd.reason})`.
    # 8. `done = append(uow, cmd, item.id, item.record_type, events,
    #    expected=cmd.expected_version or item.version)`; return
    #    `CommandResult(stream_id=item.id, key=item.number, version=done.new_version,
    #    events=list(done.events))`.
    raise NotImplementedError


def handle_submit_technical(uow: UnitOfWork, cmd: SubmitTechnical) -> CommandResult:
    """Move a Draft to Internal review.

    Raises ``RecordNotFoundError``, ``ItemStateError`` (not a Draft) and ``InvalidItemError`` (no
    recipient, or no date for the answer, or that date has passed).
    """
    # STEPS
    # 1. `cmd = correlated(cmd)`; `row = open_technical(uow, cmd, cmd.stream_id)`; `item,
    #    data = row.item, row.data`; `require_state(item, ST_DRAFT)`.
    # 2. `missing` lists `"a recipient"` when `item.to` is empty and `"required_by"` when
    #    `data.required_by is None`, in that order. If it is not empty raise
    #    `InvalidItemError(f"item {item.number} needs {' and '.join(missing)} before
    #    review")`.
    # 3. If `data.required_by` is not None and is before `today()` (ISO dates compare as
    #    text), raise `InvalidItemError(f"required_by {data.required_by} is before today
    #    ({today()})")`.
    # 4. Return `transition(uow, cmd, item.id, "submit", expected=cmd.expected_version)`.
    raise NotImplementedError


def handle_return_technical(uow: UnitOfWork, cmd: ReturnTechnical) -> CommandResult:
    """Move an item in internal review back to Draft, with the reason.

    Raises ``RecordNotFoundError`` and ``ItemStateError`` (not in internal review).
    """
    # STEPS
    # 1. `cmd = correlated(cmd)`; `row = open_technical(uow, cmd, cmd.stream_id)`;
    #    `require_state(row.item, ST_INTERNAL_REVIEW)`.
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
def check_flag(value: str, what: str) -> str:
    """``value`` when it is ``yes``, ``no`` or ``unknown``; otherwise ``ValueError``."""
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

def open_technical(uow: UnitOfWork, cmd: Command, item_id: str) -> registry_domain.TechnicalRow:
    """The Technical item in the command's scope that the viewer may read and that still takes
    changes. A missing item, one of another scope, a hidden one and an item of another kind all
    raise the same ``RecordNotFoundError`` (ADR-0016); a closed one raises ``ItemStateError``."""
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
class TechnicalData:
    question: str
    proposed_solution: str | None
    discipline: str | None
    required_by: str | None
    potential_cost_impact: str
    potential_schedule_impact: str
    answer: str | None
    answered_on: str | None
    answer_cost_impact: str | None
    answer_schedule_impact: str | None
    answer_item_id: str | None
    answering_revision_id: str | None
    review_decision: str | None
    reviewed_on: str | None
    review_note: str | None

@dataclass(frozen=True)
class TechnicalRow:
    """An RFI, a technical query or a deviation request: the item and its domain data."""

    item: ItemRow
    data: TechnicalData
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
    def raise_technical(self, subject="Beam B12 clashes with line 47", subtype="rfi", **more) -> CommandResult: ...
    def update_technical(self, item_id: str, **more) -> CommandResult: ...
    def submit_technical(self, item_id: str, **more) -> CommandResult: ...
    def return_technical(self, item_id: str, reason="...", **more) -> CommandResult: ...
    def issue_technical(self, item_id: str, **more) -> CommandResult: ...      # merged later: used by one test
    def technical(self, number: str) -> TechnicalRow: ...                      # a read; `.item` and `.data`
    def forge_technical(self, number="P123-RFI-0001", *, subject=..., state="Draft", subtype="rfi",
                        confidentiality="internal", scope=PROJECT, **data) -> str: ...  # raw events; returns the id
    def forge_item(self, number="P123-COR-0001", *, subject=..., state="Received", **more) -> str: ...
    def forge_party(self, code="MER", name="Meridian Energy") -> str: ...
    def events_of(self, stream_id: str) -> list[tuple[str, dict]]: ...
    def clocks(self, number: str) -> list[ClockRow]: ...

```

## Context (read these, nothing else)
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/technical.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/common.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/domain.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/create.py`
- `docs/tickets/P1-I6/provided/t02a-test_technical.py.txt`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/testing.py`
- `docs/templates/haiku-report.md`
may explore: (none)

## Allowed paths
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/technical.py` (complete)
- `packages/tl-modules/correspondence/tests/test_technical.py` (create: a byte-for-byte copy of the provided file)
- `docs/reports/P1-I6/P1-I6-T02a.md` (create: your report)

## Steps
1. `cp docs/tickets/P1-I6/provided/t02a-test_technical.py.txt packages/tl-modules/correspondence/tests/test_technical.py` and do not edit it.
2. Replace the body of each function that has a STEPS comment (`handle_raise_technical`, `handle_update_technical`, `handle_submit_technical`, `handle_return_technical`) by the steps of its comment; delete the STEPS comments, the `STUB` paragraph of the module docstring and the `ruff: noqa` line.
3. Run the commands below and keep their output.

## Acceptance
```
uv run ruff format packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/technical.py
uv run pytest packages/tl-modules/correspondence/tests/test_technical.py -q
uv run pytest packages/tl-modules/correspondence/tests/test_technical.py -q --adapters sqlite,postgres
just check
uv run pytest packages/tl-modules/correspondence -q
```
Expected: 45 passed on SQLite; 90 passed with both adapters (every case uses the `world` fixture, so each runs twice); `just check` clean (ruff, format, pyright, no codegen drift); the package suite passes. `TL_PG_URL` is exported by the session hook; if Postgres is not running, `sudo pg_ctlcluster 16 main start`.

## Tests to add
- `packages/tl-modules/correspondence/tests/test_technical.py` (provided, 45 tests): the Draft with its data and register text; the flag defaults; numbering by kind (each kind counts alone); the record type; the references that become the raiser's links; every refusal before any write (unknown subtype, a date before today, a bad date, bad flags, blank texts, an extra field, a bad address, an unknown, foreign, hidden or repeated reference, a scope that is not a project); the update (fields, register text following the question and the date, clearing with `null`, recipients, the question and flags that cannot be cleared, no-change, the reason, the states that take a change, a stale version, an unreadable item); submit (recipient and date needed, the date passed, the state); return (reason and state); a party that is not of the project; a transition on a stale version.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), saved as `docs/reports/P1-I6/P1-I6-T02a.md` and committed with the ticket. Deviations first. Paste the decisive lines of every acceptance command. Say which lines of the STEPS you found unclear, if any.

## Escalation triggers
- Stop and report *Blocked* if the pasted interface and the repo disagree, a command in *Acceptance* fails for a reason outside *Allowed paths*, or the provided test cannot pass without editing it.
- Stop if you find yourself changing a model, a field, a docstring or a name that this ticket does not own.
- Stop if a STEPS line and the provided test disagree.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
