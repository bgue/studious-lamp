"""FeedProjector: posts, tombstones, reactions and event cards (P0-I6-S4; brief 21.1, D1)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from tl_adapters.sqlite.engine import make_engine
from tl_adapters.sqlite.ledger import SqliteLedger
from tl_adapters.sqlite.uow import SqliteUnitOfWork, create_schema, rebuild_projections
from tl_core.feed.types import CARD_WINDOW_SECONDS
from tl_core.ledger import NewEvent
from tl_core.projection.defaults import default_registry
from tl_core.projection.feed import FeedProjector
from tl_core.services.commands import CreateRecord, UpdateRecord
from tl_core.services.feed import PostToFeed, handle_post
from tl_core.services.records import handle_create_record, handle_update_record

P1 = "project:P1"
P2 = "project:P2"
T0 = datetime(2026, 10, 9, 9, 0, 0, tzinfo=UTC)


SUBJECTS = "SELECT kind, record_id FROM cur_feed_tags WHERE item_id = :i"


class World:
    """A ledger whose clock the test sets, with all default projectors."""

    def __init__(self, path: Path) -> None:
        self.path = path
        create_schema(path)
        self.engine: Engine = make_engine(path)
        self.now = T0
        self.ledger = SqliteLedger(self.engine, clock=lambda: self.now)

    def at(self, seconds: float) -> None:
        self.now = T0 + timedelta(seconds=seconds)

    def uow(self, *, readonly: bool = False) -> SqliteUnitOfWork:
        return SqliteUnitOfWork(self.engine, self.ledger, default_registry(), readonly=readonly)

    def create(self, actor: str = "user:jo", scope: str = P1, key: str | None = None) -> str:
        cmd = CreateRecord(
            actor=actor, source="t", scope=scope, record_type="core.Record", title="t", key=key
        )
        with self.uow() as uow:
            return handle_create_record(uow, cmd).stream_id

    def update(self, record_id: str, version: int, actor: str = "user:jo", scope: str = P1) -> None:
        cmd = UpdateRecord(
            actor=actor,
            source="t",
            scope=scope,
            stream_id=record_id,
            expected_version=version,
            changes={"title": f"title v{version}"},
        )
        with self.uow() as uow:
            handle_update_record(uow, cmd)

    def post(self, body: str, actor: str = "user:jo", scope: str = P1) -> str:
        with self.uow() as uow:
            return handle_post(
                uow, PostToFeed(actor=actor, source="t", scope=scope, body=body)
            ).stream_id

    def raw(self, post_id: str, version: int, event_type: str, actor: str, **payload: Any) -> None:
        with self.uow() as uow:
            uow.append(
                stream_id=post_id,
                stream_type="core.ActivityPost",
                scope=P1,
                expected_version=version,
                events=[NewEvent(event_type=event_type, payload={"post_id": post_id, **payload})],
                actor=actor,
                source="t",
                correlation_id="c",
            )

    def rows(self, query: str, **params: Any) -> list[Any]:
        with self.uow(readonly=True) as uow:
            return list(uow.conn().execute(text(query), params).mappings().all())

    def cards(self, scope: str = P1) -> list[Any]:
        return self.rows(
            "SELECT * FROM cur_feed_items WHERE item_type = 'card' AND scope = :s ORDER BY seq",
            s=scope,
        )


@pytest.fixture
def world(tmp_path: Path) -> Iterator[World]:
    w = World(tmp_path / "tl.db")
    yield w
    w.engine.dispose()


def test_the_projector_sees_every_event_type() -> None:
    registry = default_registry()
    assert any(isinstance(p, FeedProjector) for p in registry.for_event("Anything.AtAll"))
    assert any(isinstance(p, FeedProjector) for p in registry.for_event("Record.Created"))


def test_a_burst_of_creates_is_one_card_even_with_numbering_events_between(world: World) -> None:
    for second in (0, 1, 2):
        world.at(second)
        world.create()  # key None: the numbering service allocates, writing Numbering.Allocated
    (card,) = world.cards()
    assert card["event_count"] == 3
    assert card["summary"] == "jo created 3 records"
    assert card["importance"] == "low" and card["event_type"] == "Record.Created"
    assert card["open_scope"] == P1
    assert card["item_id"].startswith("card:")
    subjects = world.rows(
        "SELECT record_id FROM cur_feed_tags WHERE item_id = :i", i=card["item_id"]
    )
    assert len(subjects) == 3


def test_a_card_moves_with_its_latest_event(world: World) -> None:
    world.at(0)
    world.create()
    (first,) = world.cards()
    world.at(30)
    world.create()
    (later,) = world.cards()
    assert later["item_id"] == first["item_id"]
    assert later["seq"] > first["seq"]
    assert later["occurred_at"] > first["occurred_at"]
    assert later["first_seq"] == first["first_seq"] and later["first_us"] == first["first_us"]


def test_the_window_runs_from_the_first_event(world: World) -> None:
    world.at(0)
    world.create()
    world.at(CARD_WINDOW_SECONDS)
    world.create()  # exactly at the end: still the same card
    world.at(CARD_WINDOW_SECONDS + 1)
    world.create()  # past it: a new card
    first, second = world.cards()
    assert (first["event_count"], second["event_count"]) == (2, 1)
    assert first["open_scope"] is None and second["open_scope"] == P1


def test_another_actor_or_event_type_closes_the_card(world: World) -> None:
    rec = world.create(actor="user:jo")
    world.create(actor="user:al")
    world.update(rec, 1, actor="user:al")
    world.create(actor="user:jo")
    cards = world.cards()
    assert [(c["actor"], c["event_type"], c["event_count"]) for c in cards] == [
        ("user:jo", "Record.Created", 1),
        ("user:al", "Record.Created", 1),
        ("user:al", "Record.Updated", 1),
        ("user:jo", "Record.Created", 1),
    ]
    assert [c["open_scope"] for c in cards] == [None, None, None, P1]


def test_a_post_closes_the_open_card_and_is_not_a_card(world: World) -> None:
    world.create()
    world.post("hello")
    world.create()
    items = world.rows("SELECT item_type, event_count FROM cur_feed_items ORDER BY seq")
    assert [(i["item_type"], i["event_count"]) for i in items] == [
        ("card", 1),
        ("post", 1),
        ("card", 1),
    ]


def test_scopes_keep_separate_open_cards(world: World) -> None:
    world.create(scope=P1)
    world.create(scope=P2)
    world.create(scope=P1)
    assert [c["event_count"] for c in world.cards(P1)] == [2]
    assert [c["event_count"] for c in world.cards(P2)] == [1]


def test_a_suggested_link_does_not_split_a_burst_or_make_a_card(world: World) -> None:
    rec = world.create(key="P1-REC-0001")
    world.post("see #P1-REC-0001")  # posts a Link.Suggested after Feed.Posted
    world.create()
    cards = world.cards()
    assert [c["event_type"] for c in cards] == ["Record.Created", "Record.Created"]
    assert rec


def test_card_subjects_are_recorded_once_per_record(world: World) -> None:
    rec = world.create()
    world.update(rec, 1)
    world.update(rec, 2)
    card = world.cards()[-1]
    assert card["event_count"] == 2
    rows = world.rows(
        "SELECT kind, record_id, tag_row_id FROM cur_feed_tags WHERE item_id = :i",
        i=card["item_id"],
    )
    assert [(r["kind"], r["record_id"]) for r in rows] == [("record", rec)]


def test_a_scope_cannot_have_two_open_cards(world: World) -> None:
    world.create()
    with pytest.raises(IntegrityError), world.uow() as uow:
        uow.conn().execute(
            text(
                "INSERT INTO cur_feed_items (item_id, item_type, scope, actor, occurred_at, seq, "
                "summary, open_scope) VALUES ('x', 'card', :s, 'a', 't', 1, 's', :s)"
            ),
            {"s": P1},
        )


def test_a_post_row_and_its_tag_rows(world: World) -> None:
    rec = world.create(key="P1-REC-0001")
    pid = world.post("Spool #P1-REC-0001 #hold @party:fab-a #area:A12 #Bevel", actor="user:mlee")
    (row,) = world.rows("SELECT * FROM cur_feed_items WHERE item_id = :i", i=pid)
    assert (row["item_type"], row["actor"], row["importance"], row["base_importance"]) == (
        "post",
        "user:mlee",
        "high",
        "normal",
    )
    assert row["open_scope"] is None and row["event_type"] is None and row["version"] == 1
    tags = world.rows(
        "SELECT kind, tag_text, tag_key, namespace, record_id, start_pos, end_pos "
        "FROM cur_feed_tags WHERE item_id = :i ORDER BY start_pos",
        i=pid,
    )
    assert [(t["kind"], t["tag_text"], t["tag_key"], t["namespace"]) for t in tags] == [
        ("record", "P1-REC-0001", "p1-rec-0001", None),
        ("signal", "hold", "hold", None),
        ("mention", "party:fab-a", "party:fab-a", "party"),
        ("code", "area:A12", "area:a12", "area"),
        ("topic", "Bevel", "bevel", None),
    ]
    assert tags[0]["record_id"] == rec
    body = row["summary"]
    for t in tags:
        assert body[t["start_pos"] + 1 : t["end_pos"]] == t["tag_text"]


def test_retraction_leaves_a_tombstone_without_body_or_non_record_tags(world: World) -> None:
    world.create(key="P1-REC-0001")
    pid = world.post("Spool #P1-REC-0001 #hold")
    world.raw(pid, 1, "Feed.Retracted", "user:jo", reason="wrong project")
    (row,) = world.rows("SELECT * FROM cur_feed_items WHERE item_id = :i", i=pid)
    assert row["retracted"] and row["summary"] == "" and row["retract_reason"] == "wrong project"
    assert row["version"] == 2
    kinds = world.rows("SELECT kind FROM cur_feed_tags WHERE item_id = :i", i=pid)
    assert [k["kind"] for k in kinds] == ["record"]


def test_reactions_are_per_actor_and_idempotent(world: World) -> None:
    pid = world.post("hello")

    def react(version: int, actor: str, reaction: str, on: bool) -> dict[str, list[str]]:
        world.raw(pid, version, "Feed.Reacted", actor, reaction=reaction, on=on)
        (row,) = world.rows("SELECT reactions_json FROM cur_feed_items WHERE item_id = :i", i=pid)
        return json.loads(row["reactions_json"])

    assert react(1, "user:b", "ack", True) == {"ack": ["user:b"]}
    assert react(2, "user:a", "ack", True) == {"ack": ["user:a", "user:b"]}
    assert react(3, "user:a", "ack", True) == {"ack": ["user:a", "user:b"]}
    assert react(4, "user:a", "+1", True) == {"+1": ["user:a"], "ack": ["user:a", "user:b"]}
    assert react(5, "user:a", "ack", False) == {"+1": ["user:a"], "ack": ["user:b"]}
    assert react(6, "user:b", "ack", False) == {"+1": ["user:a"]}
    (row,) = world.rows("SELECT version FROM cur_feed_items WHERE item_id = :i", i=pid)
    assert row["version"] == 7


def test_events_for_an_unknown_post_fail_loudly(world: World) -> None:
    retraction = NewEvent(event_type="Feed.Retracted", payload={"post_id": "ghost", "reason": "x"})
    with pytest.raises(LookupError), world.uow() as uow:
        uow.append(
            stream_id="ghost",
            stream_type="core.ActivityPost",
            scope=P1,
            expected_version=0,
            events=[retraction],
            actor="user:a",
            source="t",
            correlation_id="c",
        )


def test_reset_and_a_feed_only_rebuild_reproduce_the_rows(world: World) -> None:
    rec = world.create(key="P1-REC-0001")
    world.at(5)
    world.update(rec, 1)
    pid = world.post("hi #P1-REC-0001 #hold")
    world.raw(pid, 1, "Feed.Reacted", "user:q", reaction="ack", on=True)
    world.at(1000)
    world.create()

    def dump() -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]:
        items = world.rows("SELECT * FROM cur_feed_items ORDER BY item_id")
        tags = world.rows("SELECT * FROM cur_feed_tags ORDER BY tag_row_id")
        return [tuple(r.values()) for r in items], [tuple(r.values()) for r in tags]

    live = dump()
    assert live[0] and live[1]
    rebuild_projections(world.path, types=["feed"])
    assert dump() == live
    rebuild_projections(world.path)
    assert dump() == live
