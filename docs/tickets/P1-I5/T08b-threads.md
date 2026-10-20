# P1-I5-T08b — Threading wiring: threads, AssignThread and SupersedeCorrespondence

Status: ready
Tier: haiku
Labels: module, core
Depends on: P1-I5-T07a (you add one call to the receive handler it writes)
Branch: `p1/i5-t08b-threads`

## Goal
`handlers/threads.py` has the two command models, `thread_facts_for`, `_open_thread` and `_join`; `find_match`, `assign_thread`, `with_thread`, `handle_assign_thread` and `handle_supersede_correspondence` raise `NotImplementedError`. You implement them by their STEPS comments, then wire `with_thread` into `handle_receive_correspondence` (`handlers/items.py`) and `handle_draft_correspondence` (`handlers/responses.py`) so every new item joins the thread it belongs to. The pure rules are `threading.match_thread` (merged); this ticket feeds them from the register and writes the result. One provided test file must pass on SQLite and on Postgres.

## Brief references (pasted)
> **How a correspondence command is written (D6, D6b, ADR-0010, ADR-0016).** A handler is `handle_x(uow, cmd)`; it runs in an entered unit of work, appends through it and never commits. Every check is made before anything is appended. It reads an item **only** through `open_item`, `load_item` or `registry.get_item` (they apply the confidentiality filter: an item the person may not read answers the same `RecordNotFoundError` as one that does not exist); it never queries the item table itself and never inspects who the caller is: who may call a command is decided by the API (`commands.py`). The module moves its own items through the workflow with `transition(...)` (the generic `TransitionWorkflow` is not allowed on items). Time comes only from `today()` in `handlers/common.py`.
>
> **Command models and docstrings are the contract.** Do not change a model, a field, a docstring or a name in a file you complete; only the function bodies that carry a STEPS comment are yours.
>
> **Threading (brief 9, M10).** Replies, follow-ups and superseding letters thread automatically from email headers, references in the subject or body and domain keys; an item that matches nothing opens a thread of its own. Only items and threads the person may read are candidates: a thread hangs on its governing item, so a hidden thread is never joined (ADR-0016). `CorrespondenceThread.Defined` already counts the first item: do not also add it with `ItemAdded`.

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
`packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/threads.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401, F841
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

STUB (P1-I5-T08b): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
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
    # STEPS
    # 1. `conn = uow.conn()`. When `item.responds_to_id is not None`: `answered =
    #    registry.get_item(conn, item.responds_to_id)` (it applies the viewer's
    #    confidentiality); when `answered is not None and answered.id != item.id` return
    #    `ThreadMatch(answered.thread_id, answered.id, "manual")` (a reply we drafted joins the
    #    thread of what it answers).
    # 2. `facts = thread_facts_for(item, references)`. `by_message_id = {}`: for each
    #    `message_id` in `[*facts.references, *([facts.in_reply_to] if facts.in_reply_to else
    #    [])]`: `found = registry.find_by_message_id(conn, item.scope, message_id)`; when `found
    #    is not None and found.id != item.id` set `by_message_id[message_id] =
    #    KnownItem(found.id, found.thread_id)`.
    # 3. `by_number = {}`: for each `number` in `facts.numbers`: `found =
    #    registry.find_item(conn, item.scope, number)`; same condition, `by_number[number] =
    #    KnownItem(found.id, found.thread_id)`.
    # 4. `subjects = {}`: for each `thread` in `registry.thread_candidates(conn, item.scope,
    #    facts.subject_key)`: `subjects.setdefault(thread.subject_key, thread.id)`.
    # 5. Return `match_thread(facts, by_message_id, by_number, subjects)` (it may be `None`).
    raise NotImplementedError


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
    # STEPS
    # 1. When `item.thread_id is not None` return `[]` (an item already in a thread is left
    #    alone).
    # 2. `match = find_match(uow, item, references)`.
    # 3. No match: `thread_id, events = _open_thread(uow, cmd, item)`; return `[*events,
    #    *_join(uow, cmd, thread_id, item, None, "manual", first=True)]`.
    # 4. `thread_id = match.thread_id`. When it is `None` the matched item has no thread yet:
    #    `earlier = registry.get_item(uow.conn(), match.responds_to_id or "")`. If `earlier` is
    #    None, do what the no-match step does. Otherwise open the thread for the earlier item:
    #    `thread_id, events = _open_thread(uow, cmd, earlier)` and `events += _join(uow, cmd,
    #    thread_id, earlier, None, match.matched_by, first=True)`.
    # 5. Finally return `[*events, *_join(uow, cmd, thread_id, item, match.responds_to_id,
    #    match.matched_by)]` (`events` is empty when the match already had a thread).
    raise NotImplementedError


