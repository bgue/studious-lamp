"""``purge_due`` (V3-F4, D19): the retention boundary, who is purged, once, and the body table."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from forms_world import SCOPE, World
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_mod_forms import intake

RECEIVED = datetime(2026, 12, 1, 9, 0, 0, tzinfo=UTC)  # what ``World.stage_item`` writes
DAYS = 30


def purge(
    world: World,
    now: datetime,
    *,
    scope: str | None = None,
    viewer: cf.Viewer | None = None,
    limit: int = intake.BATCH,
) -> int:
    with open_uow(world.db) as uow:
        return intake.purge_due(
            uow, now, actor="user:ada", source="test", scope=scope, viewer=viewer, limit=limit
        )


def purged_events(world: World, item: str) -> int:
    return len(world.events(item, "IntakeItem.Purged"))


def test_an_item_is_purged_after_the_retention_window_and_not_before(world: World) -> None:
    code = world.stage_code(world.intake_template())
    item = world.stage_item(code)
    edge = RECEIVED + timedelta(days=DAYS)
    assert purge(world, edge - timedelta(seconds=1)) == 0
    assert world.body_rows(item) == 1 and purged_events(world, item) == 0
    assert purge(world, edge + timedelta(seconds=1)) == 1
    assert world.body_rows(item) == 0 and purged_events(world, item) == 1
    row = world.rows("SELECT purged_at FROM cur_forms_intake_item WHERE id = :i", i=item)[0]
    assert row["purged_at"] is not None


def test_a_second_run_finds_nothing_and_adds_no_event(world: World) -> None:
    item = world.stage_item(world.stage_code(world.intake_template()))
    late = RECEIVED + timedelta(days=DAYS + 1)
    assert purge(world, late) == 1
    count = world.count()
    assert purge(world, late) == 0
    assert world.count() == count and purged_events(world, item) == 1


def test_a_rejected_and_an_undecided_item_are_purged_and_an_accepted_one_has_no_body(
    world: World,
) -> None:
    code = world.stage_code(world.intake_template())
    pending, rejected, accepted = (world.stage_item(code) for _ in range(3))
    world.call("ada", "RejectIntakeItem", item_id=rejected, reason="spam")
    world.call(
        "ada",
        "AcceptIntakeItem",
        item_id=accepted,
        command_type="SubmitForm",
        command_args={"template_id": world.template(), "answers": [{"q": "topic", "value": "x"}]},
    )
    assert purged_events(world, accepted) == 1 and world.body_rows(accepted) == 0
    assert purge(world, RECEIVED + timedelta(days=DAYS + 1)) == 2
    assert purged_events(world, pending) == purged_events(world, rejected) == 1
    assert purged_events(world, accepted) == 1  # not a second time


def test_a_run_is_bounded(world: World) -> None:
    code = world.stage_code(world.intake_template())
    items = [world.stage_item(code) for _ in range(5)]
    late = RECEIVED + timedelta(days=DAYS + 1)
    assert purge(world, late, limit=2) == 2
    assert sum(world.body_rows(i) for i in items) == 3
    assert purge(world, late) == 3
    assert intake.BATCH == 100


def test_the_retention_setting_is_honoured_per_company(world: World) -> None:
    item = world.stage_item(world.stage_code(world.intake_template()))
    world.setting("forms.intake.retention_days", 10)
    assert purge(world, RECEIVED + timedelta(days=9)) == 0
    assert purge(world, RECEIVED + timedelta(days=11)) == 1
    assert world.body_rows(item) == 0


def test_a_viewer_leaves_alone_an_item_it_may_not_read(world: World) -> None:
    template = world.intake_template()
    hidden = world.stage_item(
        world.stage_code(template, context_id=world.hidden_record("privileged"))
    )
    shown = world.stage_item(world.stage_code(template))
    late = RECEIVED + timedelta(days=DAYS + 1)
    admin = cf.Viewer(actor="user:ada", level=1, account="user:ada")
    assert purge(world, late, scope=SCOPE, viewer=admin) == 1
    assert world.body_rows(hidden) == 1 and world.body_rows(shown) == 0
    assert purge(world, late) == 1  # the job, with no viewer, purges it
    assert world.body_rows(hidden) == 0


def test_a_scope_limits_the_run(world: World) -> None:
    item = world.stage_item(world.stage_code(world.intake_template()))
    assert purge(world, RECEIVED + timedelta(days=DAYS + 1), scope="project:P999") == 0
    assert world.body_rows(item) == 1


def test_the_purge_event_holds_no_text(world: World) -> None:
    item = world.stage_item(world.stage_code(world.intake_template()))
    purge(world, RECEIVED + timedelta(days=DAYS + 1))
    (event,) = world.events(item, "IntakeItem.Purged")
    assert set(event["payload"]) == {"purged_at", "feed_policy"}


def test_only_the_purge_and_the_accept_handler_delete_body_rows() -> None:
    src = Path(__file__).resolve().parents[1] / "src" / "tl_mod_forms"
    delete = re.compile(r"DELETE\s+FROM\s+(\{INTAKE_BODY_TABLE\}|forms_intake_body)")
    found = {str(p.relative_to(src)) for p in src.rglob("*.py") if delete.search(p.read_text())}
    assert found == {"intake.py", "handlers/intake.py"}
