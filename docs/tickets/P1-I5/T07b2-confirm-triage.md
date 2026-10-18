# P1-I5-T07b2 — ConfirmTriage and ReclassifyCorrespondence

Status: ready
Tier: haiku
Labels: module, core, agent
Depends on: P1-I5-T07a (the test receives items with the receive command), P1-I5-T07b1 (triage calls `suggest`), P1-I5-T07f (the test retires a clause with the retire command)
Branch: `p1/i5-t07b2-confirm-triage`

## Goal
`handlers/triage.py` has the two command models, `start_template_clocks` and `_clause_id`; `handle_confirm_triage`, `handle_reclassify_correspondence` and `_check_references` raise `NotImplementedError`. You implement them by their STEPS comments. Confirming a triage records the domain and subtype of a received item, starts the clocks its subtype defines for receipt, links the records it refers to and moves it to Triaged; an agent may only *propose* it (`propose_triage`). Reclassify corrects the domain before issue. One provided test file must pass on SQLite and on Postgres.

## Brief references (pasted)
> **How a correspondence command is written (D6, D6b, ADR-0010, ADR-0016).** A handler is `handle_x(uow, cmd)`; it runs in an entered unit of work, appends through it and never commits. Every check is made before anything is appended. It reads an item **only** through `open_item`, `load_item` or `registry.get_item` (they apply the confidentiality filter: an item the person may not read answers the same `RecordNotFoundError` as one that does not exist); it never queries the item table itself and never inspects who the caller is: who may call a command is decided by the API (`commands.py`). The module moves its own items through the workflow with `transition(...)` (the generic `TransitionWorkflow` is not allowed on items). Time comes only from `today()` in `handlers/common.py`.
>
> **Command models and docstrings are the contract.** Do not change a model, a field, a docstring or a name in a file you complete; only the function bodies that carry a STEPS comment are yours.
>
> **Triage (brief 9, M10).** Received items are triaged: the module proposes the domain and the subtype from keywords; a person confirms; the domain's clock templates for *receipt* start; the records the item refers to are linked (`references`, rule links). A record the person may not read is never referenced: it answers `RecordNotFoundError` with the same text as a missing one.

### Learnings that apply
> **L-P1-I5-1.** Postgres cannot infer the type of a bare parameter in `CASE WHEN :p IS NOT NULL ...` (`could not determine data type of parameter $1`), and a Python bool is the portable value for a boolean column. Compute such choices in Python; run the test on both adapters before you report.
>
> **L-P1-I1-6.** A parity run's count is not the SQLite count twice: a case that does not use the `db`/`new_db`/`engine`/`world` fixtures runs once. The counts below are exact.
>
> **L-P1-I3-5.** A test that only passes with the whole module in place is the module's test: run the provided file as it is; do not add helpers to it or to the shared test support (`tl_mod_correspondence/testing.py`).
> **L-P0-I1-6.** ruff's `E501` applies to docstrings and comments at 100 columns, and pyright strict flags `@contextmanager` functions annotated `Iterator[X]`. Wrap prose.
>
> **L-P0-I6C-8 / L-P1-I0B-3.** Write files with the Write tool, not a long `cat > file <<'EOF'` inside a `&&` chain, and never `pkill -f`: kill only a PID you started.
>
> **L-P1-I3B-6.** Copy the provided test byte for byte (`cp`), run `ruff` and `pyright` on the tree, and do not edit the copy: if it cannot pass, stop and report *Blocked*.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/triage.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401, F841
"""Triage: confirm the domain and subtype of a received item, and reclassify before issue.

A received item is **triaged** when a person confirms which domain it belongs to and what kind of
item it is (``ConfirmTriage``). The suggestion engine (``suggest.py``) proposes; the person decides;
an agent's ``propose_triage`` is a proposal that becomes this command only when a person accepts it.
Confirming does four things in one append: records the domain and subtype, links the item to the
records it refers to, starts the clocks the subtype defines for *receipt*, and moves the item to
Triaged. The clocks that start on *issue* start when a reply is issued (``IssueCorrespondence``).

``ReclassifyCorrespondence`` corrects the domain or subtype of a draft, a received or a triaged
item. After issue a misfiled item gets a linked item in the right domain instead (the issued item
is the record of what was sent).

STUB (P1-I5-T07b2): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
"""

