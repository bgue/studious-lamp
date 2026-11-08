"""T06a1 and T06a3: the readiness check ``documents_current`` and the pin resolver filtered by link
ids, plus the D22/D26 twin (a hidden pinned document answers like a missing one).

The IWPs are made by the awp commands (``CreateIwp``, ``PinIwpDocument``) in the awp test world;
the documents by the documents module's own world. SQLite temp ledgers.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "awp" / "tests"))
from awp_world import SCOPE, World  # noqa: E402  # pyright: ignore[reportMissingImports]
from sqlalchemy import Connection, Engine, create_engine, event, text  # noqa: E402
from tl_adapters.db import as_target, create_schema  # noqa: E402
from tl_core import confidentiality as cf  # noqa: E402
from tl_core.readiness import (  # noqa: E402
    CheckResult,
    ContractViolation,
    ContractWorld,
    IwpFacts,
    check_readiness_contract,
    load_checks,
)
from tl_mod_awp.facts import iwp_facts  # noqa: E402
from tl_mod_documents.resolver import links_to_documents  # noqa: E402
from tl_mod_documents.testing import DocumentsWorld  # noqa: E402

TODAY = date(2026, 11, 7)
RECORD_TYPES = frozenset({"awp.IWP", "documents.Document", "documents.Revision"})
FIXED, PER_PINNED, PER_FLOATING = 2, 6, 2  # the pin-based statement bound (decision Q1)
OTHER_LINKS = 1100


class Rig:
    def __init__(self, tmp: Path, *numbers: str) -> None:
        self.world = World(as_target(str(tmp / "t06.db")))
        create_schema(self.world.db)
        self.world.people()
        self.world.editions()
        objects = tmp / "objects"
        self.docs = self.world.documents(objects, *numbers)
        self.dw = DocumentsWorld(self.world.db, objects)
        self.engine: Engine = create_engine(f"sqlite:///{tmp / 't06.db'}")
        self.check = load_checks()["documents_current"]

    def facts(self, iwp: str) -> IwpFacts:
        with self.engine.connect() as conn:
            return iwp_facts(conn, iwp)

    def pin_ids(self, iwp: str) -> list[str]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT link_id FROM cur_links WHERE from_id = :id AND relation = 'references' "
                    "AND status IN ('active', 'stale') ORDER BY link_id"
                ),
                {"id": iwp},
            ).scalars()
            return [str(i) for i in rows]

    def all_pins(self, iwp: str) -> IwpFacts:
        """The facts with every reference link of the IWP as a pin (stale and floating too)."""
        return self.facts(iwp).model_copy(update={"pinned_document_links": self.pin_ids(iwp)})

    def answer(self, found: IwpFacts) -> CheckResult:
        with self.engine.connect() as conn:
            return self.check.evaluate(conn, found, TODAY)

    def pin(self, iwp: str, number: str, code: str | None) -> None:
        self.world.call("uma", "PinIwpDocument", iwp=iwp, document=self.docs[number], pin=code)

    def issue_new_revision(self, number: str, code: str = "B") -> None:
        self.dw.create_revision(number)
        self.dw.attach(number, code)
        self.dw.issue(number, code, "IFR")

    def issued(self, number: str, **more: Any) -> str:
        self.dw.register(number, **more)
        self.dw.create_revision(number)
        self.dw.attach(number, "A")
        self.dw.issue(number, "A")
        return str(self.dw.document(number).id)

    def statements(self, run: Callable[[Connection], object]) -> int:
        seen: list[str] = []

        def listen(_c: Any, _cur: Any, statement: str, *_rest: Any) -> None:
            seen.append(statement)

        with self.engine.connect() as conn:
            event.listen(conn, "before_cursor_execute", listen)
            try:
                run(conn)
            finally:
                event.remove(conn, "before_cursor_execute", listen)
        return len(seen)


@pytest.fixture
def rig(tmp_path: Path) -> Iterator[Rig]:
    r = Rig(tmp_path, "ISO-1", "ISO-2", "ISO-3")
    yield r
    r.engine.dispose()


def refs(result: CheckResult) -> list[str]:
    return [r.record_id for r in result.resolve_via]


def test_load_checks_finds_documents_current_with_its_watches(rig: Rig) -> None:
    assert rig.check.watches == frozenset({"documents.Document", "documents.Revision"})


def test_no_pins_is_n_a_and_the_contract_holds(rig: Rig) -> None:
    empty = rig.world.iwp()
    world = ContractWorld(rig.engine.connect, rig.facts(empty), TODAY, RECORD_TYPES, True)
    try:
        check_readiness_contract(rig.check, world)
    except ContractViolation as exc:  # pragma: no cover - the failure text is the message
        pytest.fail(str(exc))
    got = rig.answer(rig.facts(empty))
    assert got.state == "n_a" and not got.resolve_via


def test_two_current_pins_are_ok(rig: Rig) -> None:
    pinned = rig.world.iwp()
    rig.pin(pinned, "ISO-1", "A")
    rig.pin(pinned, "ISO-2", "A")
    got = rig.answer(rig.facts(pinned))
    assert got.state == "ok" and (got.count_ok, got.count_total) == (2, 2)
    assert got.detail.startswith("2/2")


def test_a_floating_pin_is_current(rig: Rig) -> None:
    floating = rig.world.iwp()
    rig.pin(floating, "ISO-2", None)
    for found in (rig.facts(floating), rig.all_pins(floating)):
        got = rig.answer(found)
        assert got.state == "ok" and (got.count_ok, got.count_total) == (1, 1)


def test_a_pin_on_a_missing_revision_is_blocked(rig: Rig) -> None:
    unknown = rig.world.iwp()
    rig.dw.link(unknown, "ISO-2", "ZZ")
    got = rig.answer(rig.facts(unknown))
    assert got.state == "blocked" and refs(got) == [rig.docs["ISO-2"]] and got.count_ok == 0


def test_a_new_revision_makes_a_stale_pin_blocked(rig: Rig) -> None:
    pinned = rig.world.iwp()
    rig.pin(pinned, "ISO-1", "A")
    rig.pin(pinned, "ISO-2", "A")
    rig.issue_new_revision("ISO-1")
    for found in (rig.all_pins(pinned), rig.facts(pinned)):
        got = rig.answer(found)
        assert got.state == "blocked" and (got.count_ok, got.count_total) == (1, 2)
        assert refs(got) == [rig.docs["ISO-1"]]
    assert rig.answer(rig.all_pins(pinned)).detail == "1/2 pinned drawings current; 1 behind"


def test_sixty_stale_pins_list_fifty(rig: Rig) -> None:
    bulk = rig.world.iwp()
    numbers = [f"ISO-{1000 + n}" for n in range(60)]
    for number in numbers:
        rig.issued(number)
        rig.world.call(
            "uma", "PinIwpDocument", iwp=bulk, document=str(rig.dw.document(number).id), pin="A"
        )
        rig.issue_new_revision(number)
    got = rig.answer(rig.all_pins(bulk))
    assert got.state == "blocked" and (got.count_ok, got.count_total) == (0, 60)
    assert got.detail == "0/60 pinned drawings current; 60 behind" and len(got.resolve_via) == 50
    assert all(r.record_type == "documents.Document" for r in got.resolve_via)


def test_twin_hidden_pinned_document_equals_a_missing_one(rig: Rig) -> None:
    """D22/D26: the whole CheckResult for a hidden pinned document equals the missing one's."""
    with cf.system_view():
        hidden_id = rig.issued("ISO-H", confidentiality="restricted")
        missing_id = rig.issued("ISO-M")
    with rig.engine.connect() as conn:
        assert cf.is_hidden(conn, hidden_id)
    with_hidden, with_missing = rig.world.iwp(), rig.world.iwp()
    for iwp, number in ((with_hidden, "ISO-H"), (with_missing, "ISO-M")):
        rig.pin(iwp, "ISO-2", "A")
        with cf.system_view():
            rig.dw.link(iwp, number, "A")
    with rig.engine.begin() as conn:  # the pin now names no document
        conn.execute(text("DELETE FROM cur_core_record WHERE id = :id"), {"id": missing_id})
    a, b = rig.answer(rig.facts(with_hidden)), rig.answer(rig.facts(with_missing))
    assert a == b
    assert a.model_dump_json() == b.model_dump_json()  # byte for byte
    assert a.state == "blocked" and (a.count_ok, a.count_total) == (1, 2)
    assert hidden_id not in refs(a) and "ISO-H" not in a.detail


