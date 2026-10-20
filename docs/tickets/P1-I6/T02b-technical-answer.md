# P1-I6-T02b — Technical items: issue, answer, review, reissue, close

Status: ready
Tier: haiku
Labels: module, handlers
Depends on: T02a merged (the provided test raises and submits items with the commands of T02a)
Branch: `p1/i6-t02b-technical-answer`

## Goal
`handlers/technical_flow.py` has the five command models (`IssueTechnical`, `AnswerTechnical`, `ReviewTechnicalAnswer`, `ReissueTechnical`, `CloseTechnical`) and the helpers `_letter_text`, `_tell_the_sink` and `_check_revision`; the five `handle_*` functions raise `NotImplementedError`. You implement them by their STEPS comments. They are the rest of the life of an RFI: a document controller issues it (a letter as a PDF, a stub send, a clock that counts to the date the answer is needed), the answer is recorded with the answerer's statement on cost and schedule and meets the clock, the raiser accepts the answer or sends the question round again, and a closed item cancels what is still open. One provided test file must pass on SQLite and on Postgres.

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
`packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/technical_flow.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401, F841
"""Issue a Technical item, record its answer, judge the answer, send it round again, close it.

The raiser's commands are in ``technical.py``; these are the rest of the life of an RFI, a
technical query or a deviation request (workflow ``correspondence.technical``):

* ``IssueTechnical`` (a document controller's act, like issuing a letter): renders the question to
  a PDF, stores it, "sends" it (a stub: nothing leaves the machine), starts the clock that ends on
  the date the answer is needed, and moves the item Internal review, Issued, Awaiting response.
* ``AnswerTechnical``: records the answer with the answerer's statement on cost and schedule. A
  ``yes`` on either is what the RFI to Commercial escalation rule listens for. The clocks that
  waited for the answer are met on the answer's day.
* ``ReviewTechnicalAnswer``: the raiser accepts the answer, or rejects it with a reason.
* ``ReissueTechnical``: a rejected item goes back to internal review for another round; the
  answer of the round before is cleared from the current state (the events keep it).
* ``CloseTechnical``: the item needs no more work; its open clocks are cancelled.

STUB (P1-I6-T02b): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
"""

from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field, field_validator
from sqlalchemy import text
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import RecordNotFoundError
from tl_core.uow import UnitOfWork

from tl_mod_correspondence import catalog, constraints, files, registry, registry_domain
from tl_mod_correspondence.errors import InvalidItemError, ItemStateError, LetterRenderError
from tl_mod_correspondence.handlers.clocks import close_clocks_of_item
from tl_mod_correspondence.handlers.common import (
    append,
    correlated,
    require_state,
    resolve_date,
    today,
    transition,
)
from tl_mod_correspondence.handlers.domain import (
    Reference,
    check_flag,
    check_references,
    feed_fields,
    link_if_new,
    open_technical,
    require_readers_may_read,
    start_domain_clocks,
)
from tl_mod_correspondence.handlers.models import non_blank
from tl_mod_correspondence.letter import LetterError, LetterFields, compose_letter, render_pdf
from tl_mod_correspondence.limits import MAX_BODY, MAX_NUMBER, MAX_REASON
from tl_mod_correspondence.names import (
    CORR_ISSUED,
    CORR_RESPONDED,
    DOMAIN_TECHNICAL,
    ST_ACCEPTED,
    ST_ANSWERED,
    ST_AWAITING_RESPONSE,
    ST_INTERNAL_REVIEW,
    ST_REJECTED,
    TECH_ANSWERED,
    TECH_REISSUED,
    TECH_REVIEWED,
)
from tl_mod_correspondence.textcheck import clean_body, clean_optional_text, clean_text

ANSWER_CLOCKS = ("response_from_them", "response_from_us")
_ISSUES_SQL = text(
    "SELECT COUNT(*) FROM events WHERE stream_id = :id AND event_type = 'Correspondence.Issued'"
)
Decision = Literal["accepted", "rejected"]


class IssueTechnical(Command):
    """Issue a Technical item that has passed internal review (a document controller's act).

    The letter is rendered from the domain's template for the subtype (or ``template``). The send
    is a stub: nothing leaves the machine. ``issued_on`` is the date on the letter (today by
    default; an earlier day needs ``date_reason``; never later than today).
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


class AnswerTechnical(Command):
    """Record the answer to an item that is awaiting one.

    ``cost_impact`` and ``schedule_impact`` are the answerer's statement (``yes``, ``no`` or
    ``unknown``). ``answer_item_id`` is the item of the register that carries the answer (the
    client's letter) and ``answering_revision_id`` the document revision that answers (a re-issued
    drawing); each is linked to the item. ``answered_on`` is today by default; an earlier day
    needs ``date_reason``.
    """

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    answer: str = Field(min_length=1, max_length=MAX_BODY)
    cost_impact: str = Field(default="unknown", max_length=7)
    schedule_impact: str = Field(default="unknown", max_length=7)
    answer_item_id: str | None = Field(default=None, max_length=MAX_NUMBER)
    answering_revision_id: str | None = Field(default=None, max_length=MAX_NUMBER)
    answered_on: str | None = Field(default=None, max_length=10)
    date_reason: str | None = Field(default=None, max_length=MAX_REASON)

    @field_validator("answer")
    @classmethod
    def _answer(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return clean_body(value)

    @field_validator("cost_impact")
    @classmethod
    def _cost(cls, value: str) -> str:
        return check_flag(value, "cost_impact")

    @field_validator("schedule_impact")
    @classmethod
    def _schedule(cls, value: str) -> str:
        return check_flag(value, "schedule_impact")

    @field_validator("date_reason")
    @classmethod
    def _clean_date_reason(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


class ReviewTechnicalAnswer(Command):
    """Accept the answer, or reject it. A rejection needs a ``note`` that says why."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    decision: Decision
    note: str | None = Field(default=None, max_length=MAX_REASON)

    @field_validator("note")
    @classmethod
    def _note(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


class ReissueTechnical(Command):
    """Send a rejected item back to internal review for another round. A reason is required."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return clean_text(non_blank(value))


class CloseTechnical(Command):
    """Close an item that needs no more work. Its open clocks are cancelled.

    An item still waiting for its answer, and one whose answer was rejected, need a ``reason``.
    """

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    reason: str | None = Field(default=None, max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


def _letter_text(question: str, proposed: str | None, required_by: str | None) -> str:
    body = f"Question:\n{question}"
    if proposed:
        body += f"\n\nProposed solution:\n{proposed}"
    if required_by:
        body += f"\n\nAn answer is needed by {required_by}."
    return body


def _tell_the_sink(uow: UnitOfWork, item_id: str, *, issued: bool) -> None:
    """Call the constraint hook (a stub in Phase 1) with the item as it is now."""
    now = registry_domain.get_technical(uow.conn(), item_id)
    if now is None:  # the viewer reads what it just changed; this is not reachable
        return
    sink = constraints.current()
    (sink.rfi_issued if issued else sink.rfi_answered)(uow, now.item, now.data)


def handle_issue_technical(uow: UnitOfWork, cmd: IssueTechnical) -> CommandResult:
    """Render and store the PDF, "send" it, start the issue clocks, append
    ``Correspondence.Issued`` and move the item to Awaiting response.

    Raises ``RecordNotFoundError``, ``ItemStateError`` (not in internal review),
    ``InvalidItemError`` (no recipient), ``UnknownDomainError``, ``LetterRenderError`` (no such
    template, a letter the renderer refuses, no file service), ``InvalidClockError`` (the answer
    is needed by a day that is not after the issue day) and the date errors of ``resolve_date``.
    """
    # STEPS
    # 1. `cmd = correlated(cmd)`; `row = open_technical(uow, cmd, cmd.stream_id)`; `item,
    #    data = row.item, row.data`; `require_state(item, ST_INTERNAL_REVIEW)`.
    # 2. `recipients = ", ".join(r.get("name") or r.get("email") or "" for r in
    #    item.to).strip(", ")`; if it is empty raise `InvalidItemError(f"item
    #    {item.number} has no recipient")`.
    # 3. `definition = catalog.check_subtype(cmd.scope, DOMAIN_TECHNICAL, item.subtype or
    #    "")`; `day, date_reason = resolve_date(cmd.issued_on, cmd.date_reason, "the issue
    #    day")`.
    # 4. The template: `wanted = cmd.template`; `templates = [t for t in
    #    definition.templates if wanted is None or t.code == wanted]`; when `wanted is
    #    None` keep only those with `t.subtype == item.subtype`. If none is left raise
    #    `LetterRenderError(f"domain {definition.code} has no letter template " +
    #    (repr(wanted) if wanted else f"for subtype {item.subtype}"))`. `template =
    #    templates[0]`.
    # 5. Inside `try`: `lines = compose_letter(template.header, template.footer,
    #    LetterFields(number=item.number, date=day, subject=item.subject, to=recipients,
    #    body=_letter_text(data.question, data.proposed_solution, data.required_by)))` and
    #    `pdf = render_pdf(lines, title=f"{item.number} {item.subject}")`; `except
    #    LetterError as exc:` raise `LetterRenderError(str(exc)) from exc`.
    # 6. `stored = files.write_rendition(uow, actor=cmd.actor, source=cmd.source,
    #    scope=cmd.scope, record_id=item.id, filename=f"{item.number}.pdf", data=pdf,
    #    correlation_id=cmd.correlation_id or "")`.
    # 7. `clock_ids, clock_events = start_domain_clocks(uow, cmd, item, definition,
    #    "issue", day, answer_by=data.required_by)`.
    # 8. `done = append(uow, cmd, item.id, item.record_type,
    #    [NewEvent(event_type=CORR_ISSUED, payload={...})], expected=cmd.expected_version
    #    or item.version)`. The payload keys: `issued_on` (`day`), `date_reason`,
    #    `rendition_file_id` (`stored.file_id`), `rendition_sha256` (`stored.sha256`),
    #    `template` (`template.code`), `delivery` (`"stub"`), `clock_ids`, and the feed
    #    keys `**feed_fields(definition, full=f"{item.number} issued: {item.subject}",
    #    minimal="A technical request was issued")`.
    # 9. `issued = transition(uow, cmd, item.id, "issue")`; `waiting = transition(uow,
    #    cmd, item.id, "await_response")`; then call the constraint hook
    #    `_tell_the_sink(uow, item.id, issued=True)`.
    # 10. Return `CommandResult(stream_id=item.id, key=item.number,
    #    version=waiting.version, events=[*clock_events, *done.events, *issued.events,
    #    *waiting.events])`.
    raise NotImplementedError


