# ruff: noqa: F401
# pyright: reportUnusedImport=false, reportUnusedVariable=false
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


STUB (P1-I7): the methods below whose body is `raise NotImplementedError` are yours;
everything else is final. Remove this paragraph, the two lint-silencing lines at the top of the
file, the STEPS paragraphs and `NotImplementedError` when you implement them.
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
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.integration_text import COLUMNS, LABELS, cells, detail_lines

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
        """Read the table again and keep the highlighted row where it is.

        STEPS: remember `keep = self._row_id(self.current())`. Set `self.kill_switch =
        self._read_kill_switch()`. Then read `self.rows =
        self.client.list_integration(self.kind)`; for the error queue (`self.kind ==
        "deliveries"`) also set `self.names` to a dict from each endpoint's `endpoint_id` to
        `f"{e['app']}/{e['name']}"` over `self.client.list_integration("endpoints")`. On a
        `CLIENT_ERRORS` error set `self.rows = []`, call `self._fill(None)`, say
        `describe_error(exc)` with `error=True` and return. Otherwise call
        `self._fill(keep)`.
        """
        raise NotImplementedError

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
        """Show `self.rows` in the table, the title and the detail panel.

        STEPS: query `#integration-table` (a `DataTable`), `clear(columns=True)`,
        `add_columns(*COLUMNS[self.kind])`, and add one row per row of `self.rows`:
        `Text(c)` for each `c` in `cells(self.kind, row, self.names)`, with
        `key=self._row_id(row)`. When there are rows, `move_cursor(row=...)` to the index of
        `keep` (an id) among `[self._row_id(r) for r in self.rows]` if present, else 0. Then
        call `self._title()` and `self._describe()`.
        """
        raise NotImplementedError

    def _title(self) -> None:
        """Set the title line and the tab line.

        STEPS: the `#integration-title` Static shows `f"{LABELS[self.kind]}
        ({len(self.rows)})   {switch}"` (three spaces) where `switch` is `"Kill switch:
        unknown"` when `self.kill_switch is None`, `"! KILL SWITCH ON: nothing runs
        (settings F9)"` when true, else `"Kill switch: off (settings F9)"`. The
        `#integration-tabs` Static shows every kind as `f"{n} {LABELS[k]}"` for `n, k in
        enumerate(KINDS, 1)`, the current one as `f"[{n} {LABELS[k]}]"`, all joined with two
        spaces.
        """
        raise NotImplementedError

    def current(self) -> dict[str, Any] | None:
        """The highlighted row, or `None` when there is none.

        STEPS: read `cursor_row` of `#integration-table`; return `self.rows[cursor_row]`
        when `self.rows` is not empty and the row is in range, else `None`.
        """
        raise NotImplementedError

    def _describe(self) -> None:
        """Fill the panel under the table with the highlighted row.

        STEPS: query the `#integration-detail` Static. With no highlighted row set it to
        `f"No {LABELS[self.kind].lower()}."`. Otherwise set it to the lines of
        `detail_lines(self.kind, row, self.names)` joined with newlines.
        """
        raise NotImplementedError

    def _say(self, text: str, *, error: bool = False) -> None:
        self.query_one("#integration-status", Static).update(("! " if error else "") + text)

    # --- events --------------------------------------------------------------------------

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        event.stop()
        self._describe()

    # --- actions -------------------------------------------------------------------------

    def action_show_kind(self, index: int) -> None:
        """Show the table at `index` of `KINDS`.

        STEPS: set `self.kind = KINDS[index]`, `self.rows = []`, and call `self.reload()`.
        """
        raise NotImplementedError

    def action_next_kind(self, step: int) -> None:
        """Show the next (or, with a negative `step`, the previous) table, wrapping round.

        STEPS: call `self.action_show_kind((KINDS.index(self.kind) + step) % len(KINDS))`.
        """
        raise NotImplementedError

    def action_switch(self) -> None:
        """Switch the highlighted app, endpoint, rule or enricher on or off.

        STEPS: take `row = self.current()` and stop when it is `None`. Take `switch =
        SWITCHES.get(self.kind)`; when `None`, `self._say(f"{LABELS[self.kind]} are not
        switched here.")` and stop. When `row.get("retired")`, `self._say("This one is
        retired and cannot be switched.")` and stop. Unpack `on, off, field, column =
        switch`; `enable = not row["enabled"]`. When `off is None` the command is `on` and
        it takes the extra field `enabled=enable`; otherwise the command is `on` if `enable`
        else `off` and there is no extra field. Call `self.client.integration_command(name,
        self.scope, **{field: row[column]}, **extra)`. On a `CLIENT_ERRORS` error call
        `self.reload()` (to show what the row really is now), then
        `self._say(describe_error(exc), error=True)` and return. On success call
        `self.reload()` and `self._say(f"{'Enabled' if enable else 'Disabled'}
        {cells(self.kind, row)[0]}")`.
        """
        raise NotImplementedError

    def action_retry(self) -> None:
        """Queue the highlighted failed delivery again.

        STEPS: when `self.kind != "deliveries"`, `self._say("Retry is on the error queue
        (key 7).")` and stop. Take `row = self.current()` and stop when it is `None`. Call
        `self.client.integration_command("RetryInboundDelivery", self.scope,
        delivery_id=row["delivery_id"])`. On a `CLIENT_ERRORS` error call `self.reload()`,
        then `self._say(describe_error(exc), error=True)` and return. On success call
        `self.reload()` and `self._say("Queued the delivery again.")`.
        """
        raise NotImplementedError

    def action_reload(self) -> None:
        self.reload()
        self._say("Reloaded.")

    def action_close(self) -> None:
        self.dismiss(None)
