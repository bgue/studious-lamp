"""The document register: a project's controlled documents, their revisions and links (P1-I2).

A full-size log opened with ``F7``, on the shared ``LogScreen`` (P1-UX2): breadcrumb, the table of
the project's documents by number, the panel of the highlighted document (its revisions and links,
and under them the files of its current revision with a page-1 picture), the actions bar and the
keys row. The bar is what the server offers the signed-in person on this document and its
revisions (``allowed_actions``); each action runs a command of the documents module through
``document_command`` and a refusal lands in the status line. ``v`` opens the current revision's
file in the system viewer. ``r`` re-pins the first stale link (after showing what changed) and
``t`` drafts a transmittal. The filter keys narrow the list on the screen (state, type, text);
``a`` asks the client for the void documents too.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import ClassVar

from textual.binding import Binding, BindingType
from textual.widgets import Input
from tl_core.actions import ActionOffer
from tl_core.services.commands import Command
from tl_mod_documents.handlers.documents import SupersedeDocument, VoidDocument
from tl_mod_documents.handlers.revisions import IssueRevision, SupersedeRevision
from tl_mod_documents.views import DocumentView, RevisionView

from tl_tui.client import ClientInterface
from tl_tui.display import Labels, mode_of
from tl_tui.document_text import (
    COLUMNS,
    detail_lines,
    next_choice,
    row_cells,
    stale_links,
    summary_line,
)
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.labels_load import load_labels
from tl_tui.widgets.action_form import ActionFormScreen, FormField
from tl_tui.widgets.file_panel import FilePanel
from tl_tui.widgets.log_screen import LogAction, LogScreen
from tl_tui.widgets.record_screen import open_record
from tl_tui.widgets.repin_dialog import RepinScreen
from tl_tui.widgets.transmittal_composer import TransmittalComposerScreen

MAX_DOCUMENTS = 5000
NEEDS_NEWER = "Nothing to replace it with: no other issued revision."
NEEDS_DOCUMENT = "Nothing to replace it with: no other document has an issued revision."


class DocumentRegisterScreen(LogScreen[DocumentView]):
    """The documents of ``project`` (the id, not the scope)."""

    LOG_NAME = "Documents"
    KEY_HINTS: ClassVar[str] = (
        "s state  y type  a void too  / filter  Enter open record  F5 reload  Esc close"
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("s", "state_filter", "State", show=False),
        Binding("y", "type_filter", "Type", show=False),
        Binding("a", "void", "Void too", show=False),
    ]

    DEFAULT_CSS = """
    DocumentRegisterScreen FilePanel { margin-top: 1; }
    """

    def __init__(
        self, client: ClientInterface, project: str, actor: str, *, is_controller: bool = False
    ) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.actor = actor
        self.is_controller = is_controller  # an admin or a document controller (ADR-0013)
        self.state: str | None = None
        self.doc_type: str | None = None
        self.include_void = False
        self.views: list[DocumentView] = []  # as listed, before the screen's own filters
        self.detail: DocumentView | None = None  # the highlighted document, in full
        self._labels: Labels | None = None  # the code and type labels, loaded on first use
        self._full: dict[str, DocumentView] = {}  # number -> the document in full, per read
        self._reread = True  # False: the next load reuses ``self.views`` (a filter changed)
        self._files_for: str | None = None  # the record whose files the panel shows
        self.files: FilePanel | None = None
        self._note = ""  # said once, with the next summary (a reload would otherwise wipe it)

    @property
    def labels(self) -> Labels:
        """The code and type labels; read on first use."""
        if self._labels is None:
            self._labels = load_labels(
                self.client, f"project:{self.project}", ("documents.Document",)
            )
        return self._labels

    # --- LogScreen hooks ------------------------------------------------------------------

    def log_project(self) -> str:
        return self.project

    def columns(self) -> Sequence[str]:
        return COLUMNS

    def load_rows(self) -> Sequence[DocumentView]:
        if self._reread:
            self.views = self.client.list_documents(
                self.project, include_void=self.include_void, limit=MAX_DOCUMENTS
            )
            self._full = {}
        self._reread = True
        return [
            v
            for v in self.views
            if (self.state is None or v.state == self.state)
            and (self.doc_type is None or v.doc_type == self.doc_type)
        ]

    def row_key(self, row: DocumentView) -> str:
        return row.number

    def row_cells(self, row: DocumentView) -> Sequence[str]:
        return row_cells(row, self.labels, technical=mode_of(self.app).technical)

    def row_record(self, row: DocumentView) -> tuple[str, str]:
        return (row.number, row.title)

    def tell(self, text: str, *, error: bool = False) -> None:
        """Say ``text`` now and again with the next summary (the reload that follows an action
        rewrites the status line)."""
        self._note = ("! " if error else "") + text
        self.say(text, error=error)

    def summary_text(self) -> str:
        note, self._note = self._note, ""
        line = self._summary()
        return f"{note}  {line}" if note else line

    def _summary(self) -> str:
        return summary_line(
            len(self.shown),
            len(self.views),
            state=self.state,
            doc_type=self.doc_type,
            include_void=self.include_void,
            text=self.filter_text,
            labels=self.labels,
        )

    def open_row(self, row: DocumentView) -> None:
        open_record(self, self.client, f"project:{self.project}", self.project, self.actor, row.id)

    def full(self, row: DocumentView) -> DocumentView:
        """The document with its revisions and links (one read per document and listing)."""
        found = self._full.get(row.number)
        if found is None:
            found = self.client.get_document(self.project, row.number)
            self._full[row.number] = found
        return found

    def panel_text(self, row: DocumentView | None) -> str:
        """The highlighted document with its revisions and links; the files go under it."""
        if row is None:
            self.detail = None  # nothing is highlighted, so nothing is described
            self._show_files(None)
            return "No document matches."
        try:
            full = self.full(row)
        except CLIENT_ERRORS as exc:
            full = row  # the listing's copy: no revisions
            self.say(describe_error(exc), error=True)
        self.detail = full
        self._show_files(full)
        technical = mode_of(self.app).technical
        return "\n".join(detail_lines(full, self.labels, technical=technical))

    # --- the files of the current revision -------------------------------------------------

    def on_mount(self) -> None:
        self.files = FilePanel(self.client, id="doc-files")
        self.query_one("#log-panel").mount(self.files)

    @staticmethod
    def file_revision(view: DocumentView) -> RevisionView | None:
        """The revision whose file is shown and opened: the current one, else the newest."""
        current = [r for r in view.revisions if r.is_current]
        if current:
            return current[0]
        return view.revisions[-1] if view.revisions else None

    def _show_files(self, view: DocumentView | None) -> None:
        if self.files is None:
            return
        revision = self.file_revision(view) if view is not None else None
        record = revision.id if revision is not None else None
        if record == self._files_for:
            return
        self._files_for = record
        pages = (
            {r.sha256: r.page_count for r in revision.renditions} if revision is not None else {}
        )
        self.files.show(record, pages)

    def on_file_panel_note(self, message: FilePanel.Note) -> None:
        message.stop()
        self.tell(message.text, error=message.error)

    def _open_file(self) -> None:
        if self.files is not None:
            self.files.action_open_file()

    # --- actions (off the UI thread) ---------------------------------------------------------

    def actions_for(self, row: DocumentView) -> Sequence[LogAction]:
        """What the viewer may do to ``row``: the server's offers on the document and on the
        revisions that can take one, as actions; plus the re-pin and the file when they apply."""
        full = self.full(row)
        offers: list[tuple[ActionOffer, RevisionView | None]] = [
            (offer, None) for offer in self.client.allowed_actions(full.id).actions
        ]
        for revision in self._revisions_asked(full):
            offers += [(o, revision) for o in self.client.allowed_actions(revision.id).actions]
        made: list[LogAction] = []
        seen: set[str] = set()
        for offer, revision in offers:
            builder = self._builders().get(offer.command)
            if builder is None or offer.command in seen:
                continue  # a command this log has no form for, or one already offered
            seen.add(offer.command)
            made.append(builder(offer, full, revision))
        if stale_links(full):
            made.append(LogAction("r", "Re-pin", self._repin))
        revision = self.file_revision(full)
        if revision is not None and self.client.list_record_files(revision.id):
            made.append(LogAction("v", "Open file", self._open_file))
        return made

    @staticmethod
    def _revisions_asked(view: DocumentView) -> list[RevisionView]:
        """The revisions worth asking about: the newest draft and the current one."""
        asked: list[RevisionView] = []
        drafts = [r for r in view.revisions if r.state == "Draft"]
        if drafts:
            asked.append(drafts[-1])
        current = DocumentRegisterScreen.file_revision(view)
        if current is not None and current not in asked:
            asked.append(current)
        return asked

    Builder = Callable[[ActionOffer, DocumentView, RevisionView | None], LogAction]

    def _builders(self) -> dict[str, Builder]:
        return {
            "IssueRevision": self._issue_revision,
            "SupersedeRevision": self._supersede_revision,
            "SupersedeDocument": self._supersede_document,
            "VoidDocument": self._void_document,
            "CreateTransmittal": self._transmittal,
        }

    def _send(self, name: str, make: Callable[[], Command]) -> None:
        """Run a documents command (the person's, so the server checks the access)."""
        self.client.document_command(name, make())

    def _ask(
        self,
        title: str,
        fields: Sequence[FormField],
        name: str,
        make: Callable[[dict[str, str]], Command],
    ) -> None:
        """Open the form; when it is sent, run the command built from its answers."""

        def sent(answers: dict[str, str] | None) -> None:
            if answers is not None:
                self.attempt(lambda: self._send(name, lambda: make(answers)))

        self.app.push_screen(ActionFormScreen(title, fields), sent)

    @property
    def _scope(self) -> str:
        return f"project:{self.project}"

    def _issue_revision(
        self, offer: ActionOffer, doc: DocumentView, rev: RevisionView | None
    ) -> LogAction:
        def run() -> None:
            assert rev is not None
            revision_id = rev.id
            self._ask(
                f"{offer.label} revision {rev.code} of {doc.number}",
                [FormField("status", "Issue status (for example IFR, IFC)")],
                offer.command,
                lambda a: IssueRevision(
                    actor=self.actor,
                    source="tui",
                    scope=self._scope,
                    stream_id=revision_id,
                    issue_status=a["status"],
                ),
            )

        return LogAction("i", offer.label, run)

    def _supersede_revision(
        self, offer: ActionOffer, doc: DocumentView, rev: RevisionView | None
    ) -> LogAction:
        def run() -> None:
            assert rev is not None
            revision_id = rev.id
            newer = {
                f"{r.code} {r.issue_status or ''}".strip(): r.id
                for r in doc.revisions
                if r.id != rev.id and r.state == "Issued"
            }
            if not newer:
                self.tell(NEEDS_NEWER, error=True)
                return
            self._ask(
                f"{offer.label} revision {rev.code} of {doc.number}",
                [
                    FormField("by", "Replaced by", "choice", tuple(newer)),
                    FormField("reason", "Reason"),
                ],
                offer.command,
                lambda a: SupersedeRevision(
                    actor=self.actor,
                    source="tui",
                    scope=self._scope,
                    stream_id=revision_id,
                    superseded_by_id=newer[a["by"]],
                    reason=a["reason"],
                ),
            )

        return LogAction("u", f"{offer.label} revision", run)

    def _supersede_document(
        self, offer: ActionOffer, doc: DocumentView, rev: RevisionView | None
    ) -> LogAction:
        def run() -> None:
            others = {
                v.number: v.id
                for v in self.views
                if v.id != doc.id and v.current_revision_code is not None and v.state != "Void"
            }
            if not others:
                self.tell(NEEDS_DOCUMENT, error=True)
                return
            self._ask(
                f"{offer.label} {doc.number}",
                [
                    FormField("by", "Replaced by", "choice", tuple(others)),
                    FormField("reason", "Reason"),
                ],
                offer.command,
                lambda a: SupersedeDocument(
                    actor=self.actor,
                    source="tui",
                    scope=self._scope,
                    stream_id=doc.id,
                    expected_version=doc.version,
                    superseded_by_id=others[a["by"]],
                    reason=a["reason"],
                ),
            )

        return LogAction("x", f"{offer.label} document", run)

    def _void_document(
        self, offer: ActionOffer, doc: DocumentView, rev: RevisionView | None
    ) -> LogAction:
        def run() -> None:
            self._ask(
                f"{offer.label} {doc.number}",
                [FormField("reason", "Reason")],
                offer.command,
                lambda a: VoidDocument(
                    actor=self.actor,
                    source="tui",
                    scope=self._scope,
                    stream_id=doc.id,
                    expected_version=doc.version,
                    reason=a["reason"],
                ),
            )

        return LogAction("d", f"{offer.label} document", run)

    def _transmittal(
        self, offer: ActionOffer, doc: DocumentView, rev: RevisionView | None
    ) -> LogAction:
        def run() -> None:
            composer = TransmittalComposerScreen(
                self.client,
                self.project,
                self.actor,
                document=doc.number,
                is_controller=self.is_controller,
            )

            def closed(made: str | None) -> None:
                self._drafted(made, composer)

            self.app.push_screen(composer, closed)

        return LogAction("t", offer.label, run)

    def _drafted(self, number: str | None, composer: TransmittalComposerScreen) -> None:
        """The composer closed: say which transmittal was drafted, and whether it was issued."""
        if not number:
            return
        if composer.issued:
            self.say(f"Drafted and issued transmittal {number}.")
        elif composer.issue_error:
            self.say(f"Drafted transmittal {number}; issuing it failed: {composer.issue_error}")
        else:
            self.say(f"Drafted transmittal {number}.")

    def _repin(self) -> None:
        """Re-pin the first stale link of the highlighted document, after showing the diff."""
        if self.detail is None:
            self.say("No document is highlighted.")
            return
        found = stale_links(self.detail)
        if not found:
            self.say(f"{self.detail.number} has no stale link to re-pin.")
            return
        self.app.push_screen(
            RepinScreen(self.client, self.project, self.detail.number, found[0], self.actor),
            self._repinned,
        )

    def _repinned(self, moved: bool | None) -> None:
        """The re-pin dialog closed: read again when a link was moved."""
        if moved:
            self._full = {}
            self.tell("Link re-pinned.")
            self.reload()

    # --- the screen's own filters ----------------------------------------------------------

    def _narrow(self) -> None:
        """Read the rows again from the listing already held (no new read)."""
        self._reread = False
        self.reload()

    def action_state_filter(self) -> None:
        """Show the next state: all, then each state that has a document in the list, then all."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.state = next_choice(self.state, [v.state for v in self.views])
        self._narrow()

    def action_type_filter(self) -> None:
        """Show the next document type: all, then each type in the list, then all."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.doc_type = next_choice(
            self.doc_type, [v.doc_type for v in self.views if v.doc_type is not None]
        )
        self._narrow()

    def action_void(self) -> None:
        """Include the void documents, or leave them out again (reads again)."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.include_void = not self.include_void
        self.reload()
