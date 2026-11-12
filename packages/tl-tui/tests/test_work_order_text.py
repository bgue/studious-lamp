"""The work order text (P2-I4A T07b): cells, summary and page lines from the seed's two work
orders. No 32-hex id is printed; unset dates and hours print as the layout's empty value."""

from __future__ import annotations

import re

from fakes import FakeClient
from fakes_requisitions import PROJECT, seed_requisitions
from tl_mod_requisitions.api import WorkOrderRow
from tl_tui.layout import plain_lines
from tl_tui.text import EMPTY
from tl_tui.work_order_text import (
    WO_COLUMNS,
    WO_DROP,
    WO_RIGHT,
    wo_cells,
    wo_page,
    wo_summary,
)

HEX_ID = re.compile(r"[0-9a-f]{32}")


def _seeded() -> FakeClient:
    client = FakeClient()
    seed_requisitions(client)
    return client


def _rows() -> dict[str, WorkOrderRow]:
    rows = _seeded().list_work_orders(PROJECT).rows
    return {row.key: row for row in rows}


def test_the_columns_and_drops_name_the_cells() -> None:
    assert len(WO_COLUMNS) == 7
    assert set(WO_DROP) <= set(WO_COLUMNS)
    assert WO_RIGHT == ("Hours",)


def test_a_scheduled_order_has_its_dates_and_hours_as_cells() -> None:
    row = _rows()[f"{PROJECT}-WO-0001"]
    assert wo_cells(row) == (
        f"{PROJECT}-WO-0001",
        "Labor",
        "Scheduled",
        EMPTY,
        "2026-11-02",
        "2026-11-13",
        "48",
    )


def test_an_open_order_prints_unset_dates_and_hours_as_the_empty_value() -> None:
    row = _rows()[f"{PROJECT}-WO-0002"]
    cells = wo_cells(row)
    assert cells[3] == "uma"
    assert cells[4] == EMPTY
    assert cells[5] == EMPTY
    assert cells[6] == EMPTY


def test_the_summary_counts_and_names_the_filters() -> None:
    assert wo_summary(2, 2) == "2 work orders"
    assert wo_summary(1, 1) == "1 work order"
    assert wo_summary(4, 2, state="Scheduled") == "2 of 4 work orders, state Scheduled"
    assert wo_summary(2, 1, assigned_to="user:uma") == "1 of 2 work orders, assigned to uma"


def test_the_page_has_identity_state_dates_and_hours_and_no_hex_id() -> None:
    client = _seeded()
    detail = client.get_work_order(PROJECT, f"{PROJECT}-WO-0001")
    page = wo_page(detail)
    lines = plain_lines(page)
    assert lines[0] == f"{PROJECT}-WO-0001 · {PROJECT}-REQ-0001"
    assert lines[1] == "Scheduled"
    text = "\n".join(lines)
    assert "Planned start" in text and "2026-11-02" in text
    assert "Hours planned" in text and "48" in text
    assert not HEX_ID.search(text)


def test_the_page_of_an_unset_order_prints_the_empty_value_for_dates_and_hours() -> None:
    client = _seeded()
    detail = client.get_work_order(PROJECT, f"{PROJECT}-WO-0002")
    text = "\n".join(plain_lines(wo_page(detail)))
    assert "Planned start" in text and EMPTY in text
    assert "Hours actual" in text
    assert not HEX_ID.search(text)
