"""`tl lake sync --watch` waits `lake.sync.interval` between syncs (P0-I8-T07; brief 30.5)."""

from __future__ import annotations

from pathlib import Path

import pytest
from tl_adapters.sqlite.uow import open_uow
from tl_cli import lake
from tl_cli.main import app
from tl_core.settings import set_setting
from tl_lake import LakeError
from typer.testing import CliRunner
from typer.testing import Result as RunResult

runner = CliRunner()


def test_the_loop_runs_then_waits_the_interval_read_just_before_each_wait() -> None:
    events: list[str] = []
    intervals = iter([10.0, 20.0])

    def interval() -> float:
        value = next(intervals)
        events.append(f"read {value:g}")
        return value

    runs = lake.watch_loop(
        run_once=lambda: events.append("run"),
        interval=interval,
        sleep=lambda seconds: events.append(f"wait {seconds:g}"),
        max_runs=3,
    )
    assert runs == 3
    assert events == ["run", "read 10", "wait 10", "run", "read 20", "wait 20", "run"]


def test_there_is_no_wait_after_the_last_run() -> None:
    waits: list[float] = []
    lake.watch_loop(run_once=lambda: None, interval=lambda: 5.0, sleep=waits.append, max_runs=1)
    assert waits == []


def test_an_unreadable_interval_keeps_the_last_good_one_and_the_default_before_any() -> None:
    answers: list[object] = [ValueError("bad"), 42.0, OSError("busy")]

    def interval() -> float:
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return float(answer)  # type: ignore[arg-type]

    waits: list[float] = []
    lake.watch_loop(run_once=lambda: None, interval=interval, sleep=waits.append, max_runs=4)
    assert waits == [lake.DEFAULT_INTERVAL_S, 42.0, 42.0]


def test_a_failed_sync_is_reported_and_the_loop_goes_on(
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[int] = []

    def once() -> None:
        calls.append(1)
        if len(calls) == 1:
            raise LakeError("the lake is locked")

    runs = lake.watch_loop(run_once=once, interval=lambda: 1.0, sleep=lambda _s: None, max_runs=2)
    assert runs == 2
    assert "error: the lake is locked" in capsys.readouterr().err


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    values = {"TL_DB": str(tmp_path / "tl.db"), "TL_LAKE_DIR": str(tmp_path / "lake")}
    assert run(values, "init").exit_code == 0
    result = run(values, "record", "create", "--project", "P1", "--key", "A-1", "--title", "A")
    assert result.exit_code == 0, result.output
    return values


def run(env: dict[str, str], *args: str) -> RunResult:
    return runner.invoke(app, list(args), env=env)


def set_interval(env: dict[str, str], value: str) -> None:
    with open_uow(Path(env["TL_DB"])) as uow:
        set_setting(
            uow,
            key="lake.sync.interval",
            layer="company",
            value=value,
            actor="user:dev",
            source="test",
        )


def test_watch_syncs_each_round_and_waits_the_company_interval_read_again_each_time(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    waits: list[float] = []

    def sleep(seconds: float) -> None:
        waits.append(seconds)
        if len(waits) == 1:
            set_interval(env, "30s")  # changed while the watcher waits

    monkeypatch.setattr(lake, "_sleep", sleep)
    set_interval(env, "10m")
    result = run(env, "lake", "sync", "--watch", "--max-runs", "3")
    assert result.exit_code == 0, result.output
    assert waits == [600.0, 30.0]
    lines = result.stdout.splitlines()
    assert lines[0].startswith("synced seq 1..")
    assert lines[1].startswith("silver rows:")
    assert sum(ln.startswith("lake is up to date") for ln in lines) >= 1


def test_watch_without_a_setting_waits_the_default_of_five_minutes(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    waits: list[float] = []
    monkeypatch.setattr(lake, "_sleep", waits.append)
    result = run(env, "lake", "sync", "--watch", "--max-runs", "2")
    assert result.exit_code == 0, result.output
    assert waits == [300.0]


def test_max_runs_without_watch_is_refused(env: dict[str, str]) -> None:
    result = run(env, "lake", "sync", "--max-runs", "2")
    assert result.exit_code == 1
    assert "--max-runs only applies with --watch" in result.output


def test_a_plain_sync_still_syncs_once(env: dict[str, str]) -> None:
    result = run(env, "lake", "sync")
    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines()[0].startswith("synced seq 1..")


def test_ctrl_c_stops_the_watch_cleanly(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupt(_seconds: float) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(lake, "_sleep", interrupt)
    result = run(env, "lake", "sync", "--watch")
    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines()[-1] == "watch stopped"
