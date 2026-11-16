"""The job ``permits.lapse``: flags a lapse once, changes nothing else, leaks no text."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from permit_world import SCOPE, START, World
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from tl_adapters.db import make_uow_factory, open_uow
from tl_adapters.queue import job_queue_for
from tl_core import confidentiality as cf
from tl_core.jobs import JobFailure, JobRunner
from tl_core.jobs.types import Claim
from tl_core.services.errors import ReservedIdentifierError
from tl_core.services.reserved import refuse_reserved
from tl_mod_permits import lapse, views
from tl_mod_permits.commands import RequestPermit
from tl_mod_permits.lapse import LapseKind, job_id, parse_job_id, request, run_once
from tl_mod_permits.names import JOB_ACTOR, JOB_KIND, JOB_SOURCE, PERMIT_TABLE

LATE = START + timedelta(hours=12)  # 19:00, after the first valid_until (18:00)
PROJECT = "P123"
CLOSED_COLUMNS = ("lapse_flagged_for", "last_seq")


def run(world: World, now: datetime | None = None, project: str = PROJECT) -> int:
    """Queue and run the job for the minute of ``now`` (the world's clock by default); the number
    of events it appended."""
    factory = make_uow_factory(world.db)
    try:
        return run_once(factory, project, world.at if now is None else now)
    finally:
        factory.dispose()


def flagged(world: World) -> list[dict[str, Any]]:
    return world.rows(
        "SELECT stream_id, payload, actor, source, event_type FROM events "
        "WHERE event_type = 'Permit.Lapsed' ORDER BY seq"
    )


def payload(row: dict[str, Any]) -> dict[str, Any]:
    raw = row["payload"]
    return raw if isinstance(raw, dict) else json.loads(raw)


def flag_of(world: World, permit: str) -> str | None:
    found = world.row(permit)["lapse_flagged_for"]
    return None if found is None else str(found)


def instant(value: Any) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


class Statements:
    """The statements of every engine while the block runs (adapter neutral)."""

    def __init__(self) -> None:
        self.seen: list[str] = []

    def _on(self, _c: Any, _cur: Any, statement: str, *_a: Any) -> None:
        self.seen.append(statement)

    def __enter__(self) -> Statements:
        event.listen(Engine, "before_cursor_execute", self._on)
        return self

    def __exit__(self, *_exc: object) -> None:
        event.remove(Engine, "before_cursor_execute", self._on)

    def event_inserts(self) -> list[str]:
        return [s for s in self.seen if s.lstrip().upper().startswith("INSERT INTO EVENTS")]


def test_a_lapsed_permit_is_flagged_once(world: World) -> None:
    permit = world.active()
    until = instant(world.row(permit)["valid_until"])
    assert run(world, START + timedelta(hours=2)) == 0  # still valid
    world.at = LATE
    assert run(world) == 1
    (flag,) = flagged(world)
    assert flag["stream_id"] == permit
    assert flag["actor"] == JOB_ACTOR and flag["source"] == JOB_SOURCE
    body = payload(flag)
    assert instant(body["valid_until"]) == until and instant(body["at"]) == LATE
    assert body["record_id"] == permit and body["feed_policy"] == "none"
    assert instant(flag_of(world, permit)) == until
    # the same instant again, and a later one: nothing, and no insert into events
    with Statements() as spy:
        assert run(world) == 0
        assert run(world, LATE + timedelta(minutes=5)) == 0
    assert spy.event_inserts() == []
    assert len(flagged(world)) == 1


def test_a_permit_is_lapsed_at_the_very_instant_its_validity_ends(world: World) -> None:
    permit = world.active()
    until = instant(world.row(permit)["valid_until"])
    assert run(world, until - timedelta(minutes=1)) == 0
    assert run(world, until) == 1  # the same boundary as rules.effective_state
    assert instant(flag_of(world, permit)) == until


def test_the_shown_state_is_lapsed_with_or_without_the_job(world: World) -> None:
    permit = world.active()
    number = str(world.row(permit)["id"])
    key = world.scalar("SELECT key FROM cur_core_record WHERE id = :i", i=number)

    def shown(at: datetime) -> str:
        with open_uow(world.db, readonly=True) as uow:
            found = views.permit_detail(uow.conn(), SCOPE, key, now=at)
        assert found is not None
        return found.row.state

    assert shown(START + timedelta(hours=2)) == "Active"
    assert shown(LATE) == "Lapsed"
    world.at = LATE
    run(world)
    assert shown(LATE) == "Lapsed"
    assert shown(START + timedelta(hours=2)) == "Active"
    assert world.state(permit) == "Active"


def test_a_revalidated_permit_lapses_and_is_flagged_again(world: World) -> None:
    permit = world.active()
    world.at = LATE
    assert run(world) == 1
    world.call("rob", "RevalidatePermit", permit=permit)
    second = instant(world.row(permit)["valid_until"])
    assert second > LATE and run(world) == 0  # valid again: nothing
    world.at = second + timedelta(minutes=1)
    assert run(world) == 1
    assert run(world) == 0
    assert len(flagged(world)) == 2
    assert instant(payload(flagged(world)[1])["valid_until"]) == second
    assert instant(flag_of(world, permit)) == second


def test_only_active_permits_are_flagged(world: World) -> None:
    requested = world.request()
    approved = world.approved()
    suspended = world.active()
    world.call("uma", "SuspendPermit", permit=suspended, reason="Stop work")
    handed = world.active()
    world.call("rob", "HandBackPermit", permit=handed, handback_note="Clear")
    closed = world.active()
    world.call("rob", "HandBackPermit", permit=closed, handback_note="Clear")
    world.call("pam", "ClosePermit", permit=closed)
    cancelled = world.approved()
    world.call("sue", "CancelPermit", permit=cancelled, reason="Not needed")
    rejected = world.request()
    world.call("sue", "RejectPermit", permit=rejected, reason="No")
    live = world.active()
    world.at = LATE
    assert run(world) == 1
    assert [f["stream_id"] for f in flagged(world)] == [live]
    for other in (requested, approved, suspended, handed, closed, cancelled, rejected):
        assert flag_of(world, other) is None


def test_the_run_changes_nothing_but_the_flag(world: World) -> None:
    permit = world.active()
    other = world.active()
    world.call("uma", "SuspendPermit", permit=other, reason="Stop work")
    before = {p: world.row(p) for p in (permit, other)}
    states = {p: world.state(p) for p in (permit, other)}
    status_rows = world.rows("SELECT * FROM cur_core_record ORDER BY id")
    events_before = world.count()
    world.at = LATE
    assert run(world) == 1
    for p in (permit, other):
        after = world.row(p)
        assert {k: v for k, v in after.items() if k not in CLOSED_COLUMNS} == {
            k: v for k, v in before[p].items() if k not in CLOSED_COLUMNS
        }
        assert world.state(p) == states[p]
    assert world.row(permit)["lapse_flagged_for"] is not None
    assert world.row(other)["lapse_flagged_for"] is None
    after_rows = world.rows("SELECT * FROM cur_core_record ORDER BY id")
    keep = ("status", "id", "key", "scope", "type", "voided")
    assert [{k: r[k] for k in keep} for r in after_rows] == [
        {k: r[k] for k in keep} for r in status_rows
    ]
    new = world.rows("SELECT event_type FROM events ORDER BY seq")[events_before:]
    assert [n["event_type"] for n in new] == ["Permit.Lapsed"]


def test_a_run_is_keyed_by_project_and_minute(world: World) -> None:
    at = datetime(2026, 12, 1, 18, 7, 42, tzinfo=UTC)
    assert job_id(PROJECT, at) == "ptwlapse:P123:2026-12-01T18:07"
    assert parse_job_id("ptwlapse:P123:2026-12-01T18:07") == (
        PROJECT,
        datetime(2026, 12, 1, 18, 7, tzinfo=UTC),
    )
    for bad in (
        "ready:P123",
        "ptwlapse:2026-12-01T18:07",
        "ptwlapse:P1:2026-12-01",
        "ptwlapse::2026-12-01T18:07",
        "ptwlapse:P1:nope",
    ):
        with pytest.raises(ValueError):
            parse_job_id(bad)
    with pytest.raises(ValueError):
        job_id(PROJECT, datetime(2026, 12, 1, 18, 7))
    assert JOB_KIND == "permits.lapse" and JOB_SOURCE == "job:permits.lapse"
    factory = make_uow_factory(world.db)
    try:
        with factory() as uow:
            assert request(uow, PROJECT, at)
            assert not request(uow, PROJECT, at + timedelta(seconds=10))  # queued
            assert request(uow, PROJECT, at + timedelta(minutes=1))
            assert request(uow, "P999", at)
        run_once(factory, PROJECT, at)
        with factory() as uow:
            assert not request(uow, PROJECT, at)  # done
    finally:
        factory.dispose()


def test_a_job_with_a_bad_id_fails_for_good(world: World) -> None:
    claim = Claim(
        job_id="ptwlapse:nope",
        kind=JOB_KIND,
        scope=SCOPE,
        attempt=1,
        max_attempts=3,
        owner="t",
        lease_until="2026-01-01T00:00:00.000000Z",
    )
    with open_uow(world.db) as uow, pytest.raises(JobFailure) as caught:
        LapseKind().prepare(uow, claim)
    assert not caught.value.retryable
    assert LapseKind.kind == JOB_KIND


def test_an_active_permit_with_no_end_is_never_flagged(world: World) -> None:
    permit = world.active()
    with open_uow(world.db) as uow:
        uow.conn().execute(
            text(f"UPDATE {PERMIT_TABLE} SET valid_until = NULL WHERE id = :i"), {"i": permit}
        )
    world.at = LATE
    assert run(world) == 0
    assert run(world, LATE + timedelta(minutes=1)) == 0
    assert flagged(world) == [] and flag_of(world, permit) is None


def test_the_limit_requeues_once(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    if str(world.db).startswith("postgres"):  # the Postgres run seeds few: it is slow there
        monkeypatch.setattr(lapse, "LIMIT", 3)
    ids = world.active_many(lapse.LIMIT + 1, START + timedelta(hours=11))
    world.at = LATE
    factory = make_uow_factory(world.db)
    try:
        with factory() as uow:
            assert request(uow, PROJECT, world.at)
        with factory() as uow:
            queue = job_queue_for(uow.conn())
        results = JobRunner(factory, queue, [LapseKind()], worker_id="t").run_until_idle()
    finally:
        factory.dispose()
    assert len(results) == 2 and {r.job_id for r in results} == {job_id(PROJECT, LATE)}
    flags = flagged(world)
    assert len(flags) == lapse.LIMIT + 1
    assert sorted(f["stream_id"] for f in flags) == sorted(ids)
    assert run(world) == 0  # the requeued run was the last


def test_source_is_reserved() -> None:
    cmd = RequestPermit(
        actor="user:rob",
        source=JOB_SOURCE,
        scope=SCOPE,
        permit_type="general",
        area="A1",
        location_text="Pump room",
        work_description="Weld",
        holder="Rob",
        needed_from="2026-12-01",
        needed_until="2026-12-31",
    )
    with pytest.raises(ReservedIdentifierError, match="source"):
        refuse_reserved(cmd)
    refuse_reserved(cmd.model_copy(update={"source": "test"}))


def test_no_text_leaks(world: World, caplog: pytest.LogCaptureFixture) -> None:
    permit = world.active(area="Zone-Q9", holder="Holder-Zed", work_description="Secret weld Z7")
    secrets = ("Zone-Q9", "Holder-Zed", "Secret weld Z7")
    world.at = LATE
    with caplog.at_level(logging.DEBUG):
        assert run(world) == 1
        claim = Claim(
            job_id="ptwlapse:x",
            kind=JOB_KIND,
            scope=SCOPE,
            attempt=1,
            max_attempts=3,
            owner="t",
            lease_until="2026-01-01T00:00:00.000000Z",
        )
        with open_uow(world.db) as uow, pytest.raises(JobFailure) as caught:
            LapseKind().prepare(uow, claim)
    (flag,) = flagged(world)
    assert flag["stream_id"] == permit
    seen = json.dumps(flag, default=str) + str(caught.value) + caplog.text
    queue_rows = world.rows("SELECT * FROM job_queue")
    seen += json.dumps(queue_rows, default=str)
    for secret in secrets:
        assert secret not in seen


def test_hidden_permits_are_flagged_too(world: World) -> None:
    secret = world.hidden_record()
    permit = world.request("dora", for_record_id=secret)
    world.call("ada", "ApprovePermit", permit=permit)
    world.call("ada", "IssuePermit", permit=permit, precautions=["jha_attached"])
    world.at = LATE
    assert run(world) == 1
    assert flag_of(world, permit) is not None
    with open_uow(world.db, readonly=True) as uow:
        assert cf.is_hidden(uow.conn(), permit)
        key = (
            uow.conn()
            .execute(
                text("SELECT key FROM cur_core_record WHERE id = :i"),
                {"i": permit},
            )
            .scalar_one()
        )
        assert views.permit_detail(uow.conn(), SCOPE, key, now=LATE) is None


def test_another_project_is_not_touched(world: World) -> None:
    permit = world.active()
    world.at = LATE
    assert run(world, project="P999") == 0
    assert flag_of(world, permit) is None
