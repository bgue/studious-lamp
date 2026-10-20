# P1-I6-T04b — Commercial items: issue, assess, close, refer to legal

Status: ready
Tier: haiku
Labels: module, handlers
Depends on: T04a merged (the provided test raises, submits and reviews items with the commands of T04a)
Branch: `p1/i6-t04b-commercial-assess`

## Goal
`handlers/commercial_flow.py` has the four command models (`IssueCommercial`, `AssessCommercial`, `CloseCommercial`, `ReferCommercialToLegal`) and the helper `_letter_body`; the four `handle_*` functions raise `NotImplementedError`. You implement them by their STEPS comments. A document controller issues the approved notice (a letter as a PDF, a stub send, the time bar met on the issue day, the clocks that wait for the assessment), records the other party's assessment (agreed, disputed or partly agreed, with a value), closes the item or takes a dispute to the legal route. One provided test file must pass on SQLite and on Postgres.

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
`packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/commercial_flow.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401, F841
"""Issue a Commercial item, record its assessment, close it, refer a dispute to the legal route.

The author's commands are in ``commercial.py``; these are the rest of the life of a Commercial
item (workflow ``correspondence.commercial``). All of them are a document controller's:

* ``IssueCommercial``: approves and issues the notice. Renders it to a PDF, stores it, "sends" it
  (a stub: nothing leaves the machine), **meets the time bar** on the issue day (the notice was
  given; a day after the due date shows as late), starts the clocks that wait for the assessment,
  and moves the item PM approval, Issued, Awaiting assessment.
* ``AssessCommercial``: records the other party's assessment: agreed, disputed or partially
  agreed, with the value they assessed. The clocks that waited for it are met.
* ``CloseCommercial``: the item needs no more work; its open clocks are cancelled.
* ``ReferCommercialToLegal``: a dispute leaves this domain for the legal route (a domain of a
  later phase); the item is Escalated and its clocks are cancelled.

STUB (P1-I6-T04b): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
"""

from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field, field_validator
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.uow import UnitOfWork

from tl_mod_correspondence import catalog, files, registry
from tl_mod_correspondence.errors import InvalidItemError, ItemStateError, LetterRenderError
from tl_mod_correspondence.handlers.clocks import close_clocks_of_item
from tl_mod_correspondence.handlers.commercial import require_controller_viewer
from tl_mod_correspondence.handlers.common import (
    append,
    correlated,
    require_state,
    resolve_date,
    today,
    transition,
)
from tl_mod_correspondence.handlers.domain import (
    check_money,
    feed_fields,
    open_commercial,
    start_domain_clocks,
)
from tl_mod_correspondence.handlers.models import non_blank
from tl_mod_correspondence.letter import LetterError, LetterFields, compose_letter, render_pdf
from tl_mod_correspondence.limits import MAX_NUMBER, MAX_REASON
from tl_mod_correspondence.names import (
    ASSESSMENT_STATUSES,
    COMM_ASSESSED,
    CORR_ISSUED,
    DOMAIN_COMMERCIAL,
    ST_AGREED,
    ST_AWAITING_ASSESSMENT,
    ST_DISPUTED,
    ST_PARTLY_AGREED,
    ST_PM_APPROVAL,
)
from tl_mod_correspondence.textcheck import clean_optional_text, clean_text

AssessmentStatus = Literal["agreed", "disputed", "partially_agreed"]
_MOVE = {"agreed": "agree", "disputed": "dispute", "partially_agreed": "part_agree"}
ASSESSMENT_CLOCKS = ("response_from_them",)


class IssueCommercial(Command):
    """Approve and issue a Commercial item that has passed commercial review.

    The notice is rendered from the domain's template for the subtype (or ``template``). The send
    is a stub: nothing leaves the machine. ``issued_on`` is the date on the notice (today by
    default; an earlier day needs ``date_reason``; never later than today). A notice issued after
    its time bar ran out is issued all the same and the clock shows it was late.
    """

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    template: str | None = Field(default=None, max_length=MAX_NUMBER)
    issued_on: str | None = Field(default=None, max_length=10)
    date_reason: str | None = Field(default=None, max_length=MAX_REASON)

    @field_validator("date_reason")
    @classmethod
    def _clean_date_reason(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


class AssessCommercial(Command):
    """Record the other party's assessment of an issued item (or of an instruction we received).

    ``status`` is ``agreed``, ``disputed`` or ``partially_agreed``. ``assessed_value`` (in the
    currency of the item) is required unless the item is disputed. ``assessed_on`` is today by
    default; an earlier day needs ``date_reason``.
    """

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    status: AssessmentStatus
    assessed_value: str | None = Field(default=None, max_length=20)
    note: str | None = Field(default=None, max_length=MAX_REASON)
    assessed_on: str | None = Field(default=None, max_length=10)
    date_reason: str | None = Field(default=None, max_length=MAX_REASON)

    @field_validator("assessed_value")
    @classmethod
    def _value(cls, value: str | None) -> str | None:
        return check_money(value, "assessed_value")

    @field_validator("note", "date_reason")
    @classmethod
    def _text(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


class CloseCommercial(Command):
    """Close an assessed item. Its open clocks are cancelled. A disputed item needs a ``reason``."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    reason: str | None = Field(default=None, max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


class ReferCommercialToLegal(Command):
    """Take a disputed item to the legal route. The item is Escalated; a reason is required."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return clean_text(non_blank(value))


def _letter_body(item: registry.ItemRow, text_lines: list[str]) -> str:
    return "\n\n".join(line for line in [item.body or "", *text_lines] if line)


def handle_issue_commercial(uow: UnitOfWork, cmd: IssueCommercial) -> CommandResult:
    """Render and store the PDF, "send" it, meet the time bar, start the issue clocks, append
    ``Correspondence.Issued`` and move the item to Awaiting assessment.

    Raises ``ForbiddenError``, ``RecordNotFoundError``, ``ItemStateError`` (not in PM approval),
    ``InvalidItemError`` (no recipient, or an issue day before the day the contractor became
    aware), ``UnknownDomainError``, ``LetterRenderError`` and the date errors of ``resolve_date``.
    """
    # STEPS
    # 1. `require_controller_viewer()`; `cmd = correlated(cmd)`; `row =
    #    open_commercial(uow, cmd, cmd.stream_id)`; `item, data = row.item, row.data`;
    #    `require_state(item, ST_PM_APPROVAL)`.
    # 2. `recipients = ", ".join(r.get("name") or r.get("email") or "" for r in
    #    item.to).strip(", ")`; if it is empty raise `InvalidItemError(f"item
    #    {item.number} has no recipient")`.
    # 3. `definition = catalog.check_subtype(cmd.scope, DOMAIN_COMMERCIAL, item.subtype or
    #    "")`; `day, date_reason = resolve_date(cmd.issued_on, cmd.date_reason, "the issue
    #    day")`. If `data.aware_on is not None and day < data.aware_on` (ISO dates compare
    #    as text) raise `InvalidItemError(f"the issue day {day} is before the day the
    #    contractor became aware ({data.aware_on})")`: a bar cannot be met before it ran.
    # 4. The template: `wanted = cmd.template`; `templates = [t for t in
    #    definition.templates if wanted is None or t.code == wanted]`; when `wanted is
    #    None` keep only those with `t.subtype == item.subtype`. If none is left raise
    #    `LetterRenderError(f"domain {definition.code} has no letter template " +
    #    (repr(wanted) if wanted else f"for subtype {item.subtype}"))`. `template =
    #    templates[0]`.
    # 5. `lines: list[str] = []`, then add in this order: if `data.estimated_value is not
    #    None`, `f"Estimated value: {data.currency} {data.estimated_value}"`; if
    #    `data.estimated_hours is not None`, `f"Estimated hours: {data.estimated_hours}"`;
    #    if `data.schedule_impact_days is not None`, `f"Schedule impact:
    #    {data.schedule_impact_days} days"`; if `data.schedule_impact_note`, that text; if
    #    `data.entitlement_basis`, `f"Basis: {data.entitlement_basis}"`; if
    #    `data.contract_clause_id is not None`, read `clause =
    #    registry.get_clause(uow.conn(), data.contract_clause_id)` and, when it is not
    #    None, `f"Given under clause {clause.contract}/{clause.clause_number}."`.
    # 6. Inside `try`: `letter = compose_letter(template.header, template.footer,
    #    LetterFields(number=item.number, date=day, subject=item.subject, to=recipients,
    #    body=_letter_body(item, lines)))` and `pdf = render_pdf(letter,
    #    title=f"{item.number} {item.subject}")`; `except LetterError as exc:` raise
    #    `LetterRenderError(str(exc)) from exc`.
    # 7. `stored = files.write_rendition(uow, actor=cmd.actor, source=cmd.source,
    #    scope=cmd.scope, record_id=item.id, filename=f"{item.number}.pdf", data=pdf,
    #    correlation_id=cmd.correlation_id or "")`.
    # 8. Meet the time bar on the issue day: `met = close_clocks_of_item(uow, cmd,
    #    item.id, how="met", day=day, reason="the notice was issued",
    #    kinds=("time_bar",))`. Then start the clocks that wait for the assessment:
    #    `clock_ids, clock_events = start_domain_clocks(uow, cmd, item, definition,
    #    "issue", day)`.
    # 9. `done = append(uow, cmd, item.id, item.record_type,
    #    [NewEvent(event_type=CORR_ISSUED, payload={...})], expected=cmd.expected_version
    #    or item.version)`. The payload keys: `issued_on` (`day`), `date_reason`,
    #    `rendition_file_id` (`stored.file_id`), `rendition_sha256` (`stored.sha256`),
    #    `template` (`template.code`), `delivery` (`"stub"`), `clock_ids`, and the feed
    #    keys `**feed_fields(definition, full=f"{item.number} issued: {item.subject}",
    #    minimal="A commercial notice was issued")`.
    # 10. `issued = transition(uow, cmd, item.id, "issue")`; `waiting = transition(uow,
    #    cmd, item.id, "await_assessment")`.
    # 11. Return `CommandResult(stream_id=item.id, key=item.number,
    #    version=waiting.version, events=[*met, *clock_events, *done.events,
    #    *issued.events, *waiting.events])`.
    raise NotImplementedError