# --- T06a3: the resolver by link ids -----------------------------------------------------------


def three_pin_iwp(rig: Rig) -> str:
    target = rig.issued("ISO-0")
    assert target
    three = rig.world.iwp()
    rig.pin(three, "ISO-1", "A")
    rig.pin(three, "ISO-2", "A")
    rig.pin(three, "ISO-3", None)
    rig.issue_new_revision("ISO-1")
    return three


def add_other_links(rig: Rig, count: int, start: int) -> None:
    target = str(rig.dw.document("ISO-0").id)
    for n in range(start, start + count):
        rig.dw.link_from(rig.dw.tag(f"47-FV-{n:04d}"), target)


def test_statement_count_is_pin_based_and_no_cap_drops_a_pin(rig: Rig) -> None:
    three = three_pin_iwp(rig)
    add_other_links(rig, 100, 0)
    few = rig.statements(lambda c: rig.check.evaluate(c, rig.facts(three), TODAY))
    add_other_links(rig, OTHER_LINKS - 100, 100)  # a 1000 cap over the scope would drop the pins
    got = rig.answer(rig.facts(three))
    assert got.state == "blocked" and (got.count_ok, got.count_total) == (2, 3)
    assert got.detail.startswith("2/3") and refs(got) == [rig.docs["ISO-1"]]
    many = rig.statements(lambda c: rig.check.evaluate(c, rig.facts(three), TODAY))
    assert few == many <= FIXED + PER_PINNED * 2 + PER_FLOATING


