"""The punch fake (`fakes_punch.py`): seed counts, each filter, the counts and the command door."""

from __future__ import annotations

import pytest
from fakes import FakeClient
from fakes_punch import seed_punch
from tl_core.auth.errors import ForbiddenError
from tl_core.services.errors import RecordNotFoundError
from tl_mod_quality.commands import ClearPunchItem, RaisePunchItem

PROJECT = "P123"
ACTOR = "user:uma"


@pytest.fixture
def client() -> FakeClient:
    fake = FakeClient()
    seed_punch(fake, PROJECT)
    return fake


def keys(page: object) -> list[str]:
    return [row.key for row in page.rows]  # pyright: ignore[reportAttributeAccessIssue]


def test_seed_makes_six_items_one_overdue_one_from_a_source(client: FakeClient) -> None:
    page = client.list_punch_items(PROJECT)
    assert page.total == len(page.rows) == 6
    overdue = client.list_punch_items(PROJECT, overdue=True)
    assert keys(overdue) == ["P123-PUN-0001"]
    from_source = client.list_punch_items(PROJECT, from_key="P123-IWP-0001")
    assert keys(from_source) == ["P123-PUN-0002"]
    assert from_source.rows[0].source_key == "P123-IWP-0001"


def test_counts_by_state(client: FakeClient) -> None:
    assert client.get_punch_counts(PROJECT) == {
        "Open": 3,
        "Cleared": 1,
        "Verified": 1,
        "Void": 1,
    }
    assert client.get_punch_counts("NOPE") == {"Open": 0, "Cleared": 0, "Verified": 0, "Void": 0}


def test_each_filter_narrows(client: FakeClient) -> None:
    assert keys(client.list_punch_items(PROJECT, state="Open")) == [
        "P123-PUN-0001",
        "P123-PUN-0002",
        "P123-PUN-0003",
    ]
    assert keys(client.list_punch_items(PROJECT, state="Void")) == ["P123-PUN-0006"]
    assert keys(client.list_punch_items(PROJECT, area="L2")) == ["P123-PUN-0001", "P123-PUN-0005"]
    assert keys(client.list_punch_items(PROJECT, system="Electrical")) == [
        "P123-PUN-0004",
        "P123-PUN-0005",
    ]
    assert keys(client.list_punch_items(PROJECT, assignee="Okafor")) == [
        "P123-PUN-0002",
        "P123-PUN-0005",
    ]
    assert keys(client.list_punch_items(PROJECT, category="A")) == [
        "P123-PUN-0001",
        "P123-PUN-0006",
    ]
    assert keys(client.list_punch_items(PROJECT, state="Open", category="B")) == [
        "P123-PUN-0002",
        "P123-PUN-0003",
    ]
    assert keys(client.list_punch_items(PROJECT, from_key="P123-IWP-9999")) == []


def test_total_counts_the_matches_before_the_limit(client: FakeClient) -> None:
    page = client.list_punch_items(PROJECT, limit=2)
    assert len(page.rows) == 2 and page.total == 6
    assert keys(page) == ["P123-PUN-0001", "P123-PUN-0002"]


def test_a_missing_key_raises_the_not_found_error(client: FakeClient) -> None:
    detail = client.get_punch_item(PROJECT, "P123-PUN-0004")
    assert detail.row.state == "Cleared" and detail.cleared_by == "user:uma"
    with pytest.raises(RecordNotFoundError) as missing:
        client.get_punch_item(PROJECT, "P123-PUN-9999")
    assert "P123-PUN-9999" not in str(missing.value)


def test_a_command_is_recorded_and_its_name_is_checked(client: FakeClient) -> None:
    cmd = RaisePunchItem(actor=ACTOR, source="tui", scope=f"project:{PROJECT}", subject="New")
    result = client.quality_command("RaisePunchItem", cmd)
    assert result.stream_id == "PUN-1"
    assert client.punch_commands == [cmd]
    with pytest.raises(ForbiddenError):
        client.quality_command("NoSuchCommand", cmd)
    clear = ClearPunchItem(
        actor=ACTOR, source="tui", scope=f"project:{PROJECT}", punch_item="PUN-1", note="Done"
    )
    with pytest.raises(ForbiddenError):
        client.quality_command("RaisePunchItem", clear)  # a command of another class
    assert len(client.punch_commands) == 1
