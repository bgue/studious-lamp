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