from __future__ import annotations

from pydantic import ConfigDict, Field, field_validator
from sqlalchemy import text
from tl_core import confidentiality
from tl_core.ledger import Event, NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import NoChangesError, RecordNotFoundError
from tl_core.services.links import AddLink, handle_add_link
from tl_core.uow import UnitOfWork

from tl_mod_correspondence import catalog, registry
from tl_mod_correspondence.domains import DomainDefinition
from tl_mod_correspondence.errors import InvalidClockError, InvalidItemError
from tl_mod_correspondence.handlers.clocks import start_clock
from tl_mod_correspondence.handlers.common import (
    append,
    correlated,
    open_item,
    plausible_date,
    require_state,
    today,
    transition,
)
from tl_mod_correspondence.handlers.models import non_blank
from tl_mod_correspondence.limits import MAX_NUMBER, MAX_REASON, MAX_REFERENCES
from tl_mod_correspondence.names import (
    CORR_RECLASSIFIED,
    CORR_TRIAGED,
    CORR_UPDATED,
    CORRESPONDENCE,
    ST_DRAFT,
    ST_RECEIVED,
    ST_TRIAGED,
)
from tl_mod_correspondence.suggest import suggest

_RECORD_SQL = text("SELECT id, scope FROM cur_core_record WHERE id = :id")


class ConfirmTriage(Command):
    """Confirm the domain and subtype of a received item (an agent may propose it).

    ``referenced_ids`` are records the item refers to (the keys found in its text, confirmed by
    the person); each gets a ``references`` link from the item. ``response_required`` and
    ``response_due`` set what the subtype implies when you leave them out. ``start_clocks=false``
    skips the clocks the subtype starts on receipt (start them by hand later).
    """

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    domain: str = Field(min_length=1, max_length=MAX_NUMBER)
    subtype: str = Field(min_length=1, max_length=MAX_NUMBER)
    referenced_ids: list[str] = Field(default_factory=list, max_length=MAX_REFERENCES)
    response_required: bool | None = None
    response_due: str | None = Field(default=None, max_length=10)
    start_clocks: bool = True


