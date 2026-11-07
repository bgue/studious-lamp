"""Acceptance for P2-I2-T06a1: the readiness check ``documents_current``. SQLite temp ledger;
exit 0, one ``PASS <check>`` line per check, then ``T06a1 ok``.

Two readings of the pins are checked. The *facts* lines run the check on ``iwp_facts`` as the awp
module builds it (what a job sees). The *links* lines run the same check on the same IWP with
``pinned_document_links`` read from ``cur_links`` (every reference link of the IWP, stale and
floating ones too), which isolates the check's own rules. A ``FAIL`` on a facts line is a finding,
not a reason to weaken the expectation (see the ticket's Blocked section).

The IWPs are made by the awp commands (``CreateIwp``, ``PinIwpDocument``); the documents by the
documents module's own world. A pin on a restricted document is written with the documents
module's link helper, the way the pin command writes it, so the check sees the same rows.

Run: ``uv run python dev/accept/P2-I2/T06a1.py``.
"""

# ruff: noqa: E402  (the awp test world is imported after the sys.path line below)
from __future__ import annotations

import sys
import tempfile
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "tl-modules" / "awp" / "tests"))

from awp_world import SCOPE, World
from sqlalchemy import Connection, create_engine, event, text
from tl_adapters.db import as_target, create_schema
from tl_core import confidentiality as cf
from tl_core.readiness import (
    CheckResult,
    ContractViolation,
    ContractWorld,
    IwpFacts,
    check_readiness_contract,
    load_checks,
)
from tl_mod_awp.facts import iwp_facts
from tl_mod_documents.resolver import links_to_documents
from tl_mod_documents.testing import DocumentsWorld

TODAY = date(2026, 11, 7)
RECORD_TYPES = frozenset({"awp.IWP", "documents.Document", "documents.Revision"})
DOCUMENT_TYPE = "documents.Document"
MAX_STATEMENTS_OVER_RESOLVER = 3
failures: list[str] = []


def expect(condition: bool, what: str) -> None:
    if condition:
        print(f"PASS {what}")
    else:
        failures.append(what)
        print(f"FAIL {what}")


