# ruff: noqa: F401  (STUB P0-I8-T25: delete this line when the unused imports are gone)
"""New-record modal for an extension record type (P0-I8, brief 31.1 and 10.2).

The form is generated from the type's `TypeForm`: Key, Title and Description, then one editor per
slot under its group heading. A managed type's values are sent as psets, an object-backed type's as
its body (`tl_tui.extension_fields.split_values`). The modal validates what it can inline (required
slots, typed text) and shows what the server refuses, including the issue list of an invalid body,
without closing.
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

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.extension_fields import FormSection, sections, split_values
from tl_tui.widgets.form_fields import FieldEditor
from tl_tui.widgets.new_record_form import FIELDS as CORE_FIELDS


class ExtensionRecordForm(ModalScreen[str | None]):
    """Modal that creates an instance of an extension type; dismisses with its key or ``None``."""

    KEY_HINTS: ClassVar[str] = "Tab next field  Ctrl+S create  Esc cancel"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+s", "save", "Create"),
        Binding("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    ExtensionRecordForm { align: center middle; }
    ExtensionRecordForm > Vertical {
        width: 80%;
        height: 90%;
        border: round $accent;
        background: $surface;
        padding: 1 2;
    }
    ExtensionRecordForm VerticalScroll { height: 1fr; }
    ExtensionRecordForm .form-title { text-style: bold; margin-bottom: 1; }
    ExtensionRecordForm .group-title { text-style: bold underline; margin-bottom: 1; }
    ExtensionRecordForm #form-status { color: $error; height: auto; margin-bottom: 1; }
    ExtensionRecordForm Horizontal { height: auto; }
    ExtensionRecordForm Button { margin-right: 2; }
    """

    def __init__(
        self,
        client: ClientInterface,
        scope: str,
        form: TypeForm,
        *,
        actor: str = "user:dev",
    ) -> None:
        super().__init__()
        self.client = client
        self.scope = scope
        self.form = form
        self.actor = actor
        self._sections: list[FormSection] = sections(form)

    # --- layout ------------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        # Mirror NewRecordForm.compose (widgets/new_record_form.py): a Vertical(id="new-
        # record") holding the title Static ("New <type_name>", class form-title), a
        # VerticalScroll with FieldEditor(meta, id=f"new_{meta.path}") for each CORE_FIELDS
        # entry, then per section a Static(section.label, class group-title) and a
        # FieldEditor(meta, id=f"ext_{name}") per field (name = last dotted part of
        # meta.path); then the Static(id=form-status) and the Horizontal with the Create
        # (primary) and Cancel buttons. Static takes markup=False.
        raise NotImplementedError("STUB (P0-I8-T25)")

    def _core(self, path: str) -> FieldEditor:
        return self.query_one(f"#new_{path}", FieldEditor)

    def _slot_editors(self) -> dict[str, FieldEditor]:
        # Map each slot name (last dotted part of meta.path) to its editor, found with
        # self.query_one(f"#ext_{name}", FieldEditor).
        raise NotImplementedError("STUB (P0-I8-T25)")

    def _status(self, text: str) -> None:
        self.query_one("#form-status", Static).update(text)

    # --- actions -----------------------------------------------------------------------------

    def _check(self, editors: dict[str, FieldEditor]) -> bool:
        """Mark every editor that cannot be saved; ``True`` when none is marked."""
        # Title unset: title.set_error("Required"). For each slot editor: if not
        # editor.validate() the form is not ok; otherwise if meta.enforcement == "required"
        # and editor.value is None: set_error("Required"). Check every editor (do not stop
        # at the first). Return True when none was marked.
        raise NotImplementedError("STUB (P0-I8-T25)")

    def action_save(self) -> None:
        # If _check fails: _status("Fix the marked fields") and return. Else collect values
        # {name: editor.value}, split_values(self.form, values), and call
        # self.client.create_instance(self.form.type_name, scope=, title=str(title),
        # key=None when blank else str, description=, psets=split.psets, body=split.body).
        # On ValidationError or CLIENT_ERRORS: _status(f"Not created:
        # {describe_error(exc)}") and stay open. On success self.dismiss(result.key).
        raise NotImplementedError("STUB (P0-I8-T25)")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "create":
            self.action_save()
        elif event.button.id == "cancel":
            self.action_cancel()
