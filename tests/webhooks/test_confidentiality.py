"""Webhooks deliver to the subscription owner's clearance, not the sender's (ADR-0016).

One ledger holds an item of each class. A person's subscription hears about the internal item in
full; a document controller's hears about the restricted item as a thin notice (no subject, no
fields) and never about a privileged or an unknown-class item; a plain user's hears of neither.
The numbering counter's events name the record they numbered and follow that record.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.auth import accounts
from tl_core.auth.password import prepare_password
from tl_core.services.commands import Command
from tl_core.webhooks.subscriptions import CreateWebhookSubscription, create_subscription
from tl_mod_correspondence.handlers.create import create_item
from tl_mod_correspondence.testing import CorrWorld, frozen_today
from world import World

SCOPE = "project:P123"


class _Cmd(Command):
    """A command carrier for seeding."""


def person(world: World, name: str, roles: list[str], kind: str = "person") -> None:
    with world.factory() as uow:
        accounts.create_account(
            uow,
            username=name,
            display_name=name,
            kind=kind,  # type: ignore[arg-type]
            roles=roles,  # type: ignore[arg-type]
            password=prepare_password("correct horse battery") if kind == "person" else None,
            by="svc:test",
        )


def subscribe(world: World, owner: str, mode: str = "full") -> str:
    with world.factory() as uow:
        issued = create_subscription(
            uow,
            CreateWebhookSubscription(
                actor=owner,
                source="test",
                scope=SCOPE,
                name=f"hook {owner}",
                target_url="https://hook.test/in",
                filter={},
                payload_mode=mode,  # type: ignore[arg-type]
            ),
            clock=world.clock,
        )
    return issued.subscription_id


def bodies(world: World, sid: str) -> list[dict[str, Any]]:
    rows = world.query(
        "SELECT body FROM wh_delivery WHERE subscription_id = :s ORDER BY seq", s=sid
    )
    return [json.loads(str(r["body"])) for r in rows]


@pytest.fixture
def ledger(world: World, tmp_path: Path) -> Iterator[dict[str, str]]:
    person(world, "alice", ["user"])
    person(world, "ctl", ["document_controller"])
    person(world, "bot", ["user"], kind="agent")
    subs = {
        "alice": subscribe(world, "user:alice"),
        "ctl": subscribe(world, "user:ctl"),
    }
    corr = CorrWorld(world.path)
    cmd = _Cmd(actor="user:seed", source="test", scope=SCOPE)
    ids: dict[str, str] = {}
    with frozen_today("2026-10-19"), cf.system_view():
        for kind in ("internal", "restricted", "privileged", "bogus"):
            with open_uow(world.path) as uow:
                made = create_item(
                    uow,
                    cmd,
                    subject=f"{kind.upper()}SUBJECT",
                    direction="in",
                    medium="letter",
                    received_via="manual",
                    confidentiality=kind,
                    received_on="2026-10-19",
                    received=True,
                )
            ids[kind] = made.stream_id
            ids[f"{kind}_number"] = made.key or ""
    assert corr  # (the corr world only gives the tables; the items were made above)
    world.dispatcher().run_until_idle()
    yield {**subs, **ids}


def about(body: dict[str, Any]) -> str:
    return json.dumps(body)


def test_a_plain_user_hears_of_the_internal_item_only(world: World, ledger: dict[str, str]) -> None:
    text = " ".join(about(b) for b in bodies(world, ledger["alice"]))
    assert ledger["internal"] in text and "INTERNALSUBJECT" in text
    for kind in ("restricted", "privileged", "bogus"):
        assert ledger[kind] not in text and ledger[f"{kind}_number"] not in text, kind
        assert f"{kind.upper()}SUBJECT" not in text, kind


def test_a_controller_hears_of_the_restricted_item_as_a_thin_notice(
    world: World, ledger: dict[str, str]
) -> None:
    mine = bodies(world, ledger["ctl"])
    restricted = [b for b in mine if ledger["restricted"] in about(b)]
    assert restricted, "the controller hears of the restricted item"
    for body in restricted:
        assert "RESTRICTEDSUBJECT" not in about(body)  # thin: the notice names the record only
        assert body["data"].get("changes") in (None, [], {})
    text = " ".join(about(b) for b in mine)
    for kind in ("privileged", "bogus"):  # never delivered, to anyone
        assert ledger[kind] not in text and ledger[f"{kind}_number"] not in text, kind
        assert f"{kind.upper()}SUBJECT" not in text, kind


def test_the_numbering_events_follow_the_record_they_numbered(
    world: World, ledger: dict[str, str]
) -> None:
    for owner in ("alice", "ctl"):
        counters = [
            b for b in bodies(world, ledger[owner]) if "Numbering" in str(b.get("type", ""))
        ]
        named = " ".join(about(b) for b in counters)
        assert ledger["internal_number"] in named, owner
        assert ledger["privileged_number"] not in named and ledger["bogus_number"] not in named
    plain = " ".join(
        about(b) for b in bodies(world, ledger["alice"]) if "Numbering" in str(b.get("type", ""))
    )
    assert ledger["restricted_number"] not in plain and ledger["restricted"] not in plain


def test_an_agent_owner_is_the_lowest_clearance(world: World, ledger: dict[str, str]) -> None:
    sid = subscribe(world, "user:nobody-at-all")  # an owner who is no account reads internal only
    with frozen_today("2026-10-19"), cf.system_view():
        with open_uow(world.path) as uow:
            create_item(
                uow,
                _Cmd(actor="user:seed", source="test", scope=SCOPE),
                subject="LATERRESTRICTED",
                direction="in",
                medium="letter",
                received_via="manual",
                confidentiality="restricted",
                received_on="2026-10-19",
                received=True,
            )
    world.dispatcher().run_until_idle()
    text = " ".join(about(b) for b in bodies(world, sid))
    assert "LATERRESTRICTED" not in text


def test_a_link_to_a_hidden_record_and_a_post_that_tags_one_are_not_delivered(
    world: World, ledger: dict[str, str]
) -> None:
    from tl_core.services.feed import PostToFeed, handle_post
    from tl_core.services.links import AddLink, handle_add_link

    def link(to: str, note: str) -> None:
        with open_uow(world.path) as uow:
            handle_add_link(
                uow,
                AddLink(
                    actor="user:seed",
                    source="test",
                    scope=SCOPE,
                    from_id=ledger["internal"],
                    to_id=to,
                    relation="references",
                    note=note,
                ),
                by_module=True,
            )

    with cf.system_view():
        link(ledger["restricted"], "RESTRICTEDNOTE")
        link(ledger["privileged"], "PRIVNOTE")
        with open_uow(world.path) as uow:
            handle_post(
                uow,
                PostToFeed(
                    actor="user:seed",
                    source="test",
                    scope=SCOPE,
                    body=f"see #{ledger['privileged_number']} PRIVPOST",
                ),
            )
        with open_uow(world.path) as uow:
            handle_post(
                uow,
                PostToFeed(
                    actor="user:seed",
                    source="test",
                    scope=SCOPE,
                    body=f"see #{ledger['restricted_number']} RESTRICTEDPOST",
                ),
            )
        with frozen_today("2026-10-19"), open_uow(world.path) as uow:
            other = create_item(
                uow,
                _Cmd(actor="user:seed", source="test", scope=SCOPE),
                subject="OTHERINTERNAL",
                direction="in",
                medium="letter",
                received_via="manual",
                confidentiality="internal",
                received_on="2026-10-19",
                received=True,
            )
        link(other.stream_id, "PLAINNOTE")  # a link between two readable records is delivered
    world.dispatcher().run_until_idle()
    for owner in ("alice", "ctl"):
        text = " ".join(about(b) for b in bodies(world, ledger[owner]))
        assert "PRIVNOTE" not in text and "PRIVPOST" not in text, owner
        assert ledger["privileged"] not in text.replace(ledger["privileged_number"], ""), owner
    assert "RESTRICTEDNOTE" not in " ".join(about(b) for b in bodies(world, ledger["alice"]))
    assert "RESTRICTEDPOST" not in " ".join(about(b) for b in bodies(world, ledger["alice"]))
    ctl = " ".join(about(b) for b in bodies(world, ledger["ctl"]))
    assert "RESTRICTEDNOTE" not in ctl and "RESTRICTEDPOST" not in ctl  # thin, not these events
    for owner in ("alice", "ctl"):
        assert "PLAINNOTE" in " ".join(about(b) for b in bodies(world, ledger[owner])), owner
