"""The re-pin dialog: show what changed between two revisions, then move the link on a yes.

Opened from the document register (``r``) for a stale link. It reads the module's diff between the
revision the link is pinned to and the document's current one, shows it, and only on a yes sends
``RepinDocumentLink`` (brief 7.3: the person sees what changed before confirming). Enter or ``y``
confirms; Esc or ``n`` leaves the link as it is. A refusal stays on screen and the dialog stays
open. The dialog decides nothing: the diff is the module's words and the move is the module's
command (any signed-in person may re-pin; ADR-0011).
"""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static
from tl_mod_documents.resolver import RepinDocumentLink
from tl_mod_documents.views import DocumentLinkView, RevisionDiffView

from tl_tui.client import ClientInterface
from tl_tui.document_text import repin_lines
from tl_tui.errors import CLIENT_ERRORS, describe_error


class RepinScreen(ModalScreen[bool]):
    """Dismisses with ``True`` when the link was moved, ``False`` when it was left alone."""

    KEY_HINTS: ClassVar[str] = "Enter or y re-pin  Esc or n leave it"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("enter", "confirm", "Re-pin", show=False),
        Binding("y", "confirm", "Re-pin", show=False),
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("n", "cancel", "Cancel", show=False),
    ]

    DEFAULT_CSS = """
    RepinScreen { align: center middle; }
    RepinScreen > Vertical {
        width: 90%;
        height: auto;
        max-height: 90%;
        border: round $accent;
        background: $surface;
        padding: 1 2;
    }
    RepinScreen #repin-title { text-style: bold; }
    RepinScreen #repin-status { color: $error; height: auto; }
    RepinScreen #repin-hints { color: $text-muted; }
    """

    def __init__(
        self,
        client: ClientInterface,
        project: str,
        number: str,
        link: DocumentLinkView,
        actor: str,
    ) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.number = number
        self.link = link
        self.actor = actor
        self.diff: RevisionDiffView | None = None
        self.target: str | None = None  # the revision the link would move to

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Re-pin a stale link", markup=False, id="repin-title")
            yield Static("", markup=False, id="repin-body")
            yield Static("", markup=False, id="repin-status")
            yield Static(self.KEY_HINTS, markup=False, id="repin-hints")

    def on_mount(self) -> None:
        """Read the diff the link would move through and show it."""
        # STEPS
        # 1. link = self.link. If link.pin is None, or link.current_code is None, or the two are
        #    the same code, show the reason in #repin-body ("This link floats; nothing to
        #    re-pin.", "<number> has no issued revision to move to." or "The link already points
        #    to <code>.") and return. self.target stays None.
        # 2. Otherwise self.target = link.current_code, and try self.diff =
        #    self.client.document_diff(self.project, self.number, link.pin, self.target).
        #    On CLIENT_ERRORS show describe_error(exc) in #repin-status, set self.target = None
        #    and return.
        # 3. Show "\n".join(repin_lines(link, diff)) in #repin-body.
        link = self.link
        body = self.query_one("#repin-body", Static)
        if link.pin is None:
            body.update("This link floats; nothing to re-pin.")
            return
        if link.current_code is None:
            body.update(f"{self.number} has no issued revision to move to.")
            return
        if link.pin == link.current_code:
            body.update(f"The link already points to {link.pin}.")
            return
        self.target = link.current_code
        try:
            self.diff = self.client.document_diff(self.project, self.number, link.pin, self.target)
        except CLIENT_ERRORS as exc:
            self.target = None
            self.query_one("#repin-status", Static).update(describe_error(exc))
            return
        body.update("\n".join(repin_lines(link, self.diff)))

    def action_confirm(self) -> None:
        """Move the link to the current revision, or say why it cannot be moved."""
        # STEPS
        # 1. With self.target None there is nothing to confirm: set #repin-status to "Nothing to
        #    re-pin." and return.
        # 2. Send self.client.repin_document_link(RepinDocumentLink(actor=self.actor,
        #    source="tui", scope=f"project:{self.project}", link_id=self.link.link_id,
        #    pin=self.target)). On CLIENT_ERRORS show describe_error(exc) in #repin-status and
        #    stay open.
        # 3. Otherwise self.dismiss(True).
        if self.target is None:
            self.query_one("#repin-status", Static).update("Nothing to re-pin.")
            return
        try:
            self.client.repin_document_link(
                RepinDocumentLink(
                    actor=self.actor,
                    source="tui",
                    scope=f"project:{self.project}",
                    link_id=self.link.link_id,
                    pin=self.target,
                )
            )
        except CLIENT_ERRORS as exc:
            self.query_one("#repin-status", Static).update(describe_error(exc))
            return
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)
