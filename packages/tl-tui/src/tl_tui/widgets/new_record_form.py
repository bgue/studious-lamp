"""New-record modal: Key, Title and Description, created through `ClientInterface` (brief 10.2).

The form only collects values and reports the outcome. Keys are typed by the user in Phase 0;
the numbering service arrives in Increment 3. Errors stay on screen and the form stays open so
the user can correct them.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import ValidationError
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static
from tl_core.services.commands import CreateRecord
from tl_schema.forms import FieldMeta

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.widgets.form_fields import FieldEditor

FIELDS: tuple[FieldMeta, ...] = (
    FieldMeta(
        path="key",
        label="Key",
        description="Record key, unique in the project scope",
        kind="string",
        layer="core",
        group="details",
        order=1,
        enforcement="required",
    ),
    FieldMeta(
        path="title",
        label="Title",
        description="Short title shown in the grid",
        kind="string",
        layer="core",
        group="details",
        order=2,
        enforcement="required",
    ),
    FieldMeta(
        path="description",
        label="Description",
        description="Optional longer description",
        kind="text",
        layer="core",
        group="details",
        order=3,
    ),
)


class NewRecordForm(ModalScreen[str | None]):
    """Modal that creates a record and dismisses with its key, or ``None`` when cancelled."""

    KEY_HINTS: ClassVar[str] = "Tab next field  Ctrl+S create  Esc cancel"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+s", "save", "Create"),
        Binding("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    NewRecordForm { align: center middle; }
    NewRecordForm > Vertical {
        width: 70%;
        height: auto;
        border: round $accent;
        background: $surface;
        padding: 1 2;
    }
    NewRecordForm .form-title { text-style: bold; margin-bottom: 1; }
    NewRecordForm #form-status { color: $error; height: auto; margin-bottom: 1; }
    NewRecordForm Horizontal { height: auto; }
    NewRecordForm Button { margin-right: 2; }
    """

    def __init__(
        self,
        client: ClientInterface,
        scope: str,
        *,
        record_type: str = "core.Record",
        actor: str = "user:dev",
    ) -> None:
        super().__init__()
        self.client = client
        self.scope = scope
        self.record_type = record_type
        self.actor = actor

    def compose(self) -> ComposeResult:
        # Editors hold Inputs, so they are created here, not in __init__.
        with Vertical(id="new-record"):
            yield Static("New record", classes="form-title", markup=False)
            for field in FIELDS:
                yield FieldEditor(field, id=f"new_{field.path}")
            yield Static("", id="form-status", markup=False)
            with Horizontal():
                yield Button("Create", id="create", variant="primary")
                yield Button("Cancel", id="cancel")

    def _editor(self, path: str) -> FieldEditor:
        return self.query_one(f"#new_{path}", FieldEditor)

    def _status(self, text: str) -> None:
        self.query_one("#form-status", Static).update(text)

    def action_save(self) -> None:
        key = self._editor("key")
        title = self._editor("title")
        description = self._editor("description")
        missing = False
        for editor in (key, title):
            if editor.value is None:
                editor.set_error("Required")
                missing = True
        if missing:
            self._status("Fill in the required fields")
            return
        cmd = CreateRecord(
            actor=self.actor,
            source="tui",
            scope=self.scope,
            record_type=self.record_type,
            key=str(key.value),
            title=str(title.value),
            description=description.value,
        )
        try:
            result = self.client.create_record(cmd)
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
