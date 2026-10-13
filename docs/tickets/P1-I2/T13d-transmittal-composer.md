# P1-I2-T13d — TUI: the transmittal composer

Status: ready
Tier: haiku
Labels: tui
Depends on: S17 on `p1/i2` (the choice and recipient text functions and the client write method, in the tree); no other ticket
Branch: `p1/i2-t13d-tui-transmittal-composer`

## Goal
A person drafts a transmittal: ticks the issued revisions to send, types a subject, a purpose, the recipients and an optional due date, and creates it as a draft. `packages/tl-tui/src/tl_tui/widgets/transmittal_composer.py` has the dialog's layout, bindings and `action_cancel` written; `on_mount` and `action_create` raise `NotImplementedError`. You implement them. One provided test file must pass.

## Brief references (pasted)
> **Brief 9 M1.** `Transmittal`: number, direction (outgoing/incoming), recipients, purpose (for review / for construction / for information), item revisions, issue date, due date, response; the response is recorded against the transmittal.
>
> **ADR-0011.** Preparing a transmittal (creating the draft) is open to any signed-in person; issuing it, which freezes its items, is an admin's command and is not in this dialog.

### Specification
- The dialog is a modal (`ModalScreen[str | None]`): it dismisses with the new transmittal's number, or `None` when cancelled. `ctrl+s` creates; Esc cancels.
- `on_mount` offers the issued revisions of the project's documents (`ClientInterface.list_documents` then `get_document` for each document that has a current revision; text from `document_text.issued_choices`, final) in the selection list `#tc-revisions`, with the current revision of `self.document` ticked. A client failure is shown in `#tc-status`.
- `action_create` builds `CreateTransmittal` from the inputs (recipients from `document_text.parse_recipients`), sends it with `ClientInterface.create_transmittal`, and dismisses with the number the result returns. Validation errors and refusals (`CLIENT_ERRORS`) are shown in `#tc-status` with `describe_error`; the dialog stays open.
- The dialog decides nothing: the numbering, the purposes' meaning and the rules for items are the module's.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-tui/src/tl_tui/widgets/transmittal_composer.py` (the stub you complete):
```python
"""The transmittal composer: pick issued revisions, name the recipients, draft the transmittal.

Opened from the document register (``t``). It lists the issued revisions of the project's documents
(current ones and since replaced), with the highlighted document's current revision ticked, and a
few fields: subject, purpose, recipients (``Name:Organisation:email; Name2``) and an optional due
date. ``Ctrl+S`` drafts the transmittal with ``CreateTransmittal`` and closes with its number; Esc
cancels. A refusal stays on screen and the composer stays open. A draft is only a draft: issuing it
is an admin's command (ADR-0011) and has no key here. The composer decides nothing: which revisions
may be sent, the numbering and the dates are the module's rules.

STUB (P1-I2-T13d): the bodies of on_mount and action_create raise NotImplementedError; their
signatures, options, docstrings and the helpers are final. Each body has a STEPS comment.
Implement them, then delete this paragraph, the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, SelectionList, Static
from tl_mod_documents.handlers.transmittals import CreateTransmittal, Recipient

from tl_tui.client import ClientInterface
from tl_tui.document_text import issued_choices, parse_recipients
from tl_tui.errors import CLIENT_ERRORS, describe_error

MAX_DOCUMENTS = 200
PURPOSES = (
    "for_review",
    "for_information",
    "for_approval",
    "for_construction",
    "as_built",
    "for_record",
)


class TransmittalComposerScreen(ModalScreen[str | None]):
    """Dismisses with the new transmittal's number, or ``None`` when cancelled."""

    KEY_HINTS: ClassVar[str] = "Space tick a revision  Tab next field  Ctrl+S draft  Esc cancel"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+s", "create", "Draft", show=False),
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    DEFAULT_CSS = """
    TransmittalComposerScreen { align: center middle; }
    TransmittalComposerScreen > Vertical {
        width: 90%;
        height: 90%;
        border: round $accent;
        background: $surface;
        padding: 1 2;
    }
    TransmittalComposerScreen #tc-title { text-style: bold; height: 1; }
    TransmittalComposerScreen #tc-revisions { height: 1fr; min-height: 4; }
    TransmittalComposerScreen Input { height: 3; }
    TransmittalComposerScreen #tc-status { color: $error; height: auto; }
    TransmittalComposerScreen #tc-hints { color: $text-muted; height: 1; }
    """

    def __init__(
        self,
        client: ClientInterface,
        project: str,
        actor: str,
        *,
        document: str | None = None,
    ) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.actor = actor
        self.document = document  # the number whose current revision starts ticked
        self.choices: list[tuple[str, str]] = []  # (label, revision id) of what can be sent

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"New transmittal in {self.project}", markup=False, id="tc-title")
            yield SelectionList[str](id="tc-revisions")
            yield Input(placeholder="Subject", id="tc-subject")
            yield Input(value="for_construction", placeholder=" / ".join(PURPOSES), id="tc-purpose")
            yield Input(placeholder="Recipients: Name:Organisation:email; Name2", id="tc-to")
            yield Input(placeholder="Due date YYYY-MM-DD (optional)", id="tc-due")
            yield Static("", markup=False, id="tc-status")
            yield Static(self.KEY_HINTS, markup=False, id="tc-hints")

    def on_mount(self) -> None:
        """Offer the issued revisions of the project's documents."""
        # STEPS
        # 1. Try documents = self.client.list_documents(self.project, limit=MAX_DOCUMENTS). On
        #    CLIENT_ERRORS show describe_error(exc) in #tc-status and return.
        # 2. For each listed document whose state is "Issued" or "Superseded", read the full one
        #    with self.client.get_document(self.project, number) (on CLIENT_ERRORS show the error
        #    and skip it) and extend self.choices with issued_choices(full).
        # 3. Fill #tc-revisions: for each (label, revision id) of self.choices add an option
        #    (label, revision id, selected) where selected is True for the revision that is the
        #    current one of the document named self.document. Find that id from the full document:
        #    the revision with is_current and the code self.document's current_revision_code.
        # 4. Focus #tc-revisions.
        raise NotImplementedError

    def action_create(self) -> None:
        """Draft the transmittal with the ticked revisions."""
        # STEPS
        # 1. subject = the stripped text of #tc-subject; purpose = #tc-purpose stripped; due =
        #    #tc-due stripped or None; ids = list(self.query_one("#tc-revisions",
        #    SelectionList).selected); recipients = [Recipient(name=n, organisation=o, email=e)
        #    for n, o, e in parse_recipients(the text of #tc-to)].
        # 2. Build CreateTransmittal(actor=self.actor, source="tui",
        #    scope=f"project:{self.project}", subject=subject, purpose=purpose, due_date=due,
        #    recipients=recipients, revision_ids=ids) and send it with
        #    self.client.create_transmittal(cmd), both inside one `try`. On CLIENT_ERRORS show
        #    describe_error(exc) in #tc-status and stay open (an empty list of revisions or of
        #    recipients, a blank subject and a bad purpose or date are refused by the model and
        #    arrive as a ValidationError, which is in CLIENT_ERRORS).
        # 3. Otherwise self.dismiss(result.key).
        raise NotImplementedError

    def action_cancel(self) -> None:
        self.dismiss(None)
