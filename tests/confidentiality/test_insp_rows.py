"""The inspection confidentiality row (P2-INSP S2): an inspection is hidden when its subject is.

Five readers (no clearance, a person with a clearance, the company admin, an agent token, and
nobody signed in) read the records, the counts and the event rows. Records are made through the
quality commands and the correspondence module's own confidentiality command.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, create_schema, open_uow
from tl_core import confidentiality as cf
from tl_core.services import queries
from tl_core.services.errors import RecordNotFoundError
from tl_core.util import new_ulid

_QUALITY_TESTS = Path(__file__).resolve().parents[2] / "packages/tl-modules/quality/tests"
if str(_QUALITY_TESTS) not in sys.path:
    sys.path.insert(0, str(_QUALITY_TESTS))

from insp_world import IWP, InspWorld, answers  # noqa: E402

LOW = cf.Viewer(actor="user:vera", level=0, account="user:vera")
AGENT = cf.Viewer(actor="agent:bot", level=0, account="")
NOBODY = cf.LOWEST
CLEARED = cf.Viewer(actor="user:dora", level=1, account="user:dora")
ADMIN = cf.Viewer(actor="user:ada", level=1, account="user:ada")
LOWS = {"user": LOW, "agent": AGENT, "nobody": NOBODY}
HIGHS = {"cleared": CLEARED, "admin": ADMIN}


@pytest.fixture
def world(new_db: Callable[[], DbTarget]) -> InspWorld:
    target = new_db()
    create_schema(target)
    made = InspWorld(target)
    made.people()
    return made


class Built:
    """An inspection on a restricted record and one on an open record, each with a failed answer."""

    def __init__(self, world: InspWorld) -> None:
        self.world = world
        self.secret = world.hidden_record()
        self.open = world.record(IWP, "IWP-OPEN")
        self.checklist = world.checklist()
        self.hidden_inspection = world.scheduled(self.secret, self.checklist, who="dora")
        self.open_inspection = world.scheduled(self.open, self.checklist)
        world.recorded(self.hidden_inspection, who="dora", answers=answers(q1="no"))
        world.recorded(self.open_inspection, answers=answers(q1="no"))
        self.hidden_punch = world.raised_by(self.hidden_inspection)[0]["id"]
        self.open_punch = world.raised_by(self.open_inspection)[0]["id"]


@pytest.fixture
def built(world: InspWorld) -> Built:
    return Built(world)


def is_hidden(world: InspWorld, record: str, viewer: cf.Viewer) -> bool:
    with open_uow(world.db, readonly=True) as uow:
        return cf.is_hidden(uow.conn(), record, viewer)


def visible_count(world: InspWorld, table: str, viewer: cf.Viewer) -> int:
    """Rows of ``table`` the viewer reads, counted after the filter (as a view counts)."""
    visible, extra = cf.not_hidden("r.id", viewer)
    sql = f"SELECT COUNT(*) FROM {table} t JOIN cur_core_record r ON r.id = t.id WHERE {visible}"
    with open_uow(world.db, readonly=True) as uow:
        return int(uow.conn().execute(text(sql), extra).scalar_one())


def test_the_row_is_the_last_of_the_table_and_the_chain_is_two_hops() -> None:
    assert cf.SUBJECT_LINKS[10:11] == (
        (
            "quality.Inspection",
            "cur_quality_inspection",
            "id",
            "subject_id",
        ),
    )
    assert cf._HOPS == 2  # pyright: ignore[reportPrivateUsage]


def test_an_inspection_on_a_restricted_record_is_absent_for_the_five_readers(
    world: InspWorld, built: Built
) -> None:
    ghost = new_ulid()
    for name, viewer in LOWS.items():
        assert is_hidden(world, built.hidden_inspection, viewer), name
        assert not is_hidden(world, built.open_inspection, viewer), name
        with open_uow(world.db, readonly=True) as uow, cf.use_viewer(viewer):
            # the record read and its history answer as for an id that never existed
            assert queries.get_record_by_id(uow, built.hidden_inspection) is None
            assert queries.record_history(uow, built.hidden_inspection) == queries.record_history(
                uow, ghost
            )
            with pytest.raises(RecordNotFoundError):
                cf.require_visible(uow.conn(), built.hidden_inspection)
            assert queries.get_record_by_id(uow, built.open_inspection) is not None
        # counts are taken after the filter
        assert visible_count(world, "cur_quality_inspection", viewer) == 1, name
    for name, viewer in HIGHS.items():
        assert not is_hidden(world, built.hidden_inspection, viewer), name
        assert visible_count(world, "cur_quality_inspection", viewer) == 2, name
        with open_uow(world.db, readonly=True) as uow, cf.use_viewer(viewer):
            assert queries.get_record_by_id(uow, built.hidden_inspection) is not None


def test_the_events_and_the_feed_rows_of_a_hidden_inspection_are_filtered(
    world: InspWorld, built: Built
) -> None:
    rows = world.rows("SELECT event_id, stream_id, stream_type, payload FROM events")
    own = {
        r["event_id"]
        for r in rows
        if r["stream_id"] in (built.hidden_inspection, built.hidden_punch)
    }
    other = {r["event_id"] for r in rows if r["stream_id"] == built.open_inspection}
    assert own and other
    for name, viewer in LOWS.items():
        with open_uow(world.db, readonly=True) as uow, cf.use_viewer(viewer):
            gone = cf.hidden_row_ids(uow.conn(), rows)
            assert gone & own == own, name
            assert gone & other == set(), name
            streams = [(built.hidden_inspection, "quality.Inspection")]
            assert cf.hidden_event_streams(uow.conn(), streams) == {built.hidden_inspection}
    for name, viewer in HIGHS.items():
        with open_uow(world.db, readonly=True) as uow, cf.use_viewer(viewer):
            assert cf.hidden_row_ids(uow.conn(), rows) & own == set(), name


def test_a_punch_item_a_failed_answer_raised_has_the_subjects_class(
    world: InspWorld, built: Built
) -> None:
    for name, viewer in LOWS.items():
        assert is_hidden(world, built.hidden_punch, viewer), name
        assert not is_hidden(world, built.open_punch, viewer), name
        assert visible_count(world, "cur_quality_punch_item", viewer) == 1, name
    for name, viewer in HIGHS.items():
        assert not is_hidden(world, built.hidden_punch, viewer), name
        assert visible_count(world, "cur_quality_punch_item", viewer) == 2, name


def test_planning_on_a_hidden_subject_and_on_a_missing_id_answer_alike_and_write_nothing(
    world: InspWorld, built: Built
) -> None:
    before = world.count()
    messages = set()
    for subject in (built.secret, new_ulid()):
        with pytest.raises(RecordNotFoundError) as caught:
            world.call("uma", "PlanInspection", title="t", point="hold", subject_id=subject)
        messages.add(str(caught.value))
        assert type(caught.value) is RecordNotFoundError
    assert messages == {"no record with that id"}
    assert world.count() == before
    assert world.scalar("SELECT count(*) FROM cur_quality_inspection") == 2


def test_a_checklist_is_readable_at_the_lowest_class_by_every_reader(
    world: InspWorld, built: Built
) -> None:
    for name, viewer in {**LOWS, **HIGHS}.items():
        assert not is_hidden(world, built.checklist, viewer), name
        assert visible_count(world, "cur_quality_checklist", viewer) == 1, name
    rows: list[dict[str, Any]] = world.rows(
        "SELECT event_id, stream_id, stream_type, payload FROM events"
    )
    mine = {r["event_id"] for r in rows if r["stream_id"] == built.checklist}
    with open_uow(world.db, readonly=True) as uow, cf.use_viewer(NOBODY):
        assert cf.hidden_row_ids(uow.conn(), rows) & mine == set()