def main() -> int:
    tmp = Path(tempfile.mkdtemp())
    db = tmp / "t06a1.db"
    world = World(as_target(str(db)))
    create_schema(world.db)
    world.people()
    world.editions()
    objects = tmp / "objects"
    docs = world.documents(objects, "ISO-1", "ISO-2")
    dw = DocumentsWorld(world.db, objects)
    engine = create_engine(f"sqlite:///{db}")

    check = load_checks()["documents_current"]
    expect(
        check.watches == frozenset({"documents.Document", "documents.Revision"}),
        "load_checks() finds documents_current with its watches",
    )

    def facts(iwp: str) -> IwpFacts:
        with engine.connect() as conn:
            return iwp_facts(conn, iwp)

    def all_pins(iwp: str) -> IwpFacts:
        """The facts with every reference link of the IWP as a pin (stale and floating too)."""
        with engine.connect() as conn:
            found = iwp_facts(conn, iwp)
            ids = conn.execute(
                text(
                    "SELECT link_id FROM cur_links WHERE from_id = :id AND relation = 'references' "
                    "AND status IN ('active', 'stale') ORDER BY link_id"
                ),
                {"id": iwp},
            ).scalars()
            return found.model_copy(update={"pinned_document_links": [str(i) for i in ids]})

    def answer(found: IwpFacts) -> CheckResult:
        with engine.connect() as conn:
            return check.evaluate(conn, found, TODAY)

    def contract(found: IwpFacts, expect_n_a: bool = False) -> bool:
        world_ = ContractWorld(engine.connect, found, TODAY, RECORD_TYPES, expect_n_a)
        try:
            check_readiness_contract(check, world_)
        except ContractViolation as exc:
            print(f"  {exc}")
            return False
        return True

    def pin(iwp: str, number: str, code: str | None) -> None:
        world.call("uma", "PinIwpDocument", iwp=iwp, document=docs[number], pin=code)

    def refs(result: CheckResult) -> list[str]:
        return [r.record_id for r in result.resolve_via]

    # no pins -> n_a
    empty = world.iwp()
    expect(contract(facts(empty), expect_n_a=True), "the contract passes for an IWP with no pins")
    r = answer(facts(empty))
    expect(r.state == "n_a" and not r.resolve_via, "no pins -> n_a")

    # two current pins -> ok, 2/2
    pinned = world.iwp()
    pin(pinned, "ISO-1", "A")
    pin(pinned, "ISO-2", "A")
    expect(contract(facts(pinned)), "the contract passes for an IWP with pins")
    r = answer(facts(pinned))
    expect(
        r.state == "ok" and (r.count_ok, r.count_total) == (2, 2) and r.detail.startswith("2/2"),
        "two current pins -> ok, 2/2",
    )

    # a floating pin counts as current (the check, reading every reference link)
    floating = world.iwp()
    pin(floating, "ISO-2", None)
    r = answer(facts(floating))
    expect(r.state == "ok" and (r.count_ok, r.count_total) == (1, 1), "a floating pin -> current")
    r = answer(all_pins(floating))
    expect(
        r.state == "ok" and (r.count_ok, r.count_total) == (1, 1),
        "links: a floating pin -> current",
    )

    # a pin on a revision that does not exist -> blocked (unknown resolution)
    unknown = world.iwp()
    dw.link(unknown, "ISO-2", "ZZ")
    expect(contract(facts(unknown)), "the contract passes for a pin on a missing revision")
    r = answer(facts(unknown))
    expect(
        r.state == "blocked" and refs(r) == [docs["ISO-2"]] and r.count_ok == 0,
        "a pin on a revision that does not exist -> blocked, resolve_via is its document",
    )

    # a new issued revision of one pinned drawing -> blocked, 1/2, resolve_via is that document
    dw.create_revision("ISO-1")
    dw.attach("ISO-1", "B")
    dw.issue("ISO-1", "B", "IFR")
    r = answer(all_pins(pinned))
    expect(
        r.state == "blocked"
        and (r.count_ok, r.count_total) == (1, 2)
        and r.detail == "1/2 pinned drawings current; 1 behind"
        and refs(r) == [docs["ISO-1"]],
        "links: a new revision of a pinned drawing -> blocked, 1/2, resolve_via is that document",
    )
    r = answer(facts(pinned))
    expect(
        r.state == "blocked"
        and (r.count_ok, r.count_total) == (1, 2)
        and refs(r) == [docs["ISO-1"]],
        "facts: a new revision of a pinned drawing -> blocked, 1/2, resolve_via is that document",
    )

    # a hidden pinned document answers like a missing one (never a title, never an error)
    with cf.system_view():
        dw.register("ISO-H", confidentiality="restricted")
        dw.create_revision("ISO-H")
        dw.attach("ISO-H", "A")
        dw.issue("ISO-H", "A")
        hidden_id = str(dw.document("ISO-H").id)
    with engine.connect() as conn:
        expect(cf.is_hidden(conn, hidden_id), "the restricted document is hidden from a job read")
    mixed = world.iwp()
    pin(mixed, "ISO-2", "A")
    with cf.system_view():
        dw.link(mixed, "ISO-H", "A")
    r = answer(facts(mixed))
    expect(
        r.state == "blocked"
        and (r.count_ok, r.count_total) == (1, 2)
        and r.detail == "1/2 pinned drawings current"
        and hidden_id not in refs(r),
        "a hidden pinned document does not change the answer shape",
    )

    # 60 stale pins -> resolve_via has 50 entries
    bulk = world.iwp()
    bulk_numbers = [f"ISO-{1000 + n}" for n in range(60)]
    for number in bulk_numbers:
        dw.register(number)
        dw.create_revision(number)
        dw.attach(number, "A")
        dw.issue(number, "A")
    for number in bulk_numbers:
        world.call("uma", "PinIwpDocument", iwp=bulk, document=str(dw.document(number).id), pin="A")
        dw.create_revision(number)
        dw.attach(number, "B")
        dw.issue(number, "B", "IFR")
    r = answer(all_pins(bulk))
    expect(
        r.state == "blocked"
        and (r.count_ok, r.count_total) == (0, 60)
        and r.detail == "0/60 pinned drawings current; 60 behind"
        and len(r.resolve_via) == 50
        and all(ref.record_type == DOCUMENT_TYPE for ref in r.resolve_via),
        "links: 60 stale pins -> resolve_via has 50 entries",
    )

    # the check's own statements: none beyond the resolver's (limit 3)
    def statements(run: Callable[[Connection], object]) -> int:
        seen: list[str] = []

        def listen(_conn: Any, _cursor: Any, statement: str, *_rest: Any) -> None:
            seen.append(statement)

        with engine.connect() as conn:
            event.listen(conn, "before_cursor_execute", listen)
            try:
                run(conn)
            finally:
                event.remove(conn, "before_cursor_execute", listen)
        return len(seen)

    bulk_facts = all_pins(bulk)
    own = statements(lambda conn: check.evaluate(conn, bulk_facts, TODAY))
    resolver_only = statements(lambda conn: links_to_documents(conn, SCOPE, limit=1000))
    expect(
        0 <= own - resolver_only <= MAX_STATEMENTS_OVER_RESOLVER,
        f"statement count within the limit ({own} with the resolver's {resolver_only})",
    )

    engine.dispose()
    if failures:
        print(f"T06a1 FAILED: {len(failures)} check(s)")
        return 1
    print("T06a1 ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