def handle_assess_commercial(uow: UnitOfWork, cmd: AssessCommercial) -> CommandResult:
    """Append ``Commercial.Assessed``, move the item to Agreed, Disputed or Partially agreed and
    meet the clocks that waited for the assessment.

    Raises ``ForbiddenError``, ``RecordNotFoundError``, ``ItemStateError`` (not awaiting an
    assessment), ``InvalidItemError`` (a value is missing for an agreed or partly agreed item, or
    the item states no currency) and the date errors of ``resolve_date``.
    """
    # STEPS
    # 1. `require_controller_viewer()`; `cmd = correlated(cmd)`; `row =
    #    open_commercial(uow, cmd, cmd.stream_id)`; `item, data = row.item, row.data`;
    #    `require_state(item, ST_AWAITING_ASSESSMENT)`.
    # 2. If `cmd.status not in ASSESSMENT_STATUSES` raise `InvalidItemError(f"status is
    #    one of {', '.join(ASSESSMENT_STATUSES)}")` (the model's `Literal` already says
    #    it; keep the check).
    # 3. If `cmd.status != "disputed"` and `cmd.assessed_value is None` raise
    #    `InvalidItemError(f"an {cmd.status.replace('_', ' ')} item needs the assessed
    #    value")`.
    # 4. If `cmd.assessed_value is not None` and `data.currency is None` raise
    #    `InvalidItemError(f"item {item.number} states no currency; update it before
    #    recording a value")`.
    # 5. `day, date_reason = resolve_date(cmd.assessed_on, cmd.date_reason, "the
    #    assessment day")`; `definition = catalog.check_subtype(cmd.scope,
    #    DOMAIN_COMMERCIAL, item.subtype or "")`.
    # 6. `append(uow, cmd, item.id, item.record_type, [NewEvent(event_type=COMM_ASSESSED,
    #    payload={...})], expected=cmd.expected_version or item.version)`. The payload
    #    keys: `status`, `assessed_value` (from `cmd`), `assessed_on` (`day`),
    #    `date_reason`, `note` (from `cmd`) and `**feed_fields(definition,
    #    full=f"{item.number} assessed as {cmd.status.replace('_', ' ')}", minimal="A
    #    commercial notice was assessed")`.
    # 7. `moved = transition(uow, cmd, item.id, _MOVE[cmd.status], reason=cmd.note)`; `met
    #    = close_clocks_of_item(uow, cmd, item.id, how="met", day=day, reason="assessed",
    #    kinds=ASSESSMENT_CLOCKS)`.
    # 8. Return `CommandResult(stream_id=item.id, key=item.number, version=moved.version,
    #    events=[*moved.events, *met])`.
    raise NotImplementedError


