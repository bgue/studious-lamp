"""The integration group of `ClientInterface`: the embedded client over the real services, and the
fake it is tested against (P1-I7). Provided; do not edit.

The embedded client runs a screen's command through the command table, as the signed-in person: an
admin switches, a person accepts; an actor with no account, or too few roles, is refused.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fakes import FakeClient
from tl_adapters.sqlite.uow import create_schema
from tl_core.auth import accounts
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.password import prepare_password
from tl_core.integration.errors import IntegrationNotFoundError, IntegrationStateError
from tl_core.integration.rules.service import CreateRule, handle_create_rule
from tl_tui.embedded import EmbeddedClient

SCOPE = "project:P123"
GOOD = "correct horse battery"
RULE = {
    "key": "hse-notify",
    "title": "Notify HSE",
    "when": {"event_types": ["Feed.Posted"], "hashtags": ["safety"]},
    "then": [{"command": "PostToFeed", "args": {"body": "HSE notified"}}],
}


def make(tmp_path: Path, actor: str) -> EmbeddedClient:
    db = tmp_path / "tl.db"
    create_schema(db)
    client = EmbeddedClient.for_sqlite(db, actor=actor)
    with client._uow(False) as uow:  # pyright: ignore[reportPrivateUsage]
        for name, roles in (("boss", ["admin"]), ("bob", ["user"])):
            accounts.create_account(
                uow, username=name, display_name=name, kind="person", roles=roles,
                password=prepare_password(GOOD), by="svc:test",
            )  # fmt: skip
        handle_create_rule(uow, CreateRule(actor="user:boss", source="test", scope=SCOPE, **RULE))
    return client


def test_the_rows_of_a_kind_come_back_parsed(tmp_path: Path) -> None:
    client = make(tmp_path, "user:bob")
    [rule] = client.list_integration("rules")
    assert rule["key"] == "hse-notify" and rule["enabled"] in (0, False)
    assert rule["when"] == RULE["when"] and rule["then"][0]["command"] == "PostToFeed"
    assert "when_json" not in rule
    assert client.list_integration("apps") == [] and client.list_integration("endpoints") == []
    with pytest.raises(IntegrationNotFoundError):
        client.list_integration("nonsense")


def test_the_error_queue_is_the_admins(tmp_path: Path) -> None:
    assert make(tmp_path, "user:boss").list_integration("deliveries") == []
    (tmp_path / "other").mkdir()
    with pytest.raises(ForbiddenError):
        make(tmp_path / "other", "user:bob").list_integration("deliveries")


def test_an_admin_switches_a_rule_and_a_person_may_not(tmp_path: Path) -> None:
    boss = make(tmp_path, "user:boss")
    rule_id = boss.list_integration("rules")[0]["rule_id"]
    boss.integration_command("EnableRule", SCOPE, rule_id=rule_id)
    assert bool(boss.list_integration("rules")[0]["enabled"])
    with pytest.raises(IntegrationStateError):
        boss.integration_command("EnableRule", SCOPE, rule_id=rule_id)
    boss.integration_command("DisableRule", SCOPE, rule_id=rule_id)
    assert not bool(boss.list_integration("rules")[0]["enabled"])
    bob = EmbeddedClient.for_sqlite(tmp_path / "tl.db", actor="user:bob")
    with pytest.raises(Exception) as refused:
        bob.integration_command("EnableRule", SCOPE, rule_id=rule_id)
    assert "access" in str(refused.value).lower()


def test_an_actor_with_no_account_is_refused_and_so_is_a_command_a_screen_does_not_run(
    tmp_path: Path,
) -> None:
    make(tmp_path, "user:boss")
    ghost = EmbeddedClient.for_sqlite(tmp_path / "tl.db", actor="user:ghost")
    with pytest.raises(Exception) as refused:
        ghost.integration_command("EnableRule", SCOPE, rule_id="x")
    assert "access" in str(refused.value).lower()
    boss = EmbeddedClient.for_sqlite(tmp_path / "tl.db", actor="user:boss")
    with pytest.raises(ValueError, match="not a command a screen runs"):
        boss.integration_command("CreateRule", SCOPE, key="x")


def test_the_fake_agrees_with_the_embedded_client_on_the_errors(tmp_path: Path) -> None:
    fake = FakeClient()
    row: dict[str, Any] = {"rule_id": "r1", "key": "hse-notify", "enabled": False}
    fake.seed_integration("rules", **row)
    fake.integration_command("EnableRule", SCOPE, rule_id="r1")
    with pytest.raises(IntegrationStateError):
        fake.integration_command("EnableRule", SCOPE, rule_id="r1")
    with pytest.raises(IntegrationNotFoundError):
        fake.integration_command("EnableRule", SCOPE, rule_id="missing")
    fake.is_admin_integration = False
    with pytest.raises(ForbiddenError):
        fake.integration_command("DisableRule", SCOPE, rule_id="r1")
    with pytest.raises(ForbiddenError):
        fake.list_integration("deliveries")
    assert fake.list_integration("rules")[0]["key"] == "hse-notify"