def _check_revision(uow: UnitOfWork, cmd: Command, revision_id: str, own_id: str) -> None:
    """The revision is a readable ``documents.Revision`` of the scope."""
    check_references(uow, cmd, [Reference(record_id=revision_id)], own_id)
    kind = (
        uow.conn()
        .execute(text("SELECT type FROM cur_core_record WHERE id = :id"), {"id": revision_id})
        .scalar_one()
    )
    if kind != "documents.Revision":
        raise InvalidItemError(f"record {revision_id!r} is not a document revision")


def handle_answer_technical(uow: UnitOfWork, cmd: AnswerTechnical) -> CommandResult:
    """Append ``Technical.Answered`` and ``Correspondence.Responded``, link what answers, move the
    item to Answered and meet the clocks that waited for the answer.

    Raises ``RecordNotFoundError`` (the item, the answering item or the revision is unknown,
    foreign or hidden, or is of a class that some reader of the item may not read: the item's own
    events name it), ``ItemStateError`` (not awaiting a response), ``InvalidItemError`` (the
    answering item is the item itself, or the revision is not a document revision) and the date
    errors of ``resolve_date``.
    """
    # STEPS
    # 1. `cmd = correlated(cmd)`; `row = open_technical(uow, cmd, cmd.stream_id)`; `item =
    #    row.item`; `require_state(item, ST_AWAITING_RESPONSE)`.
    # 2. If `cmd.answer_item_id` is not None: `answer = registry.get_item(uow.conn(),
    #    cmd.answer_item_id)`; if `answer is None or answer.scope != cmd.scope` raise
    #    `RecordNotFoundError(f"no record {cmd.answer_item_id!r}")`; if `answer.id ==
    #    item.id` raise `InvalidItemError("an item cannot be its own answer")`; then
    #    `require_readers_may_read(uow, item, answer.id)` (the item's own events will name
    #    the answer, so everyone who reads the item must be able to read it; it raises the
    #    same `RecordNotFoundError`).
    # 3. If `cmd.answering_revision_id` is not None call `_check_revision(uow, cmd,
    #    cmd.answering_revision_id, item.id)` and then `require_readers_may_read(uow,
    #    item, cmd.answering_revision_id)`.
    # 4. `day, date_reason = resolve_date(cmd.answered_on, cmd.date_reason, "the answer
    #    day")`; `definition = catalog.check_subtype(cmd.scope, DOMAIN_TECHNICAL,
    #    item.subtype or "")`.
    # 5. `done = append(uow, cmd, item.id, item.record_type, [two events],
    #    expected=cmd.expected_version or item.version)`. First
    #    `NewEvent(event_type=TECH_ANSWERED, payload={...})` with keys `answer`,
    #    `answered_on` (`day`), `date_reason`, `cost_impact`, `schedule_impact`,
    #    `answer_item_id`, `answering_revision_id` (from `cmd`) and
    #    `**feed_fields(definition, full=f"{item.number} answered: {item.subject}",
    #    minimal="A technical request was answered")`. Then
    #    `NewEvent(event_type=CORR_RESPONDED, payload={"response_id": cmd.answer_item_id,
    #    "responded_on": day})`.
    # 6. `linked = []`. For `(target, note)` in `((cmd.answer_item_id, "the answer"),
    #    (cmd.answering_revision_id, "the answering revision"))`, when `target is not
    #    None`: `linked += link_if_new(uow, cmd, item.id, target, note)`.
    # 7. `moved = transition(uow, cmd, item.id, "answer")`.
    # 8. `met = close_clocks_of_item(uow, cmd, item.id, how="met", day=day,
    #    reason="answered", response_id=cmd.answer_item_id, kinds=ANSWER_CLOCKS)`; then
    #    `_tell_the_sink(uow, item.id, issued=False)`.
    # 9. Return `CommandResult(stream_id=item.id, key=item.number, version=moved.version,
    #    events=[*done.events, *linked, *moved.events, *met])`.
    raise NotImplementedError


