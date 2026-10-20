"""`tl xer unscheduled` (P1-I4-T10b)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow
from tl_core.services.commands import CreateRecord
from tl_core.services.records import handle_create_record
from xercli_support import Cast, P, published_pair, tl, xer_env

AUTO_SIGN_IN = False
SCHED = ("--schedule", "MAIN")


@pytest.fixture
def cast(new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Cast:
    return Cast(xer_env(new_db, monkeypatch, tmp_path), tmp_path)


def more_records(cast: Cast, *keys: str) -> None:
    for key in keys:
        with open_uow(cast.target) as uow:
            handle_create_record(
                uow,
                CreateRecord(
                    actor="user:ursula", source="test", scope="project:P123",
                    record_type="core.Record", title=f"Record {key}", key=key,
                ),
            )  # fmt: skip


def lines(cast: Cast, *args: str) -> list[str]:
    """What a plain user (who may only read) sees for one command."""
    return tl(cast.ursula, "xer", "unscheduled", *args, ok=True).stdout.splitlines()


def test_unscheduled_lists_the_records_that_point_at_no_activity(
    cast: Cast, tmp_path: Path
) -> None:
    published_pair(cast, tmp_path)  # REC-A on A1230, REC-B on A1990 (which left and is flagged)
    more_records(cast, "REC-D", "REC-C")
    [head, b, c, d] = lines(cast, *P, "--type", "core.Record")
    assert head == "records without an activity (core.Record): 3"
    assert b.startswith("REC-B  ") and b.endswith("  REC-B")
    assert c.startswith("REC-C  ") and c.endswith("  Record REC-C")
    assert d.startswith("REC-D  ") and len(d.split()[1]) == 26


def test_a_link_to_an_activity_that_left_counts_only_once_the_worker_has_flagged_it(
    cast: Cast, tmp_path: Path
) -> None:
    published_pair(cast, tmp_path, worker_after=False)
    assert lines(cast, *P, "--type", "core.Record") == [
        "records without an activity (core.Record): 0"
    ]
    tl(cast.boss, "xer", "worker", "--once", ok=True)
    assert lines(cast, *P, "--type", "core.Record")[0] == (
        "records without an activity (core.Record): 1"
    )


def test_unscheduled_takes_a_type_a_schedule_and_a_limit(cast: Cast, tmp_path: Path) -> None:
    published_pair(cast, tmp_path)
    more_records(cast, "REC-C", "REC-D")
    assert lines(cast, *P, "--type", "core.Other") == [
        "records without an activity (core.Other): 0"
    ]
    one = lines(cast, *P, "--type", "core.Record", "--limit", "2")
    assert one[0] == "records without an activity (core.Record): 2"
    assert [x.split()[0] for x in one[1:]] == ["REC-B", "REC-C"]
    main = lines(cast, *P, "--type", "core.Record", *SCHED)
    assert main[0] == "records without an activity (core.Record) in MAIN: 3"
    tl(cast.dora, "xer", "define", "OTHER", *P, "--name", "Another", ok=True)
    other = lines(cast, *P, "--type", "core.Record", "--schedule", "OTHER")
    assert other[0] == "records without an activity (core.Record) in OTHER: 4"  # REC-A too
    missing = tl(
        cast.ursula, "xer", "unscheduled", *P, "--type", "core.Record", "--schedule", "NOPE"
    )
    assert missing.exit_code == 1 and "error: no schedule 'NOPE' in project:P123" in missing.output


def test_unscheduled_needs_a_type_and_sees_only_its_own_project(cast: Cast, tmp_path: Path) -> None:
    published_pair(cast, tmp_path)
    assert tl(cast.ursula, "xer", "unscheduled", *P).exit_code == 2
    assert lines(cast, "--project", "P999", "--type", "core.Record") == [
        "records without an activity (core.Record): 0"
    ]


def test_the_report_writes_nothing_to_the_ledger(cast: Cast, tmp_path: Path) -> None:
    published_pair(cast, tmp_path)

    def count() -> int:
        with open_uow(cast.target, readonly=True) as uow:
            return int(uow.conn().execute(text("SELECT COUNT(*) FROM events")).scalar_one())

    before = count()
    lines(cast, *P, "--type", "core.Record")
    assert count() == before
