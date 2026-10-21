"""What the correspondence screen shows, as text (P1-I5)."""

from __future__ import annotations

from fakes import FakeClient
from fakes_correspondence import seed_correspondence
from tl_mod_correspondence.views import SuggestionView
from tl_tui import correspondence_text as ct


def seeded() -> FakeClient:
    client = FakeClient()
    seed_correspondence(client)
    return client


def test_a_register_row_has_eight_cells_and_marks_a_source_line() -> None:
    lines = seeded().list_correspondence("P123")
    cells = {line.number: ct.register_cells(line) for line in lines}
    assert all(len(c) == len(ct.REGISTER_COLUMNS) for c in cells.values())
    assert cells["P123-TRN-0001"][-1] == "Isometrics [transmittal]"
    assert cells["P123-TRN-0001"][3] == "Transmittal"  # the domain label, not its key
    assert cells["P123-COR-0001"][2:4] == ("in", "-")


def test_a_clock_row_shows_the_days_left_and_its_length() -> None:
    [clock] = seeded().list_clocks("P123")
    assert ct.clock_cells(clock) == (
        "P123-COR-0003", "Running", "2026-11-02", "14", "14 cal", "response from them",
        "Reply expected",
    )  # fmt: skip
    assert ct.clock_cells(clock, technical=True)[0] == "P123-COR-0003-C01"
    over = clock.model_copy(update={"days_left": -3, "effective_state": "expired"})
    assert ct.left_text(over) == "-3"
    assert ct.left_text(clock.model_copy(update={"days_left": None})) == "-"


def test_the_item_panel_lists_clocks_and_the_suggestion_of_a_received_item() -> None:
    client = seeded()
    issued = ct.item_lines(client.get_correspondence("P123", "P123-COR-0003"))
    assert issued[0].startswith("P123-COR-0003  Issued  out")
    assert "delivery: stub" in issued
    assert any("running due 2026-11-02 left 14 (14 calendar days)" in x for x in issued)
    assert not any("P123-COR-0003-C01" in x or "P123-default@1" in x for x in issued)
    received = ct.item_lines(
        client.get_correspondence("P123", "P123-COR-0001"),
        client.get_correspondence_suggestion("P123", "P123-COR-0001"),
    )
    assert received[-1] == "suggestion: Letter (score 0): no keyword matched; the default domain"
    shown = ct.item_lines(client.get_correspondence("P123", "P123-COR-0003"), technical=True)
    assert any(x.strip().startswith("P123-COR-0003-C01 running due") for x in shown)
    assert "P123-default@1" in " ".join(shown) and "record ID-P123-COR-0003" in shown


def test_the_summary_and_the_mode_order() -> None:
    assert ct.summary_line("inbox", 1) == "1 item awaiting triage"
    assert ct.summary_line("clocks", 2, closed_too=True) == "2 all clocks"
    assert ct.summary_line("register", 0) == "0 lines in the register"
    assert [ct.next_mode(m) for m in ct.MODES] == ["inbox", "clocks", "register"]
    assert ct.next_mode("register", -1) == "clocks"
    assert (
        ct.suggestion_text(
            SuggestionView(domain=None, subtype=None, score=0, reasons=[], scores={})
        )
        == "no domain is defined"
    )