def handle_review_technical_answer(uow: UnitOfWork, cmd: ReviewTechnicalAnswer) -> CommandResult:
    """Append ``Technical.Reviewed`` and move the item to Accepted or Rejected.

    Raises ``RecordNotFoundError``, ``ItemStateError`` (no answer to judge) and
    ``InvalidItemError`` (a rejection without a note).
    """
    # STEPS
    # 1. `cmd = correlated(cmd)`; `row = open_technical(uow, cmd, cmd.stream_id)`; `item =
    #    row.item`; `require_state(item, ST_ANSWERED)`.
    # 2. If `cmd.decision == "rejected"` and `cmd.note` is None, empty or blank (`not
    #    (cmd.note and cmd.note.strip())`) raise `InvalidItemError("say why the answer is
    #    rejected")`.
    # 3. `append(uow, cmd, item.id, item.record_type, [NewEvent(event_type=TECH_REVIEWED,
    #    payload={"decision": cmd.decision, "note": cmd.note, "reviewed_on": today()})],
    #    expected=cmd.expected_version or item.version)`.
    # 4. Return `transition(uow, cmd, item.id, "accept" if cmd.decision == "accepted" else
    #    "reject", reason=cmd.note)`.
    raise NotImplementedError


def handle_reissue_technical(uow: UnitOfWork, cmd: ReissueTechnical) -> CommandResult:
    """Append ``Technical.Reissued`` (with the number of the round that starts) and move the item
    back to Internal review.

    Raises ``RecordNotFoundError`` and ``ItemStateError`` (the answer was not rejected).
    """
    # STEPS
    # 1. `cmd = correlated(cmd)`; `row = open_technical(uow, cmd, cmd.stream_id)`; `item =
    #    row.item`; `require_state(item, ST_REJECTED)`.
    # 2. `rounds = int(uow.conn().execute(_ISSUES_SQL, {"id": item.id}).scalar_one()) + 1`
    #    (the number of letters sent so far, plus the one that starts).
    # 3. `append(uow, cmd, item.id, item.record_type, [NewEvent(event_type=TECH_REISSUED,
    #    payload={"reason": cmd.reason, "round": rounds})], expected=cmd.expected_version
    #    or item.version)`.
    # 4. Return `transition(uow, cmd, item.id, "reissue", reason=cmd.reason)`.
    raise NotImplementedError


