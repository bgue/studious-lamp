"""Acceptance for T06a2 (P2-I2): the readiness check ``rfis_answered``. SQLite, exit 0, one
``PASS <check>`` line per check.

Run: ``uv run python dev/accept/P2-I2/T06a2.py``.

The IWP is a hand-written ``awp.IWP`` row; each RFI is a hand-written core record, an item row
(with ``subtype`` on the item row) and a Technical row, linked from the IWP by an active
``references`` link.
"""

from __future__ import annotations

import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

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
failures: list[str] = []


def expect(condition: bool, what: str) -> None:
    if condition:
        print(f"PASS {what}")
    else:
        failures.append(what)
        print(f"FAIL {what}")


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


def main() -> int:
    checks = load_checks()
    expect("rfis_answered" in checks, "load_checks() finds rfis_answered")
    check = checks["rfis_answered"]

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        def ledger(name: str) -> Ledger:
            return Ledger(root / f"{name}.db")

        # Contract: the no-RFI world and a world with RFIs.
        empty = ledger("empty")
        with_rfi = ledger("contract_rfi")
        with_rfi.rfi("P123-RFI-0001", "Answered")
        for label, lg in (("no-RFI", empty), ("RFI", with_rfi)):
            world = ContractWorld(lg.engine.connect, lg.facts(), TODAY, RECORD_TYPES, False)
            try:
                check_readiness_contract(check, world)
            except ContractViolation as exc:
                failures.append(str(exc))
                expect(False, f"the contract passes for the {label} world")
            else:
                expect(True, f"the contract passes for the {label} world")

        # No RFI -> ok with the fixed detail.
        res, _ = empty.evaluate(check)
        expect(
            res.state == "ok" and res.detail == NO_RFIS,
            "no RFI -> ok with the fixed detail",
        )

        # All answered -> ok, 3/3.
        lg = ledger("all_answered")
        for n, status in enumerate(("Answered", "Accepted", "Closed"), start=1):
            lg.rfi(f"P123-RFI-{n:04d}", status)
        res, _ = lg.evaluate(check)
        expect(
            res.state == "ok"
            and res.count_ok == 3
            and res.count_total == 3
            and res.detail == "3/3 RFIs answered",
            "all Answered/Accepted/Closed -> ok, 3/3",
        )

        # One Awaiting response -> pending, 2/3.
        lg = ledger("one_pending")
        lg.rfi("P123-RFI-0001", "Answered")
        lg.rfi("P123-RFI-0002", "Answered")
        open_rid = lg.rfi("P123-RFI-0003", "Awaiting response")
        res, _ = lg.evaluate(check)
        expect(
            res.state == "pending"
            and res.count_ok == 2
            and res.count_total == 3
            and [r.record_id for r in res.resolve_via] == [open_rid],
            "one Awaiting response -> pending, 2/3",
        )

        # A Draft (NULL state) one and a pending one -> blocked wins; blocked listed first.
        lg = ledger("blocked_wins")
        lg.rfi("P123-RFI-0001", "Awaiting response")
        draft_rid = lg.rfi("P123-RFI-0002", None)
        res, _ = lg.evaluate(check)
        expect(
            res.state == "blocked"
            and res.count_ok == 0
            and res.count_total == 2
            and len(res.resolve_via) > 0
            and res.resolve_via[0].record_id == draft_rid,
            "a Draft one -> blocked wins over a pending one",
        )

        # A Void RFI is ignored.
        lg = ledger("void")
        lg.rfi("P123-RFI-0001", "Answered")
        lg.rfi("P123-RFI-0002", "Void")
        res, _ = lg.evaluate(check)
        expect(
            res.state == "ok" and res.count_total == 1 and res.count_ok == 1,
            "a Void RFI is ignored",
        )

        # A TQ linked is ignored.
        lg = ledger("tq")
        lg.rfi("P123-RFI-0001", "Answered")
        lg.rfi("P123-TQ-0001", None, subtype="tq")
        res, _ = lg.evaluate(check)
        expect(
            res.state == "ok" and res.count_total == 1 and res.count_ok == 1,
            "a TQ (subtype tq) linked is ignored",
        )

        # 60 open RFIs -> resolve_via holds 50 entries.
        lg = ledger("sixty")
        for n in range(1, 61):
            lg.rfi(f"P123-RFI-{n:04d}", "Issued")
        res, statements = lg.evaluate(check)
        expect(
            res.state == "pending" and len(res.resolve_via) == 50 and res.count_total == 60,
            "60 open RFIs -> resolve_via has 50 entries",
        )

        # Statement count is at most 2 per evaluation.
        expect(statements <= 2, "statement count at most 2 per evaluation")

        # A failed read answers unknown with the fixed detail (no RFI table in this ledger).
        bare = root / "bare.db"
        engine = create_engine(f"sqlite:///{bare}")
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE unrelated (id INTEGER)"))
        with engine.connect() as conn:
            res = check.evaluate(conn, empty.facts(), TODAY)
        engine.dispose()
        expect(
            res.state == "unknown" and res.detail == UNKNOWN,
            "a failed read answers unknown with the fixed detail",
        )

    if failures:
        print("FAILED:", *failures, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
