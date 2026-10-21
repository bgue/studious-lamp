"""The integration registry: what acts on the ledger, and what it did (P1-I7-T07; brief 18.13).

A full-size modal opened with ``Ctrl+E`` by an admin. One table at a time: endpoints, rules,
actions, enrichers, apps, invocations and the inbound error queue; ``[`` and ``]`` (or the keys
``1`` to ``7``) switch. The panel under the table describes the highlighted row: who owns it, which
service actor it acts as, with which access. ``e`` switches the highlighted app, endpoint, rule or
enricher on or off and ``y`` retries a failed delivery. The title shows the kill switch
(``integration.kill_switch``: while it is on nothing runs); it is changed in the settings (F9). The
service decides what is allowed (only an admin changes anything): a refusal is shown in the status
line and nothing changes. Every change is one client call and the lists are read again afterwards;
nothing is stored here, and no secret or payload is ever in a row.
"""

from __future__ import annotations

from typing import Any, ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Static
from tl_core.settings.layers import project_of_scope

from tl_tui.client import ClientInterface
from tl_tui.display import Labels, mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.integration_text import LABELS, cells, columns, detail_lines
from tl_tui.labels_load import load_labels

KINDS = ("endpoints", "rules", "actions", "enrichers", "apps", "invocations", "deliveries")
KILL_SWITCH = "integration.kill_switch"
#: kind -> (command when switching on, command when off, id field, id column). A command with a
#: ``None`` off-name is one command that takes ``enabled``.
SWITCHES: dict[str, tuple[str, str | None, str, str]] = {
    "endpoints": ("SetInboundEndpointEnabled", None, "endpoint_id", "endpoint_id"),
    "rules": ("EnableRule", "DisableRule", "rule_id", "rule_id"),
    "enrichers": ("SetEnricherEnabled", None, "enricher_id", "enricher_id"),
    "apps": ("SetIntegrationAppEnabled", None, "app_id", "app_id"),
}