def handle_close_commercial(uow: UnitOfWork, cmd: CloseCommercial) -> CommandResult:
    """Move the item to Closed and cancel its open clocks.

    Raises ``ForbiddenError``, ``RecordNotFoundError``, ``ItemStateError`` (the item is not
    Agreed, Partially agreed or Disputed; or it is Disputed and no ``reason`` was given).
    """
    # STEPS
    # 1. `require_controller_viewer()`; `cmd = correlated(cmd)`; `row =
    #    open_commercial(uow, cmd, cmd.stream_id)`; `item = row.item`;
    #    `require_state(item, ST_AGREED, ST_PARTLY_AGREED, ST_DISPUTED)`.
    # 2. If `item.state == ST_DISPUTED` and `cmd.reason` is None, empty or blank raise
    #    `ItemStateError(f"item {item.number} is disputed; give the reason for closing
    #    it")`.
    # 3. `moved = transition(uow, cmd, item.id, "close", reason=cmd.reason,
    #    expected=cmd.expected_version)`; `cancelled = close_clocks_of_item(uow, cmd,
    #    item.id, how="cancelled", day=today(), reason=cmd.reason or "item closed")`.
    # 4. Return `CommandResult(stream_id=item.id, key=item.number, version=moved.version,
    #    events=[*moved.events, *cancelled])`.
    raise NotImplementedError


