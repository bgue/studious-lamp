"""The review queue: values an enricher proposed, waiting for a person (P1-I7-T05c; brief 18.9).

A full-size modal opened with ``Ctrl+R``, a ``LogScreen`` (P1-UX2-S3). The list shows the proposed
values (``s`` switches to every value, decided ones included); the panel describes the highlighted
one: record, property, the proposed value, the confidence and the enricher. The actions bar offers
``a`` accept and ``x`` reject (after asking for a reason), as the screen has always enabled them.
The service decides what is allowed (the target type must allow ``SetPsetValues``, a value that is
no longer waiting cannot be decided): a refusal is shown in the status line and nothing changes.
Every change is one client call (``AcceptEnrichment`` or ``RejectEnrichment``) and the list is read
again afterwards; nothing is stored here.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

from textual.binding import Binding, BindingType
from textual.widgets import DataTable, Input
from tl_core.services.errors import ServiceError
from tl_core.settings.layers import project_of_scope

from tl_tui.client import ClientInterface
from tl_tui.display import humanize, mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.integration_text import (
    cells,
    columns,
    detail_lines,
    property_words,
    record_name,
)
from tl_tui.widgets.action_form import ActionFormScreen, FormField
from tl_tui.widgets.log_screen import LogAction, LogScreen
from tl_tui.widgets.record_screen import open_record

WAITING = "proposed"


class ReviewQueueScreen(LogScreen[dict[str, Any]]):
    """The proposed values of an enricher for ``scope``, to accept or reject."""

    LOG_NAME: ClassVar[str] = "Review queue"
    KEY_HINTS: ClassVar[str] = "s waiting/all  / filter  F5 reload  Esc close"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("s", "toggle_all", "Waiting or all", show=False),
    ]

    def __init__(self, client: ClientInterface, scope: str, actor: str) -> None:
        super().__init__()
        self.client = client
        self.scope = scope
        self.actor = actor
        self.show_all = False
        self._flash = ""  # a note for the status line that the reload would replace

    @property
    def values(self) -> list[dict[str, Any]]:
        """The values as listed, before the filter box."""
        return self.rows

    # --- the log's hooks -----------------------------------------------------------------

    def log_project(self) -> str:
        return project_of_scope(self.scope) or "Company"

    def columns(self) -> Sequence[str]:
        return columns("enrichments", technical=mode_of(self.app).technical)

    def load_rows(self) -> Sequence[dict[str, Any]]:
        return self.client.list_integration("enrichments", state=None if self.show_all else WAITING)

    def row_key(self, row: dict[str, Any]) -> str:
        return str(row["value_id"])

    def row_cells(self, row: dict[str, Any]) -> Sequence[str]:
        return cells("enrichments", row, technical=mode_of(self.app).technical)

    def row_record(self, row: dict[str, Any]) -> tuple[str, str]:
        return (record_name(row["target"], technical=False), property_words(row["property_path"]))

    def panel_text(self, row: dict[str, Any] | None) -> str:
        if row is None:
            return "No values." if self.show_all else "Nothing is waiting for review."
        return "\n".join(detail_lines("enrichments", row, technical=mode_of(self.app).technical))

    def summary_text(self) -> str:
        if self._flash:
            flash, self._flash = self._flash, ""
            return flash
        what = "All values" if self.show_all else "Values waiting for review"
        return f"{what} ({len(self.rows)})   s switches"

    def open_row(self, row: dict[str, Any]) -> None:
        """Enter opens the full record the value is about; Esc there comes back to this row."""
        target = row.get("target")
        if not isinstance(target, dict) or not target.get("id"):
            return  # a value with no record to open (guarded; reported)
        open_record(
            self,
            self.client,
            self.scope,
            project_of_scope(self.scope) or "",
            self.actor,
            str(target["id"]),
        )

    def refresh_for_display_mode(self) -> None:
        """The technical toggle changed: rebuild the columns, rows and panel, keeping the row."""
        table = self.query_one("#log-table", DataTable)
        table.clear(columns=True)
        table.add_columns(*self.columns())
        super().refresh_for_display_mode()

    # --- the actions bar: the keys the screen has always enabled -------------------------------

    def actions_for(self, row: dict[str, Any]) -> Sequence[LogAction]:
        return [
            LogAction("a", "Accept", self._accept),
            LogAction("x", "Reject", self._reject),
        ]

    def _property(self, value: dict[str, Any]) -> str:
        """The property as the display mode shows it: its words in plain, the path in technical."""
        if mode_of(self.app).technical:
            return str(value["property_path"])
        return property_words(value["property_path"])

    def _waiting(self) -> dict[str, Any]:
        """The highlighted value when a person can still decide it, else the refusal."""
        value = self.current()
        if value is None:
            raise ServiceError("No value is highlighted.")
        state = value["acceptance_state"]
        if state != WAITING:
            shown = state if mode_of(self.app).technical else humanize(state)
            raise ServiceError(f"This value is already {shown}.")
        return value

    def _decide(self, done: str, name: str, **fields: Any) -> None:
        """Send one decision. A refusal is kept for the status line and the list is read again
        (the attempt does that) so it shows what the value really is now."""
        try:
            self.client.integration_command(name, self.scope, **fields)
        except CLIENT_ERRORS as exc:
            self._flash = "! " + describe_error(exc)
            return
        self._flash = done

    def _accept(self) -> None:
        value = self._waiting()
        self._decide(
            f"Accepted {self._property(value)}",
            "AcceptEnrichment",
            value_id=value["value_id"],
        )

    def _reject(self) -> None:
        """Reject the highlighted value after asking for a reason."""
        value = self._waiting()

        def answered(answer: dict[str, str] | None) -> None:
            if answer is None:  # cancelled: nothing is changed
                return
            self.attempt(
                lambda: self._decide(
                    f"Rejected {self._property(value)}",
                    "RejectEnrichment",
                    value_id=value["value_id"],
                    reason=answer["reason"],
                )
            )

        self.app.push_screen(
            ActionFormScreen(f"Reject {self._property(value)}", (FormField("reason", "Reason"),)),
            answered,
        )

    # --- the log's own keys --------------------------------------------------------------

    def action_toggle_all(self) -> None:
        """Switch between the waiting values and all of them."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.show_all = not self.show_all
        self.reload()

    def action_reload(self) -> None:
        self._flash = "Reloaded."
        self.reload()
