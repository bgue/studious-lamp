"""`FakeClient` schedule and cost reads answer like the embedded client (P1-I4)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fakes import FakeClient
from tl_adapters.db import open_uow
from tl_adapters.sqlite.factory import SqliteUowFactory
from tl_adapters.sqlite.uow import create_schema
from tl_core.auth.errors import ForbiddenError
from tl_mod_cost.errors import CostCodeNotFoundError
from tl_mod_cost.testing import CostWorld, row
from tl_mod_schedule import registry
from tl_mod_schedule.errors import (
    ActivityNotFoundError,
    NoCurrentSnapshotError,
    ScheduleNotFoundError,
    SnapshotNotFoundError,
    SnapshotStateError,
)
from tl_mod_schedule.handlers.activity import LinkActivity
from tl_mod_schedule.handlers.publish import PublishScheduleSnapshot
from tl_mod_schedule.testing import BASE, ScheduleWorld
from tl_tui.client import ClientInterface
from tl_tui.embedded import EmbeddedClient

PROJECT = "P123"
COMMON: dict[str, Any] = {"actor": "user:kim", "source": "tui", "scope": "project:P123"}


@pytest.fixture
def both(tmp_path: Path) -> Iterator[tuple[ClientInterface, ClientInterface, ScheduleWorld]]:
    """An embedded client over a ledger with two published snapshots, and a fake holding them."""
    path = tmp_path / "tl.db"
    create_schema(path)
    world = ScheduleWorld(path, tmp_path / "objects")
    world.define()
    one, two = world.two_weeks()
    world.publish(one)
    for key, activity in (("REC-A", "A1230"), ("REC-B", "A1990")):
        world.link(world.record(key), activity)
    world.publish(two)
    world.define("EMPTY")
    world.open_snapshot("EMPTY")
    cost = CostWorld(path)
    cost.import_snapshot(
        [row("4210", "Piping", hours_budget=1000), row("4210-PIP", "Pipe", "4210", uom="m")],
        period="2026-06", as_of="2026-06-30",
    )  # fmt: skip
    cost.import_snapshot(
        [row("4210-PIP", hours_budget=600, hours_actual=150)], period="2026-07", as_of="2026-07-31"
    )
    factory = SqliteUowFactory(path)
    embedded = EmbeddedClient(factory, actor="user:kim")
    fake = FakeClient()
    for code in ("MAIN", "EMPTY"):
        detail = embedded.get_schedule(PROJECT, code)
        rows: dict[int, Any] = {}
        with open_uow(path, readonly=True) as uow:
            for shown in detail.snapshots:
                if shown.state in ("Valid", "Published", "Superseded"):
                    rows[shown.number] = (
                        registry.activities(uow.conn(), shown.id),
                        registry.relationships(uow.conn(), shown.id),
                    )
        fake.put_schedule(PROJECT, detail, rows)
    fake.put_look_ahead(PROJECT, "MAIN", embedded.get_look_ahead(PROJECT, "MAIN"))
    fake.put_orphans(PROJECT, "MAIN", embedded.list_orphaned_links(PROJECT, "MAIN"))
    for found in world.rows("SELECT DISTINCT from_id FROM cur_links"):
        record_id = str(found["from_id"])
        fake.put_activity_links(record_id, embedded.list_activity_links(record_id))
    for activity_id, as_of in (("A1230", None), ("A1230", "1"), ("A1990", None)):
        fake.put_resolution(
            PROJECT, "MAIN", activity_id, as_of,
            embedded.resolve_activity(PROJECT, "MAIN", activity_id, as_of=as_of),
        )  # fmt: skip
    fake.put_cost_snapshots(PROJECT, embedded.list_cost_snapshots(PROJECT))
    for item in embedded.list_cost_codes(PROJECT):
        fake.put_cost_code(PROJECT, embedded.get_cost_code(PROJECT, item.code))
    try:
        yield embedded, fake, world
    finally:
        factory.dispose()


READS = [
    ("schedules", lambda c: c.list_schedules(PROJECT)),
    ("another project", lambda c: c.list_schedules("OTHER")),
    ("one schedule", lambda c: c.get_schedule(PROJECT, "MAIN")),
    ("one snapshot", lambda c: c.get_schedule_snapshot(PROJECT, "MAIN", 1)),
    ("activities", lambda c: c.list_activities(PROJECT, "MAIN", limit=1000)),
    ("activities of snapshot 1", lambda c: c.list_activities(PROJECT, "MAIN", snapshot=1)),
    ("critical", lambda c: c.list_activities(PROJECT, "MAIN", critical=True)),
    ("not critical", lambda c: c.list_activities(PROJECT, "MAIN", critical=False)),
    ("by status", lambda c: c.list_activities(PROJECT, "MAIN", status="completed")),
    ("by text", lambda c: c.list_activities(PROJECT, "MAIN", q="pipe rack")),
    ("a page", lambda c: c.list_activities(PROJECT, "MAIN", limit=3, offset=2)),
    ("compare", lambda c: c.compare_snapshots(PROJECT, "MAIN")),
    ("compare backwards", lambda c: c.compare_snapshots(PROJECT, "MAIN", new=1, old=2)),
    ("compare cut", lambda c: c.compare_snapshots(PROJECT, "MAIN", limit=1)),
    ("an activity", lambda c: c.get_schedule_activity(PROJECT, "MAIN", "A1230")),
    (
        "an activity of the first",
        lambda c: c.get_schedule_activity(PROJECT, "MAIN", "A1990", snapshot=1),
    ),
    ("a trend", lambda c: c.get_activity_trend(PROJECT, "MAIN", "A1230")),
    ("a trend that ends", lambda c: c.get_activity_trend(PROJECT, "MAIN", "A1990")),
    ("look-ahead", lambda c: c.get_look_ahead(PROJECT, "MAIN")),
    ("orphans", lambda c: c.list_orphaned_links(PROJECT, "MAIN")),
    ("resolve now", lambda c: c.resolve_activity(PROJECT, "MAIN", "A1230")),
    ("resolve as of 1", lambda c: c.resolve_activity(PROJECT, "MAIN", "A1230", as_of="1")),
    ("resolve a gone one", lambda c: c.resolve_activity(PROJECT, "MAIN", "A1990")),
    ("cost snapshots", lambda c: c.list_cost_snapshots(PROJECT)),
    ("cost codes", lambda c: c.list_cost_codes(PROJECT)),
    ("cost children", lambda c: c.list_cost_codes(PROJECT, parent="4210")),
    ("cost text", lambda c: c.list_cost_codes(PROJECT, q="pipe")),
    ("cost limit", lambda c: c.list_cost_codes(PROJECT, limit=1)),
    ("a cost code", lambda c: c.get_cost_code(PROJECT, "4210-PIP")),
]


@pytest.mark.parametrize(("name", "read"), READS, ids=[n for n, _ in READS])
def test_a_read_is_the_same_on_both(
    both: tuple[ClientInterface, ClientInterface, ScheduleWorld], name: str, read: Any
) -> None:
    embedded, fake, _ = both
    assert read(fake) == read(embedded), name


def test_the_links_of_a_record_are_the_same_on_both(
    both: tuple[ClientInterface, ClientInterface, ScheduleWorld],
) -> None:
    embedded, fake, world = both
    record = world.rows("SELECT from_id FROM cur_links ORDER BY created_at")[0]["from_id"]
    links = embedded.list_activity_links(str(record))
    assert links and fake.list_activity_links(str(record)) == links


def test_unknowns_are_the_modules_errors_on_both(
    both: tuple[ClientInterface, ClientInterface, ScheduleWorld],
) -> None:
    embedded, fake, _ = both
    for client in (embedded, fake):
        with pytest.raises(ScheduleNotFoundError):
            client.get_schedule(PROJECT, "NOPE")
        with pytest.raises(SnapshotNotFoundError):
            client.get_schedule_snapshot(PROJECT, "MAIN", 9)
        with pytest.raises(SnapshotNotFoundError):
            client.compare_snapshots(PROJECT, "MAIN", new=1)  # nothing before the first
        with pytest.raises(ActivityNotFoundError):
            client.get_schedule_activity(PROJECT, "MAIN", "NOPE")
        with pytest.raises(ActivityNotFoundError):
            client.get_activity_trend(PROJECT, "MAIN", "NOPE")
        with pytest.raises(SnapshotStateError):
            client.list_activities(PROJECT, "EMPTY", snapshot=1)
        with pytest.raises(NoCurrentSnapshotError):
            client.list_activities(PROJECT, "EMPTY")
        with pytest.raises(CostCodeNotFoundError):
            client.get_cost_code(PROJECT, "9999")


def test_linking_and_publishing_are_commands_both_accept_and_publishing_is_a_controllers(
    both: tuple[ClientInterface, ClientInterface, ScheduleWorld],
) -> None:
    embedded, fake, world = both
    schedule_id = embedded.get_schedule(PROJECT, "MAIN").id
    record = world.record("REC-NEW")
    link = LinkActivity(**COMMON, from_id=record, schedule_id=schedule_id, activity_id="A1240")
    assert embedded.link_activity(link).stream_id
    assert fake.link_activity(link).stream_id
    assert [x.ref_key for x in embedded.list_activity_links(record)] == ["MAIN/A1240"]
    publish = PublishScheduleSnapshot(**COMMON, snapshot_id="whatever")
    with pytest.raises(ForbiddenError):  # kim holds no account: not a controller
        embedded.publish_schedule_snapshot(publish)
    fake.is_controller = False  # type: ignore[attr-defined]
    with pytest.raises(ForbiddenError):
        fake.publish_schedule_snapshot(publish)
    fake.is_controller = True  # type: ignore[attr-defined]
    fake.publish_schedule_snapshot(publish)
    assert fake.schedule_commands[-1] == publish  # type: ignore[attr-defined]
    assert BASE["scope"] == COMMON["scope"]
