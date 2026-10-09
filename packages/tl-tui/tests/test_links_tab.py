"""Links tab: row text, grouping, row actions, following (P0-I3-T13; brief 7.4, sketch 12)."""

from __future__ import annotations

from typing import Any

from fakes import FakeClient
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from textual.widgets import DataTable, Input, TabbedContent
from tl_core.links.expected import ExpectedLink, MissingLink
from tl_core.services.link_queries import LinkView
from tl_tui.app import TlApp
from tl_tui.widgets.footer import TlFooter
from tl_tui.widgets.links_tab import (
    LinksTab,
    build_rows,
    group_title,
    missing_line,
    pin_text,
    status_text,
)
from tl_tui.widgets.record_view import RecordView


def view(**kw: Any) -> LinkView:
    data: dict[str, Any] = {
        "link_id": "L1",
        "direction": "out",
        "relation": "references",
        "label": "references",
        "other_id": "O1",
        "other_key": "FV-1002",
        "other_title": "Manual valve",
        "other_type": "core.Record",
        "other_status": "Design",
        "other_voided": False,
        "status": "active",
        "pin": None,
        "note": None,
        "source": "manual",
        "confidence": None,
        "reason": None,
        "declined": False,
        "verified_by": None,
        "verified_at": None,
        "created_at": "2026-10-09T10:00:00+00:00",
        "version": 1,
    }
    data.update(kw)
    return LinkView(**data)


# --- pure functions -----------------------------------------------------------------------------


def test_status_text_per_status() -> None:
    assert status_text(view()) == "active"
    assert status_text(view(verified_by="user:qa")) == "✓ verified"
    assert status_text(view(status="stale")) == "! stale"
    assert status_text(view(status="broken")) == "✗ broken"
    assert status_text(view(status="suggested", confidence=0.82)) == "? suggested (0.82)"
    assert status_text(view(status="suggested")) == "? suggested"
    assert status_text(view(status="retracted")) == "retracted"
    assert status_text(view(status="retracted", declined=True)) == "declined"


def test_pin_text() -> None:
    assert pin_text(view()) == "floating"
    assert pin_text(view(pin="C")) == "▪ C"


def test_group_title() -> None:
    assert group_title("raised against", 2) == "▾ raised against (2)"


def test_missing_line_shows_the_rule() -> None:
    plain = MissingLink(
        expectation=ExpectedLink(relation="requires", label="permit-to-work", by_state="Issued"),
        found=0,
        needed=1,
    )
    assert missing_line(plain) == ("! expected but missing: permit-to-work (rule: requires@Issued)")
    several = MissingLink(
        expectation=ExpectedLink(relation="references", min_count=3), found=1, needed=3
    )
    assert missing_line(several) == "! expected but missing: references (rule: references, 1 of 3)"


def test_rows_are_grouped_by_direction_and_relation_with_suggestions_last() -> None:
    rows = build_rows(
        [
            view(link_id="A", other_key="K-1", other_title="One", pin="C", note="n"),
            view(link_id="B", other_key="K-2", other_title="Two", verified_by="u"),
            view(
                link_id="C",
                direction="in",
                relation="blocks",
                label="blocked by",
                other_key="K-3",
                other_title="Three",
                status="stale",
            ),
            view(
                link_id="D",
                relation="requires",
                label="requires",
                other_key=None,
                other_title="No key",
                status="suggested",
                confidence=0.5,
            ),
        ]
    )
    assert [(r.link_id, r.cells) for r in rows] == [
        (None, ("▾ references (2)", "", "", "", "", "")),
        ("A", ("", "K-1", "One", "active", "▪ C", "n")),
        ("B", ("", "K-2", "Two", "✓ verified", "floating", "")),
        (None, ("▾ blocked by (1)", "", "", "", "", "")),
        ("C", ("", "K-3", "Three", "! stale", "floating", "")),
        (None, ("▾ suggested (1)", "", "", "", "", "")),
        ("D", ("requires", "—", "No key", "? suggested (0.50)", "floating", "")),
    ]