class ReclassifyCorrespondence(Command):
    """Change the domain and subtype of a draft, received or triaged item. A reason is required."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    domain: str = Field(min_length=1, max_length=MAX_NUMBER)
    subtype: str = Field(min_length=1, max_length=MAX_NUMBER)
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return non_blank(value)


def _check_references(uow: UnitOfWork, cmd: Command, ids: list[str], own_id: str) -> list[str]:
    """The ids once each is a record of the scope the viewer may read (else ``RecordNotFoundError``,
    the same for an unknown, a foreign and a hidden record)."""
    # STEPS
    # 1. When `len(set(ids)) != len(ids)` raise `InvalidItemError("a record can be referenced
    #    only once")`.
    # 2. For each `record_id` in `ids`: `row = uow.conn().execute(_RECORD_SQL, {"id":
    #    record_id}).first()`. When `row is None`, or `row.scope != cmd.scope`, or
    #    `confidentiality.is_hidden(uow.conn(), record_id)`, raise `RecordNotFoundError(f"no
    #    record {record_id!r}")` (the same text for all three: a hidden record must look like a
    #    missing one). Then, when `record_id == own_id`, raise `InvalidItemError("an item cannot
    #    refer to itself")`.
    # 3. Return `list(ids)`.
    raise NotImplementedError


def _clause_id(
    uow: UnitOfWork, cmd: Command, definition: DomainDefinition, ref: str | None
) -> str | None:
    if ref is None:
        return None
    contract, _, number = ref.partition("/")
    found = registry.find_clause(uow.conn(), cmd.scope, contract, number)
    if found is None or not found.is_active:
        raise InvalidClockError(
            f"domain {definition.code} names clause {ref}, which is not an active clause of "
            f"{cmd.scope}"
        )
    return found.id


def start_template_clocks(
    uow: UnitOfWork,
    cmd: Command,
    item: registry.ItemRow,
    definition: DomainDefinition,
    subtype: str,
    trigger: str,
    start_on: str,
) -> tuple[list[str], list[Event]]:
    """Start the clocks of ``subtype`` whose trigger is ``trigger``; return their ids and events."""
    chosen = definition.subtype(subtype)
    assert chosen is not None  # check_subtype ran
    ids: list[str] = []
    events: list[Event] = []
    for template in chosen.clocks:
        if template.trigger != trigger:
            continue
        made = start_clock(
            uow,
            cmd,
            item=item,
            label=template.label,
            kind=template.kind,
            duration_days=template.duration_days,
            day_type=template.day_type,
            warn_days=template.warn_days,
            start_on=start_on,
            trigger=trigger,
            clause_id=_clause_id(uow, cmd, definition, template.clause),
        )
        ids.append(made.stream_id)
        events.extend(made.events)
    return ids, events


def handle_confirm_triage(uow: UnitOfWork, cmd: ConfirmTriage) -> CommandResult:
    """Record the triage: clocks, ``Correspondence.Triaged``, links, the move to Triaged.

    Raises ``RecordNotFoundError`` (the item or a referenced record is unknown, foreign or hidden),
    ``ItemStateError`` (the item is not Received), ``UnknownDomainError`` (no such domain or
    subtype), ``InvalidItemError`` and ``InvalidClockError`` (a clause the domain names is not
    registered). The suggestion the engine makes for the item is kept in the event when it
    differs from the confirmed domain.
    """
    # STEPS
    # 1. `cmd = correlated(cmd)`; `item = open_item(uow, cmd, cmd.stream_id)` (never read the
    #    item any other way: it answers `RecordNotFoundError` for an unknown, foreign or hidden
    #    item); `require_state(item, ST_RECEIVED)`.
    # 2. `definition = catalog.check_subtype(cmd.scope, cmd.domain, cmd.subtype)`; `references =
    #    _check_references(uow, cmd, cmd.referenced_ids, item.id)`; `due =
    #    plausible_date(cmd.response_due, "response_due")` (a `ValueError` becomes
    #    `InvalidItemError(str(exc))`); `chosen = definition.subtype(cmd.subtype)` (assert it is
    #    not None).
    # 3. `proposed = suggest(catalog.domain_set().for_scope(cmd.scope), subject=item.subject,
    #    body=item.body)`.
    # 4. `clock_ids`, `clock_events` start empty. When `cmd.start_clocks`: `clock_ids,
    #    clock_events = start_template_clocks(uow, cmd, item, definition, cmd.subtype,
    #    "receipt", item.received_on or today())` (it creates the clock records and returns
    #    their ids and events).
    # 5. `required = chosen.response_required if cmd.response_required is None else
    #    cmd.response_required`.
    # 6. `events = [NewEvent(event_type=CORR_TRIAGED, payload={"domain": cmd.domain, "subtype":
    #    cmd.subtype, "referenced_ids": references, "clock_ids": clock_ids, "triaged_on":
    #    today(), "suggestion": proposed.domain if proposed.domain != cmd.domain else None})]`.
    # 7. `changes = {}`: when `required != item.response_required` set
    #    `changes["response_required"] = [item.response_required, required]`; when `due is not
    #    None and due != item.response_due` set `changes["response_due"] = [item.response_due,
    #    due]`. When `changes` is not empty append `NewEvent(event_type=CORR_UPDATED,
    #    payload={"changes": changes, "reason": "triage"})`.
    # 8. `done = append(uow, cmd, item.id, CORRESPONDENCE, events, expected=cmd.expected_version
    #    or item.version)`.
    # 9. For each `target` in `references`: `linked = handle_add_link(uow,
    #    AddLink(actor=cmd.actor, source=cmd.source, scope=cmd.scope,
    #    correlation_id=cmd.correlation_id, causation_id=cmd.causation_id, from_id=item.id,
    #    to_id=target, relation="references", link_source="rule", note="confirmed at triage"),
    #    by_module=True)`; collect `linked.events`.
    # 10. `moved = transition(uow, cmd, item.id, "triage")`. Return
    #    `CommandResult(stream_id=item.id, key=item.number, version=moved.version,
    #    events=[*clock_events, *done.events, *link_events, *moved.events])`.
    raise NotImplementedError


def handle_reclassify_correspondence(
    uow: UnitOfWork, cmd: ReclassifyCorrespondence
) -> CommandResult:
    """Append ``Correspondence.Reclassified`` with the old and new domain and subtype.

    Raises ``RecordNotFoundError``, ``ItemStateError`` (not a Draft, Received or Triaged item),
    ``UnknownDomainError`` and ``NoChangesError`` (already that domain and subtype).
    """
    # STEPS
    # 1. `cmd = correlated(cmd)`; `item = open_item(uow, cmd, cmd.stream_id)`;
    #    `require_state(item, ST_DRAFT, ST_RECEIVED, ST_TRIAGED)`.
    # 2. `catalog.check_subtype(cmd.scope, cmd.domain, cmd.subtype)`. When `(item.domain,
    #    item.subtype) == (cmd.domain, cmd.subtype)` raise `NoChangesError(f"item {item.number}
    #    is already {cmd.domain}/{cmd.subtype}")`.
    # 3. `done = append(uow, cmd, item.id, CORRESPONDENCE,
    #    [NewEvent(event_type=CORR_RECLASSIFIED, payload={"from_domain": item.domain,
    #    "from_subtype": item.subtype, "domain": cmd.domain, "subtype": cmd.subtype, "reason":
    #    cmd.reason})], expected=cmd.expected_version or item.version)`; return
    #    `CommandResult(stream_id=item.id, key=item.number, version=done.new_version,
    #    events=list(done.events))`.
    raise NotImplementedError
```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/common.py` (read-only; names and signatures):
```python
def require_project(cmd: Command) -> None:
    """"""
    ...
def correlated[C: Command](cmd: C) -> C:
    """``cmd`` with a correlation id, so every event of the command carries the same one."""
    ...
def now() -> datetime:
    """The current instant: the one place this module reads the clock (tests freeze it)."""
    ...
def today() -> str:
    """Today's date, ISO, from ``now``."""
    ...