def with_thread(uow: UnitOfWork, cmd: Command, made: CommandResult) -> CommandResult:
    """``made`` (a new item) once the item is in its thread: the events are added to the result."""
    # STEPS
    # 1. `item = registry.get_item(uow.conn(), made.stream_id)`. When it is `None` (the viewer
    #    cannot read what they just made) return `made` unchanged.
    # 2. `events = assign_thread(uow, cmd, item)`; `current = registry.get_item(uow.conn(),
    #    item.id)`.
    # 3. Return `CommandResult(stream_id=made.stream_id, key=made.key, version=current.version
    #    if current else made.version, events=[*made.events, *events])`.
    raise NotImplementedError


def handle_assign_thread(uow: UnitOfWork, cmd: AssignThread) -> CommandResult:
    """Join ``stream_id`` to a thread by hand (or open a new one).

    Raises ``RecordNotFoundError`` (item or answered item unknown, foreign or hidden),
    ``ThreadNotFoundError`` (no readable thread of that id in the scope), ``ItemStateError`` (the
    item is void) and ``NoChangesError`` (it is in that thread already).
    """
    # STEPS
    # 1. `cmd = correlated(cmd)`; `item = load_item(uow, cmd, cmd.stream_id)`. When `item.voided
    #    or item.state == "Void"` raise `ItemStateError(f"item {item.number} is void")`.
    # 2. When `cmd.responds_to_id is not None`: `answered = registry.get_item(uow.conn(),
    #    cmd.responds_to_id)`; when `answered is None or answered.scope != cmd.scope` raise
    #    `RecordNotFoundError(f"no record {cmd.responds_to_id!r}")`; when `answered.id ==
    #    item.id` raise `InvalidItemError("an item cannot answer itself")`.
    # 3. `events = []`. When `cmd.thread_id is None`: `thread_id, events = _open_thread(uow,
    #    cmd, item)`. Otherwise `thread = registry.get_thread(uow.conn(), cmd.thread_id)`; when
    #    `thread is None or thread.scope != cmd.scope` raise `ThreadNotFoundError(f"no thread
    #    {cmd.thread_id!r} in scope {cmd.scope!r}")`; when `item.thread_id == thread.id and
    #    cmd.responds_to_id in (None, item.responds_to_id)` raise `NoChangesError(f"item
    #    {item.number} is already in thread {thread.number}")`; `thread_id = thread.id`.
    # 4. `events += _join(uow, cmd, thread_id, item, cmd.responds_to_id, "manual",
    #    first=cmd.thread_id is None)`.
    # 5. `current = registry.get_item(uow.conn(), item.id)`; return
    #    `CommandResult(stream_id=item.id, key=item.number, version=current.version if current
    #    else item.version, events=events)`.
    raise NotImplementedError


def handle_supersede_correspondence(uow: UnitOfWork, cmd: SupersedeCorrespondence) -> CommandResult:
    """Append ``Correspondence.Superseded`` and a ``supersedes`` link from the new item.

    Raises ``RecordNotFoundError`` (either item unknown, foreign or hidden), ``ItemStateError``
    (the old item is closed, or the new one is void) and ``InvalidItemError`` (an item cannot
    replace itself).
    """
    # STEPS
    # 1. `cmd = correlated(cmd)`; `old = open_item(uow, cmd, cmd.stream_id)`; `new =
    #    load_item(uow, cmd, cmd.superseded_by_id)`.
    # 2. When `new.id == old.id` raise `InvalidItemError("an item cannot supersede itself")`.
    #    When `new.voided or new.state == "Void"` raise `ItemStateError(f"item {new.number} is
    #    void and cannot replace another")`.
    # 3. `done = append(uow, cmd, old.id, CORRESPONDENCE, [NewEvent(event_type=CORR_SUPERSEDED,
    #    payload={"superseded_by_id": new.id, "reason": cmd.reason})],
    #    expected=cmd.expected_version or old.version)`.
    # 4. `linked = handle_add_link(uow, AddLink(actor=cmd.actor, source=cmd.source,
    #    scope=cmd.scope, correlation_id=cmd.correlation_id, causation_id=cmd.causation_id,
    #    from_id=new.id, to_id=old.id, relation="supersedes", link_source="rule",
    #    note=cmd.reason), by_module=True)`.
    # 5. Return `CommandResult(stream_id=old.id, key=old.number, version=done.new_version,
    #    events=[*done.events, *linked.events])`.
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

