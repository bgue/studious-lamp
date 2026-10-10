"""The polling watcher: snapshots, diffs and the loop (FANOUT D8)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from tl_core.extypes.lock import write_lock
from tl_core.extypes.watch import Change, diff, snapshot, watch

FIXTURES = Path(__file__).resolve().parents[2] / "schema" / "fixtures" / "types"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    target = tmp_path / "types"
    shutil.copytree(FIXTURES, target)
    return target


def test_a_snapshot_has_one_entry_per_package(root: Path) -> None:
    assert sorted(snapshot(root)) == ["co.acme/LiftPlan/1.0.0", "co.acme/SafetyObservation/1.0.0"]


def test_a_snapshot_of_an_unchanged_tree_is_equal(root: Path) -> None:
    assert snapshot(root) == snapshot(root)
    assert diff(snapshot(root), snapshot(root)) == []


def test_an_edit_shows_as_changed_even_when_the_size_does_not(root: Path) -> None:
    before = snapshot(root)
    readme = root / "co.acme" / "LiftPlan" / "1.0.0" / "README.md"
    text = readme.read_text()
    readme.write_text(text.replace("planned", "PLANNED"))  # same length
    stat = readme.stat()
    os.utime(readme, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
    assert diff(before, snapshot(root)) == [Change("co.acme/LiftPlan/1.0.0", "changed")]


def test_a_rewritten_lock_shows_as_changed(root: Path) -> None:
    before = snapshot(root)
    package = root / "co.acme" / "LiftPlan" / "1.0.0"
    (package / "README.md").write_text("new text\n")
    write_lock(package)
    assert [c.kind for c in diff(before, snapshot(root))] == ["changed"]


def test_a_new_and_a_removed_package(root: Path) -> None:
    before = snapshot(root)
    shutil.copytree(
        root / "co.acme" / "LiftPlan" / "1.0.0", root / "co.acme" / "LiftPlan" / "1.1.0"
    )
    shutil.rmtree(root / "co.acme" / "SafetyObservation")
    assert diff(before, snapshot(root)) == [
        Change("co.acme/LiftPlan/1.1.0", "added"),
        Change("co.acme/SafetyObservation/1.0.0", "removed"),
    ]


def test_watch_reports_everything_first_then_only_changes(root: Path) -> None:
    seen: list[list[Change]] = []
    cycle = {"n": 0}

    def sleep(seconds: float) -> None:
        cycle["n"] += 1
        if cycle["n"] == 2:
            (root / "co.acme" / "LiftPlan" / "1.0.0" / "README.md").write_text("edited\n")
            write_lock(root / "co.acme" / "LiftPlan" / "1.0.0")

    cycles = watch(root, interval=0, on_change=seen.append, sleep=sleep, max_cycles=4)
    assert cycles == 4
    assert [[(c.path, c.kind) for c in batch] for batch in seen] == [
        [("co.acme/LiftPlan/1.0.0", "added"), ("co.acme/SafetyObservation/1.0.0", "added")],
        [("co.acme/LiftPlan/1.0.0", "changed")],
    ]


def test_watch_stops_when_asked(root: Path) -> None:
    calls: list[int] = []
    cycles = watch(
        root,
        interval=0,
        on_change=lambda changes: calls.append(len(changes)),
        stop=lambda: len(calls) >= 1,
        sleep=lambda _: None,
    )
    assert cycles == 1 and calls == [2]


def test_watch_waits_the_interval_between_cycles(root: Path) -> None:
    waits: list[float] = []
    watch(root, interval=2.5, on_change=lambda _: None, sleep=waits.append, max_cycles=3)
    assert waits == [2.5, 2.5]


def test_a_missing_root_is_an_empty_snapshot(tmp_path: Path) -> None:
    assert snapshot(tmp_path / "nowhere") == {}
