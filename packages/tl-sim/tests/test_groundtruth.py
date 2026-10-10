"""The ground-truth log is canonical, so one seed gives one file and one digest."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from tl_sim import groundtruth as gt
from tl_sim.types import GroundTruth

AT = datetime(2026, 11, 2, 7, 0, tzinfo=UTC)


def item(ref: str = "K-1", **expect: object) -> GroundTruth:
    return GroundTruth(
        at=AT, actor="agent:sim-crew", intent=gt.RECORD_CREATED, ref=ref, expect=expect or {"a": 1}
    )


def test_a_line_is_compact_sorted_json_in_utc() -> None:
    other_zone = AT.astimezone(timezone(timedelta(hours=2)))
    line = gt.to_line(
        GroundTruth(other_zone, "agent:sim-crew", "post.created", "p", {"b": 1, "a": 2})
    )
    assert line == (
        '{"actor":"agent:sim-crew","at":"2026-11-02T07:00:00+00:00","expect":{"a":2,"b":1},'
        '"intent":"post.created","ref":"p"}'
    )


def test_a_line_round_trips() -> None:
    original = item("K-9", title="Valve é", n=2.5, flag=False)
    assert gt.from_line(gt.to_line(original)) == original


def test_the_digest_depends_on_content_and_order_only() -> None:
    a, b = item("K-1"), item("K-2")
    assert gt.digest([a, b]) == gt.digest([item("K-1"), item("K-2")])
    assert gt.digest([a, b]) != gt.digest([b, a])
    assert gt.digest([a]) != gt.digest([item("K-1", other=True)])


def test_the_log_appends_and_reads_back(tmp_path: Path) -> None:
    log = gt.GroundTruthLog(tmp_path / "deep" / "gt.ndjson")
    assert log.read() == [] and log.append([]) == 0
    assert log.append([item("K-1"), item("K-2")]) == 2
    assert log.append([item("K-3")]) == 1
    assert [i.ref for i in log.read()] == ["K-1", "K-2", "K-3"]
    assert log.digest() == gt.digest(log.read())
    assert log.path.read_text().count("\n") == 3
