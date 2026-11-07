"""T06a2: the readiness check ``rfis_answered`` (P2-I2-T06a2).

The IWP is a hand-written ``awp.IWP`` row; each RFI is a hand-written core record, an item row (with
``subtype`` on the item row) and a Technical row, linked from the IWP by an active ``references``
link. One SQLite ledger per scenario.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, event, text
from tl_adapters.db import create_schema
from tl_core.readiness import (
    CheckResult,
    ContractViolation,
    ContractWorld,
    IwpFacts,
    check_readiness_contract,
    load_checks,
)
from tl_mod_correspondence.names import TECHNICAL

TODAY = date(2026, 11, 2)
IWP_TYPE = "awp.IWP"
RECORD_TYPES = frozenset({TECHNICAL, IWP_TYPE})
NO_RFIS = "no RFIs linked to this work package"
UNKNOWN = "the RFIs of this work package could not be read"


class Ledger:
    """A temp SQLite ledger with hand-written rows; one file per scenario."""

    def __init__(self, db: Path) -> None:
        create_schema(db)
        self.engine = create_engine(f"sqlite:///{db}")
        self.count = 0
        self.iwp = self.record(IWP_TYPE, "P123-IWP-PIP-0001", "Draft")

    def _next(self) -> str:
        self.count += 1
        return f"rec{self.count:05d}"

    def record(self, rtype: str, key: str, status: str | None, voided: int = 0) -> str:
        rid = self._next()
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO cur_core_record (id, key, type, scope, title, status, voided, "
                    "version, last_seq, created_at, updated_at) VALUES (:id, :key, :type, "
                    ":scope, :title, :status, :voided, 1, 1, '2026-11-01', '2026-11-01')"
                ),
                {
                    "id": rid,
                    "key": key,
                    "type": rtype,
                    "scope": "P123",
                    "title": "a title that must never appear in a detail",
                    "status": status,
                    "voided": voided,
                },
            )
        return rid

    def item(self, rid: str, subtype: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO cur_correspondence_correspondence (id, scope, number, direction, "
                    "medium, received_via, subtype, last_seq) VALUES (:id, 'P123', :num, 'out', "
                    "'email', 'manual', :subtype, 1)"
                ),
                {"id": rid, "num": rid, "subtype": subtype},
            )
            conn.execute(
                text(
                    "INSERT INTO cur_correspondence_technical_item (id, scope, question, last_seq) "
                    "VALUES (:id, 'P123', 'a question', 1)"
                ),
                {"id": rid},
            )

    def rfi(self, key: str, status: str | None, *, subtype: str = "rfi", voided: int = 0) -> str:
        rid = self.record(TECHNICAL, key, status, voided)
        self.item(rid, subtype)
        self.link(self.iwp, rid)
        return rid

    def link(self, frm: str, to: str, relation: str = "references", status: str = "active") -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO cur_links (link_id, scope, from_id, to_id, relation, status, "
                    "source, created_by, created_at, updated_at, version, last_seq) VALUES "
                    "(:lid, 'P123', :frm, :to, :rel, :st, 'test', 'test', '2026-11-01', "
                    "'2026-11-01', 1, 1)"
                ),
                {
                    "lid": f"link-{frm}-{to}-{relation}-{status}",
                    "frm": frm,
                    "to": to,
                    "rel": relation,
                    "st": status,
                },
            )

    def facts(self) -> IwpFacts:
        return IwpFacts(record_id=self.iwp, scope="P123", key="P123-IWP-PIP-0001", status="Draft")

    def evaluate(self, check: Any) -> tuple[CheckResult, int]:
        statements: list[str] = []
        with self.engine.connect() as conn:
            event.listen(
                conn,
                "before_cursor_execute",
                lambda _c, _cu, stmt, *_r: statements.append(stmt),
            )
            result = check.evaluate(conn, self.facts(), TODAY)
        return result, len(statements)


@pytest.fixture
def check() -> Any:
    return load_checks()["rfis_answered"]


@pytest.fixture
def ledger(tmp_path: Path) -> Ledger:
    return Ledger(tmp_path / "rfis.db")


def test_load_checks_finds_rfis_answered() -> None:
    assert "rfis_answered" in load_checks()


@pytest.mark.parametrize("with_rfi", [False, True], ids=["no-RFI", "RFI"])
def test_the_contract_passes(check: Any, ledger: Ledger, with_rfi: bool) -> None:
    if with_rfi:
        ledger.rfi("P123-RFI-0001", "Answered")
    world = ContractWorld(ledger.engine.connect, ledger.facts(), TODAY, RECORD_TYPES, False)
    try:
        check_readiness_contract(check, world)
    except ContractViolation as exc:  # pragma: no cover
        pytest.fail(str(exc))


def test_no_rfi_is_ok_with_the_fixed_detail(check: Any, ledger: Ledger) -> None:
    res, _ = ledger.evaluate(check)
    assert res.state == "ok" and res.detail == NO_RFIS


def test_all_answered_accepted_closed_is_ok(check: Any, ledger: Ledger) -> None:
    for n, status in enumerate(("Answered", "Accepted", "Closed"), start=1):
        ledger.rfi(f"P123-RFI-{n:04d}", status)
    res, _ = ledger.evaluate(check)
    assert (res.state, res.count_ok, res.count_total) == ("ok", 3, 3)
    assert res.detail == "3/3 RFIs answered"


def test_one_awaiting_response_is_pending(check: Any, ledger: Ledger) -> None:
    ledger.rfi("P123-RFI-0001", "Answered")
    ledger.rfi("P123-RFI-0002", "Answered")
    open_rid = ledger.rfi("P123-RFI-0003", "Awaiting response")
    res, _ = ledger.evaluate(check)
    assert (res.state, res.count_ok, res.count_total) == ("pending", 2, 3)
    assert [r.record_id for r in res.resolve_via] == [open_rid]


def test_a_draft_rfi_is_blocked_and_wins_over_pending(check: Any, ledger: Ledger) -> None:
    ledger.rfi("P123-RFI-0001", "Awaiting response")
    draft = ledger.rfi("P123-RFI-0002", None)
    res, _ = ledger.evaluate(check)
    assert (res.state, res.count_ok, res.count_total) == ("blocked", 0, 2)
    assert res.resolve_via[0].record_id == draft


def test_void_rfi_and_tq_are_ignored(check: Any, ledger: Ledger) -> None:
    ledger.rfi("P123-RFI-0001", "Answered")
    ledger.rfi("P123-RFI-0002", "Void")
    ledger.rfi("P123-TQ-0001", None, subtype="tq")
    res, _ = ledger.evaluate(check)
    assert (res.state, res.count_ok, res.count_total) == ("ok", 1, 1)


def test_sixty_open_rfis_list_fifty_in_at_most_two_statements(check: Any, ledger: Ledger) -> None:
    for n in range(1, 61):
        ledger.rfi(f"P123-RFI-{n:04d}", "Issued")
    res, statements = ledger.evaluate(check)
    assert res.state == "pending" and len(res.resolve_via) == 50 and res.count_total == 60
    assert statements <= 2


def test_a_failed_read_is_unknown_with_the_fixed_detail(
    check: Any, ledger: Ledger, tmp_path: Path
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'bare.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE unrelated (id INTEGER)"))
    with engine.connect() as conn:
        res = check.evaluate(conn, ledger.facts(), TODAY)
    engine.dispose()
    assert res.state == "unknown" and res.detail == UNKNOWN
