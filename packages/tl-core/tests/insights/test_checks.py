"""The Checks read (P2-INS-S2): five sources, one shape, no leak, no write.

``seed_world`` writes the rows each source reads straight into the current-state tables (the
sources are pure reads of those tables), so the file needs no ledger. ``dev/accept/P2-INS/S2.py``
reuses it.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Connection, event, text
from tl_adapters.db import open_uow
from tl_core import confidentiality
from tl_core.confidentiality import Viewer
from tl_core.insights import checks as core_checks
from tl_core.insights.checks import (
    MAX_FINDINGS,
    MAX_PER_SOURCE,
    record_checks,
    record_facts,
)
from tl_core.insights.types import CheckFinding, RecordFacts
from tl_core.util import new_ulid
from tl_mod_awp import insight_checks as awp_checks
from tl_mod_correspondence import insight_checks as clock_checks
from tl_mod_materials import insight_checks as material_checks

SCOPE = "project:P123"
HIDDEN_LINE = awp_checks.HIDDEN_LINE
SOURCES = (
    awp_checks.findings,
    core_checks.constraint_findings,
    core_checks.expected_link_findings,
    clock_checks.findings,
    material_checks.findings,
)
USER = Viewer(actor="user:bob", level=0, account="user:bob")


def record(
    conn: Connection, type_: str, key: str, *, scope: str = SCOPE, status: str | None = None
) -> str:
    rid = new_ulid()
    conn.execute(
        text(
            "INSERT INTO cur_core_record (id, key, type, scope, title, status, version, last_seq, "
            "created_at, updated_at) VALUES (:i, :k, :t, :s, :k, :st, 1, 1, "
            "'2026-10-01T00:00:00Z', '2026-10-01T00:00:00Z')"
        ),
        {"i": rid, "k": key, "t": type_, "s": scope, "st": status},
    )
    return rid


def seed_world(conn: Connection) -> dict[str, str]:
    """An IWP with a blocked check, an open constraint, a missing expected link and a short
    take-off line; a correspondence item with an overdue clock (a clock hangs on an item, and an
    item is the only record that can have one); one visible and one hidden record named by the
    blocked check."""
    ids = {"iwp": record(conn, "awp.IWP", "P123-IWP-PIP-0042", status="Draft")}
    ids["doc"] = record(conn, "test.Plain", "P123-DOC-0001")
    ids["hidden"] = record(conn, "correspondence.Correspondence", "P123-COR-SECRET-0007")
    refs = [
        {"record_id": ids["doc"], "record_type": "test.Plain", "key": "P123-DOC-0001"},
        {"record_id": ids["hidden"], "record_type": "x", "key": "P123-COR-SECRET-0007"},
    ]
    conn.execute(
        text(
            "INSERT INTO cur_awp_readiness (iwp_id, scope, evaluated_at, today, ready, facts_hash,"
            " as_of_seq) VALUES (:i, :s, '2026-10-02T08:00:00Z', '2026-10-02', :r, :h, 1)"
        ),
        {"i": ids["iwp"], "s": SCOPE, "h": "0" * 64, "r": False},
    )
    for name, state, detail, via in (
        ("documents_current", "blocked", "stale: P123-COR-SECRET-0007", refs),
        ("materials_reserved", "pending", "2 requests open", []),
        ("scaffold_tagged", "ok", "all tagged", []),
        ("permits", "n_a", "no permit module", []),
        ("tools", "unknown", "could not read", []),
    ):
        conn.execute(
            text(
                "INSERT INTO cur_awp_readiness_check (row_id, scope, iwp_id, name, version, state,"
                " detail, count_ok, count_total, resolve_via_json, as_of_seq) VALUES (:r, :s, :i,"
                " :n, '1', :st, :d, 5, 7, :v, 1)"
            ),
            {"r": new_ulid(), "s": SCOPE, "i": ids["iwp"], "n": name, "st": state, "d": detail,
             "v": json.dumps(via)},
        )  # fmt: skip
    ids["constraint"] = record(conn, "core.Constraint", "P123-CON-0001", status="Open")
    conn.execute(
        text(
            "INSERT INTO cur_core_constraint (id, scope, subject_id, phase, severity, category, "
            "source, description_text, effective_at, last_seq) VALUES (:c, :s, :i, 'ready', "
            "'blocking', 'engineering', 'manual', :d, '2026-09-01', 1)"
        ),
        {"c": ids["constraint"], "s": SCOPE, "i": ids["iwp"], "d": "x" * 200},
    )
    # a clock hangs on a correspondence item (hidden for everyone unless the item says internal)
    ids["corr"] = record(conn, "correspondence.Correspondence", "P123-COR-0003")
    conn.execute(
        text(
            "INSERT INTO cur_correspondence_correspondence (id, scope, number, direction, medium, "
            "received_via, confidentiality, last_seq) VALUES (:i, :s, 'P123-COR-0003', 'in', "
            "'letter', 'manual', 'internal', 1)"
        ),
        {"i": ids["corr"], "s": SCOPE},
    )
    clock = record(conn, "correspondence.ResponseClock", "P123-CLK-0001")
    conn.execute(
        text(
            "INSERT INTO cur_correspondence_response_clock (id, scope, item_id, item_number, label,"
            " kind, start_on, duration_days, day_type, calendar, due_on, state, last_seq) VALUES "
            "(:c, :s, :i, 'P123-COR-0003', 'Answer due', 'response_from_them', '2026-09-01', 10, "
            "'calendar', 'default', '2026-09-11', 'running', 1)"
        ),
        {"c": clock, "s": SCOPE, "i": ids["corr"]},
    )
    mto = record(conn, "materials.MTO", "P123-MTO-0001")
    item = record(conn, "materials.ProjectItem", "ELB-90")
    ids["line"] = record(conn, "materials.MTOLine", "P123-MTO-0001/001")
    conn.execute(
        text(
            "INSERT INTO cur_materials_mto_line (id, scope, mto_id, line_no, project_item_id, qty, "
            "uom, work_package_id, reserved_qty, issued_qty, last_seq) VALUES (:l, :s, :m, 1, :p,"
            " 10, 'ea', :w, 4, 0, 1)"
        ),
        {"l": ids["line"], "s": SCOPE, "m": mto, "p": item, "w": ids["iwp"]},
    )
    return ids


@contextmanager
def world(db: Any) -> Iterator[tuple[Connection, dict[str, str], RecordFacts]]:
    with open_uow(db) as uow:
        conn = uow.conn()
        ids = seed_world(conn)
        facts = record_facts(conn, ids["iwp"], USER)
        assert facts is not None
        yield conn, ids, facts


def test_one_finding_per_source_in_source_order(db: Any) -> None:
    with world(db) as (conn, ids, facts):
        found = record_checks(conn, facts, SOURCES, USER)
        item = record_facts(conn, ids["corr"], USER)
        assert item is not None
        (late,) = record_checks(conn, item, SOURCES, USER)
    assert [f.source for f in found] == [
        "readiness",  # documents_current blocked first, then the pending and unknown ones
        "readiness",
        "readiness",
        "constraints",
        "expected_links",
        "shortages",
    ]
    assert [f.severity for f in found[:3]] == ["blocking", "warning", "warning"]
    assert {f.state for f in found[:3]} == {"blocked", "pending", "unknown"}  # not ok, not n_a
    shortage = found[-1]
    assert shortage.text == "short 6 ea" and shortage.severity == "warning"
    assert found[4].text.startswith("missing link:") and found[4].severity == "warning"
    assert (late.source, late.state, late.severity) == ("clocks", "overdue", "blocking")
    assert late.since == "2026-09-11" and late.text.startswith("Answer due was due 2026-09-11")


def test_a_hidden_resolve_via_record_leaves_no_key_in_any_text(db: Any) -> None:
    with world(db) as (conn, ids, facts):
        found = record_checks(conn, facts, SOURCES, USER)
    blocked = found[0]
    assert blocked.text.endswith(HIDDEN_LINE) and "SECRET" not in blocked.text
    assert [r.record_id for r in blocked.resolve_via] == [ids["doc"]]
    assert all("SECRET" not in f.model_dump_json() for f in found)
    assert all(ids["hidden"] not in f.model_dump_json() for f in found)


def test_nothing_dropped_keeps_the_detail(db: Any) -> None:
    with world(db) as (conn, ids, facts):
        conn.execute(
            text(
                "UPDATE cur_awp_readiness_check SET resolve_via_json = '[]' WHERE state = 'blocked'"
            )
        )
        found = record_checks(conn, facts, (awp_checks.findings,), USER)
    assert found[0].text == "documents current (5 of 7): stale: P123-COR-SECRET-0007"
    assert ids["hidden"]  # the id was never named by the finding


def test_constraint_text_is_category_key_age_and_a_cut_description(db: Any) -> None:
    with world(db) as (conn, _ids, facts):
        (one,) = record_checks(conn, facts, (core_checks.constraint_findings,), USER)
    head = "engineering P123-CON-0001, open "
    assert one.text.startswith(head) and one.text.endswith(" days: " + "x" * 120)
    assert one.severity == "blocking" and one.since == "2026-09-01"


def test_a_constraint_on_a_hidden_subject_is_no_finding(db: Any) -> None:
    with world(db) as (conn, ids, facts):
        conn.execute(text("UPDATE cur_core_constraint SET subject_id = :h"), {"h": ids["hidden"]})
        found = core_checks.constraint_findings(conn, facts, USER)
    assert found == []


def test_advisory_is_a_warning_and_assigned_counts_as_open(db: Any) -> None:
    with world(db) as (conn, ids, facts):
        conn.execute(text("UPDATE cur_core_constraint SET severity = 'advisory'"))
        conn.execute(
            text("UPDATE cur_core_record SET status = 'Assigned' WHERE id = :c"),
            {"c": ids["constraint"]},
        )
        (one,) = core_checks.constraint_findings(conn, facts, USER)
        conn.execute(
            text("UPDATE cur_core_record SET status = 'Cleared' WHERE id = :c"),
            {"c": ids["constraint"]},
        )
        none = core_checks.constraint_findings(conn, facts, USER)
    assert one.severity == "warning" and none == []


def test_only_overdue_clocks_and_short_lines_of_this_record(db: Any) -> None:
    with world(db) as (conn, ids, facts):
        item = record_facts(conn, ids["corr"], USER)
        assert item is not None
        assert len(clock_checks.findings(conn, item, USER)) == 1
        assert clock_checks.findings(conn, facts, USER) == []  # the clock is on another record
        conn.execute(text("UPDATE cur_correspondence_response_clock SET due_on = '2099-01-01'"))
        assert clock_checks.findings(conn, item, USER) == []
        conn.execute(text("UPDATE cur_materials_mto_line SET reserved_qty = 10"))
        assert material_checks.findings(conn, facts, USER) == []
        conn.execute(
            text("UPDATE cur_materials_mto_line SET reserved_qty = 0, work_package_id = NULL")
        )
        assert material_checks.findings(conn, facts, USER) == []
        conn.execute(
            text("UPDATE cur_materials_mto_line SET work_package_id = :w"), {"w": ids["line"]}
        )
        assert len(material_checks.findings(conn, facts, USER)) == 0  # names another record
        line_facts = facts.model_copy(update={"record_id": ids["line"], "record_type": "x"})
        assert len(material_checks.findings(conn, line_facts, USER)) == 1  # the line is the record


def test_readiness_is_for_an_iwp_only(db: Any) -> None:
    with world(db) as (conn, _ids, facts):
        other = facts.model_copy(update={"record_type": "test.Plain"})
        assert awp_checks.findings(conn, other, USER) == []


def test_a_failing_source_yields_nothing_and_the_read_goes_on(db: Any) -> None:
    def boom(conn: Connection, facts: RecordFacts, viewer: Viewer | None) -> list[CheckFinding]:
        conn.execute(text("SELECT * FROM no_such_table"))
        return []

    with world(db) as (conn, _ids, facts):
        found = record_checks(conn, facts, (boom, core_checks.constraint_findings), USER)
        assert [f.source for f in found] == ["constraints"]
        assert conn.execute(text("SELECT 1")).scalar_one() == 1  # the transaction is usable


def finding(source: str, severity: str, since: str | None, label: str = "x") -> CheckFinding:
    return CheckFinding(
        source=source, subject_id="s", state="open", text=label, since=since,
        severity=severity,  # pyright: ignore[reportArgumentType]
    )  # fmt: skip


def test_order_is_source_then_blocking_then_since_and_caps_apply(db: Any) -> None:
    def many(source: str, n: int) -> Any:
        return lambda c, f, v: [
            finding(source, "warning", f"2026-01-{i % 28 + 1:02d}") for i in range(n)
        ]

    def mixed(c: Connection, f: RecordFacts, v: Viewer | None) -> list[CheckFinding]:
        return [
            finding("clocks", "warning", "2026-01-01", "w-early"),
            finding("clocks", "blocking", "2026-03-01", "b-late"),
            finding("clocks", "blocking", "2026-02-01", "b-early"),
            finding("clocks", "blocking", None, "b-none"),
        ]

    with world(db) as (conn, _ids, facts):
        got = record_checks(conn, facts, (mixed, many("constraints", 80)), USER)
        assert [f.text for f in got if f.source == "clocks"] == [
            "b-early", "b-late", "b-none", "w-early",
        ]  # fmt: skip
        assert got[0].source == "constraints"  # source order beats severity
        assert sum(f.source == "constraints" for f in got) == MAX_PER_SOURCE
        sources = tuple(
            many(s, 60)
            for s in ("readiness", "constraints", "expected_links", "clocks", "shortages")
        )
        capped = record_checks(conn, facts, sources, USER)
    assert len(capped) == MAX_FINDINGS


def test_record_facts_is_none_for_unknown_and_hidden_alike(db: Any) -> None:
    with world(db) as (conn, ids, _facts):
        assert record_facts(conn, new_ulid(), USER) is None
        assert record_facts(conn, ids["hidden"], USER) is None
        assert record_facts(conn, ids["doc"], USER) is not None


def test_the_read_issues_no_write(db: Any) -> None:
    verbs: list[str] = []
    with world(db) as (conn, _ids, facts):

        def seen(_c: Any, _cur: Any, statement: str, *_a: Any) -> None:
            verbs.append(statement.lstrip().split(None, 1)[0].upper())

        event.listen(conn, "before_cursor_execute", seen)
        try:
            record_checks(conn, facts, SOURCES, USER)
        finally:
            event.remove(conn, "before_cursor_execute", seen)
    assert verbs and set(verbs) <= {"SELECT", "SAVEPOINT", "RELEASE", "WITH"}, set(verbs)
    assert confidentiality.current_viewer() == confidentiality.LOWEST  # the viewer is restored