`packages/tl-modules/correspondence/src/tl_mod_correspondence/registry.py` (read-only; names and signatures):
```python
def get_item(conn: Connection, item_id: str) -> ItemRow | None:
    """The item with this id, or ``None`` when there is none or the viewer may not read it."""
    ...
def find_item(conn: Connection, scope: str, number: str) -> ItemRow | None:
    """The item of this number in the scope, under the same rule as ``get_item``."""
    ...
def find_by_message_id(conn: Connection, scope: str, message_id: str) -> ItemRow | None:
    """The item with this normalised Message-ID (email ingest refuses a repeat)."""
    ...
def get_thread(conn: Connection, thread_id: str) -> ThreadRow | None:
    """"""
    ...
def thread_candidates(conn: Connection, scope: str, subject_key: str) -> list[ThreadRow]:
    """Open threads of a scope whose normalised subject is ``subject_key`` (readable ones)."""
    ...
```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/threading.py` (read-only; names and signatures):
```python
def normalise_subject(subject: str) -> str:
    """The subject as threading compares it: no reply or forward prefixes, one space, lower case."""
    ...
def normalise_message_id(value: str | None) -> str | None:
    """A Message-ID without angle brackets, or ``None`` when it is not a usable one."""
    ...
def find_item_numbers(text: str, project: str, type_codes: Sequence[str]) -> list[str]:
    """Item numbers written in ``text``: ``<project>-<TYPE>-<digits>`` for each type code."""
    ...
def match_thread(
    facts: ThreadFacts,
    by_message_id: Mapping[str, KnownItem],
    by_number: Mapping[str, KnownItem],
    open_threads_by_subject: Mapping[str, str],
) -> ThreadMatch | None:
    """Decide the thread of a new item, or ``None`` when nothing matches."""
    ...
```

## Context (read these, nothing else)
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/common.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/registry.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/errors.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/names.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/testing.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/threading.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/items.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/responses.py`
- `docs/tickets/P1-I5/provided/t08b-test_threads.py.txt`
- `docs/templates/haiku-report.md`
may explore: (none)

## Allowed paths
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/threads.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/items.py (only: import `with_thread`, call it on the result of `create_item` in `handle_receive_correspondence`)`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/responses.py (only: the same two changes in `handle_draft_correspondence`)`
- `packages/tl-modules/correspondence/tests/test_threads.py (create: the provided test, byte for byte)`
- `docs/reports/P1-I5/P1-I5-T08b.md` (create: your report; commit it)

## Steps
1. Copy the provided test: `cp docs/tickets/P1-I5/provided/t08b-test_threads.py.txt packages/tl-modules/correspondence/tests/test_threads.py`. Do not edit the copy.
2. Implement the five functions by their STEPS comments. Then wire the two handlers: `made = create_item(...)` followed by `return with_thread(uow, cmd, made)`, with `from tl_mod_correspondence.handlers.threads import with_thread` among the imports.
3. Delete the `STUB` paragraph of the module docstring, every `# STEPS` comment and the `# ruff: noqa` line at the top of each stub file you completed.
4. Run the acceptance commands, write the report, commit with `P1-I5-T08b: <imperative summary>`.

## Acceptance
```
just check
uv run pytest packages/tl-modules/correspondence/tests/test_threads.py -q
TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test TL_REQUIRE_POSTGRES=1 uv run pytest packages/tl-modules/correspondence/tests/test_threads.py -q --adapters sqlite,postgres
```
Expected: `just check` clean; 15 passed on SQLite; 30 passed with both adapters (every case runs once per adapter).

## Tests to add
- `packages/tl-modules/correspondence/tests/test_threads.py` is provided; it is the whole test of this ticket. Add no other test file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), saved to `docs/reports/P1-I5/P1-I5-T08b.md` and committed. State the SQLite count and the both-adapters count you got, and say whether the `STUB` paragraph, the STEPS comments and the `ruff: noqa` line are gone, and that `test_items.py` still passes.

## Escalation triggers
- A STEPS line contradicts the docstring of its function or the provided test.
- The provided test cannot pass without editing it, a file outside *Allowed paths*, or a pasted interface.
- Two attempts at the same failing test have not passed it.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