class IntegrationScreen(ModalScreen[None]):
    """The registry for ``scope``; ``kind`` is the table shown first."""

    KEY_HINTS: ClassVar[str] = "[ ] or 1-7 table  e on/off  y retry delivery  F5 reload  Esc close"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("right_square_bracket", "next_kind(1)", "Next table", show=False),
        Binding("left_square_bracket", "next_kind(-1)", "Previous table", show=False),
        *(
            Binding(str(n), f"show_kind({n - 1})", LABELS[k], show=False)
            for n, k in enumerate(KINDS, 1)
        ),
        Binding("e", "switch", "On/off", show=False),
        Binding("y", "retry", "Retry delivery", show=False),
        Binding("f5", "reload", "Reload", show=False),
        Binding("escape", "close", "Close", show=False),
    ]

    DEFAULT_CSS = """
    IntegrationScreen { background: $surface; }
    IntegrationScreen > Vertical { padding: 0 1; }
    IntegrationScreen #integration-title { text-style: bold; height: 1; }
    IntegrationScreen #integration-tabs { height: 1; }
    IntegrationScreen #integration-table { height: 1fr; min-height: 6; }
    IntegrationScreen #integration-detail { height: 12; border-top: solid $accent; padding: 0 1; }
    IntegrationScreen #integration-status { height: 1; }
    IntegrationScreen #integration-hints { height: 1; color: $text-muted; }
    """

    def __init__(
        self, client: ClientInterface, scope: str, actor: str, *, kind: str = "endpoints"
    ) -> None:
        super().__init__()
        self.client = client
        self.scope = scope
        self.actor = actor
        self.kind = kind if kind in KINDS else KINDS[0]
        self.rows: list[dict[str, Any]] = []
        self.names: dict[str, str] = {}  # endpoint id -> app/name, for the error queue
        self.labels: Labels = Labels()  # service and people names, for plain text
        self.kill_switch: bool | None = None

    # --- layout --------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("", markup=False, id="integration-title")
            yield Static("", markup=False, id="integration-tabs")
            yield DataTable[str](id="integration-table", cursor_type="row", zebra_stripes=True)
            yield Static("", markup=False, id="integration-detail")
            yield Static("", markup=False, id="integration-status")
            yield Static(self.KEY_HINTS, markup=False, id="integration-hints")

    def on_mount(self) -> None:
        self.labels = load_labels(self.client, self.scope, ())
        self.reload()
        self.query_one("#integration-table", DataTable).focus()

    # --- data ----------------------------------------------------------------------------

    def _read_kill_switch(self) -> bool | None:
        try:
            view = self.client.get_setting(KILL_SWITCH, project=project_of_scope(self.scope))
        except CLIENT_ERRORS:
            return None
        return bool(view.effective.value)

    def reload(self) -> None:
        """Read the table again and keep the highlighted row where it is."""
        keep = self._row_id(self.current())
        self.kill_switch = self._read_kill_switch()
        try:
            self.rows = self.client.list_integration(self.kind)
            if self.kind == "deliveries":
                self.names = {
                    str(e["endpoint_id"]): f"{e['app']}/{e['name']}"
                    for e in self.client.list_integration("endpoints")
                }
        except CLIENT_ERRORS as exc:
            self.rows = []
            self._fill(None)
            self._say(describe_error(exc), error=True)
            return
        self._fill(keep)

    def _row_id(self, row: dict[str, Any] | None) -> str | None:
        if row is None:
            return None
        return str(row[self._column_of_id()])

    def _column_of_id(self) -> str:
        return {
            "endpoints": "endpoint_id", "rules": "rule_id", "actions": "action_id",
            "enrichers": "enricher_id", "apps": "app_id", "invocations": "invocation_id",
            "deliveries": "delivery_id",
        }[self.kind]  # fmt: skip

    def _fill(self, keep: str | None) -> None:
        """Show `self.rows` in the table, the title and the detail panel."""
        table = self.query_one("#integration-table", DataTable)
        technical = mode_of(self.app).technical
        table.clear(columns=True)
        table.add_columns(*columns(self.kind, technical=technical))
        for row in self.rows:
            table.add_row(
                *(
                    Text(c)
                    for c in cells(
                        self.kind, row, self.names, labels=self.labels, technical=technical
                    )
                ),
                key=self._row_id(row),
            )
        if self.rows:
            ids = [self._row_id(row) for row in self.rows]
            table.move_cursor(row=ids.index(keep) if keep in ids else 0)
        self._title()
        self._describe()

    def _title(self) -> None:
        """Set the title line and the tab line."""
        if self.kill_switch is None:
            switch = "Kill switch: unknown"
        elif self.kill_switch:
            switch = "! KILL SWITCH ON: nothing runs (settings F9)"
        else:
            switch = "Kill switch: off (settings F9)"
        self.query_one("#integration-title", Static).update(
            f"{LABELS[self.kind]} ({len(self.rows)})   {switch}"
        )
        tabs = "  ".join(
            f"[{n} {LABELS[k]}]" if k == self.kind else f"{n} {LABELS[k]}"
            for n, k in enumerate(KINDS, 1)
        )
        self.query_one("#integration-tabs", Static).update(tabs)

    def current(self) -> dict[str, Any] | None:
        """The highlighted row, or `None` when there is none."""
        cursor = self.query_one("#integration-table", DataTable).cursor_row
        if not self.rows or not 0 <= cursor < len(self.rows):
            return None
        return self.rows[cursor]

    def _describe(self) -> None:
        """Fill the panel under the table with the highlighted row."""
        panel = self.query_one("#integration-detail", Static)
        row = self.current()
        if row is None:
            panel.update(f"No {LABELS[self.kind].lower()}.")
            return
        technical = mode_of(self.app).technical
        panel.update(
            "\n".join(
                detail_lines(self.kind, row, self.names, labels=self.labels, technical=technical)
            )
        )

    def _say(self, text: str, *, error: bool = False) -> None:
        self.query_one("#integration-status", Static).update(("! " if error else "") + text)

    def refresh_for_display_mode(self) -> None:
        """Redraw the columns and the panel when technical details are switched (D14)."""
        self._fill(self._row_id(self.current()))

    # --- events --------------------------------------------------------------------------

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        event.stop()
        self._describe()

    # --- actions -------------------------------------------------------------------------

    def action_show_kind(self, index: int) -> None:
        """Show the table at `index` of `KINDS`."""
        self.kind = KINDS[index]
        self.rows = []
        self.reload()

    def action_next_kind(self, step: int) -> None:
        """Show the next (or, with a negative `step`, the previous) table, wrapping round."""
        self.action_show_kind((KINDS.index(self.kind) + step) % len(KINDS))

    def action_switch(self) -> None:
        """Switch the highlighted app, endpoint, rule or enricher on or off."""
        row = self.current()
        if row is None:
            return
        switch = SWITCHES.get(self.kind)
        if switch is None:
            self._say(f"{LABELS[self.kind]} are not switched here.")
            return
        if row.get("retired"):
            self._say("This one is retired and cannot be switched.")
            return
        on, off, field, column = switch
        enable = not row["enabled"]
        extra: dict[str, Any] = {}
        if off is None:
            name = on
            extra["enabled"] = enable
        else:
            name = on if enable else off
        try:
            self.client.integration_command(name, self.scope, **{field: row[column]}, **extra)
        except CLIENT_ERRORS as exc:
            self.reload()  # show what the row really is now
            self._say(describe_error(exc), error=True)
            return
        self.reload()
        self._say(f"{'Enabled' if enable else 'Disabled'} {cells(self.kind, row)[0]}")

    def action_retry(self) -> None:
        """Queue the highlighted failed delivery again."""
        if self.kind != "deliveries":
            self._say("Retry is on the error queue (key 7).")
            return
        row = self.current()
        if row is None:
            return
        try:
            self.client.integration_command(
                "RetryInboundDelivery", self.scope, delivery_id=row["delivery_id"]
            )
        except CLIENT_ERRORS as exc:
            self.reload()  # show what the delivery really is now
            self._say(describe_error(exc), error=True)
            return
        self.reload()
        self._say("Queued the delivery again.")

    def action_reload(self) -> None:
        self.reload()
        self._say("Reloaded.")

    def action_close(self) -> None:
        self.dismiss(None)
