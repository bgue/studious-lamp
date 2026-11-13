"""The weekly plan and progress projectors (P2-I5 S1): hand-written events, no handler."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from tl_core.ledger import Event
from tl_mod_awp.module import spec
from tl_mod_awp.names import RECORD_TYPES, WEEKLY_PLAN
from tl_mod_awp.projectors.iwp import IwpProjector
from tl_mod_awp.projectors.progress import ProgressProjector
from tl_mod_awp.projectors.week import WeekProjector, commitment_id

PLAN = "01J9Z6Q4W3X2Y1V0T9S8R7Q6P0"
IWP = "01J9Z6Q4W3X2Y1V0T9S8R7Q6P1"
SCOPE = "project:P123"
NOW = datetime(2026, 11, 2, 8, 0, tzinfo=UTC)


def _engine() -> Engine:
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE cur_core_record (id TEXT PRIMARY KEY, version INTEGER, "
                "last_seq INTEGER, updated_at TEXT)"
            )
        )
        for stream in (PLAN, IWP):
            conn.execute(text("INSERT INTO cur_core_record VALUES (:i, 1, 0, '')"), {"i": stream})
        for projector in (WeekProjector(), ProgressProjector(), IwpProjector()):
            for statement in projector.ddl("sqlite"):
                conn.execute(text(statement))
    return engine


def _event(event_type: str, stream: str, seq: int, payload: dict[str, Any]) -> Event:
    return Event(
        event_id=f"e{seq}",
        seq=seq,
        stream_id=stream,
        stream_type="awp.WeeklyPlan",
        stream_version=seq,
        event_type=event_type,
        schema_version=1,
        scope=SCOPE,
        actor="user:ana",
        payload=payload,
        recorded_at=NOW,
        effective_at=NOW,
        correlation_id="c1",
        causation_id=None,
        source="test",
        prev_hash=None,
        hash="0" * 64,
    )


def _apply(engine: Engine, projector: Any, *events: Event) -> None:
    with engine.begin() as conn:
        for event in events:
            projector.apply(conn, event)


def _rows(engine: Engine, sql: str) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(text(sql))]


def test_the_plan_commitments_outcome_and_close_round_trip() -> None:
    engine = _engine()
    week = WeekProjector()
    _apply(
        engine,
        week,
        _event("WeeklyPlan.Opened", PLAN, 2, {"week": "2026-W45", "week_start": "2026-11-02"}),
        _event(
            "WeeklyPlan.IwpCommitted",
            PLAN,
            3,
            {"iwp_id": IWP, "foreman": "user:ana", "committed_hours": "40.0"},
        ),
        _event(
            "WeeklyPlan.OutcomeRecorded",
            PLAN,
            4,
            {"iwp_id": IWP, "outcome": "missed", "miss_reason": "Weather"},
        ),
        _event("WeeklyPlan.Closed", PLAN, 5, {"ppc": "0.0", "at": "2026-11-06T17:00:00Z"}),
    )
    [plan] = _rows(engine, "SELECT * FROM cur_awp_weekly_plan")
    assert (plan["week"], plan["week_start"], plan["ppc"]) == ("2026-W45", "2026-11-02", "0.0")
    assert plan["closed_at"] == "2026-11-06T17:00:00Z" and plan["last_seq"] == 5
    [row] = _rows(engine, "SELECT * FROM cur_awp_week_commitment")
    assert row["row_id"] == commitment_id(PLAN, IWP)
    assert (row["foreman"], row["committed_hours"]) == ("user:ana", "40.0")
    assert (row["outcome"], row["miss_reason"]) == ("missed", "Weather")
    [record] = _rows(engine, f"SELECT * FROM cur_core_record WHERE id = '{PLAN}'")
    assert record["version"] == 5 and record["last_seq"] == 5


def test_a_second_commit_of_one_iwp_replaces_the_row_and_reset_empties_both_tables() -> None:
    engine = _engine()
    week = WeekProjector()
    commit = {"iwp_id": IWP, "foreman": "user:ana", "committed_hours": "40.0"}
    _apply(
        engine,
        week,
        _event("WeeklyPlan.Opened", PLAN, 2, {"week": "2026-W45", "week_start": "2026-11-02"}),
        _event("WeeklyPlan.IwpCommitted", PLAN, 3, commit),
        _event("WeeklyPlan.IwpCommitted", PLAN, 4, {**commit, "committed_hours": "35.0"}),
    )
    [row] = _rows(engine, "SELECT * FROM cur_awp_week_commitment")
    assert row["committed_hours"] == "35.0"
    with engine.begin() as conn:
        week.reset(conn)
    assert _rows(engine, "SELECT * FROM cur_awp_weekly_plan") == []
    assert _rows(engine, "SELECT * FROM cur_awp_week_commitment") == []


def test_progress_replaces_the_row_of_its_iwp() -> None:
    engine = _engine()
    progress = ProgressProjector()
    body = {"iwp_id": IWP, "edition": "co.acme.awp@1.1.0", "at": "2026-11-05T16:00:00Z"}
    _apply(
        engine,
        progress,
        _event("IWP.ProgressRecorded", IWP, 2, {**body, "earned_pct": "30.0"}),
        _event("IWP.ProgressRecorded", IWP, 3, {**body, "earned_pct": "42.5"}),
    )
    [row] = _rows(engine, "SELECT * FROM cur_awp_iwp_progress")
    assert (row["earned_pct"], row["edition"], row["as_of_seq"]) == ("42.5", "co.acme.awp@1.1.0", 3)
    with engine.begin() as conn:
        progress.reset(conn)
    assert _rows(engine, "SELECT * FROM cur_awp_iwp_progress") == []


def test_started_and_field_completed_move_the_envelope_and_the_iwp_row() -> None:
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO cur_awp_iwp (id, scope, discipline, last_seq) "
                "VALUES (:i, :s, 'PIP', 1)"
            ),
            {"i": IWP, "s": SCOPE},
        )
    _apply(
        engine,
        ProgressProjector(),
        _event("IWP.Started", IWP, 4, {"at": "2026-11-03T07:00:00Z"}),
        _event("IWP.FieldCompleted", IWP, 6, {"at": "2026-11-06T15:00:00Z"}),
    )
    [iwp] = _rows(engine, "SELECT last_seq FROM cur_awp_iwp")
    [record] = _rows(engine, f"SELECT version FROM cur_core_record WHERE id = '{IWP}'")
    assert iwp["last_seq"] == 6 and record["version"] == 6


def test_an_unhandled_event_type_is_refused() -> None:
    engine = _engine()
    with pytest.raises(ValueError):
        _apply(engine, WeekProjector(), _event("IWP.Started", PLAN, 2, {}))
    with pytest.raises(ValueError):
        _apply(engine, ProgressProjector(), _event("WeeklyPlan.Closed", PLAN, 2, {}))


def test_the_module_registers_the_weekly_plan_and_both_projectors() -> None:
    module = spec()
    assert WEEKLY_PLAN in RECORD_TYPES and WEEKLY_PLAN in module.record_types
    names = {p.name for p in module.projectors()}
    assert {"awp_week", "awp_progress"} <= names
