"""Acceptance for P2-I2-T06a3: the pin resolver filtered by link ids; ``documents_current`` on it.
SQLite temp ledger; exit 0, one ``PASS <check>`` line per check, then ``T06a3 ok``.

A scope with 1100 document links of other records (all to ``ISO-0``, which sorts before the pinned
drawings, so a LIMIT of 1000 over the scope would drop the pins) plus one IWP with 3 pins (one
stale): the check must answer ``blocked``, ``2/3``, with ``resolve_via`` the stale drawing, and its
statements must be within the pin-based bound (2 + 6 per pinned document + 2 per floating pin, so
16 for this IWP), the same with 100 or 1100 other links. The 60-pin IWP counts all 60.

Run: ``uv run python dev/accept/P2-I2/T06a3.py``.
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
from tl_core.readiness import CheckResult, load_checks
from tl_mod_awp.facts import iwp_facts
from tl_mod_documents.resolver import links_to_documents
from tl_mod_documents.testing import DocumentsWorld

TODAY = date(2026, 11, 7)
#: The statement bound is pin-based (orchestrator decision Q1, option a): 2 fixed statements, 6 per
#: pinned document (get_document, find_revision, revisions_of, each with a hidden-record check), and
#: 2 per floating pin. It does not depend on the scope's link count.
FIXED_STATEMENTS = 2
PER_PINNED_DOCUMENT = 6
PER_FLOATING_PIN = 2
OTHER_LINKS = 1100
failures: list[str] = []


def expect(condition: bool, what: str) -> None:
    if condition:
        print(f"PASS {what}")
    else:
        failures.append(what)
        print(f"FAIL {what}")


def count_statements(conn: Connection, run: Callable[[], Any]) -> tuple[int, Any]:
    """How many SQL statements ``run`` issues on ``conn``, and what it returned."""
    seen: list[str] = []

    def listen(_conn: Any, _cursor: Any, statement: str, *_rest: Any) -> None:
        seen.append(statement)

    event.listen(conn, "before_cursor_execute", listen)
    try:
        result = run()
    finally:
        event.remove(conn, "before_cursor_execute", listen)
    return len(seen), result


def main() -> int:
    tmp = Path(tempfile.mkdtemp())
    db = tmp / "t06a3.db"
    world = World(as_target(str(db)))
    create_schema(world.db)
    world.people()
    world.editions()
    objects = tmp / "objects"
    docs = world.documents(objects, "ISO-1", "ISO-2", "ISO-3")
    dw = DocumentsWorld(world.db, objects)
    engine = create_engine(f"sqlite:///{db}")
    check = load_checks()["documents_current"]

    def facts(iwp: str) -> Any:
        with engine.connect() as conn:
            return iwp_facts(conn, iwp)

    def answer(iwp: str) -> CheckResult:
        found = facts(iwp)
        with engine.connect() as conn:
            return check.evaluate(conn, found, TODAY)

    def pin(iwp: str, number: str, code: str | None) -> None:
        document = str(dw.document(number).id)
        world.call("uma", "PinIwpDocument", iwp=iwp, document=document, pin=code)

    def refs(result: CheckResult) -> list[str]:
        return [r.record_id for r in result.resolve_via]

    def pin_ids(iwp: str) -> list[str]:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT link_id FROM cur_links WHERE from_id = :id AND relation = 'references' "
                    "AND status IN ('active', 'stale') ORDER BY link_id"
                ),
                {"id": iwp},
            ).scalars()
            return [str(i) for i in rows]

    def other_links(count: int, start: int) -> None:
        """``count`` document links of other records (tag records) to ``ISO-0``, in the scope."""
        target = str(dw.document("ISO-0").id)
        for n in range(start, start + count):
            tag = dw.tag(f"47-FV-{n:04d}")
            dw.link_from(tag, target)

    # --- the 3-pin IWP, one of its pins stale ---------------------------------------------
    dw.register("ISO-0")
    dw.create_revision("ISO-0")
    dw.attach("ISO-0", "A")
    dw.issue("ISO-0", "A")
    three = world.iwp()
    pin(three, "ISO-1", "A")
    pin(three, "ISO-2", "A")
    pin(three, "ISO-3", None)
    dw.create_revision("ISO-1")
    dw.attach("ISO-1", "B")
    dw.issue("ISO-1", "B", "IFR")

    other_links(100, 0)
    with engine.connect() as conn:
        statements_100, _ = count_statements(
            conn, lambda: check.evaluate(conn, facts(three), TODAY)
        )
    other_links(OTHER_LINKS - 100, 100)

    r = answer(three)
    expect(
        r.state == "blocked"
        and (r.count_ok, r.count_total) == (2, 3)
        and r.detail.startswith("2/3")
        and refs(r) == [docs["ISO-1"]],
        "1100 other links: blocked, 2/3, resolve_via is the stale drawing",
    )
    with engine.connect() as conn:
        statements_1100, _ = count_statements(
            conn, lambda: check.evaluate(conn, facts(three), TODAY)
        )
    bound = (
        FIXED_STATEMENTS
        + PER_PINNED_DOCUMENT * 2  # ISO-1 and ISO-2 are pinned to a revision
        + PER_FLOATING_PIN * 1  # ISO-3 floats
    )
    expect(
        statements_1100 <= bound and statements_100 <= bound,
        f"statements <= {bound} (2 + 6 per pinned document + 2 per floating pin; "
        f"{statements_100} with 100 links, {statements_1100} with 1100)",
    )
    expect(
        statements_100 == statements_1100,
        "the statement count does not grow with the other links",
    )

    # --- an IWP with 60 pins: all 60 counted, none dropped ---------------------------------
    bulk = world.iwp()
    bulk_numbers = [f"ISO-6{n:02d}" for n in range(60)]
    for number in bulk_numbers:
        dw.register(number)
        dw.create_revision(number)
        dw.attach(number, "A")
        dw.issue(number, "A")
        pin(bulk, number, "A")
    r = answer(bulk)
    expect(
        r.state == "ok"
        and (r.count_ok, r.count_total) == (60, 60)
        and r.detail == "60/60 pinned drawings current",
        "60 pins: all 60 counted, ok",
    )
    dw.create_revision("ISO-600")
    dw.attach("ISO-600", "B")
    dw.issue("ISO-600", "B", "IFR")
    r = answer(bulk)
    expect(
        r.state == "blocked"
        and (r.count_ok, r.count_total) == (59, 60)
        and refs(r) == [str(dw.document("ISO-600").id)],
        "60 pins: one stale -> blocked, 59/60, all 60 still counted",
    )

    # --- link_ids: [] is no statement; ids equal the filtered scope-wide result -----------
    with engine.connect() as conn:
        n_empty, empty = count_statements(
            conn, lambda: links_to_documents(conn, SCOPE, link_ids=[])
        )
    expect(n_empty == 0 and empty == [], "link_ids=[] returns [] with no statement")

    ids = pin_ids(three)
    with engine.connect() as conn:
        everything = links_to_documents(conn, SCOPE, limit=10_000)
        wanted = [p for p in everything if p.link_id in set(ids)]
        subset = links_to_documents(conn, SCOPE, link_ids=ids, limit=len(ids))
        default = links_to_documents(conn, SCOPE)
    expect(
        len(wanted) == 3 and subset == wanted,
        "link_ids result equals the filtered scope-wide result for the same ids",
    )
    expect(
        len(everything) == OTHER_LINKS + 3 + 60 and default == everything[:1000],
        "the scope-wide call with no link_ids returns what it did (ordered, limit 1000)",
    )

    # --- a hidden pinned document and a missing one answer alike ---------------------------
    with cf.system_view():
        dw.register("ISO-H", confidentiality="restricted")
        dw.create_revision("ISO-H")
        dw.attach("ISO-H", "A")
        dw.issue("ISO-H", "A")
        hidden_id = str(dw.document("ISO-H").id)
        dw.register("ISO-M")
        dw.create_revision("ISO-M")
        dw.attach("ISO-M", "A")
        dw.issue("ISO-M", "A")
        missing_id = str(dw.document("ISO-M").id)
    with engine.connect() as conn:
        expect(cf.is_hidden(conn, hidden_id), "the restricted document is hidden from a job read")
    with_hidden = world.iwp()
    pin(with_hidden, "ISO-2", "A")
    with cf.system_view():
        dw.link(with_hidden, "ISO-H", "A")
    with_missing = world.iwp()
    pin(with_missing, "ISO-2", "A")
    with cf.system_view():
        dw.link(with_missing, "ISO-M", "A")
    # the document's current row goes: the pin now names no document (a link cannot be made to a
    # missing record through the commands; this is the projection state the check must tolerate)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM cur_core_record WHERE id = :id"), {"id": missing_id})
    a = answer(with_hidden)
    b = answer(with_missing)
    expect(a == b, "a hidden pinned document and a missing one produce equal CheckResults")
    expect(
        a.state == "blocked"
        and (a.count_ok, a.count_total) == (1, 2)
        and hidden_id not in refs(a)
        and "ISO-H" not in a.detail,
        "the hidden pin counts as not current and shows no key or id",
    )

    engine.dispose()
    if failures:
        print(f"T06a3 FAILED: {len(failures)} check(s)")
        return 1
    print("T06a3 ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
