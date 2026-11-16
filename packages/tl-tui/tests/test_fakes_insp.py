"""The inspection fake (`fakes_insp.py`): seed counts, each filter, the total, the missing key and
the command door."""

from __future__ import annotations

from typing import Any

import pytest
from fakes import FakeClient
from fakes_insp import seed_inspections
from tl_core.auth.errors import ForbiddenError
from tl_core.services.errors import RecordNotFoundError
from tl_mod_quality import insp_views
from tl_mod_quality.commands import PlanInspection, ScheduleInspection

PROJECT = "P123"
ACTOR = "user:uma"


@pytest.fixture
def client() -> FakeClient:
    fake = FakeClient()
    seed_inspections(fake, PROJECT)
    return fake


def test_the_seed_makes_six_inspections_and_three_checklists(client: FakeClient) -> None:
    page = client.list_inspections(PROJECT)
    assert page.total == len(page.rows) == 6
    assert [row.state for row in page.rows] == [
        "Planned",
        "Scheduled",
        "Done",
        "Verified",
        "Cancelled",
        "Planned",
    ]
    checklists = client.list_checklists(PROJECT)
    assert checklists.total == len(checklists.rows) == 3
    assert [row.state for row in checklists.rows] == ["Draft", "Published", "Retired"]


def test_the_seed_returns_the_keys_in_key_order() -> None:
    fake = FakeClient()
    keys = seed_inspections(fake, PROJECT)
    assert keys == sorted(keys)
    assert keys == [row.key for row in fake.list_inspections(PROJECT).rows]


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({"state": "Planned"}, 2),
        ({"state": "Verified"}, 1),
        ({"point": "hold"}, 3),
        ({"area": "L2"}, 2),
        ({"inspector": "M. Okafor"}, 2),
        ({"subject": "P123-CWP-0001"}, 2),
        ({"for_key": "P123-IWP-0001"}, 1),
        ({"state": "Done", "point": "witness"}, 1),
        ({"state": "Done", "point": "hold"}, 0),
    ],
)
def test_each_filter_narrows_the_list_and_the_total(
    client: FakeClient, filters: dict[str, Any], expected: int
) -> None:
    page = client.list_inspections(PROJECT, **filters)
    assert page.total == len(page.rows) == expected


def test_the_limit_cuts_the_rows_but_not_the_total(client: FakeClient) -> None:
    page = client.list_inspections(PROJECT, limit=2)
    assert len(page.rows) == 2
    assert page.total == 6


def test_checklist_filters_narrow(client: FakeClient) -> None:
    assert client.list_checklists(PROJECT, state="Published").total == 1
    assert client.list_checklists(PROJECT, discipline="Mechanical").total == 2
    assert client.list_checklists(PROJECT, state="Draft", discipline="Piping").total == 0


def test_a_bad_state_or_point_is_the_views_value_error(client: FakeClient) -> None:
    with pytest.raises(ValueError, match=insp_views.MSG_STATE):
        client.list_inspections(PROJECT, state="Open")
    with pytest.raises(ValueError, match=insp_views.MSG_POINT):
        client.list_inspections(PROJECT, point="inspect")
    with pytest.raises(ValueError, match=insp_views.MSG_CHECKLIST_STATE):
        client.list_checklists(PROJECT, state="Open")


def test_a_missing_key_raises_the_one_text_for_each_kind(client: FakeClient) -> None:
    with pytest.raises(RecordNotFoundError, match="no inspection"):
        client.get_inspection(PROJECT, "P123-INS-9999")
    with pytest.raises(RecordNotFoundError, match="no checklist"):
        client.get_checklist(PROJECT, "P123-CHK-9999")
    with pytest.raises(RecordNotFoundError, match="no inspection"):
        client.get_inspection("OTHER", "P123-INS-0001")


def test_a_present_key_reads_its_detail(client: FakeClient) -> None:
    detail = client.get_inspection(PROJECT, "P123-INS-0003")
    assert detail.row.result == "Reject"
    assert detail.punch_keys == ["P123-PUN-0001"]
    assert client.get_checklist(PROJECT, "P123-CHK-0002").row.state == "Published"


def test_the_command_door_records_a_quality_command(client: FakeClient) -> None:
    plan = PlanInspection(
        actor=ACTOR,
        source="tui",
        scope=f"project:{PROJECT}",
        title="Flange make-up",
        subject_id="SUB-1",
        point="hold",
    )
    client.quality_command("PlanInspection", plan)
    schedule = ScheduleInspection(
        actor=ACTOR,
        source="tui",
        scope=f"project:{PROJECT}",
        inspection="INS-1",
        checklist="CHK-1",
        scheduled_for="2026-12-01",
        inspector="M. Okafor",
    )
    client.quality_command("ScheduleInspection", schedule)
    assert client.punch_commands == [plan, schedule]


def test_an_unknown_name_or_a_wrong_class_is_forbidden(client: FakeClient) -> None:
    plan = PlanInspection(
        actor=ACTOR,
        source="tui",
        scope=f"project:{PROJECT}",
        title="Flange make-up",
        subject_id="SUB-1",
        point="hold",
    )
    with pytest.raises(ForbiddenError, match="is not a quality command"):
        client.quality_command("NoSuchCommand", plan)
    with pytest.raises(ForbiddenError, match="is not a quality command"):
        client.quality_command("ScheduleInspection", plan)
    assert client.punch_commands == []
