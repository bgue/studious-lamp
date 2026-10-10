"""Edit form modal: one editor per writable field, saved through `save_record_edits` (P0-I2-T16b).

The form takes the record and its form metadata from the record view, collects the fields the
user changed, and hands them to `tl_tui.forms.save_record_edits`. Failures stay visible in the
form, and what the user typed is kept.
"""

from __future__ import annotations

from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static
from tl_core.ledger import ConcurrencyError
from tl_schema.forms import FieldMeta, FormMetadata

from tl_tui.client import ClientInterface
from tl_tui.errors import describe_error
from tl_tui.forms import save_record_edits
from tl_tui.paths import pset_value
from tl_tui.widgets.form_fields import FieldEditor


def editor_id(path: str) -> str:
    """The DOM id of a field's editor: ``f_`` plus the field path with dots as underscores."""
    return "f_" + path.replace(".", "_")


class EditForm(ModalScreen[bool]):
    """Edit the writable fields of one record. Dismisses True after a save, False on cancel."""

    KEY_HINTS: ClassVar[str] = "Tab next field  Ctrl+S save  Esc cancel"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+s", "save", show=False),
        Binding("escape", "cancel", show=False),
    ]

    DEFAULT_CSS = """
    EditForm { align: center middle; }
    #edit-box { width: 80%; height: 90%; border: round $accent; background: $surface; }
    #edit-scroll { height: 1fr; }
    #edit-buttons { height: auto; }
    #form-conflict { height: auto; display: none; background: $error 50%; padding: 0 1; }
    .form-group { text-style: bold; margin: 1 0 0 0; }
    """

    def __init__(
        self,
        client: ClientInterface,
        scope: str,
        record: dict[str, Any],
        meta: FormMetadata,
        *,
        actor: str = "user:dev",
    ) -> None:
        super().__init__()
        self.client = client
        self.scope = scope
        self.record = record
        self.meta = meta
        self.actor = actor
        self.editors: list[FieldEditor] = []
        self.headings: list[str] = []
        self.opened_version = int(record["version"])
        self.conflict = False  # true once the record is known to have moved past opened_version

    def _sections(self) -> list[tuple[str, list[tuple[FieldMeta, Any]]]]:
        """Heading and (field, initial value) rows: Details first, then each writable pset group."""
        psets: dict[str, Any] = self.record.get("psets") or {}
        details = [(f, self.record.get(f.path)) for f in self.meta.core_fields if not f.readonly]
        sections: list[tuple[str, list[tuple[FieldMeta, Any]]]] = [("Details", details)]
        for group in self.meta.psets:
            fields = [(f, pset_value(psets, f.path)) for f in group.fields if not f.readonly]
            if fields:
                sections.append((f"{group.name}   {group.package} {group.version}", fields))
        return sections

    def compose(self) -> ComposeResult:
        with Vertical(id="edit-box"):
            yield Static(f"Edit {self.record['key']}", markup=False)
            yield Static("", id="form-conflict", markup=False)
            with VerticalScroll(id="edit-scroll"):
                for heading, rows in self._sections():
                    self.headings.append(heading)
                    yield Static(heading, classes="form-group", markup=False)
                    for field, initial in rows:
                        # Editors build their widgets in compose, so they are created here.
                        editor = FieldEditor(field, initial, id=editor_id(field.path))
                        self.editors.append(editor)
                        yield editor
            yield Static("", id="form-status", markup=False)
            with Horizontal(id="edit-buttons"):
                yield Button("Save", id="save", variant="primary")
                yield Button("Cancel", id="cancel")

    def _status(self, text: str) -> None:
        self.query_one("#form-status", Static).update(text)

    def mark_conflict(self, actor: str | None = None, version: int | None = None) -> None:
        """Say that someone else changed the record while this form was open, and block saving.

        ``actor`` and ``version`` are the writer and the record version now, when known. The
        typed values stay in the form so the user can copy them; Esc cancels.
        """
        self.conflict = True
        who = f"{actor} changed this record" if actor else "this record changed"
        now = f" (now v{version}, you opened v{self.opened_version})" if version else ""
        banner = self.query_one("#form-conflict", Static)
        banner.update(f"✗ Conflict: {who}{now}. Saving is blocked: Esc cancels, then e opens it.")
        banner.display = True

    # --- actions -----------------------------------------------------------------------------

    def action_save(self) -> None:
        if self.conflict:
            self._status("Not saved: the record changed; cancel and open the form again")
            return
        invalid = [e for e in self.editors if not e.validate()]
        if invalid:
            self._status(f"Fix {len(invalid)} field(s) first")
            return
        edits = {e.meta.path: e.value for e in self.editors if e.changed}
        if not edits:
            self._status("No changes to save")
            return
        try:
            outcome = save_record_edits(
                self.client,
                scope=self.scope,
                actor=self.actor,
                record=self.record,
                meta=self.meta,
                edits=edits,
            )
        except ValueError as exc:  # metadata offered a field that users cannot write
            self._status(f"Not saved: {exc}")
            return
        if outcome.ok:
            self.dismiss(True)
            return
        reason = describe_error(outcome.error) if outcome.error is not None else "unknown error"
        self._status(f"Not saved: {reason}")
        if isinstance(outcome.error, ConcurrencyError):
            self.mark_conflict()

    def action_cancel(self) -> None:
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "save":
            self.action_save()
        elif event.button.id == "cancel":
            self.action_cancel()