def today_date() -> date:
    """"""
    ...
def check_date(value: str | None, what: str) -> str | None:
    """``value`` when it is an ISO calendar date (or ``None``); otherwise a ``ValueError``."""
    ...
def plausible_date(value: str | None, what: str) -> str | None:
    """``check_date``, and the day is at most a year ahead and 50 years back of today."""
    ...
def resolve_date(value: str | None, reason: str | None, what: str) -> tuple[str, str | None]:
    """``(date, reason)`` for an act's date: today by default, never in the future."""
    ...
def version_of(uow: UnitOfWork, record_id: str) -> int:
    """The stream version of a record now (the envelope row follows every module event)."""
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
def load_item(uow: UnitOfWork, cmd: Command, item_id: str) -> registry.ItemRow:
    """The item, in the command's scope and readable by the viewer."""
    ...
def open_item(uow: UnitOfWork, cmd: Command, item_id: str) -> registry.ItemRow:
    """Like ``load_item``, and the item must still take changes (not void, closed or replaced)."""
    ...
def require_state(item: registry.ItemRow, *states: str) -> None:
    """Raise ``ItemStateError`` unless the item is in one of ``states``."""
    ...
def changes_of(old: dict[str, Any], new: dict[str, Any]) -> dict[str, list[Any]]:
    """``{field: [old, new]}`` for each field of ``new`` that differs."""
    ...
