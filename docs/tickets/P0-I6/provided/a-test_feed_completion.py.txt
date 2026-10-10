"""Feed suggestions and composer completion on a real SQLite ledger (P0-I6-T03). Provided."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

import pytest
from tl_adapters.db import DbTarget, create_schema, open_uow
from tl_core.services.commands import CreateRecord, VoidRecord
from tl_core.services.feed import PostToFeed, handle_post
from tl_core.services.feed_actions import RetractPost, handle_retract_post
from tl_core.services.feed_completion import complete_tags, feed_suggestions
from tl_core.services.feed_queries import Completion, get_post, list_feed
from tl_core.services.records import handle_create_record, handle_void_record

P1 = "project:P123"
P2 = "project:P999"
K1, K2 = "P123-REC-0001", "P123-REC-0002"


@pytest.fixture
def db(new_db: Callable[[], DbTarget]) -> DbTarget:
    target = new_db()
    create_schema(target)
    return target


def record(db: DbTarget, key: str, scope: str = P1) -> str:
    cmd = CreateRecord(
        actor="user:jo",
        source="t",
        scope=scope,
        record_type="core.Record",
        title=f"T {key}",
        key=key,
    )
    with open_uow(db) as uow:
        return handle_create_record(uow, cmd).stream_id


def post(db: DbTarget, body: str, actor: str = "user:mlee", scope: str = P1) -> str:
    with open_uow(db) as uow:
        return handle_post(
            uow, PostToFeed(actor=actor, source="t", scope=scope, body=body)
        ).stream_id


def suggestions_for(db: DbTarget, *post_ids: str) -> dict[str, list[tuple[str, str | None, str]]]:
    with open_uow(db, readonly=True) as uow:
        items = [get_post(uow, P1, pid) for pid in post_ids]
        found = feed_suggestions(uow, items)
    return {k: [(s.kind, s.record_key, s.prompt) for s in v] for k, v in found.items()}


def complete(
    db: DbTarget, sigil: Literal["#", "@"], prefix: str, scope: str = P1, limit: int = 8
) -> list[tuple[str, str, str]]:
    with open_uow(db, readonly=True) as uow:
        found: list[Completion] = complete_tags(uow, scope, sigil, prefix, limit=limit)
    return [(c.text, c.kind, c.detail) for c in found]


# --- suggestions ------------------------------------------------------------------------------


def test_hold_on_a_post_that_references_a_record_suggests_a_constraint(db: DbTarget) -> None:
    record(db, K1)
    record(db, K2)
    held = post(db, f"Spool damaged #{K1} #hold #{K2}")
    assert suggestions_for(db, held) == {
        held: [
            ("constraint", K1, f"Create a constraint on {K1}?"),
            ("constraint", K2, f"Create a constraint on {K2}?"),
        ]
    }


def test_no_suggestion_without_hold_or_without_a_record_or_after_retraction(db: DbTarget) -> None:
    record(db, K1)
    no_hold = post(db, f"just #{K1} #fyi")
    no_record = post(db, "stop #hold")
    retracted = post(db, f"stop #hold #{K1}")
    with open_uow(db) as uow:
        handle_retract_post(
            uow,
            RetractPost(actor="u", source="t", scope=P1, post_id=retracted, reason="oops"),
        )
    assert suggestions_for(db, no_hold, no_record, retracted) == {}


def test_hold_is_matched_without_regard_to_case_and_cards_are_ignored(db: DbTarget) -> None:
    record(db, K1)
    held = post(db, f"stop #HOLD #{K1}")
    with open_uow(db, readonly=True) as uow:
        items = list_feed(uow, P1).items
        assert any(i.item_type == "card" for i in items)
        assert set(feed_suggestions(uow, items)) == {held}


def test_a_suggestion_names_the_record_by_key(db: DbTarget) -> None:
    rec = record(db, K1)
    held = post(db, f"#hold #{K1}")
    with open_uow(db, readonly=True) as uow:
        (s,) = feed_suggestions(uow, [get_post(uow, P1, held)])[held]
    assert (s.item_id, s.kind, s.record_id, s.record_key) == (held, "constraint", rec, K1)


def test_a_voided_record_keeps_its_suggestion_with_its_key(db: DbTarget) -> None:
    rec = record(db, K1)
    held = post(db, f"#hold #{K1}")
    with open_uow(db) as uow:
        handle_void_record(
            uow,
            VoidRecord(
                actor="u", source="t", scope=P1, stream_id=rec, expected_version=1, reason="dup"
            ),
        )
    assert suggestions_for(db, held)[held][0][1] == K1


# --- completion after # -----------------------------------------------------------------------


def test_hash_completes_record_keys_by_key_with_the_title(db: DbTarget) -> None:
    record(db, K2)
    record(db, K1)
    record(db, "ACME-REC-0001", scope="company")
    record(db, "P999-REC-0001", scope=P2)
    assert complete(db, "#", "p123") == [
        (K1, "record", f"T {K1}"),
        (K2, "record", f"T {K2}"),
    ]
    assert complete(db, "#", "ACME") == [("ACME-REC-0001", "record", "T ACME-REC-0001")]
    assert complete(db, "#", "P999") == []


def test_voided_records_are_not_offered(db: DbTarget) -> None:
    rec = record(db, K1)
    with open_uow(db) as uow:
        handle_void_record(
            uow,
            VoidRecord(
                actor="u", source="t", scope=P1, stream_id=rec, expected_version=1, reason="dup"
            ),
        )
    assert complete(db, "#", "P123") == []


def test_hash_completes_signal_tags_in_their_configured_order(db: DbTarget) -> None:
    assert complete(db, "#", "") == [
        ("safety", "signal", "signal tag"),
        ("hold", "signal", "signal tag"),
        ("decision", "signal", "signal tag"),
        ("urgent", "signal", "signal tag"),
        ("fyi", "signal", "signal tag"),
    ]
    assert complete(db, "#", "HO") == [("hold", "signal", "signal tag")]


def test_hash_completes_codes_and_topics_already_used_most_used_first(db: DbTarget) -> None:
    post(db, "a #bevel-damage #area:A12")
    post(db, "b #bevel-damage #BEVEL-damage")
    post(db, "c #bevel-wear")
    post(db, "other project #bevel-other", scope=P2)
    assert complete(db, "#", "bev") == [
        ("bevel-damage", "topic", "used 3 times"),
        ("bevel-wear", "topic", "used 1 time"),
    ]
    assert complete(db, "#", "area") == [("area:a12", "code", "used 1 time")]


def test_wildcard_characters_in_the_prefix_are_literal(db: DbTarget) -> None:
    post(db, "a #alpha #a_b")
    assert complete(db, "#", "a_") == [("a_b", "topic", "used 1 time")]
    assert complete(db, "#", "%") == []


def test_the_limit_applies_to_the_whole_list(db: DbTarget) -> None:
    record(db, K1)
    assert [c[0] for c in complete(db, "#", "", limit=3)] == [K1, "safety", "hold"]
    assert complete(db, "#", "", limit=1) == [(K1, "record", f"T {K1}")]


# --- completion after @ -----------------------------------------------------------------------


def test_at_completes_mentions_then_authors(db: DbTarget) -> None:
    post(db, "x @party:fab-a @party:fab-a @crew:p-07", actor="user:mlee")
    post(db, "y", actor="agent:triage")
    post(db, "z", actor="svc:importer")
    post(db, "w", actor="user:pat", scope=P2)
    assert complete(db, "@", "") == [
        ("party:fab-a", "mention", "used 2 times"),
        ("crew:p-07", "mention", "used 1 time"),
        ("agent:triage", "mention", "agent"),
        ("mlee", "mention", "person"),
    ]
    assert complete(db, "@", "PA") == [("party:fab-a", "mention", "used 2 times")]
    assert complete(db, "@", "ml") == [("mlee", "mention", "person")]
    assert complete(db, "@", "agent:") == [("agent:triage", "mention", "agent")]


def test_an_author_who_is_also_a_used_mention_is_listed_once(db: DbTarget) -> None:
    post(db, "ping @mlee", actor="user:mlee")
    assert complete(db, "@", "ml") == [("mlee", "mention", "used 1 time")]