def handle_close_technical(uow: UnitOfWork, cmd: CloseTechnical) -> CommandResult:
    """Move the item to Closed and cancel its open clocks.

    Raises ``RecordNotFoundError``, ``ItemStateError`` (the item is not awaiting a response,
    accepted or rejected; or it is waiting for an answer, or was rejected, and no ``reason`` was
    given).
    """
    # STEPS
    # 1. `cmd = correlated(cmd)`; `row = open_technical(uow, cmd, cmd.stream_id)`; `item =
    #    row.item`; `require_state(item, ST_AWAITING_RESPONSE, ST_ACCEPTED, ST_REJECTED)`.
    # 2. If `item.state != ST_ACCEPTED` and `cmd.reason` is None, empty or blank raise
    #    `ItemStateError(f"item {item.number} is {item.state}; give the reason for closing
    #    it")`.
    # 3. `moved = transition(uow, cmd, item.id, "close", reason=cmd.reason,
    #    expected=cmd.expected_version)`.
    # 4. `cancelled = close_clocks_of_item(uow, cmd, item.id, how="cancelled",
    #    day=today(), reason=cmd.reason or "item closed")`.
    # 5. Return `CommandResult(stream_id=item.id, key=item.number, version=moved.version,
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

def check_references(
    uow: UnitOfWork, cmd: Command, references: Sequence[Reference], own_id: str | None
) -> None:
    """Each referenced record is in the scope and readable by the viewer (the same
    ``RecordNotFoundError`` for an unknown, a foreign and a hidden record), once each."""
    ...