def handle_refer_commercial_to_legal(uow: UnitOfWork, cmd: ReferCommercialToLegal) -> CommandResult:
    """Move a disputed item to Escalated and cancel its open clocks.

    Raises ``ForbiddenError``, ``RecordNotFoundError`` and ``ItemStateError`` (not Disputed).
    """
    # STEPS
    # 1. `require_controller_viewer()`; `cmd = correlated(cmd)`; `row =
    #    open_commercial(uow, cmd, cmd.stream_id)`; `item = row.item`;
    #    `require_state(item, ST_DISPUTED)`.
    # 2. `moved = transition(uow, cmd, item.id, "escalate", reason=cmd.reason,
    #    expected=cmd.expected_version)`; `cancelled = close_clocks_of_item(uow, cmd,
    #    item.id, how="cancelled", day=today(), reason="referred to the legal route")`.
    # 3. Return `CommandResult(stream_id=item.id, key=item.number, version=moved.version,
    #    events=[*moved.events, *cancelled])`.
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
def check_money(value: str | None, what: str) -> str | None:
    """A decimal text with at most two places, written with exactly two (``12500`` is
    ``12500.00``); ``None`` stays ``None``. A float, a sign, an exponent, a separator or a digit
    that is not ``0`` to ``9`` is refused (L-P1-I4-1)."""
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

def feed_fields(definition: DomainDefinition, *, full: str, minimal: str) -> dict[str, str]:
    """The ``feed_policy`` and ``feed_text`` keys an event carries so that the feed shows what the
    domain's policy allows (``tl_core.feed.cards``): the line ``full`` for policy full, the line
    ``minimal`` for policy minimal, and no card at all for policy none. The policy is fixed when
    the event is written, so a rebuild of the feed never depends on a file that changed later."""
    ...
```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/clocks.py` (read-only; abridged to the names used):
```python
def close_clocks_of_item(
    uow: UnitOfWork,
    cmd: Command,
    item_id: str,
    *,
    how: Literal["met", "cancelled"],
    day: str,
    reason: str,
    response_id: str | None = None,
    kinds: Sequence[str] | None = None,
) -> list[Event]:
    """Close the item's open clocks (``kinds`` limits which) and return the events.

    Used by recording a response (``met``, with the answering item) and by voiding or closing an
    item (``cancelled``). A clock that is already closed is left alone.
    """
    ...
```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/commercial.py` (read-only; abridged to the names used):
```python
def require_controller_viewer() -> None:
    """Refuse a viewer below a document controller: Commercial items are ``restricted``."""
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

