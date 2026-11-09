"""``note_need`` (P2-INS-S2): one append-only write path, closed sets, no content, never aborts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Connection, text
from tl_adapters.db import open_uow, rebuild_projections
from tl_core import telemetry
from tl_core.telemetry import note_need, role_word
from tl_core.util import new_ulid

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
GOOD: dict[str, Any] = dict(
    request_kind="check",
    trigger="request",
    record_type="awp.IWP",
    viewer_role="user",
    outcome="shown",
    now=NOW,
)


def rows(conn: Connection) -> list[Any]:
    return list(conn.execute(text("SELECT * FROM telemetry_need ORDER BY recorded_at, row_id")))


def test_one_row_and_a_second_call_appends_a_second(db: Any) -> None:
    with open_uow(db) as uow:
        note_need(uow.conn(), **GOOD)
        note_need(uow.conn(), **{**GOOD, "outcome": "accepted"})
        got = rows(uow.conn())
    assert len(got) == 2 and got[0].row_id != got[1].row_id
    assert got[0].why is None and got[0].record_id is None and got[0].scope is None
    assert got[0].recorded_at == "2026-11-01T12:00:00.000000Z"
    assert got[0].viewer_role == "user" and got[0].need_id and got[0].duration_ms is None


def test_need_id_ties_outcomes_and_every_field_lands(db: Any) -> None:
    rid, nid = new_ulid(), new_ulid()
    with open_uow(db) as uow:
        note_need(
            uow.conn(), **{**GOOD, "trigger": "event:Workflow.Transitioned"},
            scope="project:P123", record_id=rid, provider_kind="rules", duration_ms=12, need_id=nid,
        )  # fmt: skip
        note_need(uow.conn(), **{**GOOD, "outcome": "dismissed"}, need_id=nid)
        got = rows(uow.conn())
    assert {r.need_id for r in got} == {nid}
    first = next(r for r in got if r.outcome == "shown")
    assert (first.scope, first.record_id, first.provider_kind, first.duration_ms) == (
        "project:P123", rid, "rules", 12,
    )  # fmt: skip


@pytest.mark.parametrize(
    "bad",
    [
        {"request_kind": "guess"},
        {"outcome": "ignored"},
        {"viewer_role": "root"},
        {"trigger": "screen:other"},
        {"trigger": "request " + "x" * 100},
        {"trigger": "free text about a weld"},
        {"record_type": "has spaces and text"},
        {"record_id": "not-an-id"},
        {"trigger": "screen:insights.checks", "record_id": new_ulid()},  # a screen names no record
        {"provider_kind": "Some Text"},
        {"duration_ms": -1},
        {"need_id": "x"},
    ],
)
def test_the_closed_sets_refuse_and_nothing_is_written(db: Any, bad: dict[str, Any]) -> None:
    with open_uow(db) as uow:
        with pytest.raises(ValueError):
            note_need(uow.conn(), **{**GOOD, **bad})
        assert rows(uow.conn()) == []


def test_the_screen_triggers_are_accepted_and_hold_no_record(db: Any) -> None:
    with open_uow(db) as uow:
        note_need(uow.conn(), **{**GOOD, "trigger": "screen:insights.checks"})
        (row,) = rows(uow.conn())
    assert row.trigger == "screen:insights.checks" and row.record_id is None


def test_the_table_has_no_content_column_and_the_signature_takes_no_text(db: Any) -> None:
    with open_uow(db) as uow:
        names = set(uow.conn().execute(text("SELECT * FROM telemetry_need WHERE 1 = 0")).keys())
    assert names == {
        "row_id", "need_id", "scope", "recorded_at", "request_kind", "trigger", "record_type",
        "record_id", "viewer_role", "provider_kind", "duration_ms", "outcome", "why",
    }  # fmt: skip
    params = set(note_need.__kwdefaults__ or {}) | {"conn"}
    assert not params & {"text", "content", "body", "prompt", "why", "detail", "message"}


def test_rows_past_retention_are_pruned_in_the_same_call_and_newer_stay(db: Any) -> None:
    old, edge = NOW - timedelta(days=366), NOW - timedelta(days=364)
    with open_uow(db) as uow:
        note_need(uow.conn(), **{**GOOD, "now": old})
        note_need(uow.conn(), **{**GOOD, "now": old})  # nothing is old enough yet: both stay
        note_need(uow.conn(), **{**GOOD, "now": edge})
        assert len(rows(uow.conn())) == 3
        note_need(uow.conn(), **GOOD)  # now the two 366-day rows are past a year
        got = rows(uow.conn())
    assert [r.recorded_at[:10] for r in got] == [edge.date().isoformat(), "2026-11-01"]


def test_retention_follows_the_setting(db: Any) -> None:
    from tl_core.settings.resolver import resolve

    with open_uow(db) as uow:
        assert resolve(uow.conn(), telemetry.RETENTION_SETTING).value == 365


def test_a_database_error_leaves_the_callers_transaction_usable(
    db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    with open_uow(db) as uow:
        conn = uow.conn()
        conn.execute(text("CREATE TABLE IF NOT EXISTS caller_work (n INTEGER)"))
        conn.execute(text("INSERT INTO caller_work VALUES (1)"))
        monkeypatch.setattr(telemetry, "_INSERT", text("INSERT INTO telemetry_nope VALUES (1)"))
        note_need(conn, **GOOD)  # must not raise
        conn.execute(text("INSERT INTO caller_work VALUES (2)"))  # the transaction still works
        assert conn.execute(text("SELECT COUNT(*) FROM caller_work")).scalar_one() == 2
        assert rows(conn) == []
    with open_uow(db, readonly=True) as uow:
        assert uow.conn().execute(text("SELECT COUNT(*) FROM caller_work")).scalar_one() == 2


def test_a_failed_prune_does_not_keep_the_row_or_abort(
    db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    with open_uow(db) as uow:
        monkeypatch.setattr(telemetry, "_PRUNE", text("DELETE FROM telemetry_nope"))
        note_need(uow.conn(), **GOOD)
        assert rows(uow.conn()) == []  # one savepoint: the insert went with the failed prune
        assert uow.conn().execute(text("SELECT 1")).scalar_one() == 1


def test_rebuild_projections_leaves_the_rows_alone(db: Any) -> None:
    with open_uow(db) as uow:
        note_need(uow.conn(), **GOOD)
        note_need(uow.conn(), **{**GOOD, "outcome": "unmet"})
    rebuild_projections(db)
    with open_uow(db, readonly=True) as uow:
        assert len(rows(uow.conn())) == 2


def test_role_word_is_the_most_powerful_role_or_unknown() -> None:
    assert role_word(["user", "admin"]) == "admin"
    assert role_word(["document_controller", "user"]) == "document_controller"
    assert role_word(["user"]) == "user"
    assert role_word([]) == "unknown"