def require_readers_may_read(uow: UnitOfWork, item: registry.ItemRow, target_id: str) -> None:
    """Refuse ``target_id`` unless everyone who reads ``item`` may read it too.

    An event on the item's stream names the record (the answering item, the answering revision),
    and every reader of the item reads that event: a record they may not read must not be named
    there. The readers of an ``internal`` item are anyone, of a ``restricted`` one a controller,
    of a ``privileged`` one the accounts named on it; an unknown class has none we can vouch for.
    The refusal is the one for an unknown record (ADR-0016).
    """
    ...

def link_if_new(
    uow: UnitOfWork, cmd: Command, from_id: str, to_id: str, note: str | None
) -> list[Event]:
    """Link ``from_id`` to ``to_id`` with a ``references`` link unless one is there already (a
    link of any status counts: a retracted link is not made again behind someone's back)."""
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

def open_technical(uow: UnitOfWork, cmd: Command, item_id: str) -> registry_domain.TechnicalRow:
    """The Technical item in the command's scope that the viewer may read and that still takes
    changes. A missing item, one of another scope, a hidden one and an item of another kind all
    raise the same ``RecordNotFoundError`` (ADR-0016); a closed one raises ``ItemStateError``."""
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

`packages/tl-modules/correspondence/src/tl_mod_correspondence/catalog.py` (read-only; abridged to the names used):
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
    def answer_technical(self, item_id: str, **more) -> CommandResult: ...     # defaults: cost_impact and schedule_impact "no"
    def review_technical(self, item_id: str, decision="accepted", **more) -> CommandResult: ...
    def reissue_technical(self, item_id: str, reason="names both beams", **more) -> CommandResult: ...
    def close_technical(self, item_id: str, **more) -> CommandResult: ...
    def run(self, model, handler, /, **fields) -> CommandResult: ...           # one command in its own unit of work
    files: FileService | None                                                  # the object store the letter is written to

