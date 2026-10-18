# P1-I5-T07c — IssueCorrespondence: render, store, send (a stub), start the clocks

Status: ready
Tier: haiku
Labels: module, core
Depends on: — (the letter renderer, clocks, drafts and the test support are in the tree at the branch point)
Branch: `p1/i5-t07c-issue`

## Goal
`handlers/issue.py` has the command model and `_recipient_line`; `handle_issue_correspondence` raises `NotImplementedError`. You implement it by its STEPS comment. Issuing is a document controller's act: the draft letter is filled from its domain's template, rendered to a deterministic PDF, stored in the item's slot `rendition`, "sent" (**a stub: nothing leaves the machine**), its issue clocks are started and, when it answers a letter, that letter is recorded as answered. One provided test file must pass on SQLite and on Postgres.

## Brief references (pasted)
> **How a correspondence command is written (D6, D6b, ADR-0010, ADR-0016).** A handler is `handle_x(uow, cmd)`; it runs in an entered unit of work, appends through it and never commits. Every check is made before anything is appended. It reads an item **only** through `open_item`, `load_item` or `registry.get_item` (they apply the confidentiality filter: an item the person may not read answers the same `RecordNotFoundError` as one that does not exist); it never queries the item table itself and never inspects who the caller is: who may call a command is decided by the API (`commands.py`). The module moves its own items through the workflow with `transition(...)` (the generic `TransitionWorkflow` is not allowed on items). Time comes only from `today()` in `handlers/common.py`.
>
> **Command models and docstrings are the contract.** Do not change a model, a field, a docstring or a name in a file you complete; only the function bodies that carry a STEPS comment are yours.
>
> **Issue (brief 9, M10; D9).** Phase 1 has no SMTP. `Correspondence.Issued` carries `delivery = "stub"`; no network call, no outbox. The PDF is made by `letter.py` (no library) and stored through `files.write_rendition`, which uses the process's configured file service and the module-only slot `rendition`. The issue date is today unless the person gives an earlier one with a reason; never a later one.

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
`packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/issue.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401, F841
"""Issue a letter: render the PDF, store it, "send" it (a stub), start the clocks (brief 9 M10).

``IssueCorrespondence`` is the external act: a document controller (or admin) issues a Draft
outgoing letter. In one unit of work it:

1. fills the domain's letter template with the item's number, date, subject, recipients and text;
2. renders a deterministic PDF (``letter.py``, no library) and stores it in the slot ``rendition``;
3. starts the clocks the subtype defines for *issue* (a reply expected in 14 days, say);
4. appends ``Correspondence.Issued`` with ``delivery = "stub"``: **nothing is sent**. Phase 1 has
   no SMTP; the record says so, and a later increment replaces the stub;
5. moves the item to Issued; and, when the letter answers an item that is still waiting for an
   answer, records that answer (``mark_responded``).

STUB (P1-I5-T07c): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
"""

from __future__ import annotations

from pydantic import ConfigDict, Field
from tl_core.ledger import Event, NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.uow import UnitOfWork

from tl_mod_correspondence import catalog, files, registry
from tl_mod_correspondence.errors import InvalidItemError, ItemStateError, LetterRenderError
from tl_mod_correspondence.handlers.common import (
    append,
    correlated,
    open_item,
    require_state,
    resolve_date,
    transition,
)
from tl_mod_correspondence.handlers.responses import mark_responded
from tl_mod_correspondence.handlers.triage import start_template_clocks
from tl_mod_correspondence.letter import LetterError, LetterFields, compose_letter, render_pdf
from tl_mod_correspondence.limits import MAX_NUMBER, MAX_REASON
from tl_mod_correspondence.names import (
    CORR_ISSUED,
    CORRESPONDENCE,
    ST_DRAFT,
    ST_ISSUED,
    ST_RECEIVED,
    ST_TRIAGED,
)


class IssueCorrespondence(Command):
    """Issue a Draft letter (a document controller's act).

    ``template`` is a letter template of the item's domain (by default the first one for its
    subtype). ``issued_on`` is the date on the letter (today by default; an earlier day needs
    ``date_reason``; never later than today). The send is a stub: nothing leaves the machine.
    """

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    template: str | None = Field(default=None, max_length=MAX_NUMBER)
    issued_on: str | None = Field(default=None, max_length=10)
    date_reason: str | None = Field(default=None, max_length=MAX_REASON)


def _recipient_line(item: registry.ItemRow) -> str:
    names = [r.get("name") or r.get("email") or "" for r in item.to]
    return ", ".join(n for n in names if n)


def handle_issue_correspondence(uow: UnitOfWork, cmd: IssueCorrespondence) -> CommandResult:
    """Render, store, "send", start the issue clocks, append ``Correspondence.Issued``.

    Raises ``RecordNotFoundError`` (unknown, foreign or hidden), ``ItemStateError`` (not a Draft
    outgoing letter), ``InvalidItemError`` (no domain and subtype, or no recipient),
    ``UnknownDomainError``, ``LetterRenderError`` (no such template, a letter the renderer
    refuses, no file service) and the date errors of ``resolve_date``.
    """
    # STEPS
    # 1. `cmd = correlated(cmd)`; `item = open_item(uow, cmd, cmd.stream_id)`;
    #    `require_state(item, ST_DRAFT)`. When `item.direction != "out"` raise
    #    `ItemStateError(f"item {item.number} was received; only a letter we wrote is issued")`.
    # 2. When `item.domain is None or item.subtype is None` raise `InvalidItemError(f"item
    #    {item.number} has no domain and subtype; reclassify it before issue")`. `recipients =
    #    _recipient_line(item)`; when it is empty raise `InvalidItemError(f"item {item.number}
    #    has no recipient")`.
    # 3. `definition = catalog.check_subtype(cmd.scope, item.domain, item.subtype)`; `day,
    #    date_reason = resolve_date(cmd.issued_on, cmd.date_reason, "the issue day")`.
    # 4. Choose the template: `wanted = cmd.template`; `templates = [t for t in
    #    definition.templates if wanted is None or t.code == wanted]`; when `wanted is None`
    #    keep only those with `t.subtype == item.subtype`. When none is left raise
    #    `LetterRenderError("domain " + definition.code + " has no letter template " +
    #    (repr(wanted) if wanted else "for subtype " + item.subtype))`. `template =
    #    templates[0]`.
    # 5. Render: `lines = compose_letter(template.header, template.footer,
    #    LetterFields(number=item.number, date=day, subject=item.subject, to=recipients,
    #    body=item.body or ""))` and `pdf = render_pdf(lines, title=f"{item.number}
    #    {item.subject}")`, both inside a `try` whose `except LetterError as exc` raises
    #    `LetterRenderError(str(exc)) from exc`.
    # 6. Store: `stored = files.write_rendition(uow, actor=cmd.actor, source=cmd.source,
    #    scope=cmd.scope, record_id=item.id, filename=f"{item.number}.pdf", data=pdf,
    #    correlation_id=cmd.correlation_id or "")` (it raises `LetterRenderError` when the
    #    process has no file service).
    # 7. Clocks: `clock_ids, clock_events = start_template_clocks(uow, cmd, item, definition,
    #    item.subtype, "issue", day)`.
    # 8. `done = append(uow, cmd, item.id, CORRESPONDENCE, [NewEvent(event_type=CORR_ISSUED,
    #    payload={"issued_on": day, "date_reason": date_reason, "rendition_file_id":
    #    stored.file_id, "rendition_sha256": stored.sha256, "template": template.code,
    #    "delivery": "stub", "clock_ids": clock_ids})], expected=cmd.expected_version or
    #    item.version)`. Nothing is sent: `delivery` is always the word `stub`.
    # 9. `moved = transition(uow, cmd, item.id, "issue")`.
    # 10. `answered = []`. When `item.responds_to_id is not None`: `parent =
    #    registry.get_item(uow.conn(), item.responds_to_id)`; when the parent is not None and
    #    `parent.state in (ST_RECEIVED, ST_TRIAGED, ST_ISSUED)`: `result = mark_responded(uow,
    #    cmd, parent, response_id=item.id, day=day, reason="a reply was issued")` and `answered
    #    = list(result.events)`. A parent in any other state is left alone, without an error.
    # 11. Return `CommandResult(stream_id=item.id, key=item.number, version=moved.version,
    #    events=[*clock_events, *done.events, *moved.events, *answered])`.
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

`packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/triage.py` (read-only; names and signatures):
```python
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
    ...
```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/responses.py` (read-only; names and signatures):
```python
def mark_responded(
    uow: UnitOfWork,
    cmd: Command,
    item: registry.ItemRow,
    *,
    response_id: str,
    day: str,
    reason: str | None,
) -> CommandResult:
    """Move ``item`` to Responded and meet its answer clocks. The one place this is done."""
    ...
```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/files.py` (read-only; names and signatures):
```python
class StoredFile: ...  # see the file
def file_service() -> FileService:
    """The configured file service, or ``LetterRenderError``."""
    ...
def write_rendition(
    uow: UnitOfWork,
    *,
    actor: str,
    source: str,
    scope: str,
    record_id: str,
    filename: str,
    data: bytes,
    correlation_id: str,
) -> StoredFile:
    """Store ``data`` (a PDF) in the slot ``rendition`` of the item and return its file id."""
    ...
```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/letter.py` (read-only; names and signatures):
```python
def compose_letter(header: str | None, footer: str | None, fields: LetterFields) -> list[str]:
    """The lines of the letter: header, number and date, recipient, subject, body, footer."""
    ...
def render_pdf(lines: Sequence[str], title: str) -> bytes:
    """A PDF 1.4 file with ``lines`` in Helvetica 10 pt, ``LINES_PER_PAGE`` to a page."""
    ...
```

## Context (read these, nothing else)
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/common.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/registry.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/errors.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/names.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/testing.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/triage.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/responses.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/files.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/letter.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/domains.py`
- `docs/tickets/P1-I5/provided/t07c-test_issue.py.txt`
- `docs/templates/haiku-report.md`
may explore: (none)

## Allowed paths
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/issue.py`
- `packages/tl-modules/correspondence/tests/test_issue.py (create: the provided test, byte for byte)`
- `docs/reports/P1-I5/P1-I5-T07c.md` (create: your report; commit it)

## Steps
1. Copy the provided test: `cp docs/tickets/P1-I5/provided/t07c-test_issue.py.txt packages/tl-modules/correspondence/tests/test_issue.py`. Do not edit the copy.
2. Implement `handle_issue_correspondence` by its STEPS comment.
3. Delete the `STUB` paragraph of the module docstring, every `# STEPS` comment and the `# ruff: noqa` line at the top of each stub file you completed.
4. Run the acceptance commands, write the report, commit with `P1-I5-T07c: <imperative summary>`.

## Acceptance
```
just check
uv run pytest packages/tl-modules/correspondence/tests/test_issue.py -q
TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test TL_REQUIRE_POSTGRES=1 uv run pytest packages/tl-modules/correspondence/tests/test_issue.py -q --adapters sqlite,postgres
```
Expected: `just check` clean; 11 passed on SQLite; 22 passed with both adapters (every case runs once per adapter).

## Tests to add
- `packages/tl-modules/correspondence/tests/test_issue.py` is provided; it is the whole test of this ticket. Add no other test file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), saved to `docs/reports/P1-I5/P1-I5-T07c.md` and committed. State the SQLite count and the both-adapters count you got, and say whether the `STUB` paragraph, the STEPS comment and the `ruff: noqa` line are gone.

## Escalation triggers
- A STEPS line contradicts the docstring of its function or the provided test.
- The provided test cannot pass without editing it, a file outside *Allowed paths*, or a pasted interface.
- Two attempts at the same failing test have not passed it.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