```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/clocks.py` (read-only; names and signatures):
```python
def start_clock(
    uow: UnitOfWork,
    cmd: Command,
    *,
    item: registry.ItemRow,
    label: str,
    kind: str,
    duration_days: int,
    day_type: str,
    warn_days: Sequence[int],
    start_on: str,
    trigger: str,
    owner: str | None = None,
    clause_id: str | None = None,
    calendar_ref: str | None = None,
) -> CommandResult:
    """Create a clock record for ``item``: ``Record.Created`` then ``ResponseClock.Started``."""
    ...
```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/suggest.py` (read-only; names and signatures):
```python
def suggest(
    domains: Sequence[DomainDefinition], *, subject: str, body: str | None = None
) -> Suggestion:
    """The best domain and subtype for the text, or an empty suggestion when there are no domains."""
    ...
```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/catalog.py` (read-only; names and signatures):
```python
def _signature() -> str:
    """A hash of every file a domain check reads: the schema directory, its name and contents."""
    ...
def domain_set() -> DomainSet:
    """The checked domain definitions in force. Raises ``UnknownDomainError`` on a bad file."""
    ...
def use_domains(domains: DomainSet) -> Generator[None]:
    """Install ``domains`` for the duration of the block (tests and embedders)."""
    ...
def find_domain(scope: str, code: str) -> DomainDefinition:
    """The definition that governs ``code`` in ``scope``. Raises ``UnknownDomainError``."""
    ...
def check_subtype(scope: str, domain: str, subtype: str) -> DomainDefinition:
    """The definition, once ``subtype`` is known to belong to ``domain``."""
    ...
def default_calendar_ref(scope: str) -> str:
    """``<project>-default@<highest version>`` for a project scope, else the company's."""
    ...
def calendar_for(ref: str, scope: str | None = None) -> Calendar:
    """The calendar ``ref``. Raises ``CalendarUnavailableError`` (unknown, unreadable, or one of"""
    ...
def due_for(calendar: Calendar, start_on: date, days: int, day_type: str) -> date:
    """The due date; a count that leaves the calendar's range is ``CalendarUnavailableError``."""
    ...
```

## Context (read these, nothing else)
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/common.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/registry.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/errors.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/names.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/testing.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/clocks.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/suggest.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/catalog.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/domains.py`
- `docs/tickets/P1-I5/provided/t07b2-test_triage.py.txt`
- `docs/templates/haiku-report.md`
may explore: (none)

## Allowed paths
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/triage.py`
- `packages/tl-modules/correspondence/tests/test_triage.py (create: the provided test, byte for byte)`
- `docs/reports/P1-I5/P1-I5-T07b2.md` (create: your report; commit it)

## Steps
1. Copy the provided test: `cp docs/tickets/P1-I5/provided/t07b2-test_triage.py.txt packages/tl-modules/correspondence/tests/test_triage.py`. Do not edit the copy.
2. Implement the three functions by their STEPS comments.
3. Delete the `STUB` paragraph of the module docstring, every `# STEPS` comment and the `# ruff: noqa` line at the top of each stub file you completed.
4. Run the acceptance commands, write the report, commit with `P1-I5-T07b2: <imperative summary>`.

## Acceptance
```
just check
uv run pytest packages/tl-modules/correspondence/tests/test_triage.py -q
TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test TL_REQUIRE_POSTGRES=1 uv run pytest packages/tl-modules/correspondence/tests/test_triage.py -q --adapters sqlite,postgres
```
Expected: `just check` clean; 13 passed on SQLite; 26 passed with both adapters (every case runs once per adapter).

## Tests to add
- `packages/tl-modules/correspondence/tests/test_triage.py` is provided; it is the whole test of this ticket. Add no other test file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), saved to `docs/reports/P1-I5/P1-I5-T07b2.md` and committed. State the SQLite count and the both-adapters count you got, and say whether the `STUB` paragraph, the STEPS comments and the `ruff: noqa` line are gone.

## Escalation triggers
- A STEPS line contradicts the docstring of its function or the provided test.
- The provided test cannot pass without editing it, a file outside *Allowed paths*, or a pasted interface.
- Two attempts at the same failing test have not passed it.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
