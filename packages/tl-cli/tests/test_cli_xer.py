"""`tl xer define|upload|start|publish|void|link|worker|reconcile` (P1-I4)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, as_target, open_uow
from tl_mod_schedule import views
from xercli_support import GATE, Cast, P, tl, xer_env, xer_file

AUTO_SIGN_IN = False  # this module signs in as three different people itself
SCHED = ("--schedule", "MAIN")


@pytest.fixture
def env(
    new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> dict[str, str]:
    return xer_env(new_db, monkeypatch, tmp_path)


@pytest.fixture
def cast(env: dict[str, str], tmp_path: Path) -> Cast:
    return Cast(env, tmp_path)


def defined(cast: Cast) -> None:
    out = tl(cast.dora, "xer", "define", "MAIN", *P, "--name", "Main schedule", ok=True).stdout
    assert out.startswith("defined MAIN ") and len(out.split()[2]) == 26


def detail(cast: Cast):  # noqa: ANN201
    with open_uow(cast.target, readonly=True) as uow:
        return views.schedule_detail(uow.conn(), "project:P123", "MAIN")


def uploaded_pair(cast: Cast, tmp_path: Path) -> None:
    defined(cast)
    for which in (0, 1):
        tl(cast.ursula, "xer", "upload", str(xer_file(tmp_path, which)), *P, *SCHED, ok=True)
    tl(cast.boss, "xer", "worker", "--once", ok=True)


def test_a_controller_defines_a_schedule_and_a_user_cannot(cast: Cast) -> None:
    refused = tl(cast.ursula, "xer", "define", "MAIN", *P, "--name", "x", ok=False)
    assert GATE in refused.output
    defined(cast)
    assert [s.code for s in views_list(cast)] == ["MAIN"]
    dup = tl(cast.dora, "xer", "define", "MAIN", *P, "--name", "x", ok=False)
    assert "error:" in dup.output
    bad = tl(cast.dora, "xer", "define", "X", *P, "--name", "x", "--type", "weekly", ok=False)
    assert "schedule_type must be one of" in bad.output


def views_list(cast: Cast):  # noqa: ANN201
    with open_uow(cast.target, readonly=True) as uow:
        return views.schedule_views(uow.conn(), "project:P123")


def test_any_signed_in_person_uploads_and_the_admin_builds(cast: Cast, tmp_path: Path) -> None:
    defined(cast)
    out = tl(cast.ursula, "xer", "upload", str(xer_file(tmp_path)), *P, *SCHED, ok=True).stdout
    words = out.split()
    assert words[:2] == ["queued", "MAIN#1"] and len(words[2]) == 26
    assert [(s.number, s.state) for s in detail(cast).snapshots] == [(1, "Uploaded")]
    ran = tl(cast.boss, "xer", "worker", "--once", ok=True).stdout.splitlines()
    assert ran[0].startswith("ran ") and ran[0].endswith(" schedule.build done")
    assert ran[-1] == "worker done: ran=1"
    [snapshot] = detail(cast).snapshots
    assert (snapshot.state, snapshot.data_date, snapshot.error_count) == (
        "Valid", "2026-10-05T08:00", 0,
    )  # fmt: skip
    assert snapshot.activity_count and snapshot.requested_by == "user:ursula"


def test_the_worker_and_reconcile_are_the_admins(cast: Cast) -> None:
    for who in (cast.dora, cast.ursula):
        for command in (("xer", "worker", "--once"), ("xer", "reconcile")):
            out = tl(who, *command, ok=False)
            assert "needs the admin role" in out.output, command


def test_upload_can_wait_and_start_later_and_never_queues_a_file_twice(
    cast: Cast, tmp_path: Path
) -> None:
    defined(cast)
    path = str(xer_file(tmp_path))
    held = tl(cast.ursula, "xer", "upload", path, *P, *SCHED, "--no-start", ok=True).stdout
    assert held.startswith("uploaded MAIN#1 ")
    assert tl(cast.ursula, "xer", "start", "1", *P, *SCHED, ok=True).stdout.startswith(
        "queued MAIN#1"
    )
    again = tl(cast.ursula, "xer", "start", "1", *P, *SCHED, ok=False)
    assert "already queued" in again.output
    tl(cast.boss, "xer", "worker", "--once", ok=True)
    twin = tl(cast.ursula, "xer", "upload", path, *P, *SCHED, ok=False)
    assert "(same SHA-256)" in twin.output
    # the refused upload left nothing behind: no second snapshot, no second queue entry
    assert [s.number for s in detail(cast).snapshots] == [1]


def test_upload_names_what_is_wrong(cast: Cast, tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    defined(cast)
    path = str(xer_file(tmp_path))
    nope = tl(cast.ursula, "xer", "upload", path, *P, "--schedule", "NOPE", ok=False)
    assert "no schedule 'NOPE'" in nope.output
    monkeypatch.setattr("tl_xer.limits.MAX_BYTES", 100)
    big = tl(cast.ursula, "xer", "upload", path, *P, *SCHED, ok=False)
    assert "an XER file may be at most 100" in big.output
    assert [s.number for s in detail(cast).snapshots] == []


def test_a_file_that_is_not_an_xer_makes_an_invalid_snapshot_with_a_report(
    cast: Cast, tmp_path: Path
) -> None:
    defined(cast)
    junk = tmp_path / "junk.xer"
    junk.write_bytes(b"this is not a P6 export\n")
    tl(cast.ursula, "xer", "upload", str(junk), *P, *SCHED, ok=True)
    tl(cast.boss, "xer", "worker", "--once", ok=True)
    [snapshot] = detail(cast).snapshots
    assert snapshot.state == "Invalid" and snapshot.error_count and snapshot.report_file_id
    refused = tl(cast.dora, "xer", "publish", "1", *P, *SCHED, ok=False)
    assert "only a Valid snapshot can be published" in refused.output


def test_publish_and_void_are_the_controllers(cast: Cast, tmp_path: Path) -> None:
    uploaded_pair(cast, tmp_path)
    for command in (("publish", "1"), ("void", "2", "--reason", "x")):
        assert GATE in tl(cast.ursula, "xer", *command, *P, *SCHED, ok=False).output
    assert tl(cast.dora, "xer", "publish", "1", *P, *SCHED, ok=True).stdout.strip() == (
        "published MAIN#1"
    )
    assert detail(cast).current_snapshot_number == 1
    assert tl(
        cast.dora, "xer", "void", "2", *P, *SCHED, "--reason", "wrong file", ok=True
    ).stdout == ("voided MAIN#2\n")
    assert [(s.number, s.state) for s in detail(cast).snapshots] == [(2, "Void"), (1, "Published")]
    assert (
        "snapshot MAIN#1 is Published"
        in tl(cast.dora, "xer", "void", "1", *P, *SCHED, "--reason", "x", ok=False).output
    )
    assert "no snapshot 7" in tl(cast.dora, "xer", "publish", "7", *P, *SCHED, ok=False).output


def test_publishing_flags_the_links_to_an_activity_that_left_and_says_so(
    cast: Cast, tmp_path: Path
) -> None:
    from tl_core.services.commands import CreateRecord
    from tl_core.services.records import handle_create_record

    uploaded_pair(cast, tmp_path)
    tl(cast.dora, "xer", "publish", "1", *P, *SCHED, ok=True)
    for key in ("REC-A", "REC-B"):
        with open_uow(cast.target) as uow:
            handle_create_record(
                uow,
                CreateRecord(
                    actor="user:ursula", source="test", scope="project:P123",
                    record_type="core.Record", title=key, key=key,
                ),
            )  # fmt: skip
    kept = tl(cast.ursula, "xer", "link", "REC-A", "A1230", *P, *SCHED, ok=True).stdout.split()
    assert kept[:4] == ["linked", "REC-A", "->", "MAIN/A1230"] and len(kept[4]) == 26
    tl(cast.ursula, "xer", "link", "REC-B", "A1990", *P, *SCHED, "--pin", "1", ok=True)
    out = tl(cast.dora, "xer", "publish", "2", *P, *SCHED, ok=True).stdout.splitlines()
    assert out[0] == "published MAIN#2"
    assert out[1].startswith("links to activities will be checked by the worker")

    def statuses() -> list[str]:
        with open_uow(cast.target, readonly=True) as uow:
            rows = uow.conn().execute(text("SELECT status FROM cur_links ORDER BY link_id")).all()
        return [str(r[0]) for r in rows]

    assert set(statuses()) == {"active"}  # the window: nothing flagged until the worker has run
    ran = tl(cast.boss, "xer", "worker", "--once", ok=True).stdout.splitlines()
    assert any("schedule.flag_orphans" in line for line in ran)
    assert sorted(statuses()) == ["active", "stale"]
    missing = tl(cast.ursula, "xer", "link", "REC-A", "A9999", *P, *SCHED, ok=False)
    assert "A9999" in missing.output
    assert (
        "no record with key 'NOPE'"
        in tl(cast.ursula, "xer", "link", "NOPE", "A1230", *P, *SCHED, ok=False).output
    )


def test_reconcile_writes_the_typed_rows_again_after_a_restore(cast: Cast, tmp_path: Path) -> None:
    uploaded_pair(cast, tmp_path)
    count = "SELECT COUNT(*) FROM sched_activity"

    def activities() -> int:
        with open_uow(cast.target, readonly=True) as uow:
            return int(uow.conn().execute(text(count)).scalar_one())

    before = activities()
    assert before > 0
    with open_uow(cast.target) as uow:
        uow.conn().execute(text("DELETE FROM sched_activity"))
        uow.conn().execute(text("DELETE FROM job_queue"))
    out = tl(cast.boss, "xer", "reconcile", ok=True).stdout.splitlines()
    assert out[0] == "requeued 0"
    assert [line.split()[:2] for line in out[1:3]] == [["MAIN#1", "rebuilt"], ["MAIN#2", "rebuilt"]]
    assert out[-1] == "reconciled 2 snapshot(s): rebuilt=2 problems=0"
    assert activities() == before
    again = tl(cast.boss, "xer", "reconcile", ok=True).stdout
    assert "rebuilt=0 problems=0" in again
    assert (
        "reconciled 0 snapshot(s)"
        in tl(cast.boss, "xer", "reconcile", "--project", "NONE", ok=True).stdout
    )


def test_reconcile_exits_1_for_a_file_that_no_longer_matches(cast: Cast, tmp_path: Path) -> None:
    uploaded_pair(cast, tmp_path)
    with open_uow(cast.target) as uow:
        uow.conn().execute(text("DELETE FROM sched_activity"))
        uow.conn().execute(
            text("UPDATE cur_schedule_schedule_snapshot SET source_sha256 = :x"), {"x": "0" * 64}
        )
    out = tl(cast.boss, "xer", "reconcile", ok=False)
    assert "unreadable" in out.output and "problems=2" in out.output


def test_the_worker_can_queue_lost_builds_again_first(cast: Cast, tmp_path: Path) -> None:
    defined(cast)
    tl(cast.ursula, "xer", "upload", str(xer_file(tmp_path)), *P, *SCHED, ok=True)
    with open_uow(cast.target) as uow:
        uow.conn().execute(text("DELETE FROM job_queue"))  # what a restore does
    nothing = tl(cast.boss, "xer", "worker", "--once", ok=True).stdout
    assert nothing.strip() == "worker done: ran=0"
    out = tl(cast.boss, "xer", "worker", "--once", "--requeue", ok=True).stdout.splitlines()
    assert out[0] == "requeued 1" and out[-1] == "worker done: ran=1"
    assert detail(cast).snapshots[0].state == "Valid"


def test_every_xer_command_that_writes_has_the_hooked_actor_option(tmp_path: Path) -> None:
    import typer.main
    from test_cli_actor_hooks import commands
    from tl_cli import actor_hook
    from tl_cli.main import app

    root = typer.main.get_command(app)
    actor_hook.install(root, tmp_path / "x.db")
    group = root.commands["xer"]  # type: ignore[attr-defined]
    writing = {("define",), ("upload",), ("start",), ("publish",), ("void",), ("link",)}
    found = {path[1:]: cmd for path, cmd in commands(group, ("xer",)) if cmd is not group}
    assert writing <= set(found)
    for path in writing:
        assert any("--actor" in getattr(p, "opts", []) for p in found[path].params), path
    assert as_target(str(tmp_path / "x.db")) is not None
