"""The schedule module over HTTP and through the client: reads, commands, who may do what (P1-I4).

Reads need `document.read` (a person and an agent hold it, nobody unsigned does). Defining,
publishing and voiding a schedule are the controller's (ADR-0015): a user is refused naming
`control.command.<Name>`. Opening a snapshot, starting its build and linking a record to an
activity are any signed-in person's. An agent proposes and never calls a command.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from harness import Harness
from tl_adapters.db import open_uow
from tl_api.client import ApiClient
from tl_api.tokens import add_token
from tl_core.auth import accounts, sessions
from tl_core.auth.password import prepare_password
from tl_mod_schedule import views
from tl_mod_schedule.errors import (
    ActivityNotFoundError,
    ScheduleNotFoundError,
    SnapshotStateError,
)
from tl_mod_schedule.handlers.activity import LinkActivity
from tl_mod_schedule.handlers.publish import PublishScheduleSnapshot
from tl_mod_schedule.handlers.schedules import DefineSchedule
from tl_mod_schedule.handlers.snapshots import OpenScheduleSnapshot, StartScheduleSnapshot
from tl_mod_schedule.testing import ScheduleWorld

PASSWORD = "correct horse battery"
P = "/projects/P123"
SCOPE = "project:P123"
CLIENT_BASE: dict[str, Any] = {"actor": "user:bob", "source": "test", "scope": SCOPE}


class Cast:
    """A user, a document controller, an admin and an agent, each with a client."""

    def __init__(self, harness: Harness) -> None:
        with harness.backend() as uow:
            for name, roles in (
                ("boss", ["admin"]),
                ("dora", ["user", "document_controller"]),
                ("bob", ["user"]),
            ):
                accounts.create_account(
                    uow, username=name, display_name=name, kind="person", roles=roles,
                    password=prepare_password(PASSWORD), by="svc:test",
                )  # fmt: skip
        self.tokens: dict[str, str] = {}
        self.clients: dict[str, TestClient] = {}
        for name in ("boss", "dora", "bob"):
            _, token = sessions.sign_in(harness.backend, username=name, password=PASSWORD)
            client = harness.client_for(None)
            client.headers.update({"Authorization": f"Bearer {token}"})
            self.tokens[name], self.clients[name] = token, client
        self.agent = TestClient(harness.app, raise_server_exceptions=False)
        self.agent.headers.update(
            {"Authorization": f"Bearer {add_token(harness.settings.tokens_path, 'agent:triage')}"}
        )
        self.anonymous = harness.client_for(None)

    def api(self, name: str) -> ApiClient:
        return ApiClient("http://testserver", self.tokens[name], http=self.clients[name])


@pytest.fixture
def cast(harness: Harness) -> Cast:
    return Cast(harness)


@pytest.fixture
def world(harness: Harness) -> ScheduleWorld:
    """Two published snapshots of MAIN a week apart; a record linked to A1230 and one to A1990."""
    made = ScheduleWorld(harness.db, harness.root / "objects")
    made.define()
    one, two = made.two_weeks()
    made.publish(one)
    made.__dict__["record_a"] = made.record("REC-A")
    made.__dict__["record_b"] = made.record("REC-B")
    made.link(made.__dict__["record_a"], "A1230")
    made.link(made.__dict__["record_b"], "A1990")
    made.publish(two)
    return made


def reads(world: ScheduleWorld) -> tuple[str, ...]:
    return (
        f"{P}/schedules",
        f"{P}/schedules/MAIN",
        f"{P}/schedules/MAIN/snapshots/2",
        f"{P}/schedules/MAIN/activities",
        f"{P}/schedules/MAIN/comparison",
        f"{P}/schedules/MAIN/look-ahead",
        f"{P}/schedules/MAIN/orphans",
        f"{P}/schedules/MAIN/activity-details/A1230",
        f"{P}/schedules/MAIN/activity-trends/A1230",
        f"{P}/schedules/MAIN/activity-resolutions/A1230",
        f"{P}/records/{world.__dict__['record_a']}/activity-links",
    )


def test_a_person_and_an_agent_can_read_and_nobody_unsigned_can(
    cast: Cast, world: ScheduleWorld
) -> None:
    for path in reads(world):
        assert cast.clients["bob"].get(path).status_code == 200, path
        assert cast.agent.get(path).status_code == 200, path
        assert cast.anonymous.get(path).status_code == 401, path


def test_the_schedule_and_its_snapshots(cast: Cast, world: ScheduleWorld) -> None:
    listed = cast.clients["bob"].get(f"{P}/schedules").json()
    assert [(s["code"], s["current_snapshot_number"], s["snapshot_count"]) for s in listed] == [
        ("MAIN", 2, 2)
    ]
    detail = cast.clients["bob"].get(f"{P}/schedules/MAIN").json()
    assert [(s["number"], s["state"], s["previous_number"]) for s in detail["snapshots"]] == [
        (2, "Published", 1),
        (1, "Superseded", None),
    ]
    paged = cast.clients["bob"].get(f"{P}/schedules/MAIN", params={"limit": 1, "offset": 1}).json()
    assert [s["number"] for s in paged["snapshots"]] == [1] and paged["snapshot_count"] == 2
    for bad in ({"limit": 0}, {"limit": 201}, {"offset": -1}):
        assert cast.clients["bob"].get(f"{P}/schedules/MAIN", params=bad).status_code == 422, bad
    via_client = cast.api("bob").get_schedule("P123", "MAIN", limit=1)
    assert [s.number for s in via_client.snapshots] == [2] and via_client.snapshot_count == 2
    one = cast.clients["bob"].get(f"{P}/schedules/MAIN/snapshots/1").json()
    assert one["key"] == "MAIN#1" and one["data_date"] == "2026-10-05T08:00"
    assert cast.clients["bob"].get(f"{P}/schedules/MAIN/snapshots/0").status_code == 422


def test_activities_are_filtered_and_paged(cast: Cast, world: ScheduleWorld) -> None:
    bob = cast.clients["bob"]
    page = bob.get(f"{P}/schedules/MAIN/activities", params={"limit": 3}).json()
    assert page["snapshot_number"] == 2 and len(page["rows"]) == 3 and page["total"] > 3
    critical = bob.get(f"{P}/schedules/MAIN/activities", params={"critical": "true"}).json()
    assert critical["total"] and all(r["critical"] for r in critical["rows"])
    found = bob.get(f"{P}/schedules/MAIN/activities", params={"q": "a1230", "snapshot": 1}).json()
    assert [r["activity_id"] for r in found["rows"]] == ["A1230"]
    assert found["rows"][0]["total_float_hr"] == 72.0  # 9 days of 8 hours
    assert bob.get(f"{P}/schedules/MAIN/activities", params={"limit": 5000}).status_code == 422
    assert bob.get(f"{P}/schedules/MAIN/activities", params={"offset": -1}).status_code == 422


def test_the_comparison_shows_the_shifts_and_the_erosion(cast: Cast, world: ScheduleWorld) -> None:
    got = cast.clients["bob"].get(f"{P}/schedules/MAIN/comparison").json()
    assert (got["old"]["number"], got["new"]["number"], got["data_date_shift_days"]) == (1, 2, 7)
    erosion = {c["activity_id"]: (c["old_days"], c["new_days"]) for c in got["float_changes"]}
    assert erosion["A1230"] == (9.0, 4.0)
    assert [b["activity_id"] for b in got["added"]] == ["A2500"]
    assert [b["activity_id"] for b in got["removed"]] == ["A1990"]
    cut = cast.clients["bob"].get(f"{P}/schedules/MAIN/comparison", params={"limit": 1}).json()
    assert cut["cut"] is True and len(cut["float_changes"]) == 1
    assert cut["totals"] == got["totals"]
    backwards = cast.clients["bob"].get(
        f"{P}/schedules/MAIN/comparison", params={"new": 1, "old": 2}
    )
    assert backwards.json()["data_date_shift_days"] == -7


def test_the_look_ahead_the_trend_and_the_activity(cast: Cast, world: ScheduleWorld) -> None:
    bob = cast.clients["bob"]
    ahead = bob.get(f"{P}/schedules/MAIN/look-ahead", params={"weeks": 6}).json()
    assert (ahead["window_start"], ahead["weeks"]) == ("2026-10-12", 6)
    assert bob.get(f"{P}/schedules/MAIN/look-ahead", params={"weeks": 0}).status_code == 422
    assert bob.get(f"{P}/schedules/MAIN/look-ahead", params={"weeks": 27}).status_code == 422
    trend = bob.get(f"{P}/schedules/MAIN/activity-trends/A1230").json()
    assert [(t["snapshot_number"], t["total_float_days"]) for t in trend] == [(1, 9.0), (2, 4.0)]
    detail = bob.get(f"{P}/schedules/MAIN/activity-details/A1230").json()
    assert [r["pred_activity_id"] for r in detail["predecessors"]] == ["A1220"]


def test_a_link_resolves_to_the_current_snapshot_and_as_of_the_earlier_one(
    cast: Cast, world: ScheduleWorld
) -> None:
    bob = cast.clients["bob"]
    base = f"{P}/schedules/MAIN/activity-resolutions/A1230"
    now = bob.get(base).json()
    assert (now["state"], now["snapshot_number"], now["data_date"]) == (
        "current", 2, "2026-10-12T08:00",
    )  # fmt: skip
    then = bob.get(base, params={"as_of": "2026-10-08"}).json()
    assert (then["state"], then["snapshot_number"]) == ("as_of", 1)
    assert then["activity"]["total_float_hr"] == 72.0 and now["activity"]["total_float_hr"] == 32.0
    assert bob.get(base, params={"as_of": "1"}).json()["snapshot_number"] == 1
    assert bob.get(base, params={"as_of": "2026-01-01"}).json()["state"] == "no_snapshot"
    for shaped in ("2026-02-30", "2026-10-12T25:99", "0000-01-01"):  # not dates: names nothing
        answer = bob.get(base, params={"as_of": shaped})
        assert answer.status_code == 200 and answer.json()["state"] == "no_snapshot", shaped
    gone = bob.get(f"{P}/schedules/MAIN/activity-resolutions/A1990").json()
    assert (gone["state"], gone["snapshot_number"]) == ("orphaned", 2)
    links = bob.get(f"{P}/records/{world.__dict__['record_b']}/activity-links").json()
    assert [(link["ref_key"], link["status"]) for link in links] == [("MAIN/A1990", "stale")]
    orphans = bob.get(f"{P}/schedules/MAIN/orphans").json()
    assert [(o["activity_id"], o["from_id"]) for o in orphans] == [
        ("A1990", world.__dict__["record_b"])
    ]


def test_unknown_things_are_the_modules_errors(cast: Cast, world: ScheduleWorld) -> None:
    bob = cast.clients["bob"]
    for path, status, code in (
        (f"{P}/schedules/NOPE", 404, "schedule_not_found"),
        (f"{P}/schedules/MAIN/snapshots/9", 404, "snapshot_not_found"),
        (f"{P}/schedules/MAIN/activity-details/NOPE", 404, "activity_not_found"),
        (f"{P}/schedules/MAIN/activity-trends/NOPE", 404, "activity_not_found"),
        ("/projects/P999/schedules/MAIN", 404, "schedule_not_found"),
    ):
        got = bob.get(path)
        assert (got.status_code, got.json()["error"]) == (status, code), path


def test_the_client_returns_what_the_embedded_views_return(
    harness: Harness, cast: Cast, world: ScheduleWorld
) -> None:
    api = cast.api("bob")
    with open_uow(harness.db, readonly=True) as uow:
        conn = uow.conn()
        assert api.list_schedules("P123") == views.schedule_views(conn, SCOPE)
        assert api.get_schedule("P123", "MAIN") == views.schedule_detail(conn, SCOPE, "MAIN")
        assert api.get_schedule_snapshot("P123", "MAIN", 1) == views.snapshot_view(
            conn, SCOPE, "MAIN", 1
        )
        assert api.list_activities("P123", "MAIN", critical=True, limit=10) == views.activity_page(
            conn, SCOPE, "MAIN", None, critical=True, limit=10
        )
        assert api.compare_snapshots("P123", "MAIN") == views.comparison(conn, SCOPE, "MAIN")
        assert api.get_look_ahead("P123", "MAIN", weeks=5) == views.look_ahead_view(
            conn, SCOPE, "MAIN", None, 5
        )
        assert api.list_orphaned_links("P123", "MAIN") == views.orphans(conn, SCOPE, "MAIN")
        assert api.get_schedule_activity("P123", "MAIN", "A1230", snapshot=1) == (
            views.activity_detail(conn, SCOPE, "MAIN", "A1230", 1)
        )
        assert api.get_activity_trend("P123", "MAIN", "A1230") == views.float_trend(
            conn, SCOPE, "MAIN", "A1230"
        )
        assert api.resolve_activity("P123", "MAIN", "A1230", as_of="2026-10-08") == (
            views.resolution(conn, SCOPE, "MAIN", "A1230", "2026-10-08")
        )
        record = world.__dict__["record_b"]
        assert api.list_activity_links("P123", record) == views.activity_links(conn, SCOPE, record)


def test_the_client_rebuilds_the_modules_errors(cast: Cast, world: ScheduleWorld) -> None:
    api = cast.api("bob")
    with pytest.raises(ScheduleNotFoundError):
        api.get_schedule("P123", "NOPE")
    with pytest.raises(ActivityNotFoundError):
        api.get_schedule_activity("P123", "MAIN", "NOPE")
    world.define("OTHER")
    world.open_snapshot("OTHER")
    with pytest.raises(SnapshotStateError):
        api.list_activities("P123", "OTHER", snapshot=1)


def test_an_activity_id_with_a_slash_is_reachable(cast: Cast, world: ScheduleWorld) -> None:
    got = cast.clients["bob"].get(f"{P}/schedules/MAIN/activity-resolutions/A1%2F230")
    assert got.status_code == 200 and got.json()["state"] == "unknown_activity"
    api = cast.api("bob")
    assert api.resolve_activity("P123", "MAIN", "A1/230").state == "unknown_activity"
    assert (
        cast.clients["bob"].get(f"{P}/schedules/MAIN/activity-details/A1%2F230").status_code == 404
    )


# --- who may do what ---------------------------------------------------------------------------

CONTROLLING = ("DefineSchedule", "PublishScheduleSnapshot", "VoidScheduleSnapshot")
OPEN = ("OpenScheduleSnapshot", "StartScheduleSnapshot", "LinkActivity")


def run(client: TestClient, name: str) -> tuple[int, str]:
    response = client.post(f"/commands/{name}", json={"scope": SCOPE})
    return response.status_code, str(response.json().get("message", ""))


def test_a_user_is_refused_the_controlling_commands_naming_their_action(cast: Cast) -> None:
    for name in CONTROLLING:
        status, message = run(cast.clients["bob"], name)
        assert status == 403 and f"control.command.{name}" in message, (name, status, message)


def test_a_controller_and_an_admin_pass_the_access_check(cast: Cast) -> None:
    for who in ("dora", "boss"):
        for name in CONTROLLING + OPEN:
            assert run(cast.clients[who], name)[0] != 403, (who, name)
    for name in OPEN:
        assert run(cast.clients["bob"], name)[0] != 403, name


def test_importing_cost_figures_is_the_admins_alone(cast: Cast) -> None:
    for who in ("bob", "dora"):
        status, message = run(cast.clients[who], "ImportCostSnapshot")
        assert status == 403 and "admin.command.ImportCostSnapshot" in message, who
    assert run(cast.clients["boss"], "ImportCostSnapshot")[0] != 403


def test_an_agent_proposes_and_never_calls_a_schedule_or_cost_command(cast: Cast) -> None:
    for name in (*CONTROLLING, *OPEN, "ImportCostSnapshot"):
        response = cast.agent.post(f"/commands/{name}", json={"scope": SCOPE})
        assert response.status_code == 403, name
        assert response.json()["error"] == "agent_must_propose", name


def test_a_snapshot_is_made_and_published_over_http(
    harness: Harness, cast: Cast, world: ScheduleWorld
) -> None:
    """A controller defines, a user opens and starts, the worker builds, a controller publishes."""
    dora, bob = cast.api("dora"), cast.api("bob")
    defined = dora.define_schedule(
        DefineSchedule(**CLIENT_BASE, code="LOOK", name="Look-ahead", schedule_type="look_ahead")
    )
    assert defined.key == "LOOK"
    schedule_id = defined.stream_id
    opened = bob.open_schedule_snapshot(
        OpenScheduleSnapshot(**CLIENT_BASE, schedule_id=schedule_id)
    )
    assert opened.key == "LOOK#1"
    from tl_xer.synth import make_xer, week_pair

    world.attach_xer(opened.stream_id, make_xer(week_pair()[0]))
    bob.start_schedule_snapshot(StartScheduleSnapshot(**CLIENT_BASE, snapshot_id=opened.stream_id))
    world.work()
    assert bob.get_schedule_snapshot("P123", "LOOK", 1).state == "Valid"
    from tl_core.auth.errors import ForbiddenError

    publish = PublishScheduleSnapshot(**CLIENT_BASE, snapshot_id=opened.stream_id)
    with pytest.raises(ForbiddenError):
        bob.publish_schedule_snapshot(publish)
    dora.publish_schedule_snapshot(publish)
    assert bob.get_schedule("P123", "LOOK").current_snapshot_number == 1
    record = world.record("REC-C")
    bob.link_activity(
        LinkActivity(**CLIENT_BASE, from_id=record, schedule_id=schedule_id, activity_id="A1230")
    )
    [link] = bob.list_activity_links("P123", record)
    assert link.resolution.state == "current"
