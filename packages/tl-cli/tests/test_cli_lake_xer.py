"""`tl lake sync` carries the schedule snapshots too: silver, bronze and the float-trend mart."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from tl_adapters.db import DbTarget
from xercli_support import Cast, published_pair, tl, xer_env

AUTO_SIGN_IN = False


@pytest.fixture
def cast(new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Cast:
    return Cast(xer_env(new_db, monkeypatch, tmp_path), tmp_path)


def lake(cast: Cast, tmp_path: Path, *args: str, ok: bool = True) -> str:
    result = tl(cast.boss, "lake", "--lake-dir", str(tmp_path / "lake"), *args, ok=ok)
    return result.output


def test_a_sync_loads_the_snapshots_and_a_second_one_says_nothing_new(
    cast: Cast, tmp_path: Path
) -> None:
    published_pair(cast, tmp_path)
    out = lake(cast, tmp_path, "sync").splitlines()
    assert out[0].startswith("synced seq 1..") and out[1].startswith("silver rows: ")
    assert out[2] == (
        "schedule snapshots: loaded 2 (42 activities), dropped 0, bronze tables for 2 "
        "(185 rows) in snapshot 4"
    )
    again = lake(cast, tmp_path, "sync").splitlines()
    assert len(again) == 1 and again[0].startswith("lake is up to date as of seq ")


def test_the_lake_answers_with_the_float_trend_of_an_activity(cast: Cast, tmp_path: Path) -> None:
    published_pair(cast, tmp_path)
    lake(cast, tmp_path, "sync")
    answer = json.loads(
        lake(
            cast,
            tmp_path,
            "query",
            "--json",
            "SELECT snapshot_number, total_float_days, float_change_days, eroded "
            "FROM mart_float_trend WHERE activity_id = 'A1230' ORDER BY snapshot_number",
        )
    )
    rows = answer["rows"] if isinstance(answer, dict) else answer
    assert [list(r.values()) if isinstance(r, dict) else list(r) for r in rows] == [
        [1, 9.0, None, False],
        [2, 4.0, -5.0, True],
    ]


def test_a_ledger_with_no_schedule_prints_no_schedule_lines(cast: Cast, tmp_path: Path) -> None:
    out = lake(cast, tmp_path, "sync")
    assert "schedule" not in out
    rebuilt = lake(cast, tmp_path, "rebuild", "--yes")
    assert "schedule" not in rebuilt


def test_a_rebuild_loads_the_schedule_tables_again(cast: Cast, tmp_path: Path) -> None:
    published_pair(cast, tmp_path)
    lake(cast, tmp_path, "sync")
    out = lake(cast, tmp_path, "rebuild", "--yes").splitlines()
    assert out[2].startswith("schedule snapshots: loaded 2 (42 activities)")


def test_a_snapshot_the_lake_could_not_take_is_named_in_the_sync_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from tl_cli.lake import _print_xer  # pyright: ignore[reportPrivateUsage]
    from tl_lake import XerSyncResult

    _print_xer(XerSyncResult(None, 0, 0, 0, 0, 0, 0, 0, 2))
    assert "could not be loaded" in capsys.readouterr().out
    _print_xer(XerSyncResult(None, 0, 0, 0, 0, 0, 0, 0, 0))
    assert capsys.readouterr().out == ""
