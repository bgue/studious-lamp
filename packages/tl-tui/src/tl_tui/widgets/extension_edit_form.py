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
        # Editors hold Inputs, so they are created here, not in __init__.
        with Vertical(id="edit-body"):
            yield Static(f"Edit {self.record['key']}", classes="form-title", markup=False)
            with VerticalScroll():
                for section in self._sections:
                    yield Static(section.label, classes="group-title", markup=False)
                    for meta in section.fields:
                        name = _slot_name(meta)
                        yield FieldEditor(meta, self._initial.get(name), id=f"ext_{name}")
            yield Static("", id="form-status", markup=False)
            with Horizontal():
                yield Button("Save", id="save", variant="primary")
                yield Button("Cancel", id="cancel")

    def _editors(self) -> dict[str, FieldEditor]:
        return {
            _slot_name(meta): self.query_one(f"#ext_{_slot_name(meta)}", FieldEditor)
            for section in self._sections
            for meta in section.fields
        }

    def _status(self, text: str) -> None:
        self.query_one("#form-status", Static).update(text)

    def action_save(self) -> None:
        if self.conflict:
            self._status("Not saved: the record changed; cancel and open the form again")
            return
        editors = self._editors()
        ok = True
        for editor in editors.values():
            # Clear the old mark first: validate() only sets an error for typed text.
            editor.set_error(None)
            if not editor.validate():
                ok = False
            elif editor.changed and editor.meta.enforcement == "required" and editor.value is None:
                editor.set_error("Required")
                ok = False
        if not ok:
            self._status("Fix the marked fields")
            return
        edits = {name: editor.value for name, editor in editors.items() if editor.changed}
        if not edits:
            self._status("No changes to save")
            return
        try:
            self.client.put_record_body(
                str(self.record["id"]),
                scope=self.scope,
                body=merged_body(self.form, self.body, edits),
                expected_version=self.opened_version,
            )
        except ConcurrencyError as exc:
            self.conflict = True
            self._status(f"Not saved: {describe_error(exc)}")
            return
        except ValidationError as exc:
            self._status(f"Not saved: {describe_error(exc)}")
            return
        except CLIENT_ERRORS as exc:
            self._status(f"Not saved: {describe_error(exc)}")
            return
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "save":
            self.action_save()
        elif event.button.id == "cancel":
            self.action_cancel()
