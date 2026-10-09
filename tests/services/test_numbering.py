"""Numbering through CreateRecord: keys from a pattern, one transaction, no duplicates (P0-I3)."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from tl_adapters.sqlite.uow import create_schema, open_uow, rebuild_projections
from tl_core.ledger import ConcurrencyError, Event
from tl_core.numbering import allocator
from tl_core.numbering.allocator import (
    allocate_standalone,
    reserve_range,
    segment_values,
)
from tl_core.numbering.config import NumberingPattern, NumberingRegistry, use_numbering
from tl_core.services.commands import CreateRecord
from tl_core.services.errors import (
    DuplicateKeyError,
    GapFreeError,
    KeyRequiredError,
    NoNumberingPatternError,
    NotAvailableError,
    NumberingValueError,
)
from tl_core.services.records import handle_create_record

P1 = "project:P123"


def make_pattern(**overrides: Any) -> NumberingPattern:
    data: dict[str, Any] = {
        "id": "core.Record",
        "record_type": "core.Record",
        "scope": "project:*",
        "template": "{project}-{type}-{seq:4}",
        "type_code": "REC",
    }
    data.update(overrides)
    return NumberingPattern.model_validate(data)


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "tl.db"
    create_schema(path)
    return path


@pytest.fixture(autouse=True)
def patterns() -> Iterator[None]:
    with use_numbering(NumberingRegistry([make_pattern()])):
        yield


def create(db: Path, scope: str = P1, **overrides: Any) -> str:
    fields: dict[str, Any] = {
        "actor": "user:u-1",
        "source": "test",
        "scope": scope,
        "record_type": "core.Record",
        "title": "NCR",
    }
    fields.update(overrides)
    with open_uow(db) as uow:
        result = handle_create_record(uow, CreateRecord(**fields))
    assert result.key is not None
    return result.key


def all_events(db: Path) -> list[Event]:
    with open_uow(db, readonly=True) as uow:
        return uow.ledger.read_after(0, limit=10_000)


def counter_rows(db: Path) -> list[dict[str, Any]]:
    with open_uow(db, readonly=True) as uow:
        rows = uow.conn().execute(text("SELECT * FROM cur_numbering ORDER BY counter_id"))
        return [dict(r._mapping) for r in rows]


# --- the basic path ----------------------------------------------------------------------------


def test_a_missing_key_is_allocated_from_the_pattern(db: Path) -> None:
    assert create(db) == "P123-REC-0001"
    assert create(db) == "P123-REC-0002"


def test_the_record_row_carries_the_allocated_key(db: Path) -> None:
    key = create(db)
    with open_uow(db, readonly=True) as uow:
        row = uow.conn().execute(text("SELECT key FROM cur_core_record")).one()
    assert row.key == key


def test_allocation_and_creation_share_one_transaction_and_correlation(db: Path) -> None:
    create(db)
    events = all_events(db)
    assert [e.event_type for e in events] == ["Numbering.Allocated", "Record.Created"]
    allocated, created = events
    assert allocated.correlation_id == created.correlation_id
    assert allocated.payload["key"] == created.payload["key"] == "P123-REC-0001"
    assert allocated.payload["sequence"] == 1
    assert allocated.payload["pattern"] == "core.Record"
    assert allocated.payload["record_id"] == created.stream_id
    assert allocated.stream_id == "numbering:project:P123:core.Record:P123-REC-"
    assert allocated.stream_type == "numbering.Counter"
    assert allocated.scope == created.scope == P1


def test_the_counter_row_follows_the_allocations(db: Path) -> None:
    create(db)
    create(db)
    (row,) = counter_rows(db)
    assert row["last_sequence"] == 2
    assert row["last_key"] == "P123-REC-0002"
    assert row["allocations"] == 2
    assert row["version"] == 2
    assert row["prefix"] == "P123-REC-"
    assert row["pattern"] == "core.Record"


def test_an_explicit_key_does_not_touch_the_counter(db: Path) -> None:
    create(db, key="MANUAL-1")
    assert counter_rows(db) == []
    assert create(db) == "P123-REC-0001"


def test_projects_count_separately(db: Path) -> None:
    assert create(db, "project:P1") == "P1-REC-0001"
    assert create(db, "project:P2") == "P2-REC-0001"
    assert create(db, "project:P1") == "P1-REC-0002"


def test_extra_segments_give_each_value_its_own_counter(db: Path) -> None:
    registry = NumberingRegistry([make_pattern(template="{project}-{type}-{discipline}-{seq:4}")])
    with use_numbering(registry):
        assert create(db, numbering={"discipline": "PIP"}) == "P123-REC-PIP-0001"
        assert create(db, numbering={"discipline": "ELE"}) == "P123-REC-ELE-0001"
        assert create(db, numbering={"discipline": "PIP"}) == "P123-REC-PIP-0002"


# --- failures ----------------------------------------------------------------------------------


def test_no_pattern_means_a_key_is_required(db: Path) -> None:
    with pytest.raises(NoNumberingPatternError, match="give a key"):
        create(db, "company")
    with pytest.raises(KeyRequiredError):
        create(db, "company")
    assert all_events(db) == []


def test_a_missing_segment_value_is_refused_before_anything_is_written(db: Path) -> None:
    registry = NumberingRegistry([make_pattern(template="{project}-{discipline}-{seq:4}")])
    with use_numbering(registry), pytest.raises(NumberingValueError, match="discipline"):
        create(db)
    assert all_events(db) == []


def test_a_segment_value_must_be_letters_and_digits(db: Path) -> None:
    registry = NumberingRegistry([make_pattern(template="{project}-{discipline}-{seq:4}")])
    with use_numbering(registry), pytest.raises(NumberingValueError, match="letters and digits"):
        create(db, numbering={"discipline": "P-1"})


def test_a_project_pattern_needs_a_project_scope(db: Path) -> None:
    registry = NumberingRegistry([make_pattern(scope="*")])
    with use_numbering(registry), pytest.raises(NumberingValueError, match="needs a project"):
        create(db, "company")


def test_a_failed_create_does_not_spend_a_number(db: Path) -> None:
    class Boom(Exception): ...

    with pytest.raises(Boom), open_uow(db) as uow:
        handle_create_record(
            uow,
            CreateRecord(actor="u", source="t", scope=P1, record_type="core.Record", title="lost"),
        )
        raise Boom  # the transaction rolls back, allocation included
    assert all_events(db) == []
    assert create(db) == "P123-REC-0001"


def test_a_number_whose_key_is_already_used_is_skipped(db: Path) -> None:
    create(db, key="P123-REC-0001")
    create(db, key="P123-REC-0002")
    assert create(db) == "P123-REC-0003"
    (row,) = counter_rows(db)
    assert row["allocations"] == 1
    assert row["last_sequence"] == 3


def test_a_duplicate_explicit_key_is_still_refused(db: Path) -> None:
    create(db, key="X-1")
    with pytest.raises(DuplicateKeyError):
        create(db, key="X-1")


# --- reserved ranges and gap-free --------------------------------------------------------------


def test_reserved_ranges_are_skipped(db: Path) -> None:
    registry = NumberingRegistry([make_pattern(reserved=[(2, 3), (5, 5)])])
    with use_numbering(registry):
        keys = [create(db) for _ in range(4)]
    assert keys == ["P123-REC-0001", "P123-REC-0004", "P123-REC-0006", "P123-REC-0007"]


def test_a_gap_free_pattern_refuses_standalone_allocation(db: Path) -> None:
    pattern = make_pattern()
    with open_uow(db) as uow, pytest.raises(GapFreeError):
        allocate_standalone(
            uow,
            pattern=pattern,
            scope=P1,
            values=segment_values(pattern, P1),
            actor="u",
            source="t",
        )
    assert all_events(db) == []


def test_a_pattern_without_gap_free_allows_standalone_allocation(db: Path) -> None:
    pattern = make_pattern(gap_free=False)
    with use_numbering(NumberingRegistry([pattern])):
        with open_uow(db) as uow:
            first = allocate_standalone(
                uow,
                pattern=pattern,
                scope=P1,
                values=segment_values(pattern, P1),
                actor="u",
                source="t",
            )
        assert (first.key, first.sequence) == ("P123-REC-0001", 1)
        assert first.event.payload["record_id"] is None
        assert create(db) == "P123-REC-0002"  # the number was spent without a record


def test_reserve_range_is_a_stub() -> None:
    with pytest.raises(NotAvailableError, match="Phase 3"):
        reserve_range("P123-REC-", 1, 100)


# --- concurrency -------------------------------------------------------------------------------


def test_concurrent_creators_never_get_the_same_key(db: Path) -> None:
    keys: list[str] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker() -> None:
        try:
            for _ in range(5):
                key = create(db)
                with lock:
                    keys.append(key)
        except BaseException as exc:  # noqa: BLE001 - the test reports any failure
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not [t for t in threads if t.is_alive()], "a creator hung"
    assert errors == []
    assert len(keys) == 40
    assert sorted(keys) == [f"P123-REC-{n:04d}" for n in range(1, 41)]


def test_a_stale_counter_read_is_stopped_by_the_ledger_version_check(
    db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Second line of defence: a writer that read an old counter cannot append a duplicate.

    The exclusive write lock makes this unreachable on SQLite, so the test forces it: the counter
    read is replaced by one that reports an empty counter although one allocation exists.
    """
    assert create(db) == "P123-REC-0001"
    monkeypatch.setattr(allocator, "_COUNTER_SQL", text("SELECT 0 AS last_sequence, 0 AS version"))
    with pytest.raises(ConcurrencyError):
        create(db)
    monkeypatch.undo()
    assert len(all_events(db)) == 2  # nothing from the refused attempt survived
    assert create(db) == "P123-REC-0002"


# --- replay ------------------------------------------------------------------------------------


def test_rebuilding_the_projections_restores_the_counters(db: Path) -> None:
    create(db)
    create(db)
    create(db, "project:P2")
    before = counter_rows(db)
    assert rebuild_projections(db) == 6
    assert counter_rows(db) == before
    assert create(db) == "P123-REC-0003"
