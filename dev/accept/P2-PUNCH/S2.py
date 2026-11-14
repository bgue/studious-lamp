"""Acceptance for P2-PUNCH S2: the punch commands, the subject join and ``open_punch_for`` (SQLite).

Run: ``uv run python dev/accept/P2-PUNCH/S2.py``. One ``PASS <check>`` line per check, then
``S2 ok``.
"""

from __future__ import annotations

import sys
import tempfile
import threading
import tomllib
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages/tl-modules/quality/tests"))
from punch_world import IWP, World  # noqa: E402
from tl_adapters.db import as_target, create_schema, open_uow  # noqa: E402
from tl_core import confidentiality as cf  # noqa: E402
from tl_core.auth.errors import ForbiddenError  # noqa: E402
from tl_core.intent import Intent, IntentInvalid  # noqa: E402
from tl_core.services.errors import RecordNotFoundError  # noqa: E402
from tl_core.util import new_ulid  # noqa: E402
from tl_mod_quality import api  # noqa: E402
from tl_mod_quality.commands import RaisePunchItem  # noqa: E402
from tl_mod_quality.errors import PunchRuleError, PunchStateError, StaleVersionError  # noqa: E402
from tl_mod_quality.module import PROPOSABLE, PUNCH_COMMANDS  # noqa: E402

CLEARED = cf.Viewer(actor="user:dora", level=1, account="user:dora")
MSG_VOID = "a void punch item accepts no further change"
MSG_SELF = "the person who cleared a punch item may not verify it"


def fresh() -> World:
    db = as_target(str(Path(tempfile.mkdtemp()) / "s2.db"))
    create_schema(db)
    world = World(db)
    world.people()
    return world


def refused(error: type[BaseException], call: Callable[[], Any]) -> str:
    try:
        call()
    except error as exc:
        return str(exc)
    raise AssertionError(f"expected {error.__name__}")


def passed(name: str) -> None:
    print(f"PASS {name}")


def read(world: World, *args: Any, **kw: Any) -> list[api.PunchRef]:
    with open_uow(world.db, readonly=True) as uow:
        return api.open_punch_for(uow.conn(), *args, **kw)