`packages/tl-modules/correspondence/src/tl_mod_correspondence/catalog.py` (read-only; abridged to the names used):
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
    def issue_commercial(self, item_id: str, **more) -> CommandResult: ...
    def assess_commercial(self, item_id: str, status="agreed", **more) -> CommandResult: ...  # assessed_value "12500.00" unless disputed
    def close_commercial(self, item_id: str, **more) -> CommandResult: ...
    def refer_to_legal(self, item_id: str, reason="the dispute is formal", **more) -> CommandResult: ...
    def start_clock(self, item_id: str, **more) -> CommandResult: ...          # an extra clock on an item
    files: FileService | None                                                  # the object store the notice is written to

```

## Context (read these, nothing else)
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/commercial_flow.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/common.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/domain.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/create.py`
- `docs/tickets/P1-I6/provided/t04b-test_commercial_flow.py.txt`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/testing.py`
- `docs/templates/haiku-report.md`
may explore: (none)

## Allowed paths
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/commercial_flow.py` (complete)
- `packages/tl-modules/correspondence/tests/test_commercial_flow.py` (create: a byte-for-byte copy of the provided file)
- `docs/reports/P1-I6/P1-I6-T04b.md` (create: your report)

## Steps
1. `cp docs/tickets/P1-I6/provided/t04b-test_commercial_flow.py.txt packages/tl-modules/correspondence/tests/test_commercial_flow.py` and do not edit it.
2. Replace the body of each function that has a STEPS comment (`handle_issue_commercial`, `handle_assess_commercial`, `handle_close_commercial`, `handle_refer_commercial_to_legal`) by the steps of its comment; delete the STEPS comments, the `STUB` paragraph of the module docstring and the `ruff: noqa` line.
3. Run the commands below and keep their output.

## Acceptance
```
uv run ruff format packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/commercial_flow.py
uv run pytest packages/tl-modules/correspondence/tests/test_commercial_flow.py -q
uv run pytest packages/tl-modules/correspondence/tests/test_commercial_flow.py -q --adapters sqlite,postgres
just check
uv run pytest packages/tl-modules/correspondence -q
```
Expected: 34 passed on SQLite; 68 passed with both adapters (every case uses the `world` fixture, so each runs twice); `just check` clean (ruff, format, pyright, no codegen drift); the package suite passes. `TL_PG_URL` is exported by the session hook; if Postgres is not running, `sudo pg_ctlcluster 16 main start`.

## Tests to add
- `packages/tl-modules/correspondence/tests/test_commercial_flow.py` (provided, 34 tests): the issue (state, issue day, the time bar met on that day and shown late when it is, the clocks that start, events, feed keys, the notice as a PDF with every figure line, a quotation, an earlier day needs a reason and a later one is refused, never before the day the contractor became aware, a named and an unknown template, state and recipient); the assessment (agreed with a value and the clock met, each status and its state, a dispute needs no value and an agreement does, a value needs a currency, an earlier day, wrong statuses and values, the state, a received instruction); the close (agreed or partly agreed without a reason, disputed with one, open clocks cancelled, other states refused, a closed item takes no more); the referral to the legal route (a disputed item, its clocks cancelled, a reason); every command refuses a plain viewer and a hidden or unknown item; issuing leaves a clock a person started running.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), saved as `docs/reports/P1-I6/P1-I6-T04b.md` and committed with the ticket. Deviations first. Paste the decisive lines of every acceptance command. Say which lines of the STEPS you found unclear, if any.

## Escalation triggers
- Stop and report *Blocked* if the pasted interface and the repo disagree, a command in *Acceptance* fails for a reason outside *Allowed paths*, or the provided test cannot pass without editing it.
- Stop if you find yourself changing a model, a field, a docstring or a name that this ticket does not own.
- Stop if a STEPS line and the provided test disagree.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
