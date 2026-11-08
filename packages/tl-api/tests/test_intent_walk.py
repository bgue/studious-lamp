"""ADR-0025 d4/d5 and ADR-0016 at the HTTP edge: intent as five kinds of reader (P2-INT-S2).

The world is the confidentiality walk's: an open item, a restricted one, a privileged one and one
of a class nobody knows, and five readers. The controller makes records whose intents point at the
hidden items; each reader then reads them back, and writes with references of their own.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from harness import SCOPE, Harness
from sqlalchemy import event, text
from test_confidentiality_walk import FAKE_ID, MAY_READ, Seed, seed
from tl_core.confidentiality import Viewer
from tl_core.intent import NOT_AVAILABLE, Intent
from tl_core.ledger import NewEvent
from tl_mod_correspondence.confseed import TOKENS

FIXED = "intent reference not found"
READERS = sorted(MAY_READ)
CANNOT_READ_RESTRICTED = [
    "bob",
    "amy",
]  # amy reads the privileged item, not the restricted; an agent proposes, it runs no command


@pytest.fixture
def harness(parity_harness: Harness) -> Harness:
    return parity_harness


@pytest.fixture
def seeded(harness: Harness, tmp_path: Path) -> Seed:
    return seed(harness, tmp_path)


def call(h: Harness, seeded: Seed, reader: str, method: str, path: str, **kw: Any) -> Any:
    client = h.client_for(None)
    headers = {"Authorization": f"Bearer {seeded.tokens[reader]}"}
    return getattr(client, method)(path, headers=headers, **kw)


def make(h: Harness, seeded: Seed, reader: str, key: str, intent: dict[str, Any]) -> Any:
    return call(
        h, seeded, reader, "post", "/commands/CreateRecord",
        json={"scope": SCOPE, "record_type": "core.Record", "title": "T " + key, "key": key,
              "intent": intent},
    )  # fmt: skip


def statements(h: Harness) -> list[str]:
    with h.backend(True) as uow:
        engine = uow.conn().engine
    seen: list[str] = []

    def record(conn: Any, cursor: Any, statement: str, *rest: Any) -> None:
        seen.append(statement.split("(")[0][:60])

    event.listen(engine, "before_cursor_execute", record)
    statements.cleanup = lambda: event.remove(engine, "before_cursor_execute", record)  # type: ignore[attr-defined]
    return seen


# --- (a) a hidden id and an unknown id answer byte for byte the same ---------------------------


@pytest.mark.parametrize("reader", CANNOT_READ_RESTRICTED)
@pytest.mark.parametrize("where", ["toward", "next"])
@pytest.mark.parametrize("by", ["id", "key"])
def test_hidden_and_unknown_references_answer_alike(
    harness: Harness, seeded: Seed, reader: str, where: str, by: str
) -> None:
    hidden_ref = seeded.ids["restricted"] if by == "id" else seeded.numbers["restricted"]
    unknown_ref = FAKE_ID if by == "id" else "P123-NOPE-9999"

    def intent(ref: str) -> dict[str, Any]:
        if where == "toward":
            return {"toward": {"target": ref, "condition": "x"}}
        return {"next": [{"command": "UpdateRecord", "target": ref}]}

    seen = statements(harness)
    try:
        a = make(harness, seeded, reader, "R-A", intent(hidden_ref))
        hidden_statements = list(seen)
        seen.clear()
        b = make(harness, seeded, reader, "R-A", intent(unknown_ref))
        unknown_statements = list(seen)
    finally:
        statements.cleanup()  # type: ignore[attr-defined]
    assert a.status_code == b.status_code == 422
    assert a.json() == b.json() == {
        "error": "intent_reference_unknown", "message": FIXED, **{
            k: v for k, v in a.json().items() if k not in ("error", "message")
        },
    }  # fmt: skip
    assert a.text == b.text and sorted(a.headers) == sorted(b.headers)
    assert hidden_ref not in a.text and TOKENS["restricted"] not in a.text
    assert hidden_statements == unknown_statements  # the same work was done: one timing class
    assert (
        harness.client.get("/records/lookup", params={"scope": SCOPE, "key": "R-A"}).status_code
        == 404
    )


@pytest.mark.parametrize("reader", ["boss", "bob"])
def test_the_privileged_item_is_unknown_to_those_not_named(
    harness: Harness, seeded: Seed, reader: str
) -> None:
    got = make(
        harness,
        seeded,
        reader,
        "R-A",
        {"toward": {"target": seeded.ids["privileged"], "condition": "x"}},
    )
    nothing = make(
        harness, seeded, reader, "R-A", {"toward": {"target": FAKE_ID, "condition": "x"}}
    )
    assert got.status_code == nothing.status_code == 422 and got.text == nothing.text


def test_a_reader_who_may_read_the_item_can_point_at_it(harness: Harness, seeded: Seed) -> None:
    ok = make(
        harness,
        seeded,
        "ctl",
        "R-A",
        {"toward": {"target": seeded.ids["restricted"], "condition": "x"}},
    )
    assert ok.status_code == 200, ok.text
    amy = make(
        harness,
        seeded,
        "amy",
        "R-B",
        {"toward": {"target": seeded.ids["privileged"], "condition": "x"}},
    )
    assert amy.status_code == 200, amy.text


# --- (b) an event on a hidden stream is absent, with its intent -------------------------------


def hidden_stream_event(h: Harness, seeded: Seed) -> str:
    stream = seeded.ids["restricted"]
    with h.backend(False) as uow:
        row = (
            uow.conn()
            .execute(
                text(
                    "SELECT MAX(stream_version) ver, MIN(stream_type) kind FROM events "
                    "WHERE stream_id = :s"
                ),
                {"s": stream},
            )
            .one()
        )
        done = uow.append(
            stream_id=stream, stream_type=row.kind, scope=SCOPE, expected_version=int(row.ver),
            events=[NewEvent(event_type="Test.Noted", payload={}, intent=Intent(why="HIDDENSTREAMWHY"))],  # noqa: E501
            actor="user:ctl", source="test", correlation_id="c-hidden",
        )  # fmt: skip
    return done.events[0].event_id


@pytest.mark.parametrize("reader", READERS)
def test_an_event_on_a_hidden_stream_is_absent_with_its_intent(
    harness: Harness, seeded: Seed, reader: str
) -> None:
    event_id = hidden_stream_event(harness, seeded)
    stream = seeded.ids["restricted"]
    may = "restricted" in MAY_READ[reader]
    history = call(harness, seeded, reader, "get", f"/records/{stream}/history")
    trace = call(harness, seeded, reader, "get", f"/records/{stream}/trace")
    unknown = call(harness, seeded, reader, "get", f"/records/{FAKE_ID}/history")
    pages = []
    after = 0
    while True:
        page = call(
            harness, seeded, reader, "get", "/events", params={"after": after, "limit": 1000}
        )
        pages.append(page.text)
        body = page.json()
        if not body["has_more"]:
            break
        after = body["next_seq"]
    listed = "".join(pages)
    if may:
        assert history.status_code == 200 and "HIDDENSTREAMWHY" in history.text
        assert event_id in listed and "HIDDENSTREAMWHY" in listed
        return
    assert history.status_code == trace.status_code == unknown.status_code == 404
    assert history.text.replace(stream, FAKE_ID) == unknown.text
    assert "HIDDENSTREAMWHY" not in listed and event_id not in listed
    assert "HIDDENSTREAMWHY" not in history.text + trace.text


# --- (c) a visible event pointing at a restricted record shows "not available" ------------------


def pointing_record(h: Harness, seeded: Seed, why: str = "plain") -> str:
    rid = seeded.ids["restricted"]
    made = make(
        h, seeded, "ctl", "R-POINT",
        {
            "why": why,
            "next": [
                {"command": "UpdateRecord", "target": rid},
                {"command": "UpdateRecord", "target": seeded.ids["open"]},
                {"text": "ring them"},
            ],
            "toward": {"target": rid, "condition": "RESTRICTEDCONDITION"},
        },
    )  # fmt: skip
    assert made.status_code == 200, made.text
    return str(made.json()["stream_id"])


@pytest.mark.parametrize("reader", READERS)
def test_an_unreadable_reference_in_a_visible_event_shows_not_available(
    harness: Harness, seeded: Seed, reader: str
) -> None:
    point = pointing_record(harness, seeded)
    may = "restricted" in MAY_READ[reader]
    hidden = [seeded.ids["restricted"], seeded.numbers["restricted"], TOKENS["restricted"]]
    history = call(harness, seeded, reader, "get", f"/records/{point}/history")
    assert history.status_code == 200
    page = call(harness, seeded, reader, "get", "/events", params={"limit": 1000})
    for body in (
        history.json()[0]["intent"],
        next(e["intent"] for e in page.json()["events"] if e["stream_id"] == point),
    ):
        assert len(body["next"]) == 3  # no differing count
        assert body["next"][1]["target"] == seeded.ids["open"]  # a readable one is shown
        assert body["next"][2]["text"] == "ring them"
        if may:
            assert body["next"][0]["target"] == seeded.ids["restricted"]
            assert body["toward"]["target"] == seeded.ids["restricted"]
        else:
            assert body["next"][0] == {"command": None, "target": None, "text": NOT_AVAILABLE}
            assert body["toward"] == {"target": NOT_AVAILABLE, "state": None, "condition": None}
    if not may:
        for marker in hidden + ["RESTRICTEDCONDITION"]:
            assert marker not in history.text and marker not in page.text, (reader, marker)


def test_the_stream_filter_redacts_like_the_pages(harness: Harness, seeded: Seed) -> None:
    point = pointing_record(harness, seeded)
    with harness.backend(True) as uow:
        events = uow.ledger.read_stream(point)
    hub = harness.app.state.ctx.feed
    bob = Viewer(actor="user:bob", account="user:bob")
    ctl = Viewer(actor="user:ctl", level=1, account="user:ctl")
    for viewer, may in ((bob, False), (ctl, True)):
        intent = hub.visible(events, viewer)[0].intent
        assert intent is not None and intent.toward is not None
        assert (intent.toward.target == seeded.ids["restricted"]) is may


# --- (d) why is never filtered by words -----------------------------------------------------------


@pytest.mark.parametrize("reader", READERS)
def test_why_naming_a_hidden_record_is_shown_unchanged(
    harness: Harness, seeded: Seed, reader: str
) -> None:
    why = f"after {seeded.numbers['restricted']} ({TOKENS['restricted']}) closes"
    point = pointing_record(harness, seeded, why)
    history = call(harness, seeded, reader, "get", f"/records/{point}/history")
    assert history.json()[0]["intent"]["why"] == why


# --- (e) the lake and the webhook outbox leave the intent out of hidden rows ---------------------


def test_the_lake_leaves_the_intent_out_of_hidden_rows_of_a_real_command(
    harness: Harness, seeded: Seed, tmp_path: Path
) -> None:
    from tl_lake import LakeConfig, read_snapshot, sync_lake
    from tl_lake.duck import open_lake

    event_id = hidden_stream_event(harness, seeded)
    pointing_record(harness, seeded, "OPENWHY")
    with harness.backend(True) as uow:
        engine = uow.conn().engine
    lake = LakeConfig.at(tmp_path / "lake")
    with read_snapshot(engine) as conn:
        sync_lake(lake, conn)
    with open_lake(lake, write=False) as con:
        rows = con.execute("SELECT event_id, intent FROM events").fetchall()
        everything = str(con.execute("SELECT * FROM events").fetchall())
    by_id = dict(rows)
    assert event_id not in by_id or by_id[event_id] is None
    assert "HIDDENSTREAMWHY" not in everything
    assert any(v and "OPENWHY" in v for v in by_id.values())  # a readable row keeps it


def test_the_webhook_outbox_never_holds_an_intent(harness: Harness, seeded: Seed) -> None:
    pointing_record(harness, seeded, "OUTBOXWHY")
    hidden_stream_event(harness, seeded)
    with harness.backend(True) as uow:
        rows = uow.conn().execute(text("SELECT * FROM outbox_events")).mappings().all()
    assert rows
    assert "OUTBOXWHY" not in json.dumps([dict(r) for r in rows], default=str)
    assert "HIDDENSTREAMWHY" not in json.dumps([dict(r) for r in rows], default=str)
