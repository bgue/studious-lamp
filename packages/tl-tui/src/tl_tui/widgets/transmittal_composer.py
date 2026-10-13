"""The transmittal composer: pick issued revisions, name the recipients, draft the transmittal.

Opened from the document register (``t``). It lists the issued revisions of the project's documents
(current ones and since replaced), with the highlighted document's current revision ticked, and a
few fields: subject, purpose, recipients (``Name:Organisation:email; Name2``) and an optional due
date. ``Ctrl+S`` drafts the transmittal with ``CreateTransmittal`` and closes with its number; Esc
cancels. A refusal stays on screen and the composer stays open. A draft is only a draft: issuing it
is a controlling act (ADR-0013), so a document controller or an admin also gets ``Ctrl+T``, which
drafts and then issues it with ``IssueTransmittal``; for anyone else the key says what is missing
and the server would refuse the call anyway. The composer decides nothing: which revisions may be
sent, the numbering and the dates are the module's rules.
"""

from __future__ import annotations

from typing import ClassVar, cast

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, SelectionList, Static
from textual.widgets.selection_list import Selection
from tl_core.services.commands import CommandResult
from tl_mod_documents.handlers.transmittals import (
    CreateTransmittal,
    IssueTransmittal,
    Purpose,
    Recipient,
)

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
        Binding("ctrl+t", "issue", "Draft and issue", show=False),
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
        is_controller: bool = False,
    ) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.actor = actor
        self.document = document  # the number whose current revision starts ticked
        self.is_controller = is_controller  # a document controller or an admin (ADR-0013)
        self.issued = False  # set when the dismissed transmittal was also issued
        self.issue_error: str | None = None  # set when it was drafted but issuing was refused
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
            hints = self.KEY_HINTS
            if self.is_controller:
                hints = hints.replace("Ctrl+S draft", "Ctrl+S draft  Ctrl+T draft and issue")
            yield Static(hints, markup=False, id="tc-hints")

    def on_mount(self) -> None:
        """Offer the issued revisions of the project's documents."""
        status = self.query_one("#tc-status", Static)
        selection = self.query_one("#tc-revisions", SelectionList)
        try:
            documents = self.client.list_documents(self.project, limit=MAX_DOCUMENTS)
        except CLIENT_ERRORS as exc:
            status.update(describe_error(exc))
            return
        current_ids: set[str] = set()
        for listed in documents:
            if listed.state not in ("Issued", "Superseded"):
                continue
            try:
                full = self.client.get_document(self.project, listed.number)
            except CLIENT_ERRORS as exc:
                status.update(describe_error(exc))
                continue
            self.choices.extend(issued_choices(full))
            if full.number == self.document:
                current_ids = {
                    rev.id
                    for rev in full.revisions
                    if rev.is_current and rev.code == full.current_revision_code
                }
        selection.add_options(
            [Selection(label, rev_id, rev_id in current_ids) for label, rev_id in self.choices]
        )
        selection.focus()

    def _draft(self) -> CommandResult | None:
        """Draft the transmittal with the ticked revisions; ``None`` after a refusal (shown)."""
        subject = self.query_one("#tc-subject", Input).value.strip()
        purpose = self.query_one("#tc-purpose", Input).value.strip()
        due = self.query_one("#tc-due", Input).value.strip() or None
        ids = list(self.query_one("#tc-revisions", SelectionList).selected)
        status = self.query_one("#tc-status", Static)
        try:
            # Recipients are built inside the try too: an empty name (":Acme") is a refusal.
            recipients = [
                Recipient(name=name, organisation=org, email=email)
                for name, org, email in parse_recipients(self.query_one("#tc-to", Input).value)
            ]
            # The model checks the purpose at runtime (a refusal is a ValidationError); the cast
            # only tells the type checker that the typed field receives a string.
            cmd = CreateTransmittal(
                actor=self.actor,
                source="tui",
                scope=f"project:{self.project}",
                subject=subject,
                purpose=cast(Purpose, purpose),
                due_date=due,
                recipients=recipients,
                revision_ids=ids,
            )
            return self.client.create_transmittal(cmd)
        except CLIENT_ERRORS as exc:
            status.update(describe_error(exc))
            return None

    def action_create(self) -> None:
        """Draft the transmittal with the ticked revisions."""
        result = self._draft()
        if result is not None:
            self.dismiss(result.key)

    def action_issue(self) -> None:
        """Draft the transmittal and issue it (a controlling act: controllers and admins only)."""
        status = self.query_one("#tc-status", Static)
        if not self.is_controller:
            status.update("Issuing needs the document_controller or admin role. Ctrl+S drafts.")
            return
        result = self._draft()
        if result is None:
            return
        try:
            self.client.issue_transmittal(
                IssueTransmittal(
                    actor=self.actor,
                    source="tui",
                    scope=f"project:{self.project}",
                    stream_id=result.stream_id,
                )
            )
        except CLIENT_ERRORS as exc:
            self.issue_error = describe_error(exc)  # the draft exists; do not draft it twice
        else:
            self.issued = True
        self.dismiss(result.key)

    def action_cancel(self) -> None:
        self.dismiss(None)
