"""Retract and react handlers against a real SQLite ledger (P0-I6-T01). Provided; do not edit."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from tl_adapters.db import DbTarget, create_schema, open_uow, rebuild_projections
from tl_core.ledger import ConcurrencyError
from tl_core.services import feed_actions
from tl_core.services.commands import CommandResult
from tl_core.services.errors import (
    NoChangesError,
    PostNotFoundError,
    PostRetractedError,
    ReactionsDisabledError,
)
from tl_core.services.feed import EditPost, PostToFeed, handle_edit_post, handle_post
from tl_core.services.feed_actions import (
    ReactToPost,
    RetractPost,
    handle_react_to_post,
    handle_retract_post,
)

P1 = "project:P123"


@pytest.fixture
def db(new_db: Callable[[], DbTarget]) -> DbTarget:
    target = new_db()
    create_schema(target)
    return target


def new_post(db: DbTarget, body: str = "Spool arrived #hold", actor: str = "user:mlee") -> str:
    with open_uow(db) as uow:
        cmd = PostToFeed(actor=actor, source="test", scope=P1, body=body)
        return handle_post(uow, cmd).stream_id


def retract(db: DbTarget, post_id: str, **kw: Any) -> CommandResult:
    cmd = RetractPost(
        actor=kw.pop("actor", "user:mlee"),
        source="test",
        scope=kw.pop("scope", P1),
        post_id=post_id,
        reason=kw.pop("reason", "wrong project"),
        **kw,
    )
    with open_uow(db) as uow:
        return handle_retract_post(uow, cmd)


def react(db: DbTarget, post_id: str, reaction: str, actor: str, on: bool = True, **kw: Any) -> Any:
    cmd = ReactToPost(
        actor=actor,
        source="test",
        scope=kw.pop("scope", P1),
        post_id=post_id,
        reaction=reaction,  # type: ignore[arg-type]
        on=on,
        **kw,
    )
    with open_uow(db) as uow:
        return handle_react_to_post(uow, cmd)


def row(db: DbTarget, post_id: str) -> dict[str, Any]:
    with open_uow(db, readonly=True) as uow:
        found = uow.conn().execute(
            text("SELECT * FROM cur_feed_items WHERE item_id = :i"), {"i": post_id}
        )
        return dict(found.mappings().one())


# --- retract ----------------------------------------------------------------------------------


def test_retract_appends_one_event_and_leaves_a_tombstone(db: DbTarget) -> None:
    pid = new_post(db)
    result = retract(db, pid)
    assert [e.event_type for e in result.events] == ["Feed.Retracted"]
    event = result.events[0]
    assert event.payload == {"post_id": pid, "reason": "wrong project"}
    assert (event.stream_id, event.stream_type, event.scope) == (pid, "core.ActivityPost", P1)
    assert (event.actor, event.source, event.stream_version) == ("user:mlee", "test", 2)
    assert (result.stream_id, result.version, result.key) == (pid, 2, None)
    found = row(db, pid)
    assert (
        found["retracted"] and found["summary"] == "" and found["retract_reason"] == "wrong project"
    )


def test_anyone_may_retract_and_the_event_names_them(db: DbTarget) -> None:
    pid = new_post(db)
    result = retract(db, pid, actor="user:boss")
    assert result.events[0].actor == "user:boss"


def test_retract_refusals(db: DbTarget) -> None:
    pid = new_post(db)
    with pytest.raises(PostNotFoundError):
        retract(db, "nope")
    with pytest.raises(PostNotFoundError):
        retract(db, pid, scope="project:OTHER")
    with pytest.raises(ConcurrencyError):
        retract(db, pid, expected_version=7)
    retract(db, pid)
    with pytest.raises(PostRetractedError):
        retract(db, pid)


def test_retract_needs_a_reason() -> None:
    with pytest.raises(ValidationError):
        RetractPost(actor="u", source="t", scope=P1, post_id="x", reason="  ")


def test_a_retracted_post_cannot_be_edited(db: DbTarget) -> None:
    pid = new_post(db)
    retract(db, pid)
    cmd = EditPost(actor="user:mlee", source="t", scope=P1, post_id=pid, body="new text")
    with pytest.raises(PostRetractedError), open_uow(db) as uow:
        handle_edit_post(uow, cmd)


# --- react ------------------------------------------------------------------------------------


def test_react_appends_one_event(db: DbTarget) -> None:
    pid = new_post(db)
    result = react(db, pid, "ack", "user:a")
    assert [e.event_type for e in result.events] == ["Feed.Reacted"]
    event = result.events[0]
    assert event.payload == {"post_id": pid, "reaction": "ack", "on": True}
    assert (event.actor, event.stream_version, result.version) == ("user:a", 2, 2)
    assert row(db, pid)["reactions_json"] == '{"ack":["user:a"]}'


def test_reactions_of_several_actors_and_kinds_accumulate(db: DbTarget) -> None:
    pid = new_post(db)
    react(db, pid, "ack", "user:b")
    react(db, pid, "ack", "user:a")
    react(db, pid, "+1", "user:a")
    react(db, pid, "resolved", "user:c")
    assert row(db, pid)["reactions_json"] == (
        '{"+1":["user:a"],"ack":["user:a","user:b"],"resolved":["user:c"]}'
    )
    react(db, pid, "ack", "user:a", on=False)
    assert row(db, pid)["reactions_json"] == (
        '{"+1":["user:a"],"ack":["user:b"],"resolved":["user:c"]}'
    )


def test_setting_a_reaction_twice_or_clearing_an_unset_one_changes_nothing(db: DbTarget) -> None:
    pid = new_post(db)
    react(db, pid, "ack", "user:a")
    with pytest.raises(NoChangesError):
        react(db, pid, "ack", "user:a")
    with pytest.raises(NoChangesError):
        react(db, pid, "+1", "user:a", on=False)
    with pytest.raises(NoChangesError):
        react(db, pid, "ack", "user:b", on=False)


def test_react_refusals(db: DbTarget) -> None:
    pid = new_post(db)
    with pytest.raises(PostNotFoundError):
        react(db, "nope", "ack", "user:a")
    with pytest.raises(PostNotFoundError):
        react(db, pid, "ack", "user:a", scope="project:OTHER")
    with pytest.raises(ConcurrencyError):
        react(db, pid, "ack", "user:a", expected_version=9)
    with pytest.raises(ValidationError):
        react(db, pid, "thumbs", "user:a")
    retract(db, pid)
    with pytest.raises(PostRetractedError):
        react(db, pid, "ack", "user:a")


def test_reactions_can_be_switched_off(db: DbTarget, monkeypatch: pytest.MonkeyPatch) -> None:
    pid = new_post(db)
    monkeypatch.setattr(feed_actions, "reactions_enabled", lambda: False)
    with pytest.raises(ReactionsDisabledError):
        react(db, pid, "ack", "user:a")


def test_everything_survives_a_rebuild(db: DbTarget) -> None:
    keep, drop = new_post(db, "keep #fyi"), new_post(db, "drop #hold")
    react(db, keep, "ack", "user:a")
    retract(db, drop)

    def dump() -> list[tuple[Any, ...]]:
        with open_uow(db, readonly=True) as uow:
            rows = uow.conn().execute(text("SELECT * FROM cur_feed_items ORDER BY item_id")).all()
        return [tuple(r) for r in rows]

    live = dump()
    rebuild_projections(db)
    assert dump() == live
