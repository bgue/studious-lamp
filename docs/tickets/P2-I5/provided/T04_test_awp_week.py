"""P2-I5-T04: `tl awp look-ahead` and the `tl awp week` verbs."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from test_cli_awp import ROOT, Cli, load_world, seed_copy
from tl_adapters.db import as_target, open_uow
from tl_cli.session import session_viewer
from tl_mod_awp import kpis
from tl_mod_awp.readiness.engine import evaluate_now
from tl_mod_schedule.testing import BASE as SCHEDULE_BASE
from tl_mod_schedule.testing import ScheduleWorld
from tl_xer.synth import make_xer, week_pair

PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
NUMBER_SQL = "SELECT key FROM cur_core_record WHERE id = :i"


def load_progress_world() -> Any:
    """``progress_world`` of the module tests, loaded by path (after ``load_world``)."""
    load_world()
    if "progress_world" not in sys.modules:
        path = ROOT / "packages" / "tl-modules" / "awp" / "tests" / "progress_world.py"
        spec = importlib.util.spec_from_file_location("progress_world", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules["progress_world"] = module
        spec.loader.exec_module(module)
    return sys.modules["progress_world"]


class Built:
    """The seed ledger with the awp 1.1.0 standards (the miss reasons) and three Issued IWPs."""

    def __init__(self, cli: Cli) -> None:
        self.cli = cli
        pw = load_progress_world()
        w = load_world().World(as_target(str(cli.db)))
        self.ww = pw.WeekWorld(pw.ProgressWorld(w))
        self.ww.standards()
        self.iwps = [self.ww.issued() for _ in range(3)]
        self.numbers = [str(w.scalar(NUMBER_SQL, i=i)) for i in self.iwps]

    def week(self, *argv: str, who: str = "user:uma") -> Any:
        return self.cli.write("week", *argv, who=who)

    def lines(self, *argv: str) -> list[str]:
        return self.cli.ok("week", *argv)


@pytest.fixture
def built(tmp_path: Path) -> Built:
    return Built(Cli(seed_copy(tmp_path), tmp_path))


def test_open_names_the_week_and_a_second_open_of_it_is_refused(built: Built) -> None:
    opened = built.week("open", "--date", "2026-11-05")
    assert opened.exit_code == 0, opened.output
    assert opened.stdout.startswith("open 2026-W45  version ")
    again = built.week("open", "--date", "2026-11-02")
    assert again.exit_code == 1
    assert "error:" in again.stderr
    assert "Traceback" not in again.output


def test_commit_outcome_and_close_give_the_ppc(built: Built) -> None:
    built.week("open", "--date", "2026-11-02")
    for number in built.numbers:
        done = built.week("commit", "2026-W45", number, "--hours", "40.0", "--foreman", "user:uma")
        assert done.exit_code == 0, done.output
        assert done.stdout.startswith("commit 2026-W45  version ")
    reason = built.lines("reasons")[0]
    for number, result in zip(built.numbers, ("done", "done", "missed"), strict=True):
        extra = ("--reason", reason) if result == "missed" else ()
        said = built.week("outcome", "2026-W45", number, result, *extra)
        assert said.exit_code == 0, said.output
    closed = built.week("close", "2026-W45", who="user:sue")
    assert closed.exit_code == 0, closed.output
    assert closed.stdout.startswith("close 2026-W45  version ")
    listed = built.lines("ls")
    assert listed[0] == "weeks: 1"
    assert listed[1].split() == ["2026-W45", "Closed", "3", "ppc", "66.7"]
    assert built.lines("ppc") == ["ppc 66.7  weeks 1"]


def number_of(built: Built, iwp: str) -> str:
    return str(built.ww.w.scalar(NUMBER_SQL, i=iwp))


def test_week_ppc_is_the_ppc_tile_with_open_weeks_among_the_latest_four(
    built: Built, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TL_ENV", "dev")
    monkeypatch.setenv("TL_SESSION_FILE", str(tmp_path / "session.json"))
    assert built.lines("ppc") == ["ppc -  weeks 0", "no closed week yet"]

    def commit_new(week: str) -> str:
        number = number_of(built, built.ww.issued())
        said = built.week("commit", week, number, "--hours", "40.0")
        assert said.exit_code == 0, said.output
        return number

    reason = built.lines("reasons")[0]
    closed_plans = (
        ("2026-10-26", "2026-W44", ("done", "missed")),
        ("2026-11-02", "2026-W45", ("done", "done", "missed")),
    )
    for day, week, results in closed_plans:
        assert built.week("open", "--date", day).exit_code == 0
        for result in results:
            number = commit_new(week)
            extra = ("--reason", reason) if result == "missed" else ()
            said = built.week("outcome", week, number, result, *extra)
            assert said.exit_code == 0, said.output
        closed = built.week("close", week, who="user:sue")
        assert closed.exit_code == 0, closed.output
    # Two open weeks sit among the latest four; their commitments are not in the pool.
    assert built.week("open", "--date", "2026-11-09").exit_code == 0
    assert built.week("open", "--date", "2026-11-16").exit_code == 0
    commit_new("2026-W46")

    shown = built.lines("ppc")
    target = as_target(str(built.cli.db))
    with open_uow(target, readonly=True) as uow:
        tile = kpis.ppc_tile(uow.conn(), SCOPE, session_viewer(target), weeks=4)
    assert shown == [f"ppc {tile.value}  weeks 2"]
    assert shown == ["ppc 60.0  weeks 2"]  # 3 done of 5 committed in the two closed weeks


def test_show_lists_each_commitment_and_an_unknown_week_is_one_error(built: Built) -> None:
    built.week("open", "--date", "2026-11-02")
    built.week("commit", "2026-W45", built.numbers[0], "--hours", "12.5")
    shown = built.lines("show", "2026-W45")
    assert shown[:4] == ["week 2026-W45", "state Committed", "ppc -", "commitments 1"]
    cells = shown[4].split()
    assert cells[:3] == [built.numbers[0], "Issued", "12.5"]
    missing = built.cli.project("week", "show", "2027-W01")
    assert missing.exit_code == 1
    assert "error: no week 2027-W01" in missing.stderr


def test_a_viewer_is_refused_every_write_and_a_stale_version_too(built: Built) -> None:
    refused = built.week("open", "--date", "2026-11-02", who="user:vera")
    assert refused.exit_code == 1
    assert "error:" in refused.stderr
    built.week("open", "--date", "2026-11-02")
    stale = built.week(
        "commit", "2026-W45", built.numbers[0], "--hours", "8", "--expected-version", "99"
    )
    assert stale.exit_code == 1
    assert built.lines("show", "2026-W45")[3] == "commitments 0"
    other = built.week("outcome", "2026-W45", built.numbers[0], "maybe")
    assert other.exit_code == 1
    assert "error: 'maybe' is not done or missed" in other.stderr
    assert "Traceback" not in other.output


def test_the_reasons_are_keys_one_per_line(built: Built) -> None:
    keys = built.lines("reasons")
    assert keys and all(k == k.strip() and " " not in k for k in keys)


class Plant:
    """A published schedule snapshot, and IWPs linked to its activity A1230."""

    def __init__(self, built: Built, tmp: Path) -> None:
        SCHEDULE_BASE["actor"] = "user:sue"
        self.sw = ScheduleWorld(built.ww.w.db, tmp / "objects")
        self.sw.define()
        first, _ = week_pair()
        self.sw.publish(self.sw.upload(make_xer(first)))
        for iwp in built.iwps[:2]:
            self.sw.link(iwp, "A1230")
        # A real evaluation through the engine entry point (appends IWP.ReadinessEvaluated).
        with open_uow(built.ww.w.db) as uow:
            view = evaluate_now(uow, built.iwps[0], date(2026, 10, 5))
        self.ok = sum(1 for c in view.checks if c.state in ("ok", "n_a"))
        self.total = len(view.checks)
        self.ready = view.ready


def test_look_ahead_lists_the_linked_iwps_under_their_activity(
    built: Built, tmp_path: Path
) -> None:
    saved = dict(SCHEDULE_BASE)
    try:
        plant = Plant(built, tmp_path)
        out = built.cli.ok("look-ahead", "--schedule", "MAIN", "--weeks", "4")
    finally:
        SCHEDULE_BASE.clear()
        SCHEDULE_BASE.update(saved)
    assert out[0].startswith("window ") and out[0].endswith("weeks 4  need-by lead 4w")
    at = next(n for n, line in enumerate(out) if line.startswith("A1230  "))
    first = built.numbers[0]
    mine = next(line for line in out[at + 1 :] if line.startswith(f"  {first}  "))
    assert mine.split() == [
        first,
        "Issued",
        "need-by",
        "2026-11-03",
        "ready",
        f"{plant.ok}/{plant.total}",
        "blocking",
        "0",
    ]
    other = next(line for line in out[at + 1 :] if line.startswith(f"  {built.numbers[1]}  "))
    assert other.split()[4:6] == ["ready", "-"]  # never evaluated
    assert all("Traceback" not in line for line in out)


def test_look_ahead_without_a_published_snapshot_is_one_error(built: Built) -> None:
    result = built.cli.project("look-ahead", "--schedule", "MAIN")
    assert result.exit_code == 1
    assert "error:" in result.stderr
    assert "Traceback" not in result.output
