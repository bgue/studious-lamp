"""INS-B5 twin: a finding that names a hidden record reads like one that names an unknown id.

P2-INS-T04.

Both twins start from ``seed_world`` of ``test_checks.py``. World X names the hidden record; world Y
is the same seed with the hidden id replaced by a fresh id that names nothing. The full list of
findings of ``record_checks`` must be equal in X and Y, for the readiness finding (its resolve_via)
and for the constraint case (its subject). Both twins run on every adapter the root conftest
offers (SQLite; Postgres under ``--adapters sqlite,postgres``).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text
from tl_core.insights.checks import record_checks
from tl_core.insights.types import CheckFinding
from tl_core.util import new_ulid
from tl_mod_awp.insight_checks import HIDDEN_LINE

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_checks import SOURCES, USER, world  # noqa: E402  # pyright: ignore[reportMissingImports]


def dump(findings: list[CheckFinding]) -> list[dict[str, Any]]:
    return [f.model_dump() for f in findings]


def test_a_readiness_finding_naming_a_hidden_record_reads_like_an_unknown_id(db: Any) -> None:
    with world(db) as (conn, ids, facts):
        named = dump(record_checks(conn, facts, SOURCES, USER))
        raw = conn.execute(
            text("SELECT resolve_via_json FROM cur_awp_readiness_check WHERE state = 'blocked'")
        ).scalar_one()
        assert ids["hidden"] in raw  # world X names the hidden record
        fresh = new_ulid()
        conn.execute(
            text(
                "UPDATE cur_awp_readiness_check SET resolve_via_json = :v WHERE state = 'blocked'"
            ),
            {"v": raw.replace(ids["hidden"], fresh)},
        )  # world Y names an id that names nothing
        unknown = dump(record_checks(conn, facts, SOURCES, USER))
    assert named == unknown  # the full list, finding for finding
    assert named[0]["source"] == "readiness" and named[0]["text"].endswith(HIDDEN_LINE)
    assert ids["hidden"] not in str(named)


def test_a_constraint_on_a_hidden_subject_reads_like_one_on_an_unknown_subject(db: Any) -> None:
    with world(db) as (conn, ids, facts):
        before = dump(record_checks(conn, facts, SOURCES, USER))
        assert any(f["source"] == "constraints" for f in before)  # the twin is not vacuous
        conn.execute(text("UPDATE cur_core_constraint SET subject_id = :h"), {"h": ids["hidden"]})
        named = dump(record_checks(conn, facts, SOURCES, USER))  # world X: subject is hidden
        conn.execute(
            text("UPDATE cur_core_constraint SET subject_id = :n"), {"n": new_ulid()}
        )  # world Y: subject names nothing
        unknown = dump(record_checks(conn, facts, SOURCES, USER))
    assert named == unknown  # the full list, finding for finding
    assert not any(f["source"] == "constraints" for f in named)
    assert named != before  # the subject change is visible: the constraint finding is gone
