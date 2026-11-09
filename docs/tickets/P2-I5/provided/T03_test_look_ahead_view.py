"""P2-I5-T03: the look-ahead joined with linked IWPs, readiness counts and blocking constraints."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from awp_world import SCOPE, World
from progress_world import ProgressWorld
from sqlalchemy import text
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core import modules as core_modules
from tl_core.modules import ConfidentialSource
from tl_mod_awp.look_ahead_view import LookAheadView, look_ahead_view
from tl_mod_awp.names import IWP
from tl_mod_schedule.lookahead import look_ahead
from tl_mod_schedule.registry import SnapshotRow
from tl_mod_schedule.testing import BASE as SCHEDULE_BASE
from tl_mod_schedule.testing import ScheduleWorld
from tl_xer.synth import make_xer, week_pair


class Plant:
    """A ledger with the first demo snapshot published and three IWPs."""

    def __init__(self, w: World, tmp: Path) -> None:
        self.w = w
        self.pw = ProgressWorld(w)
        SCHEDULE_BASE["actor"] = "user:sue"
        self.sw = ScheduleWorld(w.db, tmp / "objects")
        self.sw.define()
        first, _ = week_pair()
        self.snapshot_id = self.sw.upload(make_xer(first))
        self.sw.publish(self.snapshot_id)
        self.a = w.iwp("Rack A", planned_start="2026-12-01", foreman="user:uma")
        self.b = w.iwp("Rack B", planned_start="2026-12-08", foreman="user:uma")
        self.c = w.iwp("Rack C")  # no planned start

    def snapshot(self) -> SnapshotRow:
        return self.sw.snapshot(self.snapshot_id)

    def number(self, iwp: str) -> str:
        return str(self.w.scalar("SELECT key FROM cur_core_record WHERE id = :i", i=iwp))

    def view(self, viewer: cf.Viewer | None = None, weeks: int = 4) -> LookAheadView:
        with open_uow(self.w.db, readonly=True) as uow:
            return look_ahead_view(uow.conn(), SCOPE, self.snapshot(), viewer, weeks=weeks)

    def item(self, view: LookAheadView, activity: str) -> list[str]:
        [found] = [i for i in view.items if i.row.activity_id == activity]
        return [x.number for x in found.iwps]

    def evaluated(self, iwp: str, states: tuple[str, ...]) -> None:
        """A readiness evaluation as the projector would hold it (one check per state)."""
        with open_uow(self.w.db) as uow:
            conn = uow.conn()
            ready = all(s in ("ok", "n_a") for s in states)
            conn.execute(
                text(
                    "INSERT INTO cur_awp_readiness (iwp_id, scope, evaluated_at, today, ready, "
                    "facts_hash, as_of_seq) VALUES (:i, :s, '2026-10-05T00:00:00+00:00', "
                    "'2026-10-05', :r, 'h', 0)"
                ),
                {"i": iwp, "s": SCOPE, "r": ready},
            )
            for n, state in enumerate(states):
                conn.execute(
                    text(
                        "INSERT INTO cur_awp_readiness_check (row_id, scope, iwp_id, name, "
                        "version, state, detail, count_ok, count_total, resolve_via_json, "
                        "as_of_seq) VALUES (:row, :s, :i, :n, '1', :st, '', 0, 0, '[]', 0)"
                    ),
                    {"row": f"{iwp}-{n}", "s": SCOPE, "i": iwp, "n": f"check{n}", "st": state},
                )

    @contextmanager
    def hidden(self, *iwps: str) -> Iterator[None]:
        """The IWPs are restricted: the lowest viewer cannot open them (a test source)."""
        with open_uow(self.w.db) as uow:
            conn = uow.conn()
            conn.execute(
                text("CREATE TABLE IF NOT EXISTS la_iwp_class (id TEXT PRIMARY KEY, cls TEXT)")
            )
            conn.execute(text("DELETE FROM la_iwp_class"))
            for row in self.w.rows("SELECT id FROM cur_awp_iwp"):
                cls = "restricted" if row["id"] in iwps else "internal"
                conn.execute(
                    text("INSERT INTO la_iwp_class VALUES (:i, :c)"), {"i": row["id"], "c": cls}
                )
        source = ConfidentialSource(
            record_types=frozenset({IWP}),
            table="la_iwp_class",
            id_column="id",
            class_column="cls",
        )
        real = core_modules.confidential_sources
        cf.confidential_sources = lambda: [*real(), source]  # type: ignore[attr-defined]
        try:
            yield
        finally:
            cf.confidential_sources = real  # type: ignore[attr-defined]


@pytest.fixture
def plant(world: World, tmp_path: Path) -> Iterator[Plant]:
    saved = dict(SCHEDULE_BASE)
    made = Plant(world, tmp_path)
    try:
        yield made
    finally:
        SCHEDULE_BASE.clear()
        SCHEDULE_BASE.update(saved)


def test_items_follow_the_look_ahead_rows_and_carry_the_linked_iwps(plant: Plant) -> None:
    plant.sw.link(plant.a, "A1230")
    plant.sw.link(plant.b, "A1230")
    plant.sw.link(plant.b, "A1140")
    view = plant.view()
    with open_uow(plant.w.db, readonly=True) as uow:
        plain = look_ahead(uow.conn(), plant.snapshot(), 4, scope=SCOPE)
    assert [i.row for i in view.items] == list(plain.rows)
    assert dict(view.counts) == dict(plain.counts)
    assert (view.window_start, view.window_end, view.weeks) == (
        plain.window_start,
        plain.window_end,
        4,
    )
    assert plant.item(view, "A1230") == sorted([plant.number(plant.a), plant.number(plant.b)])
    assert plant.item(view, "A1140") == [plant.number(plant.b)]
    other = [i for i in view.items if i.row.activity_id not in ("A1230", "A1140")]
    assert other and all(not i.iwps for i in other)


def test_a_link_to_an_activity_outside_the_window_shows_nowhere(plant: Plant) -> None:
    plant.sw.link(plant.a, "A1000")  # completed: not in the look-ahead
    view = plant.view()
    assert all(not i.iwps for i in view.items)
    assert "A1000" not in {i.row.activity_id for i in view.items}


def test_need_by_is_planned_start_minus_the_lead_weeks(plant: Plant) -> None:
    for iwp in (plant.a, plant.c):
        plant.sw.link(iwp, "A1230")
    view = plant.view()
    assert view.lead_weeks == 4
    [a, c] = sorted(
        [x for i in view.items if i.row.activity_id == "A1230" for x in i.iwps],
        key=lambda x: x.number,
    )
    first, second = (a, c) if a.number == plant.number(plant.a) else (c, a)
    assert (first.planned_start, first.need_by) == ("2026-12-01", "2026-11-03")
    assert (second.planned_start, second.need_by) == (None, None)


def test_readiness_is_counted_and_a_never_evaluated_iwp_says_so(plant: Plant) -> None:
    for iwp in (plant.a, plant.b, plant.c):
        plant.sw.link(iwp, "A1230")
    plant.evaluated(plant.a, ("ok", "n_a", "unknown"))
    plant.evaluated(plant.b, ("ok", "ok"))
    by = {x.number: x for i in plant.view().items for x in i.iwps if i.row.activity_id == "A1230"}
    a, b, c = (by[plant.number(i)] for i in (plant.a, plant.b, plant.c))
    assert (a.evaluated, a.ready, a.checks_ok, a.checks_total) == (True, False, 2, 3)
    assert (b.evaluated, b.ready, b.checks_ok, b.checks_total) == (True, True, 2, 2)
    assert (c.evaluated, c.ready, c.checks_ok, c.checks_total) == (False, False, 0, 0)
    assert a.state == "Draft"


def test_open_blocking_constraints_are_counted_per_iwp(plant: Plant) -> None:
    plant.sw.link(plant.a, "A1230")
    plant.sw.link(plant.b, "A1230")
    plant.pw.raise_blocking(plant.a, "start")
    plant.pw.raise_blocking(plant.a, "complete")
    by = {x.number: x for i in plant.view().items for x in i.iwps if i.row.activity_id == "A1230"}
    assert by[plant.number(plant.a)].open_blocking == 2
    assert by[plant.number(plant.b)].open_blocking == 0


def test_a_hidden_iwp_is_absent_and_the_rest_are_unchanged(plant: Plant) -> None:
    plant.sw.link(plant.a, "A1230")
    plant.sw.link(plant.b, "A1230")
    before = plant.view()
    with plant.hidden(plant.b):
        shown = plant.view()
    assert plant.item(shown, "A1230") == [plant.number(plant.a)]
    assert plant.item(before, "A1230") == sorted([plant.number(plant.a), plant.number(plant.b)])
    assert [i.row for i in shown.items] == [i.row for i in before.items]
    assert plant.number(plant.b) not in repr(shown)


def test_the_same_call_twice_is_equal_and_bad_weeks_are_refused(plant: Plant) -> None:
    plant.sw.link(plant.a, "A1230")
    assert plant.view() == plant.view()
    with pytest.raises(ValueError):
        plant.view(weeks=0)