```

## Context (read these, nothing else)
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/technical_flow.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/common.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/domain.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/create.py`
- `docs/tickets/P1-I6/provided/t02b-test_technical_flow.py.txt`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/testing.py`
- `docs/templates/haiku-report.md`
may explore: (none)

## Allowed paths
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/technical_flow.py` (complete)
- `packages/tl-modules/correspondence/tests/test_technical_flow.py` (create: a byte-for-byte copy of the provided file)
- `docs/reports/P1-I6/P1-I6-T02b.md` (create: your report)

## Steps
1. `cp docs/tickets/P1-I6/provided/t02b-test_technical_flow.py.txt packages/tl-modules/correspondence/tests/test_technical_flow.py` and do not edit it.
2. Replace the body of each function that has a STEPS comment (`handle_issue_technical`, `handle_answer_technical`, `handle_review_technical_answer`, `handle_reissue_technical`, `handle_close_technical`) by the steps of its comment; delete the STEPS comments, the `STUB` paragraph of the module docstring and the `ruff: noqa` line.
3. Run the commands below and keep their output.

## Acceptance
```
uv run ruff format packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/technical_flow.py
uv run pytest packages/tl-modules/correspondence/tests/test_technical_flow.py -q
uv run pytest packages/tl-modules/correspondence/tests/test_technical_flow.py -q --adapters sqlite,postgres
just check
uv run pytest packages/tl-modules/correspondence -q
```
Expected: 41 passed on SQLite; 82 passed with both adapters (every case uses the `world` fixture, so each runs twice); `just check` clean (ruff, format, pyright, no codegen drift); the package suite passes. `TL_PG_URL` is exported by the session hook; if Postgres is not running, `sudo pg_ctlcluster 16 main start`.

## Tests to add
- `packages/tl-modules/correspondence/tests/test_technical_flow.py` (provided, 41 tests): the issue (state, issue day, clock to the date needed, events, feed keys, the letter as a PDF with the question, the proposed solution and the date; the template per subtype, a named and an unknown template; an earlier day needs a reason, a later one is refused; the answer date must be after the issue day; state and recipient; unreadable items); the answer (statement and dates, the flags, the clock met on the day, an earlier day, the item that carries the answer and the revision that answers, what is refused before any write, blank text and wrong flags, the state; a record above the class of the item is refused like an unknown one); the review (accept, a rejection needs a note, the state); the reissue (the old answer leaves the current state, rounds are counted, the same answer item is linked once, a reason and a rejected item); the close (accepted without a reason, waiting or rejected with one, clocks cancelled, other states refused, a closed item takes no more); the constraint hook hears the issue and the answer, and not a refused command; an issue on a stale version is a conflict.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), saved as `docs/reports/P1-I6/P1-I6-T02b.md` and committed with the ticket. Deviations first. Paste the decisive lines of every acceptance command. Say which lines of the STEPS you found unclear, if any.

## Escalation triggers
- Stop and report *Blocked* if the pasted interface and the repo disagree, a command in *Acceptance* fails for a reason outside *Allowed paths*, or the provided test cannot pass without editing it.
- Stop if you find yourself changing a model, a field, a docstring or a name that this ticket does not own.
- Stop if a STEPS line and the provided test disagree.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