```

`packages/tl-tui/src/tl_tui/document_text.py` (excerpts; read-only, do not edit):
```python
def issued_choices(view: DocumentView) -> list[tuple[str, str]]:
    """``(label, revision id)`` for each issued revision of a document, newest first."""
    ...


def parse_recipients(text: str) -> list[tuple[str, str | None, str | None]]:
    """Recipients written ``Name:Org:email; Name2`` as ``(name, organisation, email)`` triples."""
    ...
```

`packages/tl-modules/documents/src/tl_mod_documents/handlers/transmittals.py` (excerpts; read-only, do not edit):
```python
class Recipient(BaseModel):
    """Who receives a transmittal."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=MAX_TEXT)
    organisation: str | None = Field(default=None, max_length=MAX_TEXT)
    email: str | None = Field(default=None, max_length=MAX_TEXT)


class CreateTransmittal(Command):
    """Draft a transmittal of issued revisions to named recipients.

    ``number`` is typed in; without it the project's numbering pattern for transmittals allocates
    one (``P123-TRN-0001``). A typed number must fit that pattern for this project. ``subject`` is
    the title.
    """

    model_config = ConfigDict(extra="forbid")

    number: str | None = Field(default=None, min_length=1, max_length=MAX_NUMBER)
    subject: str = Field(min_length=1, max_length=MAX_TEXT)
    direction: Direction = "outgoing"
    purpose: Purpose
    due_date: str | None = None
    recipients: list[Recipient] = Field(min_length=1, max_length=MAX_RECIPIENTS)
    revision_ids: list[str] = Field(min_length=1, max_length=MAX_ITEMS)
    notes: str | None = Field(default=None, max_length=MAX_DESCRIPTION)
```

`packages/tl-modules/documents/src/tl_mod_documents/views.py` (excerpts; read-only, do not edit):
```python
class RevisionView(BaseModel):
    id: str
    code: str
    state: str  # Draft | In Review | Issued | Superseded | Void
    issue_status: str | None
    status_class: str | None
    issued_on: str | None
    is_current: bool
    purpose: str | None
    change_note: str | None
    revision_date: str | None
    intended_status: str | None
    superseded_by: str | None  # the code of the revision that replaced it
    renditions: list[RenditionView] = []


class DocumentView(BaseModel):
    id: str
    number: str
    title: str
    description: str | None
    state: str
    doc_type: str | None
    discipline: str | None
    originator: str | None
    confidentiality: str | None = Field(description=CONFIDENTIALITY_NOTE)
    revision_scheme: str
    pattern_code: str | None
    current_revision_code: str | None
    current_revision_status: str | None
    current_revision_class: str | None
    current_revision_issued_on: str | None
    superseded_by: str | None  # the number of the document that replaced it
    conformance: str
    version: int
    revisions: list[RevisionView] = []
    links: list[DocumentLinkView] = []
```

`packages/tl-tui/src/tl_tui/client.py` (the document methods the dialog uses; read-only):
```python
def list_documents(self, project: str, *, doc_type: str | None = None, discipline: str | None = None, state: str | None = None, include_void: bool = False, limit: int = 1000) -> list[DocumentView]: ...
def get_document(self, project: str, number: str) -> DocumentView: ...
def create_transmittal(self, cmd: CreateTransmittal) -> CommandResult: ...
# CommandResult has .stream_id, .key (the transmittal number for a draft), .version, .events
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/widgets/transmittal_composer.py` (the file you edit)
- `packages/tl-tui/src/tl_tui/document_text.py` (final)
- `packages/tl-tui/src/tl_tui/errors.py` (`CLIENT_ERRORS`, `describe_error`)
- `packages/tl-tui/tests/fakes_documents.py` and `packages/tl-tui/tests/helpers.py` (already in the tree)
- `docs/tickets/P1-I2/provided/t13d-test_transmittal_composer.py.txt` (the test)
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing. pyright is `standard` for `packages/tl-modules`, `tl-cli`, `tl-api`; strict for `tl_core`, `tl_schema`, `tl_adapters`.
- Provided files live under `docs/tickets/P1-I2/provided/` as `.py.txt`; copy them into the tree byte for byte (the target names are in *Steps*). Do not edit the copies: they are already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I2/<ticket-id>.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. Remove the `STUB` paragraph from the module docstring, every `STEPS` comment and the `# ruff: noqa: F401` line when you implement a stub.
- The test counts below were counted from the provided files (`grep -c "^def test_"`); parametrized tests expand to more cases when run, and the pytest summary is the number of cases (L-P0-I8A-8). A test that does not use the `db`, `world` or `engine` fixtures runs once under `--adapters sqlite,postgres`; one that does runs once per adapter (L-P1-I1-6).
- Never name a module `types.py`, `enum.py` or `json.py` inside a package (L-P0-I5-B1).
- Never write a hand-made `cur_*`, `hist_*` or `v_*` object, and never change `schema/**` or anything under `generated/` unless this ticket says so.
- `just test-parity` takes about 70 minutes for the whole repository (L-P1-I1-10): run only the scoped commands in *Acceptance* (a ticket whose tests do not use the database fixtures has no Postgres command), never the whole parity suite.
- Start Postgres with `sudo pg_ctlcluster 16 main start` if it is not running; `TL_PG_URL` is `postgresql://postgres:postgres@localhost:5432/tl_test`.
- A cell of a table is a `rich.text.Text`, not a string: a title such as `[a, b]` is not markup (L-P1-I1-9 in spirit; the tag register does the same).
- The screen reads and writes only through `ClientInterface` (`self.client`); it never imports a service, a handler or the database. The tests use `FakeClient` (`tests/fakes.py`, with the document methods of `tests/fakes_documents.py`).
- Key presses are tested with `pilot.press`; a letter key does nothing while an `Input` has focus.
- `uv run pytest packages/tl-tui -q` is the package gate; the TUI tests run once (they do not use the database fixtures).

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/transmittal_composer.py` (edit)
- `packages/tl-tui/tests/test_transmittal_composer.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I2/P1-I2-T13d.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I2/provided/t13d-test_transmittal_composer.py.txt` to `packages/tl-tui/tests/test_transmittal_composer.py`.
3. Implement `on_mount` and `action_create` by their STEPS comments; remove the STUB paragraph, the STEPS comments and the `ruff: noqa` line.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-tui/tests/test_transmittal_composer.py -q
uv run pytest packages/tl-tui -q
```
Expected: `just check` clean; 7 test functions pass; the whole package passes.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`). There is no parity run for this ticket: its tests do not use the database fixtures, so Acceptance has no `--adapters` command.

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree.
- Stop if a test needs a change outside the Allowed paths.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
