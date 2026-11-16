"""The permit fake (`fakes_permits.py`): seed counts, each filter, the total, the board, the missing
key and the command door."""

from __future__ import annotations

from typing import Any

import pytest
from fakes import FakeClient
from fakes_permits import seed_permits
from tl_core.auth.errors import ForbiddenError
from tl_core.services.errors import RecordNotFoundError
from tl_mod_permits.commands import ApprovePermit, RequestPermit
from tl_mod_permits.iso_commands import RecordGasTest

PROJECT = "P123"
ACTOR = "user:pam"


@pytest.fixture
def client() -> FakeClient:
    fake = FakeClient()
    seed_permits(fake, PROJECT)
    return fake


def test_the_seed_makes_eight_permits_three_isolations_and_three_gas_tests(
    client: FakeClient,
) -> None:
    page = client.list_permits(PROJECT)
    assert page.total == len(page.rows) == 8
    assert [row.state for row in page.rows] == [
        "Requested",
        "Approved",
        "Active",
        "Lapsed",
        "Suspended",
        "Handed back",
        "Closed",
        "Rejected",
    ]
    assert [row.key for row in page.rows if row.area is not None] == [
        "P123-PTW-0003",
        "P123-PTW-0004",
    ]
    isolations = client.list_isolations(PROJECT)
    assert isolations.total == len(isolations.rows) == 3
    assert [row.state for row in isolations.rows] == ["Applied", "Verified", "Removed"]
    gas = client.list_gas_tests(PROJECT, "P123-PTW-0003")
    assert len(gas) == 3
    assert gas[0].result == "pass"  # newest first


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"state": "Active"}, ["P123-PTW-0003"]),
        ({"state": "Lapsed"}, ["P123-PTW-0004"]),
        ({"permit_type": "hot_work"}, ["P123-PTW-0002", "P123-PTW-0007"]),
        ({"area": "A2"}, ["P123-PTW-0004"]),
        ({"holder": "Ann"}, ["P123-PTW-0004", "P123-PTW-0006"]),
        ({"state": "Closed", "holder": "Ann"}, []),
    ],
)
def test_each_permit_filter_narrows(
    client: FakeClient, kwargs: dict[str, Any], expected: list[str]
) -> None:
    page = client.list_permits(PROJECT, **kwargs)
    assert [row.key for row in page.rows] == expected
    assert page.total == len(expected)


def test_total_counts_the_matches_before_the_limit(client: FakeClient) -> None:
    page = client.list_permits(PROJECT, limit=3, offset=2)
    assert page.total == 8
    assert [row.key for row in page.rows] == ["P123-PTW-0003", "P123-PTW-0004", "P123-PTW-0005"]


def test_isolation_filters_narrow(client: FakeClient) -> None:
    assert [r.key for r in client.list_isolations(PROJECT, state="Verified").rows] == [
        "P123-ISL-0002"
    ]
    assert [r.key for r in client.list_isolations(PROJECT, energy="process").rows] == [
        "P123-ISL-0003"
    ]


def test_the_board_counts_equal_the_live_list(client: FakeClient) -> None:
    board = client.get_permit_board(PROJECT)
    live = [
        r for r in client.list_permits(PROJECT).rows if r.state in ("Lapsed", "Suspended", "Active")
    ]
    assert board.counts == {"Lapsed": 1, "Suspended": 1, "Active": 1}
    assert sum(board.counts.values()) == len(live) == sum(len(a.rows) for a in board.areas)
    assert [a.area for a in board.areas] == ["A1", "A2", None]
    assert board.areas[1].rows[0].state == "Lapsed"


def test_the_board_narrows_to_one_area(client: FakeClient) -> None:
    board = client.get_permit_board(PROJECT, area="A1")
    assert [a.area for a in board.areas] == ["A1"]
    assert board.counts == {"Lapsed": 0, "Suspended": 0, "Active": 1}


def test_a_missing_permit_or_isolation_raises_its_text(client: FakeClient) -> None:
    with pytest.raises(RecordNotFoundError, match="no permit"):
        client.get_permit(PROJECT, "P123-PTW-9999")
    with pytest.raises(RecordNotFoundError, match="no isolation"):
        client.get_isolation(PROJECT, "P123-ISL-9999")
    with pytest.raises(RecordNotFoundError, match="no permit"):
        client.list_gas_tests(PROJECT, "P123-PTW-9999")


def test_a_permit_with_no_gas_tests_lists_none(client: FakeClient) -> None:
    assert client.list_gas_tests(PROJECT, "P123-PTW-0001") == []


def test_permit_command_is_recorded_and_checked(client: FakeClient) -> None:
    approve = ApprovePermit(actor=ACTOR, source="tui", scope=f"project:{PROJECT}", permit="PTW-1")
    result = client.permit_command("ApprovePermit", approve)
    assert result.stream_id == "PTW-1"
    assert client.punch_commands[-1] is approve
    with pytest.raises(ForbiddenError, match="is not a permit command"):
        client.permit_command("PlanInspection", approve)  # a quality model, not a permit one
    request = RequestPermit(
        actor=ACTOR,
        source="tui",
        scope=f"project:{PROJECT}",
        permit_type="general",
        area="A1",
        location_text="Yard",
        work_description="Repair",
        holder="Rob",
        needed_from="2026-12-01",
        needed_until="2026-12-31",
    )
    with pytest.raises(ForbiddenError):
        client.permit_command("ApprovePermit", request)  # the wrong class for the name
    gas = RecordGasTest(
        actor=ACTOR,
        source="tui",
        scope=f"project:{PROJECT}",
        permit="PTW-3",
        instrument_text="MX6",
        o2_pct="20.9",
    )
    client.permit_command("RecordGasTest", gas)
    assert client.punch_commands[-1] is gas
