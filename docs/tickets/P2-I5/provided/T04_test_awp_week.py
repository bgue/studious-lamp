"""P2-I5-T04: `tl awp look-ahead` and the `tl awp week` verbs."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from test_cli_awp import ROOT, Cli, load_world, seed_copy
from tl_adapters.db import as_target, open_uow
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
        with open_uow(built.ww.w.db) as uow:
            conn = uow.conn()
            conn.execute(
                text(
                    "INSERT INTO cur_awp_readiness (iwp_id, scope, evaluated_at, today, ready, "
                    "facts_hash, as_of_seq) VALUES (:i, :s, '2026-10-05T00:00:00+00:00', "
                    "'2026-10-05', 0, 'h', 0)"
                ),
                {"i": built.iwps[0], "s": SCOPE},
            )
            for n, state in enumerate(("ok", "n_a", "unknown")):
                conn.execute(
                    text(
                        "INSERT INTO cur_awp_readiness_check (row_id, scope, iwp_id, name, "
                        "version, state, detail, count_ok, count_total, resolve_via_json, "
                        "as_of_seq) VALUES (:row, :s, :i, :n, '1', :st, '', 0, 0, '[]', 0)"
                    ),
                    {"row": f"r{n}", "s": SCOPE, "i": built.iwps[0], "n": f"check{n}", "st": state},
                )


def test_look_ahead_lists_the_linked_iwps_under_their_activity(
    built: Built, tmp_path: Path
) -> None:
    saved = dict(SCHEDULE_BASE)
    try:
        Plant(built, tmp_path)
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
        "2/3",
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
