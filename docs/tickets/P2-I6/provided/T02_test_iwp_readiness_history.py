"""``mart_iwp_readiness_history``: one row per ``IWP.ReadinessEvaluated`` event (P2-I6 T02).

Copy this file to ``packages/tl-lake/tests/test_mart_iwp_readiness_history.py``. It builds the
bronze rows the model may read (``events``: ``seq``, ``scope``, ``event_type``, ``payload``) in a
temporary lake by direct INSERT, runs ``build_gold_marts`` and pins ``SELECT *``.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from tl_lake import LakeConfig
from tl_lake.duck import Duck, open_lake
from tl_lake.gold import build_gold_marts

P1, P2 = "project:P1", "project:P2"
MART = "mart_iwp_readiness_history"
COLUMNS = [
    "scope", "iwp_id", "seq", "evaluated_at", "today", "ready", "checks_total",
    "checks_blocked", "checks_pending", "blocked_names", "changed",
]  # fmt: skip


@pytest.fixture
def con(tmp_path: Path) -> Iterator[Duck]:
    with open_lake(LakeConfig.at(tmp_path / "lake"), write=True) as opened:
        opened.execute(
            "CREATE TABLE lake.main.events (seq BIGINT, scope VARCHAR, event_type VARCHAR, "
            "payload VARCHAR)"
        )
        yield opened


def check(name: str, state: str) -> dict[str, Any]:
    return {
        "name": name, "version": "1", "state": state, "detail": f"{name} {state}",
        "resolve_via": [], "count_ok": 0, "count_total": 1,
    }  # fmt: skip


def evaluated(
    con: Duck, seq: int, iwp: str, ready: bool, checks: list[dict[str, Any]],
    scope: str = P1, today: str = "2026-11-02",
) -> None:  # fmt: skip
    payload = {
        "iwp_id": iwp,
        "evaluated_at": f"{today}T08:00:00Z",
        "today": today,
        "ready": ready,
        "checks": checks,
        "facts_hash": "0" * 64,
        "feed_policy": "none",
    }
    con.execute(
        "INSERT INTO lake.main.events VALUES (?, ?, 'IWP.ReadinessEvaluated', ?)",
        [seq, scope, json.dumps(payload, sort_keys=True)],
    )


def rows(con: Duck) -> list[tuple[Any, ...]]:
    build_gold_marts(con)
    return con.execute(f"SELECT * FROM lake.main.{MART} ORDER BY iwp_id, seq").fetchall()


def test_no_evaluation_leaves_an_empty_table_with_the_contract_columns(con: Duck) -> None:
    con.execute("INSERT INTO lake.main.events VALUES (1, 'project:P1', 'IWP.Ready', '{}')")
    con.execute("INSERT INTO lake.main.events VALUES (2, 'internal', 'Internal.Redacted', '{}')")
    assert rows(con) == []
    described = con.execute(f"SELECT * FROM lake.main.{MART}").description
    assert [d[0] for d in described] == COLUMNS


def test_counts_blocked_names_sorted_and_the_first_row_is_changed(con: Duck) -> None:
    evaluated(
        con, 4, "I1", False,
        [check("permit", "blocked"), check("documents", "blocked"), check("crew", "pending"),
         check("access", "ok"), check("scaffold", "n_a")],
    )  # fmt: skip
    assert rows(con) == [
        (P1, "I1", 4, "2026-11-02T08:00:00Z", date(2026, 11, 2), False, 5, 2, 1,
         "documents,permit", True)
    ]  # fmt: skip


def test_changed_is_true_only_when_ready_or_the_blocked_names_differ_from_the_row_before(
    con: Duck,
) -> None:
    evaluated(con, 1, "I1", False, [check("b", "blocked"), check("a", "blocked")])
    evaluated(con, 3, "I1", False, [check("a", "blocked"), check("b", "blocked"), check("c", "ok")])
    evaluated(con, 5, "I1", False, [check("a", "blocked"), check("b", "pending")])
    evaluated(con, 6, "I1", True, [check("a", "ok"), check("b", "ok")])
    evaluated(con, 9, "I1", True, [check("a", "ok"), check("b", "pending")])
    got = rows(con)
    assert [(r[2], r[5], r[9], r[10]) for r in got] == [
        (1, False, "a,b", True),
        (3, False, "a,b", False),  # same names (order and an extra ok check do not matter)
        (5, False, "a", True),  # names differ
        (6, True, "", True),  # ready flips; no blocked check is an empty string
        (9, True, "", False),  # still ready, still no blocked name (pending is not blocked)
    ]
    counts = [(r[6], r[7], r[8]) for r in got]
    assert counts == [(2, 2, 0), (3, 2, 0), (2, 1, 1), (2, 0, 0), (2, 0, 1)]


def test_each_iwp_is_compared_with_its_own_previous_row_not_the_row_before_it_in_seq(
    con: Duck,
) -> None:
    evaluated(con, 1, "I1", True, [check("a", "ok")])
    evaluated(con, 2, "I2", False, [check("a", "blocked")], scope=P2)
    evaluated(con, 3, "I1", True, [check("a", "ok")])
    evaluated(con, 4, "I2", False, [check("a", "blocked")], scope=P2)
    evaluated(con, 5, "I2", False, [check("z", "blocked")], scope=P2)
    assert [(r[0], r[1], r[2], r[10]) for r in rows(con)] == [
        (P1, "I1", 1, True),
        (P1, "I1", 3, False),
        (P2, "I2", 2, True),
        (P2, "I2", 4, False),
        (P2, "I2", 5, True),
    ]


def test_an_evaluation_with_no_checks_has_zero_counts_and_empty_names(con: Duck) -> None:
    evaluated(con, 1, "I1", True, [])
    assert rows(con) == [
        (P1, "I1", 1, "2026-11-02T08:00:00Z", date(2026, 11, 2), True, 0, 0, 0, "", True)
    ]


def test_no_detail_resolve_via_or_hash_column_is_exposed(con: Duck) -> None:
    evaluated(con, 1, "I1", False, [check("a", "blocked")])
    build_gold_marts(con)
    described = con.execute(f"SELECT * FROM lake.main.{MART}").description
    assert [d[0] for d in described] == COLUMNS
    assert "detail" not in json.dumps(rows(con), default=str)
