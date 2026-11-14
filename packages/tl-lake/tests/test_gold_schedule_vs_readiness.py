"""``mart_schedule_vs_readiness``: IWP readiness as of each published snapshot (P2-I6 T02).

Copy this file to ``packages/tl-lake/tests/test_mart_schedule_vs_readiness.py``. It builds the
tables the model may read in a temporary lake by direct INSERT: ``mart_schedule_history``
(``scope``, ``schedule_code``, ``snapshot_number``, ``data_date``, ``latest_early_finish``,
``finish_slip_days``) and bronze ``events`` (``seq``, ``scope``, ``event_type``, ``payload``; the
readiness history mart is built from them by ``build_gold_marts``). It pins ``SELECT *``.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from tl_lake import LakeConfig
from tl_lake.duck import Duck, open_lake
from tl_lake.gold import build_gold_marts

P1, P2 = "project:P1", "project:P2"
MART = "mart_schedule_vs_readiness"
COLUMNS = [
    "scope", "schedule_code", "snapshot_number", "data_date", "latest_early_finish",
    "finish_slip_days", "iwps_evaluated", "iwps_ready", "iwps_not_ready", "ready_pct", "as_of_seq",
]  # fmt: skip


@pytest.fixture
def con(tmp_path: Path) -> Iterator[Duck]:
    with open_lake(LakeConfig.at(tmp_path / "lake"), write=True) as opened:
        opened.execute(
            "CREATE TABLE lake.main.events (seq BIGINT, scope VARCHAR, event_type VARCHAR, "
            "payload VARCHAR)"
        )
        opened.execute(
            "CREATE TABLE lake.main.mart_schedule_history (scope VARCHAR, schedule_code VARCHAR, "
            "snapshot_number BIGINT, data_date TIMESTAMP, latest_early_finish TIMESTAMP, "
            "finish_slip_days BIGINT)"
        )
        opened.execute("CREATE TABLE lake.main.cur_core_record (id VARCHAR)")
        yield opened


def snap(
    con: Duck, number: int, data_date: str, scope: str = P1, code: str = "MAIN",
    slip: int | None = None,
) -> None:  # fmt: skip
    con.execute(
        "INSERT INTO lake.main.mart_schedule_history VALUES (?, ?, ?, ?, ?, ?)",
        [scope, code, number, data_date, "2027-03-01 00:00:00", slip],
    )


def record(con: Duck, iwp: str) -> None:
    """The IWP is a readable record in silver (``cur_core_record``), as the runner requires."""
    present = con.execute("SELECT id FROM lake.main.cur_core_record WHERE id = ?", [iwp]).fetchall()
    if not present:
        con.execute("INSERT INTO lake.main.cur_core_record VALUES (?)", [iwp])


def evaluated(con: Duck, seq: int, iwp: str, today: str, ready: bool, scope: str = P1) -> None:
    record(con, iwp)
    payload = {
        "iwp_id": iwp, "evaluated_at": f"{today}T08:00:00Z", "today": today, "ready": ready,
        "checks": [], "facts_hash": "0" * 64, "feed_policy": "none",
    }  # fmt: skip
    con.execute(
        "INSERT INTO lake.main.events VALUES (?, ?, 'IWP.ReadinessEvaluated', ?)",
        [seq, scope, json.dumps(payload, sort_keys=True)],
    )


def rows(con: Duck) -> list[tuple[Any, ...]]:
    build_gold_marts(con)
    return con.execute(
        f"SELECT * FROM lake.main.{MART} ORDER BY scope, schedule_code, snapshot_number"
    ).fetchall()


def finish() -> datetime:
    return datetime(2027, 3, 1)


def test_a_snapshot_with_no_evaluation_has_zero_counts_and_null_pct_and_as_of(con: Duck) -> None:
    snap(con, 1, "2026-09-01 00:00:00")
    assert rows(con) == [(P1, "MAIN", 1, datetime(2026, 9, 1), finish(), None, 0, 0, 0, None, None)]
    described = con.execute(f"SELECT * FROM lake.main.{MART}").description
    assert [d[0] for d in described] == COLUMNS


def test_the_latest_evaluation_of_each_iwp_up_to_the_data_date_is_counted(con: Duck) -> None:
    evaluated(con, 1, "I1", "2026-08-01", False)
    evaluated(con, 2, "I2", "2026-08-02", True)
    evaluated(con, 3, "I1", "2026-08-20", True)  # I1 is ready as of snapshot 1
    evaluated(con, 4, "I3", "2026-08-25", False)
    evaluated(con, 9, "I2", "2026-09-10", False)  # after snapshot 1, before snapshot 2
    snap(con, 1, "2026-09-01 00:00:00")
    snap(con, 2, "2026-10-01 00:00:00", slip=7)
    assert rows(con) == [
        (P1, "MAIN", 1, datetime(2026, 9, 1), finish(), None, 3, 2, 1, 66.7, 4),
        (P1, "MAIN", 2, datetime(2026, 10, 1), finish(), 7, 3, 1, 2, 33.3, 9),
    ]


def test_an_evaluation_made_for_the_data_date_itself_is_counted_and_the_day_after_is_not(
    con: Duck,
) -> None:
    evaluated(con, 1, "I1", "2026-09-01", True)  # today = data date: counted
    evaluated(con, 2, "I2", "2026-09-02", True)  # a day later: not counted
    snap(con, 1, "2026-09-01 00:00:00")
    assert rows(con) == [(P1, "MAIN", 1, datetime(2026, 9, 1), finish(), None, 1, 1, 0, 100.0, 1)]


def test_the_data_date_with_a_time_of_day_still_counts_that_whole_day(con: Duck) -> None:
    evaluated(con, 1, "I1", "2026-09-01", False)
    snap(con, 1, "2026-09-01 17:30:00")
    assert [(r[6], r[7], r[8], r[9], r[10]) for r in rows(con)] == [(1, 0, 1, 0.0, 1)]


def test_scopes_and_schedules_do_not_see_each_others_iwps(con: Duck) -> None:
    evaluated(con, 1, "A1", "2026-08-01", True, scope=P1)
    evaluated(con, 2, "B1", "2026-08-01", False, scope=P2)
    evaluated(con, 3, "B2", "2026-08-01", False, scope=P2)
    snap(con, 1, "2026-09-01 00:00:00", scope=P1)
    snap(con, 1, "2026-09-01 00:00:00", scope=P2, code="MAIN")
    snap(con, 1, "2026-09-01 00:00:00", scope=P2, code="REC")
    got = rows(con)
    assert [(r[0], r[1], r[6], r[7], r[8], r[9], r[10]) for r in got] == [
        (P1, "MAIN", 1, 1, 0, 100.0, 1),
        (P2, "MAIN", 2, 0, 2, 0.0, 3),
        (P2, "REC", 2, 0, 2, 0.0, 3),  # a scope's IWPs count for each of its schedules
    ]


def test_an_iwp_that_is_not_a_readable_record_is_not_counted(con: Duck) -> None:
    evaluated(con, 1, "A1", "2026-08-01", True)
    hidden = {
        "iwp_id": "HIDDEN", "evaluated_at": "2026-08-01T08:00:00Z", "today": "2026-08-01",
        "ready": False, "checks": [], "facts_hash": "0" * 64, "feed_policy": "none",
    }  # fmt: skip
    con.execute(
        "INSERT INTO lake.main.events VALUES (2, ?, 'IWP.ReadinessEvaluated', ?)",
        [P1, json.dumps(hidden, sort_keys=True)],
    )
    snap(con, 1, "2026-09-01 00:00:00")
    assert rows(con) == [(P1, "MAIN", 1, datetime(2026, 9, 1), finish(), None, 1, 1, 0, 100.0, 1)]
