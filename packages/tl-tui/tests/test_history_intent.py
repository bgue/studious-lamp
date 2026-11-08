"""The intent of the highlighted Activity row, under the table (P2-INT-T04).

Full and revisions-only modes show ``intent_lines`` of the row's event; an event without intent
leaves the panel empty and hidden, and the table cells are those of the text functions.
"""

from __future__ import annotations

from typing import Any

from fakes import FakeClient
from helpers import run_pilot, static_of
from test_activity_tab import Host, cells_of, setup, table_of
from test_embedded_actions import (
    SCOPE as REAL_SCOPE,  # noqa: F401  # pyright: ignore[reportMissingImports]
)
from test_embedded_actions import (  # noqa: F401  # pyright: ignore[reportMissingImports]
    Ledger,
    ledger,
)
from textual.pilot import Pilot
from tl_adapters.db import open_uow
from tl_core import confidentiality
from tl_core.intent import NOT_AVAILABLE, Intent, IntentRef, IntentToward, intent_scope
from tl_core.services.commands import CreateRecord
from tl_core.services.records import handle_create_record
from tl_tui.display import DisplayMode
from tl_tui.intent_text import intent_lines
from tl_tui.record_activity_text import activity_cells
from tl_tui.widgets.activity_tab import ActivityTab


class ModeHost(Host):
    def __init__(self, client: FakeClient, record: dict[str, Any], technical: bool) -> None:
        super().__init__(client, record)
        self.display_mode = DisplayMode()
        self.display_mode.technical = technical


def with_intent(client: FakeClient, record: dict[str, Any], intent: Intent) -> None:
    """Give the newest event of the record ``intent`` (the first row of the full view)."""
    events = client._events[record["id"]]  # pyright: ignore[reportPrivateUsage]
    events[-1] = events[-1].model_copy(update={"intent": intent})


def panel(app: Any) -> tuple[str, bool]:
    return static_of(app, "#activity-why"), app.query_one("#activity-why").display


FULL = Intent(
    why="welds are late",
    toward=IntentToward(target="X", state="released"),
    goal_ref="g-1",
)


def test_the_highlighted_row_shows_its_intent_plain() -> None:
    client, record = setup()
    intent = FULL.model_copy(
        update={
            "next": [IntentRef(command="TransitionWorkflow", target=record["id"])],
            "toward": IntentToward(target=record["id"], state="released"),
        }
    )
    with_intent(client, record, intent)
    app = ModeHost(client, record, technical=False)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        text, visible = panel(app)
        want = intent_lines(intent, technical=False, names={record["id"]: record["key"]})
        assert visible and text == "\n".join(want)
        assert record["key"] in text and record["id"] not in text

    run_pilot(app, scenario)


def test_technical_mode_shows_raw_ids_and_keys() -> None:
    client, record = setup()
    intent = Intent(toward=IntentToward(target=record["id"], condition="done"))
    with_intent(client, record, intent)
    app = ModeHost(client, record, technical=True)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        text, visible = panel(app)
        assert visible and text == f"toward: {record['id']} ~ done"

    run_pilot(app, scenario)


def test_a_row_without_intent_leaves_the_panel_empty_and_hidden() -> None:
    client, record = setup()
    app = ModeHost(client, record, technical=False)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert panel(app) == ("", False)
        tab = app.query_one(ActivityTab)
        want = [
            activity_cells(r, tab.labels, technical=False, with_why=False)
            for r in client.activity(record["id"]).rows
        ]
        assert cells_of(table_of(app)) == want

    run_pilot(app, scenario)


def test_not_available_is_shown_as_is_and_the_panel_follows_the_cursor() -> None:
    client, record = setup()
    intent = Intent(toward=IntentToward(target=NOT_AVAILABLE), next=[IntentRef(text=NOT_AVAILABLE)])
    with_intent(client, record, intent)
    app = ModeHost(client, record, technical=False)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert panel(app) == (f"Next: {NOT_AVAILABLE}\nToward: {NOT_AVAILABLE}", True)
        table_of(app).move_cursor(row=1)
        await pilot.pause()
        assert panel(app) == ("", False)

    run_pilot(app, scenario)


def test_revisions_only_mode_shows_it_too() -> None:
    client, record = setup()
    with_intent(client, record, Intent(why="because"))
    app = ModeHost(client, record, technical=False)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("v")
        await pilot.pause()
        table = table_of(app)
        assert panel(app) == ("", False)  # oldest first: the cursor is on the oldest event
        table.move_cursor(row=table.row_count - 1)
        await pilot.pause()
        assert panel(app) == ("Why: because", True)

    run_pilot(app, scenario)


def make_record(ledger: Ledger, key: str, intent: Intent) -> str:  # noqa: F811
    """A record the open reader may read, created with ``intent``."""
    cmd = ledger.command(
        CreateRecord,
        "ctl",
        scope=REAL_SCOPE,
        record_type="core.Record",
        title="t",
        key=key,
        psets={},
    )
    with confidentiality.system_view(), intent_scope(intent), open_uow(ledger.harness.db) as uow:
        return handle_create_record(uow, cmd).stream_id


def test_the_embedded_history_shows_a_hidden_reference_as_not_available(
    ledger: Ledger,  # noqa: F811
) -> None:
    hidden = ledger.hidden.ids["restricted"]
    named = make_record(ledger, "P123-INT-T04-A", Intent(toward=IntentToward(target=hidden)))
    flat = make_record(ledger, "P123-INT-T04-B", Intent(toward=IntentToward(target=NOT_AVAILABLE)))
    bob = ledger.client("bob")
    a = [e.intent for e in bob.history(named)]
    b = [e.intent for e in bob.history(flat)]
    assert [i for i in a if i] == [i for i in b if i] and a != [None]
    assert hidden not in "".join(e.model_dump_json() for e in bob.history(named))
    assert hidden not in "".join(r.event.model_dump_json() for r in bob.activity(named).rows)
    assert hidden in "".join(e.model_dump_json() for e in ledger.client("ctl").history(named))