def main() -> None:
    w = fresh()
    iwp = w.record(IWP, "IWP-1")
    made = w.call("uma", "RaisePunchItem", subject="Guard missing", from_record_id=iwp)
    item = made.stream_id
    row = w.row(item)
    assert made.key == "P123-PUN-0001" and w.state(item) == "Open"
    assert row["raised_by"] == "user:uma" and row["source_id"] == iwp
    links = w.links_from(item)
    assert [(k["relation"], k["to_id"]) for k in links] == [("raised_against", iwp)]
    passed("a punch item raised by uma from an IWP: key, Open, raised_by, source_id, one link")

    try:
        RaisePunchItem(  # type: ignore[call-arg]
            actor="user:uma", source="t", scope="project:P123", subject="x", raised_by="user:rob"
        )
        raise AssertionError("raised_by was accepted")
    except ValidationError:
        pass
    free = w.raise_item()
    assert w.row(free)["source_id"] is None and w.links_from(free) == []
    passed("raised_by in the body is refused; a free-standing raise works")

    hidden, absent = w.hidden_record(), new_ulid()
    before = w.count()

    def raise_from(source: str) -> Callable[[], Any]:
        return lambda: w.call("uma", "RaisePunchItem", subject="x", from_record_id=source)

    assert refused(RecordNotFoundError, raise_from(hidden)) == refused(
        RecordNotFoundError, raise_from(absent)
    )
    assert w.count() == before
    passed("an unknown and a restricted source answer the same text and write nothing")

    refused(
        ForbiddenError,
        lambda: w.call("dora", "EditPunchItem", punch_item=item, area="Z"),
    )
    w.call("uma", "EditPunchItem", punch_item=item, area="A1", assignee="user:rob")
    w.call("rob", "EditPunchItem", punch_item=item, area="A2")
    changes = w.scalar(
        "SELECT payload FROM events WHERE event_type = 'PunchItem.Edited' AND stream_id = :i "
        "ORDER BY seq DESC LIMIT 1",
        i=item,
    )
    assert '"area":["A1","A2"]' in str(changes)
    passed("edit by a stranger is refused, by the assignee works, Edited carries changes")

    try:
        w.call("rob", "ClearPunchItem", punch_item=item, note="")
        raise AssertionError("an empty note was accepted")
    except ValidationError:
        pass
    w.call("rob", "ClearPunchItem", punch_item=item, note="Guard fitted")
    assert w.state(item) == "Cleared" and w.row(item)["cleared_by"] == "user:rob"
    passed("clear needs a note and stores the actor")

    assert (
        refused(ForbiddenError, lambda: w.call("rob", "VerifyPunchItem", punch_item=item))
        == MSG_SELF
    )
    refused(ForbiddenError, lambda: w.call("uma", "VerifyPunchItem", punch_item=item))
    w.call("sue", "VerifyPunchItem", punch_item=item)
    assert w.state(item) == "Verified" and w.row(item)["verified_by"] == "user:sue"
    passed("rob verifying is refused with the fixed message, uma is forbidden, sue verifies")

    open_one = w.raise_item()
    refused(PunchStateError, lambda: w.call("sue", "VerifyPunchItem", punch_item=open_one))
    assert w.state(open_one) == "Open"
    passed("Open -> Verified is refused")

    try:
        w.call("sue", "ReopenPunchItem", punch_item=item, reason="")
        raise AssertionError("an empty reason was accepted")
    except ValidationError:
        pass
    w.call("sue", "ReopenPunchItem", punch_item=item, reason="Guard loose")
    row = w.row(item)
    assert w.state(item) == "Open" and row["reopen_count"] == 1
    assert [row[c] for c in ("cleared_by", "cleared_on", "clear_note", "verified_by")] == [None] * 4
    passed("reopen needs a reason, resets the cleared columns and counts 1")

    again = w.raise_item()
    w.call("rob", "ClearPunchItem", punch_item=again, note="n")
    w.call("sue", "VerifyPunchItem", punch_item=again)
    w.call("sue", "ReopenPunchItem", punch_item=again, reason="Failed walkdown")
    assert w.state(again) == "Open"
    passed("a verified item can be reopened")

    from_open, from_cleared = w.raise_item(), w.raise_item()
    w.call("rob", "ClearPunchItem", punch_item=from_cleared, note="n")
    w.call("sue", "VoidPunchItem", punch_item=from_open, reason="Raised twice")
    w.call("sue", "VoidPunchItem", punch_item=from_cleared, reason="Not ours")
    assert (w.state(from_open), w.state(from_cleared)) == ("Void", "Void")
    for name, fields, who in (
        ("EditPunchItem", {"area": "Z"}, "uma"),
        ("ClearPunchItem", {"note": "n"}, "rob"),
        ("VerifyPunchItem", {}, "sue"),
        ("ReopenPunchItem", {"reason": "r"}, "sue"),
        ("VoidPunchItem", {"reason": "r"}, "sue"),
    ):
        text = refused(
            PunchStateError, lambda n=name, f=fields, u=who: w.call(u, n, punch_item=from_open, **f)
        )
        assert text == MSG_VOID
    passed("void works from Open and Cleared; a Void item refuses every command with one message")

    current = w.version(again)
    refused(
        StaleVersionError,
        lambda: w.call(
            "rob", "ClearPunchItem", punch_item=again, note="n", expected_version=current - 1
        ),
    )
    assert w.state(again) == "Open"
    passed("a stale expected_version is refused")

    future = datetime.now(UTC) + timedelta(days=1)
    refused(
        PunchRuleError,
        lambda: w.call("rob", "ClearPunchItem", punch_item=again, note="n", at=future),
    )
    assert w.state(again) == "Open"
    passed("an at in the future is refused")

    secret = w.hidden_record()
    mine = str(
        w.call("dora", "RaisePunchItem", subject="From secret", from_record_id=secret).stream_id
    )
    assert read(w, secret) == []
    assert [r.id for r in read(w, secret, viewer=CLEARED)] == [mine]
    refused(RecordNotFoundError, lambda: w.call("uma", "ClearPunchItem", punch_item=mine, note="n"))
    passed("a restricted source hides the item by default, shows it when cleared; uma gets unknown")

    constraint = w.advisory(mine, who="dora")
    with open_uow(w.db, readonly=True) as uow:
        assert cf.is_hidden(uow.conn(), constraint)
        with cf.use_viewer(CLEARED):
            assert not cf.is_hidden(uow.conn(), constraint)
    passed("a constraint raised on a punch item is hidden when the source is")

    made = w.call("uma", "RaisePunchItem", subject="x", intent=Intent(why="Walkdown 14"))
    w.call("rob", "ClearPunchItem", punch_item=made.stream_id, note="n")
    w.call("sue", "VerifyPunchItem", punch_item=made.stream_id, intent=Intent(why="Checked"))
    stored = w.rows(
        "SELECT event_type, intent FROM events WHERE stream_id = :i "
        "AND event_type IN ('PunchItem.Raised', 'PunchItem.Verified')",
        i=made.stream_id,
    )
    held = {r["event_type"]: r["intent"] for r in stored}
    assert "Walkdown 14" in held["PunchItem.Raised"] and "Checked" in held["PunchItem.Verified"]
    before = w.count()
    refused(
        IntentInvalid,
        lambda: w.call("uma", "RaisePunchItem", subject="y", intent=Intent(why="x" * 501)),
    )
    assert w.count() == before
    passed("an intent round-trips on raise and verify, and a bad intent refuses with no event")

    threaded = fresh()
    gate = threading.Barrier(2)

    def raise_ten(who: str) -> list[str]:
        gate.wait()
        return [str(threaded.call(who, "RaisePunchItem", subject="x").key) for _ in range(10)]

    with ThreadPoolExecutor(2) as pool:
        keys = [k for batch in pool.map(raise_ten, ["uma", "rob"]) for k in batch]
    assert sorted(keys) == [f"P123-PUN-{n:04d}" for n in range(1, 21)]
    passed("two threads raising 20 items get -0001..-0020 with no gap or repeat")

    v = fresh()
    anchor = v.record(IWP, "IWP-9")
    ids = [v.raise_item(from_record_id=anchor) for _ in range(4)]
    v.call("rob", "ClearPunchItem", punch_item=ids[1], note="n")
    v.call("rob", "ClearPunchItem", punch_item=ids[2], note="n")
    v.call("sue", "VerifyPunchItem", punch_item=ids[2])
    v.call("sue", "VoidPunchItem", punch_item=ids[3], reason="r")
    assert [r.id for r in read(v, anchor)] == [ids[0], ids[1]]
    passed("open_punch_for returns only Open and Cleared items")

    excluded = set(
        tomllib.loads((ROOT / "tests/tools/proposable_exclusions.toml").read_text())["commands"]
    )
    rows = {p.model.__name__ for p in PROPOSABLE}
    assert rows | excluded >= {c.model.__name__ for c in PUNCH_COMMANDS}
    passed("every command is a proposable row or an exclusion")
    print("S2 ok")


if __name__ == "__main__":
    main()
