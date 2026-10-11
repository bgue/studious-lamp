"""Account events stay internal: no feed card, no webhook delivery (ADR-0009 section 1)."""

from __future__ import annotations

from typing import Any

from authworld import World
from tl_core.auth import accounts
from tl_core.auth.password import prepare_password
from tl_core.auth.projector import ACCOUNT_EVENT_TYPES
from tl_core.services.commands import CreateRecord
from tl_core.services.records import handle_create_record
from tl_core.webhooks.dispatch import Dispatcher
from tl_core.webhooks.subscriptions import CreateWebhookSubscription, create_subscription


def make_record(world: World, key: str) -> None:
    with world.factory() as uow:
        handle_create_record(
            uow,
            CreateRecord(
                actor="user:alice",
                source="test",
                scope="company",
                record_type="core.Record",
                title=key,
                key=key,
            ),
        )


def test_account_events_make_no_feed_card_and_do_not_split_a_burst(world: World) -> None:
    make_record(world, "C-1")
    admin = world.admin()
    bob = world.create("bob")
    bot = world.create("bot", kind="agent")
    with world.factory() as uow:
        accounts.issue_agent_token(
            uow, account_id=bot.account_id, label="t", expires_at=None, by="user:root"
        )
        accounts.disable(uow, account_id=bob.account_id, by="user:root", reason="x")
        accounts.change_password(
            uow,
            account_id=admin.account_id,
            new_password=prepare_password("another long passphrase"),
            by="user:other",
        )
    make_record(world, "C-2")
    [(items, count)] = world.rows(
        "SELECT COUNT(*), MAX(event_count) FROM cur_feed_items WHERE item_type = 'card'"
    )
    assert (items, count) == (1, 2)  # one card, both record creations, nothing in between


def test_account_events_are_never_delivered_to_a_webhook(world: World) -> None:
    with world.factory() as uow:
        create_subscription(
            uow,
            CreateWebhookSubscription(
                actor="user:alice",
                source="test",
                scope="company",
                name="everything",
                target_url="https://hook.test/in",
                filter={},
            ),
            clock=world.clock,
        )
    world.admin()
    world.create("bob")
    bot = world.create("bot", kind="agent")
    with world.factory() as uow:
        accounts.issue_agent_token(
            uow, account_id=bot.account_id, label="t", expires_at=None, by="user:root"
        )
    make_record(world, "C-1")
    Dispatcher(world.factory, clock=world.clock).run_until_idle()
    delivered = world.rows(
        "SELECT o.event_type FROM wh_delivery d JOIN outbox_events o ON o.seq = d.seq "
        "ORDER BY d.seq"
    )
    assert delivered == [("Record.Created",)]
    assert world.rows("SELECT COUNT(*) FROM outbox_events WHERE stream_type = 'core.Account'") == [
        (4,)
    ]


def test_real_account_payloads_match_the_catalog_schemas(world: World) -> None:
    """What the services write validates against the generated payload class of each event type."""
    import json

    from jsonschema import Draft202012Validator
    from tl_schema import catalog

    world.admin()
    bob = world.create("bob")
    bot = world.create("bot", kind="agent")
    with world.factory() as uow:
        _, token = accounts.issue_agent_token(
            uow, account_id=bot.account_id, label="t", expires_at=None, by="user:root"
        )
        accounts.set_roles(
            uow, account_id=bob.account_id, roles=["admin", "user"], by="user:root", reason="r"
        )
        accounts.change_password(
            uow,
            account_id=bob.account_id,
            new_password=prepare_password("another long passphrase"),
            by="user:root",
        )
        accounts.disable(uow, account_id=bob.account_id, by="user:root", reason="x")
        accounts.enable(uow, account_id=bob.account_id, by="user:root", reason="y")
        view = accounts.revoke_agent_token(
            uow, token_id=_first_token(uow), by="user:root", reason="z"
        )
    assert view.revoked and token
    seen: set[str] = set()
    for event_type, _, _, payload in world.events():
        schema = catalog.envelope_schema(event_type)["properties"]["data"]["properties"]["detail"]
        errors = list(Draft202012Validator(schema).iter_errors(json.loads(payload)))
        assert not errors, (event_type, errors[0].message)
        seen.add(event_type)
    assert seen == set(ACCOUNT_EVENT_TYPES)


def _first_token(uow: Any) -> str:
    from tl_core.auth import queries

    return queries.list_agent_tokens(uow.conn())[0].token_id
