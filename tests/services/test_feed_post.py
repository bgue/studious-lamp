"""Posting to the feed and editing a post against a real SQLite ledger (P0-I6-S5; brief 21)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from tl_adapters.db import DbTarget, create_schema, open_uow, rebuild_projections
from tl_core.ledger import ConcurrencyError, NewEvent
from tl_core.services import feed as feed_service
from tl_core.services.commands import CreateRecord, VoidRecord
from tl_core.services.errors import (
    InvalidScopeError,
    NoChangesError,
    PostNotFoundError,
    PostRetractedError,
)
from tl_core.services.feed import (
    EditPost,
    PostToFeed,
    handle_edit_post,
    handle_post,
    load_post,
)
from tl_core.services.link_queries import links_of
from tl_core.services.links import DeclineLink, handle_decline_link
from tl_core.services.records import handle_create_record, handle_void_record

P1 = "project:P123"
REC1 = "P123-REC-0001"
REC2 = "P123-REC-0002"


@pytest.fixture
def db(new_db: Callable[[], DbTarget]) -> DbTarget:
    target = new_db()
    create_schema(target)
    return target


def record(db: DbTarget, key: str, scope: str = P1) -> str:
    cmd = CreateRecord(
        actor="user:a", source="t", scope=scope, record_type="core.Record", title=key, key=key
    )
    with open_uow(db) as uow:
        return handle_create_record(uow, cmd).stream_id


def post(db: DbTarget, body: str, **kw: Any) -> Any:
    cmd = PostToFeed(actor="user:mlee", source="test", scope=kw.pop("scope", P1), body=body, **kw)
    with open_uow(db) as uow:
        return handle_post(uow, cmd)


def edit(db: DbTarget, post_id: str, body: str, **kw: Any) -> Any:
    cmd = EditPost(actor="user:mlee", source="test", scope=P1, post_id=post_id, body=body, **kw)
    with open_uow(db) as uow:
        return handle_edit_post(uow, cmd)


def sql(db: DbTarget, query: str, **params: Any) -> list[Any]:
    with open_uow(db, readonly=True) as uow:
        return list(uow.conn().execute(text(query), params).all())


def test_a_plain_post_is_one_event_and_one_row(db: DbTarget) -> None:
    result = post(db, "Spool arrived with damaged bevels #bevel-damage")
    assert [e.event_type for e in result.events] == ["Feed.Posted"]
    event = result.events[0]
    assert (event.stream_type, event.scope, event.actor, event.stream_version) == (
        "core.ActivityPost",
        P1,
        "user:mlee",
        1,
    )
    assert result.stream_id == event.stream_id == event.payload["post_id"]
    assert result.version == 1 and result.key is None
    assert event.payload["author"] == "user:mlee"
    assert event.payload["importance"] == "normal"
    assert event.payload["record_ids"] == []
    assert [(t["kind"], t["text"]) for t in event.payload["tags"]] == [("topic", "bevel-damage")]

    (row,) = sql(
        db, "SELECT item_type, summary, importance, retracted, version FROM cur_feed_items"
    )
    assert tuple(row) == ("post", "Spool arrived with damaged bevels #bevel-damage", "normal", 0, 1)


def test_a_record_tag_suggests_a_references_link_in_the_same_unit_of_work(db: DbTarget) -> None:
    rec = record(db, REC1)
    result = post(db, f"Spool arrived #{REC1} #hold")
    assert [e.event_type for e in result.events] == ["Feed.Posted", "Link.Suggested"]
    posted, suggested = result.events
    assert posted.payload["record_ids"] == [rec]
    assert suggested.payload["from_ref"] == result.stream_id
    assert suggested.payload["to_ref"] == rec
    assert suggested.payload["relation"] == "references"
    assert suggested.payload["source"] == "key_detected"
    assert suggested.correlation_id == posted.correlation_id
    assert suggested.causation_id == posted.event_id
    assert suggested.actor == "user:mlee" and suggested.source == "test"

    (link,) = sql(db, "SELECT status, from_id, to_id, relation FROM cur_links")
    assert tuple(link) == ("suggested", result.stream_id, rec, "references")


def test_the_record_sees_the_suggestion_with_the_post_as_the_other_end(db: DbTarget) -> None:
    rec = record(db, REC1)
    result = post(db, f"Spool arrived #{REC1}")
    with open_uow(db, readonly=True) as uow:
        (view,) = links_of(uow, rec)
    assert view.direction == "in"
    assert view.status == "suggested"
    assert view.other_id == result.stream_id
    assert view.other_type == "core.ActivityPost"
    assert view.other_key is None
    assert view.other_title == f"Spool arrived #{REC1}"
    assert view.label == "referenced by"


def test_a_key_no_record_has_stays_a_topic_and_links_nothing(db: DbTarget) -> None:
    result = post(db, f"see #{REC2}")
    assert [e.event_type for e in result.events] == ["Feed.Posted"]
    assert [(t["kind"], t["record_id"]) for t in result.events[0].payload["tags"]] == [
        ("topic", None)
    ]
    assert sql(db, "SELECT 1 FROM cur_links") == []


def test_two_tags_for_one_record_make_one_link(db: DbTarget) -> None:
    record(db, REC1)
    result = post(db, f"#{REC1} again #{REC1}")
    assert [e.event_type for e in result.events] == ["Feed.Posted", "Link.Suggested"]
    assert len(result.events[0].payload["tags"]) == 2
    assert len(result.events[0].payload["record_ids"]) == 1


def test_a_company_record_resolves_for_a_project_post(db: DbTarget) -> None:
    company = record(db, "ACME-REC-0001", scope="company")
    result = post(db, "see #ACME-REC-0001")
    assert [e.event_type for e in result.events] == ["Feed.Posted", "Link.Suggested"]
    assert result.events[0].payload["record_ids"] == [company]


def test_a_voided_record_is_tagged_but_not_linked(db: DbTarget) -> None:
    rec = record(db, REC1)
    with open_uow(db) as uow:
        handle_void_record(
            uow,
            VoidRecord(
                actor="user:a", source="t", scope=P1, stream_id=rec, expected_version=1, reason="x"
            ),
        )
    result = post(db, f"was #{REC1}")
    assert [e.event_type for e in result.events] == ["Feed.Posted"]
    assert result.events[0].payload["record_ids"] == [rec]
    assert sql(db, "SELECT 1 FROM cur_links") == []


def test_a_signal_tag_raises_the_effective_importance_only(db: DbTarget) -> None:
    result = post(db, "stop #hold", importance="low")
    assert result.events[0].payload["importance"] == "low"
    (row,) = sql(db, "SELECT importance, base_importance FROM cur_feed_items")
    assert tuple(row) == ("high", "low")


def test_a_post_needs_a_project_scope_and_a_body(db: DbTarget) -> None:
    with pytest.raises(InvalidScopeError):
        post(db, "hello", scope="company")
    with pytest.raises(ValidationError):
        PostToFeed(actor="user:a", source="t", scope=P1, body="   ")
    with pytest.raises(ValidationError):
        PostToFeed(actor="user:a", source="t", scope=P1, body="x" * 10_001)
    assert sql(db, "SELECT 1 FROM cur_feed_items WHERE item_type = 'post'") == []


def test_a_caller_chosen_post_id_is_used_once(db: DbTarget) -> None:
    result = post(db, "first", post_id="01POST00000000000000000001")
    assert result.stream_id == "01POST00000000000000000001"
    with pytest.raises(ConcurrencyError):
        post(db, "again", post_id="01POST00000000000000000001")


def test_a_failure_while_suggesting_rolls_the_post_back(
    db: DbTarget, monkeypatch: pytest.MonkeyPatch
) -> None:
    record(db, REC1)

    def boom(*_: Any, **__: Any) -> Any:
        raise RuntimeError("boom")

    monkeypatch.setattr(feed_service, "handle_suggest_link", boom)
    with pytest.raises(RuntimeError):
        post(db, f"#{REC1}")
    assert sql(db, "SELECT 1 FROM cur_feed_items WHERE item_type = 'post'") == []
    with open_uow(db, readonly=True) as uow:
        assert uow.ledger.read_after(0, scope=P1)[-1].event_type == "Record.Created"


def test_load_post_reads_the_row_and_hides_other_scopes(db: DbTarget) -> None:
    result = post(db, "hello #fyi")
    with open_uow(db, readonly=True) as uow:
        row = load_post(uow, P1, result.stream_id)
        assert (row.author, row.body, row.retracted, row.version) == (
            "user:mlee",
            "hello #fyi",
            False,
            1,
        )
        assert row.base_importance == "normal" and row.reactions == {}
        with pytest.raises(PostNotFoundError):
            load_post(uow, "project:OTHER", result.stream_id)
        with pytest.raises(PostNotFoundError):
            load_post(uow, P1, "nope")


def test_an_edit_replaces_body_and_tags_and_keeps_the_history(db: DbTarget) -> None:
    first = post(db, "draft #topic-a")
    edited = edit(db, first.stream_id, "final #hold")
    assert [e.event_type for e in edited.events] == ["Feed.Edited"]
    assert edited.version == 2
    (row,) = sql(db, "SELECT summary, importance, edit_count, version FROM cur_feed_items")
    assert tuple(row) == ("final #hold", "high", 1, 2)
    tags = sql(db, "SELECT kind, tag_key FROM cur_feed_tags WHERE item_id = :i", i=first.stream_id)
    assert [tuple(t) for t in tags] == [("signal", "hold")]
    with open_uow(db, readonly=True) as uow:
        types = [e.event_type for e in uow.ledger.read_stream(first.stream_id)]
    assert types == ["Feed.Posted", "Feed.Edited"]


def test_an_edit_that_adds_a_record_tag_suggests_only_the_new_link(db: DbTarget) -> None:
    rec1, rec2 = record(db, REC1), record(db, REC2)
    first = post(db, f"#{REC1}")
    edited = edit(db, first.stream_id, f"#{REC1} and #{REC2}")
    assert [e.event_type for e in edited.events] == ["Feed.Edited", "Link.Suggested"]
    assert edited.events[1].payload["to_ref"] == rec2
    assert edited.events[1].causation_id == edited.events[0].event_id
    links = sql(db, "SELECT to_id FROM cur_links ORDER BY created_at, link_id")
    assert sorted(r.to_id for r in links) == sorted([rec1, rec2])


def test_a_declined_suggestion_is_not_made_again_by_a_later_edit(db: DbTarget) -> None:
    record(db, REC1)
    first = post(db, f"#{REC1}")
    (link,) = sql(db, "SELECT link_id FROM cur_links")
    with open_uow(db) as uow:
        handle_decline_link(
            uow, DeclineLink(actor="user:q", source="t", scope=P1, link_id=link.link_id)
        )
    edit(db, first.stream_id, "no record now")
    again = edit(db, first.stream_id, f"back to #{REC1}")
    assert [e.event_type for e in again.events] == ["Feed.Edited"]
    assert len(sql(db, "SELECT 1 FROM cur_links")) == 1


def test_edit_refusals(db: DbTarget) -> None:
    first = post(db, "one")
    with pytest.raises(NoChangesError):
        edit(db, first.stream_id, "one")
    with pytest.raises(PostNotFoundError):
        edit(db, "nope", "x")
    with pytest.raises(ConcurrencyError):
        edit(db, first.stream_id, "two", expected_version=5)
    with open_uow(db) as uow:
        uow.append(
            stream_id=first.stream_id,
            stream_type="core.ActivityPost",
            scope=P1,
            expected_version=1,
            events=[
                NewEvent(
                    event_type="Feed.Retracted", payload={"post_id": first.stream_id, "reason": "x"}
                )
            ],
            actor="user:mlee",
            source="t",
            correlation_id="c",
        )
    with pytest.raises(PostRetractedError):
        edit(db, first.stream_id, "three")


def test_the_feed_projection_survives_a_rebuild(db: DbTarget) -> None:
    record(db, REC1)
    first = post(db, f"hello #{REC1} #hold @party:fab-a")
    edit(db, first.stream_id, f"hello again #{REC1} #area:A12")

    def dump() -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]:
        items = sql(db, "SELECT * FROM cur_feed_items ORDER BY item_id")
        tags = sql(db, "SELECT * FROM cur_feed_tags ORDER BY tag_row_id")
        return [tuple(r) for r in items], [tuple(r) for r in tags]

    live = dump()
    rebuild_projections(db)
    assert dump() == live


# --- a post at the end of a link is not a record (decision A1) ---------------------------------


def test_a_post_link_does_not_satisfy_record_to_record_expectations(db: DbTarget) -> None:
    from tl_core.links.expected import ExpectedLink, missing_expected_links, unmet_expectations
    from tl_core.services.errors import RecordNotFoundError
    from tl_core.services.links import AcceptLink, handle_accept_link

    rec = record(db, REC1)
    result = post(db, f"on #{REC1}")
    link_id = result.events[1].stream_id
    with open_uow(db) as uow:
        handle_accept_link(uow, AcceptLink(actor="user:q", source="t", scope=P1, link_id=link_id))
    assert sql(db, "SELECT status FROM cur_links")[0].status == "active"
    wanted = [ExpectedLink(relation="references", direction="in", label="referenced by a record")]
    with open_uow(db, readonly=True) as uow:
        # The active inbound `references` link comes from a post, so the guard still sees none.
        assert [m.found for m in unmet_expectations(uow, rec, wanted)] == [0]
        # The post is not a record: record-level checks do not accept it.
        with pytest.raises(RecordNotFoundError):
            missing_expected_links(uow, result.stream_id)


def test_a_record_cannot_link_to_a_post_and_the_post_cannot_be_a_workflow_subject(
    db: DbTarget,
) -> None:
    from tl_core.services.errors import RecordNotFoundError
    from tl_core.services.links import AddLink, handle_add_link
    from tl_core.services.workflow import workflow_status

    rec = record(db, REC1)
    pid = post(db, "plain").stream_id
    with pytest.raises(RecordNotFoundError), open_uow(db) as uow:
        handle_add_link(uow, AddLink(actor="user:q", source="t", scope=P1, from_id=rec, to_id=pid))
    with pytest.raises(RecordNotFoundError), open_uow(db, readonly=True) as uow:
        workflow_status(uow, pid)


def test_a_post_may_only_reference_records(db: DbTarget) -> None:
    from tl_core.services.errors import UnknownRelationError
    from tl_core.services.links import AddLink, handle_add_link

    rec = record(db, REC1)
    pid = post(db, "plain").stream_id
    for relation in ("blocks", "requires", None):
        with pytest.raises(UnknownRelationError), open_uow(db) as uow:
            cmd = AddLink(
                actor="user:q", source="t", scope=P1, from_id=pid, to_id=rec, relation=relation
            )
            handle_add_link(uow, cmd)
    with open_uow(db) as uow:
        cmd = AddLink(
            actor="user:q", source="t", scope=P1, from_id=pid, to_id=rec, relation="references"
        )
        handle_add_link(uow, cmd)
    assert sql(db, "SELECT relation, status FROM cur_links")[0].relation == "references"
