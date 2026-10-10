"""The settings reader: caching, bus invalidation, scheduled changes, expiry (brief 30.3)."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any

import pytest
from settings_world import ALICE, P1, SRC, World, future
from sqlalchemy import Connection
from tl_adapters.db import DbTarget, make_uow_factory
from tl_core import settings as S
from tl_core.bus import InProcessBus
from tl_core.services.errors import UnknownSettingError
from tl_core.settings.reader import SettingsReader, conn_factory_from
from tl_core.util import utcnow


class Clock:
    """The real time plus an offset the test moves; ``mono`` is the monotonic clock for expiry."""

    def __init__(self) -> None:
        self.offset = timedelta(0)
        self.mono = 1000.0

    def __call__(self) -> datetime:
        return utcnow() + self.offset

    def set_to(self, moment: datetime) -> None:
        self.offset = moment - utcnow()

    def monotonic(self) -> float:
        return self.mono


class Setup:
    def __init__(self, db: DbTarget) -> None:
        self.world = World(db)
        self.bus = InProcessBus()
        self.factory = make_uow_factory(db, bus=self.bus)
        self.clock = Clock()
        self.reader = SettingsReader(
            conn_factory_from(self.factory), clock=self.clock, monotonic=self.clock.monotonic
        )

    def set(self, key: str, layer: str, value: Any, **kw: Any) -> None:
        with self.factory() as uow:
            S.set_setting(uow, key=key, layer=layer, value=value, actor=ALICE, source=SRC, **kw)


@pytest.fixture
def setup(new_db: Callable[[], DbTarget]) -> Iterator[Setup]:
    built = Setup(new_db())
    try:
        yield built
    finally:
        built.factory.dispose()


def test_a_reader_without_a_database_answers_with_the_platform_defaults() -> None:
    reader = SettingsReader()
    assert reader.get("feed.reactions.enabled") is True
    assert reader.get("feed.signal_tags") == ["safety", "hold", "decision", "urgent", "fyi"]
    assert reader.effective("lake.sync.interval").origin == "default"
    with pytest.raises(UnknownSettingError):
        reader.get("no.such")


def test_the_tables_are_read_once_for_many_questions(setup: Setup) -> None:
    setup.set("t.limit", "company", 20)
    r = setup.reader
    assert [r.get("t.limit") for _ in range(5)] == [20] * 5
    assert r.get("t.limit", project="P1") == 20
    assert r.get("t.plain") == "x"
    assert r.loads == 1


def test_project_and_user_answers_are_kept_apart(setup: Setup) -> None:
    setup.set("t.limit", "company", 20)
    setup.set("t.limit", P1, 30)
    setup.set("ui.t.pref", "user:alice", "b")
    r = setup.reader
    assert (r.get("t.limit"), r.get("t.limit", project="P1"), r.get("t.limit", project="P2")) == (
        20,
        30,
        20,
    )
    assert (r.get("ui.t.pref", user="alice"), r.get("ui.t.pref", user="bob")) == ("b", "a")
    assert r.effective("t.limit", project="P1").origin == "project"


def test_without_a_bus_a_change_is_not_seen_until_the_copy_expires(setup: Setup) -> None:
    r = setup.reader
    assert r.get("t.limit") == 10
    setup.set("t.limit", "company", 20)
    assert r.get("t.limit") == 10  # the copy is young: still the old answer
    setup.clock.mono += 31
    assert r.get("t.limit") == 20 and r.loads == 2


def test_a_change_on_the_bus_applies_to_the_next_call(setup: Setup) -> None:
    subscription = setup.reader.attach(setup.bus)
    r = setup.reader
    assert r.get("t.limit") == 10
    setup.set("t.limit", "company", 20)
    assert r.get("t.limit") == 20
    setup.set("t.limit", P1, 30)
    assert r.get("t.limit", project="P1") == 30
    with setup.factory() as uow:
        S.lock_setting(
            uow, key="t.limit", locked=True, bounds=None, actor=ALICE, source=SRC, reason="r"
        )
    assert r.effective("t.limit", project="P1").locked is True
    assert r.get("t.limit", project="P1") == 20
    assert r.loads == 4
    subscription.close()
    setup.set("t.limit", "company", 21)
    assert r.get("t.limit") == 20  # no longer told


def test_events_that_are_not_settings_leave_the_copy_alone(setup: Setup) -> None:
    from tl_core.services.commands import CreateRecord
    from tl_core.services.records import handle_create_record

    setup.reader.attach(setup.bus)
    setup.set("t.limit", "company", 20)
    setup.reader.get("t.limit")
    with setup.factory() as uow:
        handle_create_record(
            uow,
            CreateRecord(
                actor=ALICE, source=SRC, scope=P1, record_type="core.Record", title="t", key="K-1"
            ),
        )
    setup.reader.get("t.limit")
    assert setup.reader.loads == 1


def test_a_scheduled_change_applies_at_its_time_without_any_event(setup: Setup) -> None:
    setup.reader.attach(setup.bus)
    setup.set("t.limit", "company", 20)
    when = utcnow() + timedelta(hours=1)
    setup.set("t.limit", "company", 30, applies_at=when)
    r = setup.reader
    assert r.get("t.limit") == 20
    assert [s.new_value for s in r.effective("t.limit").scheduled] == [30]
    loads = r.loads
    setup.clock.set_to(when - timedelta(seconds=30))
    assert r.get("t.limit") == 20
    setup.clock.set_to(when + timedelta(seconds=1))
    assert r.get("t.limit") == 30  # the cached answer ended at applies_at
    assert r.effective("t.limit").scheduled == []
    assert r.loads == loads  # the copy of the tables is still good; only the answer expired


def test_an_answer_with_nothing_scheduled_is_kept_for_good(setup: Setup) -> None:
    setup.set("t.limit", "company", 20)
    r = setup.reader
    first = r.effective("t.limit")
    setup.clock.offset += timedelta(days=400)
    assert r.effective("t.limit") is first


def test_a_reload_that_overlaps_an_invalidation_is_not_kept(setup: Setup) -> None:
    setup.set("t.limit", "company", 20)
    state = {"first": True}

    def factory() -> Any:
        @contextmanager
        def opened() -> Iterator[Connection]:
            with setup.factory(readonly=True) as uow:
                conn = uow.conn()
                if state["first"]:
                    state["first"] = False
                    racing.invalidate()  # a Setting event arrives while the tables are read
                yield conn

        return opened()

    racing = SettingsReader(factory, clock=setup.clock, monotonic=setup.clock.monotonic)
    assert racing.get("t.limit") == 20  # this call still answers
    assert racing.get("t.limit") == 20
    assert racing.loads == 2  # the first load was not stored, so the second call loaded again


def test_many_readers_during_a_stream_of_changes_always_see_a_value_that_was_set(
    setup: Setup,
) -> None:
    setup.reader.attach(setup.bus)
    seen: set[Any] = set()
    stop = threading.Event()
    errors: list[BaseException] = []

    def read() -> None:
        try:
            while not stop.is_set():
                seen.add(setup.reader.get("t.limit"))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=read, daemon=True) for _ in range(4)]
    for thread in threads:
        thread.start()
    for value in range(1, 13):
        setup.set("t.limit", "company", value)
    stop.set()
    for thread in threads:
        thread.join(timeout=10)
    assert errors == []
    assert seen <= set(range(1, 13)) | {10}
    assert setup.reader.get("t.limit") == 12


def test_the_reader_factory_function_builds_a_reader(setup: Setup) -> None:
    built = S.reader(conn_factory_from(setup.factory), max_age_s=None)
    setup.set("t.limit", "company", 7)
    assert built.get("t.limit") == 7
    setup.set("t.limit", "company", 8)
    setup.clock.mono += 10_000
    assert built.get("t.limit") == 7  # max_age_s=None: only an invalidation refreshes it


def test_a_scheduled_value_in_the_far_future_is_not_applied_early(setup: Setup) -> None:
    setup.set("t.limit", "company", 1, applies_at=future(24 * 365))
    assert setup.reader.get("t.limit") == 10
