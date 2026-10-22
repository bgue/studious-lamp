"""The integration registry: what acts on the ledger, and what it did (P1-I7-T07; brief 18.13).

A full-size modal opened with ``Ctrl+E`` by an admin, a ``LogScreen`` (P1-UX2-S3). One list at a
time: endpoints, rules, actions, enrichers, apps, invocations and the inbound error queue; ``[`` and
``]`` (or the keys ``1`` to ``7``) switch. The panel describes the highlighted row: who owns it,
which service actor it acts as, with which access. The actions bar offers ``e`` to switch the
highlighted app, endpoint, rule or enricher on or off and ``y`` to retry a failed delivery, as the
screen has always enabled them. The status line shows the kill switch
(``integration.kill_switch``: while it is on nothing runs); it is changed in the settings (F9). The
service decides what is allowed (only an admin changes anything): a refusal is shown in the status
line and nothing changes. Every change is one client call and the lists are read again afterwards;
nothing is stored here, and no secret or payload is ever in a row.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

from textual.binding import Binding, BindingType
from textual.widgets import DataTable, Static
from tl_core.services.errors import ServiceError
from tl_core.settings.layers import project_of_scope

from tl_tui.client import ClientInterface
from tl_tui.display import Labels, humanize, mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.integration_text import LABELS, cells, columns, detail_lines
from tl_tui.labels_load import load_labels
from tl_tui.log_text import actions_text
from tl_tui.widgets.log_screen import LogAction, LogScreen

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
ID_COLUMNS = {
    "endpoints": "endpoint_id",
    "rules": "rule_id",
    "actions": "action_id",
    "enrichers": "enricher_id",
    "apps": "app_id",
    "invocations": "invocation_id",
    "deliveries": "delivery_id",
}


class IntegrationScreen(LogScreen[dict[str, Any]]):
    """The registry for ``scope``; ``kind`` is the table shown first."""

    LOG_NAME: ClassVar[str] = LABELS[KINDS[0]]
    KEY_HINTS: ClassVar[str] = "[ ] or 1-7 table  / filter  F5 reload  Esc close"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("right_square_bracket", "next_kind(1)", "Next table", show=False),
        Binding("left_square_bracket", "next_kind(-1)", "Previous table", show=False),
        *(
            Binding(str(n), f"show_kind({n - 1})", LABELS[k], show=False)
            for n, k in enumerate(KINDS, 1)
        ),
    ]

    def __init__(
        self, client: ClientInterface, scope: str, actor: str, *, kind: str = "endpoints"
    ) -> None:
        super().__init__()
        self.client = client
        self.scope = scope
        self.actor = actor
        self.kind = kind if kind in KINDS else KINDS[0]
        self.LOG_NAME = LABELS[self.kind]  # pyright: ignore[reportAttributeAccessIssue]
        self.names: dict[str, str] = {}  # endpoint id -> app/name, for the error queue
        self.labels: Labels = Labels()  # service and people names, for plain text
        self.kill_switch: bool | None = None
        self._labelled = False
        self._flash = ""  # a note for the status line that the reload would replace

    # --- the log's hooks -----------------------------------------------------------------

    def log_project(self) -> str:
        return project_of_scope(self.scope) or "Company"

    def columns(self) -> Sequence[str]:
        return columns(self.kind, technical=mode_of(self.app).technical)

    def _read_kill_switch(self) -> bool | None:
        try:
            view = self.client.get_setting(KILL_SWITCH, project=project_of_scope(self.scope))
        except CLIENT_ERRORS:
            return None
        return bool(view.effective.value)

    def load_rows(self) -> Sequence[dict[str, Any]]:
        if not self._labelled:
            self.labels = load_labels(self.client, self.scope, ())
            self._labelled = True
        self.kill_switch = self._read_kill_switch()
        found = self.client.list_integration(self.kind)
        if self.kind == "deliveries":
            self.names = {
                str(e["endpoint_id"]): f"{e['app']}/{e['name']}"
                for e in self.client.list_integration("endpoints")
            }
        return found

    def row_key(self, row: dict[str, Any]) -> str:
        return str(row[ID_COLUMNS[self.kind]])

    def row_cells(self, row: dict[str, Any]) -> Sequence[str]:
        return cells(
            self.kind,
            row,
            self.names,
            labels=self.labels,
            technical=mode_of(self.app).technical,
        )

    def row_record(self, row: dict[str, Any]) -> tuple[str, str]:
        """The name of the row and, where it has one, its title (never an id)."""
        kind = self.kind
        if kind == "endpoints":
            return (f"{row['app']}/{row['name']}", "")
        if kind == "rules":
            return (str(row["key"]), str(row["title"]))
        if kind in ("actions", "apps"):
            return (str(row["name"]), str(row["label"]))
        if kind == "enrichers":
            return (str(row["name"]), "")
        if kind == "invocations":
            return (str(row["action"]), humanize(str(row["status"])))
        return (self.names.get(str(row["endpoint_id"]), "?"), humanize(str(row["state"])))

    def panel_text(self, row: dict[str, Any] | None) -> str:
        """The tab line, then the highlighted row: who owns it, how it acts, with which access."""
        tabs = "  ".join(
            f"[{n} {LABELS[k]}]" if k == self.kind else f"{n} {LABELS[k]}"
            for n, k in enumerate(KINDS, 1)
        )
        if row is None:
            return f"{tabs}\n\nNo {LABELS[self.kind].lower()}."
        lines = detail_lines(
            self.kind,
            row,
            self.names,
            labels=self.labels,
            technical=mode_of(self.app).technical,
        )
        return "\n".join([tabs, "", *lines])

    def summary_text(self) -> str:
        if self._flash:
            flash, self._flash = self._flash, ""
            return flash
        if self.kill_switch is None:
            switch = "Kill switch: unknown"
        elif self.kill_switch:
            switch = "! KILL SWITCH ON: nothing runs (settings F9)"
        else:
            switch = "Kill switch: off (settings F9)"
        return f"{LABELS[self.kind]} ({len(self.rows)})   {switch}"

    def open_row(self, row: dict[str, Any]) -> None:
        """Nothing to open: a registry row is not a record."""

    def _draw_actions(self, *, failed: bool = False) -> None:
        """The bar without ``[Enter] Open record``: a registry row has no record to open."""
        bar = self.query_one("#log-actions", Static)
        bar.update(
            "" if failed or self.current() is None else actions_text(self.offered, can_open=False)
        )

    def refresh_for_display_mode(self) -> None:
        """Redraw the columns and the panel when technical details are switched (D14)."""
        self._new_columns()
        super().refresh_for_display_mode()

    def _new_columns(self) -> None:
        table = self.query_one("#log-table", DataTable)
        table.clear(columns=True)
        table.add_columns(*self.columns())

    # --- the actions bar: the keys the screen has always enabled -------------------------------

    def actions_for(self, row: dict[str, Any]) -> Sequence[LogAction]:
        offered: list[LogAction] = []
        if self.kind in SWITCHES:
            offered.append(
                LogAction("e", "Turn off" if row["enabled"] else "Turn on", self._switch)
            )
        if self.kind == "deliveries":
            offered.append(LogAction("y", "Retry delivery", self._retry))
        return offered

    def _decide(self, done: str, name: str, **fields: Any) -> None:
        """Send one change. A refusal is kept for the status line and the list is read again
        (the attempt does that) so it shows what the row really is now."""
        try:
            self.client.integration_command(name, self.scope, **fields)
        except CLIENT_ERRORS as exc:
            self._flash = "! " + describe_error(exc)
            return
        self._flash = done

    def _switch(self) -> None:
        """Switch the highlighted app, endpoint, rule or enricher on or off."""
        row = self.current()
        if row is None:
            return
        if row.get("retired"):
            raise ServiceError("This one is retired and cannot be switched.")
        on, off, field, column = SWITCHES[self.kind]
        enable = not row["enabled"]
        extra: dict[str, Any] = {}
        if off is None:
            name = on
            extra["enabled"] = enable
        else:
            name = on if enable else off
        done = f"{'Enabled' if enable else 'Disabled'} {cells(self.kind, row)[0]}"
        self._decide(done, name, **{field: row[column]}, **extra)

    def _retry(self) -> None:
        """Queue the highlighted failed delivery again."""
        row = self.current()
        if row is None:
            return
        self._decide(
            "Queued the delivery again.", "RetryInboundDelivery", delivery_id=row["delivery_id"]
        )

    # --- the log's own keys --------------------------------------------------------------

    def action_show_kind(self, index: int) -> None:
        """Show the table at `index` of `KINDS`."""
        self.kind = KINDS[index]
        self.LOG_NAME = LABELS[self.kind]  # pyright: ignore[reportAttributeAccessIssue]
        self.rows = []  # the rows of the other table are not rows of this one
        self._new_columns()
        self._fill(None)
        self.reload()

    def action_next_kind(self, step: int) -> None:
        """Show the next (or, with a negative `step`, the previous) table, wrapping round."""
        self.action_show_kind((KINDS.index(self.kind) + step) % len(KINDS))

    def action_reload(self) -> None:
        self._flash = "Reloaded."
        self.reload()
