"""The scaffold fake (`fakes_scaffold.py`): seed counts, each filter, the due list, the export."""

from __future__ import annotations

import pytest
from fakes import FakeClient
from fakes_scaffold import seed_scaffolds
from tl_core.services.errors import RecordNotFoundError
from tl_mod_scaffold.views import EXPORT_COLUMNS

PROJECT = "P123"
INSPECTED = "P123-SCF-0003"
IN_USE = "P123-SCF-0004"
MODIFY = "P123-SCF-0005"


@pytest.fixture
def client() -> FakeClient:
    fake = FakeClient()
    seed_scaffolds(fake, PROJECT)
    return fake


def keys(page: object) -> list[str]:
    return [row.key for row in page.rows]  # pyright: ignore[reportAttributeAccessIssue]


def test_seed_makes_five_scaffolds_in_key_order(client: FakeClient) -> None:
    page = client.list_scaffolds(PROJECT)
    assert page.total == len(page.rows) == 5
    assert keys(page) == [f"P123-SCF-{n:04d}" for n in range(1, 6)]
    assert [row.state for row in page.rows] == [
        "Designed",
        "Erecting",
        "Inspected",
        "In Use",
        "Modify",
    ]


def test_each_filter_narrows(client: FakeClient) -> None:
    assert keys(client.list_scaffolds(PROJECT, state="Designed")) == ["P123-SCF-0001"]
    assert keys(client.list_scaffolds(PROJECT, state="Requested")) == []
    assert keys(client.list_scaffolds(PROJECT, tag="green")) == [INSPECTED, IN_USE]
    assert keys(client.list_scaffolds(PROJECT, tag="red")) == [MODIFY]
    assert keys(client.list_scaffolds(PROJECT, state="In Use", tag="green")) == [IN_USE]
    assert keys(client.list_scaffolds(PROJECT, overdue=True)) == [INSPECTED, MODIFY]
    assert keys(client.list_scaffolds("NOPE")) == []


def test_total_counts_the_matches_before_the_limit(client: FakeClient) -> None:
    page = client.list_scaffolds(PROJECT, limit=2)
    assert len(page.rows) == 2 and page.total == 5
    assert keys(page) == ["P123-SCF-0001", "P123-SCF-0002"]


def test_a_missing_key_raises_the_not_found_error(client: FakeClient) -> None:
    with pytest.raises(RecordNotFoundError):
        client.get_scaffold(PROJECT, "P123-SCF-9999")


def test_the_detail_carries_the_inspections_oldest_first(client: FakeClient) -> None:
    detail = client.get_scaffold(PROJECT, MODIFY)
    assert detail.inspection_count == 2
    assert detail.modify_reason == "Cracked toe board"
    assert [item.result for item in detail.inspections] == ["pass", "fail"]


def test_the_due_list_drops_the_future_due_scaffold(client: FakeClient) -> None:
    due = client.list_scaffolds_due(PROJECT)
    assert [row.key for row in due] == [INSPECTED, MODIFY]
    assert IN_USE not in [row.key for row in due]


def test_the_export_text_starts_with_the_header_line(client: FakeClient) -> None:
    text = client.export_scaffolds(PROJECT)
    assert text.splitlines()[0] == ",".join(EXPORT_COLUMNS)
    assert len(text.splitlines()) == 1 + 5
    lines = client.export_scaffolds(PROJECT, fmt="jsonl").splitlines()
    assert len(lines) == 5


def test_an_unknown_export_format_or_state_is_a_value_error(client: FakeClient) -> None:
    with pytest.raises(ValueError):
        client.export_scaffolds(PROJECT, fmt="xml")
    with pytest.raises(ValueError):
        client.list_scaffolds(PROJECT, state="Nope")
