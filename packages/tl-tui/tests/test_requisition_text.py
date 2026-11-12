"""The requisition log and page text (P2-I4A T07a): cells, summary and page lines for each kind."""

from __future__ import annotations

import re

from fakes import FakeClient
from fakes_requisitions import PROJECT, seed_requisitions
from tl_tui.layout import Prop, plain_lines
from tl_tui.requisition_text import (
    REQ_COLUMNS,
    REQ_DROP,
    REQ_RIGHT,
    req_cells,
    req_page,
    req_summary,
)

HEX32 = re.compile(r"[0-9a-f]{32}")
KIND_WORDS = {"labour", "material", "general", "scaffold"}


def seeded() -> FakeClient:
    client = FakeClient()
    seed_requisitions(client)
    return client


def rows() -> list:
    return list(seeded().list_requisitions(PROJECT).rows)


def test_columns_and_drops_are_named() -> None:
    assert REQ_COLUMNS == ("Number", "Subject", "Kind", "State", "Priority", "Need by", "Requester")
    assert REQ_DROP == ("Requester", "Need by", "Priority")
    assert REQ_RIGHT == ()


def test_cells_for_each_kind() -> None:
    cells = {row.key: req_cells(row) for row in rows()}
    assert len(cells) == 5
    assert all(len(c) == len(REQ_COLUMNS) for c in cells.values())
    kinds = [c[2] for c in cells.values()]
    assert kinds == ["labour", "labour", "material", "general", "scaffold"]
    first = cells[f"{PROJECT}-REQ-0001"]
    assert first[0] == f"{PROJECT}-REQ-0001"
    assert first[1] == "Requisition 1"
    assert first[3] == "Approved"
    assert first[4] == "Normal"
    assert first[5] == "2026-11-20"
    assert first[6] == "uma"


def test_summary_lines() -> None:
    assert req_summary(5, 5) == "5 requisitions"
    assert req_summary(1, 1) == "1 requisition"
    assert req_summary(7, 3, state="Requested") == "3 of 7 requisitions, state Requested"
    assert req_summary(5, 1, kind="labor") == "1 of 5 requisitions, kind labour"


def test_page_for_each_kind() -> None:
    client = seeded()
    expected_fields = {
        "REQ-0001": ["Craft", "Headcount", "Start date"],
        "REQ-0003": ["Item", "Quantity", "Uom"],
        "REQ-0004": ["General type", "Description"],
        "REQ-0005": ["Area", "Bays"],
    }
    for n in (1, 3, 4, 5):
        key = f"{PROJECT}-REQ-{n:04d}"
        page = req_page(client.get_requisition(PROJECT, key))
        assert page.identity == f"{key} · Requisition {n}"
        lines = plain_lines(page)
        assert lines[0] == page.identity
        detail = next(s for s in page.sections if s.heading == "Detail")
        labels = [item.label for item in detail.items if isinstance(item, Prop)]
        assert labels == expected_fields[f"REQ-{n:04d}"]
    labour = req_page(client.get_requisition(PROJECT, f"{PROJECT}-REQ-0002"))
    assert "Work order" in [s.heading for s in labour.sections]
    assert "none yet" in plain_lines(labour)


def test_work_order_section_names_the_order() -> None:
    page = req_page(seeded().get_requisition(PROJECT, f"{PROJECT}-REQ-0001"))
    work = next(s for s in page.sections if s.heading == "Work order")
    assert work.items == (f"{PROJECT}-WO-0001 · Scheduled",)


def test_no_id_and_no_american_spelling_in_shown_text() -> None:
    client = seeded()
    texts: list[str] = []
    for row in rows():
        texts.extend(req_cells(row))
    for row in rows():
        page = req_page(client.get_requisition(PROJECT, row.key))
        texts.extend(plain_lines(page))
    texts.append(req_summary(5, 1, kind="labor", state="Requested"))
    for text in texts:
        assert not HEX32.search(text), text
        assert "labor" not in text.lower(), text
    assert any("labour" in text for text in texts)


def test_technical_mode_adds_the_id_only_there() -> None:
    client = seeded()
    detail = client.get_requisition(PROJECT, f"{PROJECT}-REQ-0001")
    plain = plain_lines(req_page(detail, technical=False))
    technical = plain_lines(req_page(detail, technical=True))
    assert not any(line.startswith("Id") for line in plain)
    assert any(line.startswith("Id") and "REQ-1" in line for line in technical)
