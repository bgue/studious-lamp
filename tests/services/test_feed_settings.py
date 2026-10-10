"""The feed reads feed.reactions.enabled and feed.signal_tags from settings (P0-I8-T05).

Provided; do not edit.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import Connection, text
from tl_adapters.db import DbTarget, create_schema, open_uow
from tl_core import settings
from tl_core.feed.config import reactions_enabled, signal_tags
from tl_core.feed.types import DEFAULT_SIGNAL_TAGS
from tl_core.services.errors import ReactionsDisabledError
from tl_core.services.feed import PostToFeed, handle_post
from tl_core.services.feed_actions import ReactToPost, handle_react_to_post
from tl_core.services.feed_completion import complete_tags

P1 = "project:P1"
P2 = "project:P2"


@pytest.fixture
def db(new_db: Callable[[], DbTarget]) -> DbTarget:
    target = new_db()
    create_schema(target)
    return target


def put(db: DbTarget, key: str, layer: str, value: object) -> None:
    with open_uow(db) as uow:
        settings.set_setting(uow, key=key, layer=layer, value=value, actor="user:a", source="t")


def post(db: DbTarget, body: str, scope: str = P1) -> str:
    with open_uow(db) as uow:
        return handle_post(
            uow, PostToFeed(actor="user:mlee", source="t", scope=scope, body=body)
        ).stream_id


def react(db: DbTarget, post_id: str, scope: str = P1) -> None:
    with open_uow(db) as uow:
        handle_react_to_post(
            uow,
            ReactToPost(
                actor="user:a", source="t", scope=scope, post_id=post_id, reaction="ack", on=True
            ),
        )


def importance_of(db: DbTarget, post_id: str) -> str:
    with open_uow(db, readonly=True) as uow:
        row = (
            uow.conn()
            .execute(
                text("SELECT importance FROM cur_feed_items WHERE item_id = :i"), {"i": post_id}
            )
            .first()
        )
    assert row is not None
    return str(row.importance)


def read(db: DbTarget, fn: Callable[[Connection], object]) -> object:
    with open_uow(db, readonly=True) as uow:
        return fn(uow.conn())


def test_the_defaults_are_the_old_constants(db: DbTarget) -> None:
    assert read(db, lambda c: signal_tags(c, P1)) == DEFAULT_SIGNAL_TAGS
    assert read(db, lambda c: reactions_enabled(c, P1)) is True
    assert read(db, lambda c: reactions_enabled(c, "company")) is True


def test_reactions_can_be_switched_off_for_a_project_and_back_on(db: DbTarget) -> None:
    pid = post(db, "Spool arrived", P1)
    other = post(db, "Spool arrived", P2)
    put(db, "feed.reactions.enabled", P1, False)
    with pytest.raises(ReactionsDisabledError):
        react(db, pid)
    react(db, other, P2)  # another project is unaffected
    put(db, "feed.reactions.enabled", P1, True)
    react(db, pid)


def test_the_company_value_applies_to_every_project_that_does_not_set_its_own(db: DbTarget) -> None:
    pid, other = post(db, "a", P1), post(db, "b", P2)
    put(db, "feed.reactions.enabled", "company", False)
    for scope, post_id in ((P1, pid), (P2, other)):
        with pytest.raises(ReactionsDisabledError):
            react(db, post_id, scope)
    put(db, "feed.reactions.enabled", P2, True)
    react(db, other, P2)
    with pytest.raises(ReactionsDisabledError):
        react(db, pid, P1)


def test_signal_tags_follow_the_setting_without_a_restart(db: DbTarget) -> None:
    assert importance_of(db, post(db, "Crane check #custom")) == "normal"
    put(db, "feed.signal_tags", P1, ["custom", "hold"])
    assert read(db, lambda c: signal_tags(c, P1)) == ("custom", "hold")
    assert importance_of(db, post(db, "Crane check #custom")) == "high"
    assert importance_of(db, post(db, "Spool #safety")) == "normal"  # no longer a signal here
    assert importance_of(db, post(db, "Crane check #custom", P2)) == "normal"  # another project


def test_completion_offers_the_signal_tags_in_force(db: DbTarget) -> None:
    put(db, "feed.signal_tags", P1, ["custom", "crane"])

    def offered(scope: str) -> list[str]:
        with open_uow(db, readonly=True) as uow:
            found = complete_tags(uow, scope, "#", "c")
        return [item.text for item in found if item.kind == "signal"]

    assert offered(P1) == ["custom", "crane"]
    assert offered(P2) == []