def test_sixty_pins_are_all_counted(rig: Rig) -> None:
    bulk = rig.world.iwp()
    numbers = [f"ISO-6{n:02d}" for n in range(60)]
    for number in numbers:
        rig.issued(number)
        rig.world.call(
            "uma", "PinIwpDocument", iwp=bulk, document=str(rig.dw.document(number).id), pin="A"
        )
    got = rig.answer(rig.facts(bulk))
    assert got.state == "ok" and (got.count_ok, got.count_total) == (60, 60)
    rig.issue_new_revision("ISO-600")
    got = rig.answer(rig.facts(bulk))
    assert got.state == "blocked" and (got.count_ok, got.count_total) == (59, 60)
    assert refs(got) == [str(rig.dw.document("ISO-600").id)]


def test_resolver_link_ids(rig: Rig) -> None:
    three = three_pin_iwp(rig)
    add_other_links(rig, 30, 0)
    with rig.engine.connect() as conn:
        assert links_to_documents(conn, SCOPE, link_ids=[]) == []
    assert rig.statements(lambda c: links_to_documents(c, SCOPE, link_ids=[])) == 0
    ids = rig.pin_ids(three)
    with rig.engine.connect() as conn:
        everything = links_to_documents(conn, SCOPE, limit=10_000)
        wanted = [p for p in everything if p.link_id in set(ids)]
        subset = links_to_documents(conn, SCOPE, link_ids=ids, limit=len(ids))
        default = links_to_documents(conn, SCOPE)
    assert len(wanted) == 3 and subset == wanted
    assert default == everything[:1000]
