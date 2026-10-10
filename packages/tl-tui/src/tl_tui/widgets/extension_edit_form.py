# ruff: noqa: F401  (STUB P0-I8-T27: delete this line when the unused imports are gone)
"""Edit modal for the body of an object-backed record (P0-I8, brief 31.2 and 10.2).

One editor per slot of the type's form, filled from the stored body. Only the slots the user
changed are applied (`tl_tui.extension_body.merged_body`); the whole body is stored as a new
version of the record's document, guarded by the record version the form was opened on.
"""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import ValidationError
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static
from tl_core.extypes.forms import TypeForm
from tl_core.ledger import ConcurrencyError
from tl_schema.forms import FieldMeta

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.extension_body import body_values, merged_body
from tl_tui.extension_fields import FormSection, sections
from tl_tui.widgets.form_fields import FieldEditor


def _slot_name(meta: FieldMeta) -> str:
    """The slot's name: the last dotted part of its path (``body.crew`` is ``crew``)."""
    return meta.path.rsplit(".", 1)[-1]


class ExtensionEditForm(ModalScreen[bool]):
    """Edit the stored body of one record. Dismisses True after a save, False on cancel."""

    KEY_HINTS: ClassVar[str] = "Tab next field  Ctrl+S save  Esc cancel"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+s", "save", "Save"),
        Binding("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    ExtensionEditForm { align: center middle; }
    ExtensionEditForm > Vertical {
        width: 80%;
        height: 90%;
        border: round $accent;
        background: $surface;
        padding: 1 2;
    }
    ExtensionEditForm VerticalScroll { height: 1fr; }
    ExtensionEditForm .form-title { text-style: bold; margin-bottom: 1; }
    ExtensionEditForm .group-title { text-style: bold underline; margin-bottom: 1; }
    ExtensionEditForm #form-status { color: $error; height: auto; margin-bottom: 1; }
    ExtensionEditForm Horizontal { height: auto; }
    ExtensionEditForm Button { margin-right: 2; }
    """

    def __init__(
        self,
        client: ClientInterface,
        scope: str,
        record: dict[str, Any],
        form: TypeForm,
        body: dict[str, Any],
    ) -> None:
        super().__init__()
        self.client = client
        self.scope = scope
        self.record = record
        self.form = form
        self.body = body
        self.opened_version = int(record["version"])
        self.conflict = False  # true once the record is known to have moved past opened_version
        self._sections: list[FormSection] = sections(form)
        self._initial = body_values(form, body)

    def compose(self) -> ComposeResult:
        # A Vertical(id="edit-body") holding the title Static (f"Edit {record key}", class
        # form- title), a VerticalScroll with, per section, a Static(section.label, class
        # group-title) and a FieldEditor(meta, self._initial.get(name), id=f"ext_{name}")
        # per field, then the Static(id=form-status) and a Horizontal with the Save
        # (primary, id save) and Cancel buttons. Static takes markup=False. Compare
        # ExtensionRecordForm.compose in widgets/extension_form.py.
        raise NotImplementedError("STUB (P0-I8-T27)")

    def _editors(self) -> dict[str, FieldEditor]:
        # Map each slot name (_slot_name(meta)) to its editor, found with
        # self.query_one(f"#ext_{name}", FieldEditor).
        raise NotImplementedError("STUB (P0-I8-T27)")

    def _status(self, text: str) -> None:
        self.query_one("#form-status", Static).update(text)

    def action_save(self) -> None:
        # 1) If self.conflict: _status("Not saved: the record changed; cancel and open the
        # form again") and return. 2) For every editor: set_error(None), then validate(); if
        # it validates and the editor changed and its meta.enforcement is "required" and its
        # value is None: set_error("Required"). Any failure: _status("Fix the marked
        # fields") and return (check every editor). 3) edits = {name: editor.value for
        # changed editors}; none: _status("No changes to save") and return. 4)
        # client.put_record_body(record id, scope=, body=merged_body(form, body, edits),
        # expected_version=self.opened_version). ConcurrencyError: set self.conflict = True
        # and _status(f"Not saved: {describe_error(exc)}") (catch it before the other
        # errors). ValidationError or CLIENT_ERRORS: _status(f"Not saved:
        # {describe_error(exc)}"). 5) On success self.dismiss(True).
        raise NotImplementedError("STUB (P0-I8-T27)")

    def action_cancel(self) -> None:
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "save":
            self.action_save()
        elif event.button.id == "cancel":
            self.action_cancel()
