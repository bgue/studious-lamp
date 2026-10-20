"""EmbeddedClient's thread methods over the real services on a temporary ledger (P1-I7 WS-B).

A dispatch runs each command as the signed-in person through the command runner, which reads what
the person holds from their account.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from tl_adapters.db import DbTarget, create_schema, open_uow
from tl_core import settings
from tl_core.auth import accounts
from tl_core.auth.errors import ForbiddenError
from tl_core.services.commands import CreateRecord
from tl_core.threads.dispatch import DispatchFromThread
from tl_core.threads.messages import PostThreadMessage
from tl_tui.embedded import EmbeddedClient

SCOPE = "project:P123"
KEYS = ("P123-REC-0001", "P123-REC-0002")


def make_account(db: DbTarget, name: str) -> None:
    with open_uow(db) as uow:
        accounts.create_account(
            uow,
            username=name,
            display_name=name,
            kind="person",
            roles=["user"],
            password=None,
            by="user:a",
        )


@pytest.fixture
def world(new_db: Callable[[], DbTarget]) -> Iterator[tuple[EmbeddedClient, DbTarget, list[str]]]:
    db = new_db()
    create_schema(db)
    make_account(db, "jo")
    with open_uow(db) as uow:
        for key, value in (("threads.enabled", True), ("threads.enabled_types", ["core.Record"])):
            settings.set_setting(
                uow, key=key, layer="company", value=value, actor="user:a", source="t", reason="t"
            )
    client = EmbeddedClient.for_target(db, actor="user:jo")
    ids = [
        client.create_record(
            CreateRecord(
                actor="user:jo",
                source="tui",
                scope=SCOPE,
                record_type="core.Record",
                title=key,
                key=key,
            )
        ).stream_id
        for key in KEYS
    ]
    yield client, db, ids
    client.close()


def test_post_and_read_a_thread(world: tuple[EmbeddedClient, DbTarget, list[str]]) -> None:
    client, _, (rid, _) = world
    client.thread_post(
        PostThreadMessage(actor="user:jo", source="tui", scope=SCOPE, record_id=rid, body="hello")
    )
    page = client.thread_page(rid)
    assert page.enabled and [m.body for m in page.messages] == ["hello"]


def test_preview_then_dispatch_runs_what_was_previewed_as_the_person(
    world: tuple[EmbeddedClient, DbTarget, list[str]],
) -> None:
    client, _, (rid, other) = world
    line = f"/link #{KEYS[1]} as requires"
    shown = client.thread_preview(rid, line)
    assert shown.preview is not None and shown.preview.can_dispatch
    assert shown.preview.planned[0].permitted
    done = client.thread_dispatch(
        DispatchFromThread(
            actor="user:jo",
            source="tui",
            scope=SCOPE,
            record_id=rid,
            text=line,
            token=shown.preview.token,
            expires_at=shown.preview.expires_at,
        )
    )
    assert done.key
    page = client.thread_page(rid)
    assert page.messages[-1].dispatch is not None and page.messages[-1].dispatch.verb == "link"
    assert other


def test_someone_else_cannot_be_dispatched_as(
    world: tuple[EmbeddedClient, DbTarget, list[str]],
) -> None:
    client, _, (rid, _) = world
    line = f"/link #{KEYS[1]}"
    shown = client.thread_preview(rid, line)
    assert shown.preview is not None
    with pytest.raises(ForbiddenError):
        client.thread_dispatch(
            DispatchFromThread(
                actor="user:mallory",
                source="tui",
                scope=SCOPE,
                record_id=rid,
                text=line,
                token=shown.preview.token,
            )
        )


def test_a_person_with_no_account_holds_nothing(
    world: tuple[EmbeddedClient, DbTarget, list[str]],
) -> None:
    _, db, (rid, _) = world
    stranger = EmbeddedClient.for_target(db, actor="user:stranger")
    try:
        shown = stranger.thread_preview(rid, f"/link #{KEYS[1]}")
    finally:
        stranger.close()
    assert shown.preview is not None and not shown.preview.can_dispatch
    assert not shown.preview.planned[0].permitted


def test_a_thread_write_is_made_as_the_signed_in_person(
    world: tuple[EmbeddedClient, DbTarget, list[str]],
) -> None:
    from tl_core.threads.messages import EditThreadMessage, RetractThreadMessage

    client, _, (rid, _) = world
    posted = client.thread_post(
        PostThreadMessage(actor="user:jo", source="tui", scope=SCOPE, record_id=rid, body="mine")
    )
    base = {"source": "tui", "scope": SCOPE, "record_id": rid}
    with pytest.raises(ForbiddenError):
        client.thread_post(PostThreadMessage(actor="user:mallory", body="as someone", **base))
    with pytest.raises(ForbiddenError):
        client.thread_edit(
            EditThreadMessage(actor="user:mallory", message_id=str(posted.key), body="x", **base)
        )
    with pytest.raises(ForbiddenError):
        client.thread_retract(
            RetractThreadMessage(
                actor="user:mallory", message_id=str(posted.key), reason="x", **base
            )
        )
    assert [m.body for m in client.thread_page(rid).messages] == ["mine"]
