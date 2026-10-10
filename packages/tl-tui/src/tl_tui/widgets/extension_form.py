"""New-record modal for an extension record type (P0-I8, brief 31.1 and 10.2).

The form is generated from the type's `TypeForm`: Key, Title and Description, then one editor per
slot under its group heading. A managed type's values are sent as psets, an object-backed type's as
its body (`tl_tui.extension_fields.split_values`). The modal validates what it can inline (required
slots, typed text) and shows what the server refuses, including the issue list of an invalid body,
without closing.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import ValidationError
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static
from tl_core.extypes.forms import TypeForm
from tl_schema.forms import FieldMeta

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.extension_fields import FormSection, sections, split_values
from tl_tui.widgets.form_fields import FieldEditor
from tl_tui.widgets.new_record_form import FIELDS as CORE_FIELDS


def _slot_name(meta: FieldMeta) -> str:
    """The slot's name: the last dotted part of its path (``psets.p.crane`` is ``crane``)."""
    return meta.path.rsplit(".", 1)[-1]


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
        # Editors hold Inputs, so they are created here, not in __init__.
        with Vertical(id="new-record"):
            yield Static(f"New {self.form.type_name}", classes="form-title", markup=False)
            with VerticalScroll():
                for meta in CORE_FIELDS:
                    yield FieldEditor(meta, id=f"new_{meta.path}")
                for section in self._sections:
                    yield Static(section.label, classes="group-title", markup=False)
                    for meta in section.fields:
                        yield FieldEditor(meta, id=f"ext_{_slot_name(meta)}")
            yield Static("", id="form-status", markup=False)
            with Horizontal():
                yield Button("Create", id="create", variant="primary")
                yield Button("Cancel", id="cancel")

    def _core(self, path: str) -> FieldEditor:
        return self.query_one(f"#new_{path}", FieldEditor)

    def _slot_editors(self) -> dict[str, FieldEditor]:
        return {
            _slot_name(meta): self.query_one(f"#ext_{_slot_name(meta)}", FieldEditor)
            for section in self._sections
            for meta in section.fields
        }

    def _status(self, text: str) -> None:
        self.query_one("#form-status", Static).update(text)

    # --- actions -----------------------------------------------------------------------------

    def _check(self, editors: dict[str, FieldEditor]) -> bool:
        """Mark every editor that cannot be saved; ``True`` when none is marked."""
        ok = True
        title = self._core("title")
        if title.value is None:
            title.set_error("Required")
            ok = False
        else:
            title.set_error(None)
        for editor in editors.values():
            # Clear the old mark first: validate() only sets an error for typed text, so a
            # stale "Required" on a choice field would otherwise survive the user's choice.
            editor.set_error(None)
            if not editor.validate():
                ok = False
            elif editor.meta.enforcement == "required" and editor.value is None:
                editor.set_error("Required")
                ok = False
        return ok

    def action_save(self) -> None:
        editors = self._slot_editors()
        if not self._check(editors):
            self._status("Fix the marked fields")
            return
        split = split_values(self.form, {name: editor.value for name, editor in editors.items()})
        title = self._core("title")
        key = self._core("key")
        description = self._core("description")
        try:
            result = self.client.create_instance(
                self.form.type_name,
                scope=self.scope,
                title=str(title.value),
                key=None if key.value is None else str(key.value),
                description=description.value,
                psets=split.psets,
                body=split.body,
            )
        except ValidationError as exc:
            self._status(f"Not created: {describe_error(exc)}")
            return
        except CLIENT_ERRORS as exc:
            self._status(f"Not created: {describe_error(exc)}")
            return
        self.dismiss(result.key)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "create":
            self.action_save()
        elif event.button.id == "cancel":
            self.action_cancel()