def test_no_links_gives_no_rows() -> None:
    assert build_rows([]) == []


# --- the tab inside the record view ------------------------------------------------------------


def test_the_tab_lists_links_both_ways_and_the_missing_expected_link() -> None:
    client = FakeClient.with_valve_example()
    client.seed_link("FV-1001", "FV-1002", "raised_against", pin="B", note="from site")
    client.seed_link("FV-1003", "FV-1001", "blocks")
    app = TlApp(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("enter")  # open FV-1001
        await pilot.pause()
        await pilot.press("3")
        await pilot.pause()
        assert app.query_one(TabbedContent).active == "tab-links"
        text = screen_text(app)
        assert "▾ raised against (1)" in text and "FV-1002" in text and "▪ B" in text
        assert "▾ blocked by (1)" in text and "FV-1003" in text
        assert "! expected but missing: data sheet (rule: references@Installed)" in text

    run_pilot(app, scenario, size=(130, 40))


def test_an_unlinked_record_shows_the_hint() -> None:
    client = FakeClient.with_valve_example()
    app = TlApp(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("3")
        await pilot.pause()
        tab = app.query_one(LinksTab)
        assert tab.text == "No links yet. Press l to link this record."
        text = screen_text(app)
        assert "No links yet. Press l to link this record." in text
        assert "! expected but missing: data sheet" in text
        assert tab.highlighted_other() is None

    run_pilot(app, scenario, size=(130, 40))


def test_the_header_shows_link_badges_and_the_state_time() -> None:
    client = FakeClient.with_valve_example()
    client.seed_link("FV-1001", "FV-1002")
    client.seed_link("FV-1003", "FV-1001", status="suggested")
    client.seed_link("FV-1001", "FV-1003", "requires", status="stale")
    app = TlApp(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        text = screen_text(app)
        assert "1 links" in text and "1 stale" in text and "1 suggested" in text
        assert "since 2026-10-09" in text

    run_pilot(app, scenario, size=(140, 40))


def test_enter_follows_the_highlighted_link_and_extends_the_trail() -> None:
    client = FakeClient.with_valve_example()
    client.seed_link("FV-1001", "FV-1002")
    app = TlApp(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("3")
        await pilot.pause()
        app.query_one("#links-table", DataTable).focus()
        await pilot.press("down", "enter")  # past the group header onto the link row
        await pilot.pause()
        await pilot.pause()
        assert app.query_one(RecordView).key == "FV-1002"
        assert app.history.trail() == "FV-1001 › FV-1002"
        await pilot.press("alt+left")
        await pilot.pause()
        await pilot.pause()
        assert app.query_one(RecordView).key == "FV-1001"

    run_pilot(app, scenario, size=(130, 40))


def _on_first_link(app: TlApp, pilot: Pilot[Any]) -> Any:
    async def go() -> None:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("3")
        await pilot.pause()
        app.query_one("#links-table", DataTable).focus()
        await pilot.press("down")
        await pilot.pause()

    return go()


def test_a_verifies_and_the_status_updates() -> None:
    client = FakeClient.with_valve_example()
    link_id = client.seed_link("FV-1001", "FV-1002")
    app = TlApp(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await _on_first_link(app, pilot)
        await pilot.press("v")
        await pilot.pause()
        await pilot.pause()
        assert client._links[link_id]["verified_by"] == "user:dev"  # pyright: ignore[reportPrivateUsage]
        assert "✓ verified" in screen_text(app)
        assert "Verified link to FV-1002" in app.query_one(TlFooter).status

    run_pilot(app, scenario, size=(130, 40))


def test_a_accepts_a_suggestion_and_d_declines_with_an_optional_reason() -> None:
    client = FakeClient.with_valve_example()
    first = client.seed_link("FV-1001", "FV-1002", status="suggested")
    second = client.seed_link("FV-1001", "FV-1003", "requires", status="suggested")
    app = TlApp(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await _on_first_link(app, pilot)
        await pilot.press("a")
        await pilot.pause()
        await pilot.pause()
        links = client._links  # pyright: ignore[reportPrivateUsage]
        assert links[first]["status"] == "active" and links[second]["status"] == "suggested"
        app.query_one("#links-table", DataTable).focus()
        await pilot.press("down", "down")  # the remaining suggestion
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        app.screen.query_one("#prompt-input", Input).value = "unrelated"
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()
        assert links[second]["status"] == "retracted" and links[second]["declined"] is True
        assert links[second]["reason"] == "unrelated"

    run_pilot(app, scenario, size=(130, 40))


def test_u_repins_through_a_prompt_and_a_blank_pin_floats() -> None:
    client = FakeClient.with_valve_example()
    link_id = client.seed_link("FV-1001", "FV-1002", pin="B")
    app = TlApp(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await _on_first_link(app, pilot)
        await pilot.press("u")
        await pilot.pause()
        prompt = app.screen.query_one("#prompt-input", Input)
        assert prompt.value == "B"
        prompt.value = "C"
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()
        links = client._links  # pyright: ignore[reportPrivateUsage]
        assert links[link_id]["pin"] == "C"
        app.query_one("#links-table", DataTable).focus()
        await pilot.press("down")
        await pilot.press("u")
        await pilot.pause()
        app.screen.query_one("#prompt-input", Input).value = ""
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()
        assert links[link_id]["pin"] is None

    run_pilot(app, scenario, size=(130, 40))


def test_x_retracts_with_a_required_reason() -> None:
    client = FakeClient.with_valve_example()
    link_id = client.seed_link("FV-1001", "FV-1002")
    app = TlApp(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await _on_first_link(app, pilot)
        await pilot.press("x")
        await pilot.pause()
        await pilot.press("enter")  # empty: refused, the prompt stays
        await pilot.pause()
        assert "Required" in screen_text(app)
        app.screen.query_one("#prompt-input", Input).value = "entered in error"
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()
        links = client._links  # pyright: ignore[reportPrivateUsage]
        assert links[link_id]["status"] == "retracted"
        assert links[link_id]["reason"] == "entered in error"
        assert "Retracted link to FV-1002" in app.query_one(TlFooter).status

    run_pilot(app, scenario, size=(130, 40))


def test_a_refused_action_shows_the_error_and_keeps_the_tab() -> None:
    client = FakeClient.with_valve_example()
    client.seed_link("FV-1001", "FV-1002")  # active: cannot be accepted
    app = TlApp(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await _on_first_link(app, pilot)
        await pilot.press("a")
        await pilot.pause()
        assert "not allowed" in app.query_one(TlFooter).status
        assert "FV-1002" in screen_text(app)

    run_pilot(app, scenario, size=(130, 40))


def test_an_action_on_a_group_header_asks_for_a_link() -> None:
    client = FakeClient.with_valve_example()
    client.seed_link("FV-1001", "FV-1002")
    app = TlApp(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("3")
        await pilot.pause()
        app.query_one("#links-table", DataTable).focus()
        await pilot.press("v")  # the cursor is on the group header
        await pilot.pause()
        assert "Highlight a link first" in app.query_one(TlFooter).status

    run_pilot(app, scenario, size=(130, 40))


def test_capital_r_adds_the_highlighted_other_record_to_the_tray() -> None:
    client = FakeClient.with_valve_example()
    client.seed_link("FV-1001", "FV-1002")
    app = TlApp(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await _on_first_link(app, pilot)
        tab = app.query_one(LinksTab)
        other = tab.highlighted_other()
        assert other is not None and other["key"] == "FV-1002"
        await pilot.press("R")
        await pilot.pause()
        assert [i.key for i in app.tray.items] == ["FV-1002"]
        assert "Added FV-1002 to the tray (1)" in app.query_one(TlFooter).status

    run_pilot(app, scenario, size=(130, 40))
