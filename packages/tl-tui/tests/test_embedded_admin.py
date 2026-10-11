"""The admin group of `ClientInterface`: the embedded client over the real services, and the fake.

One script runs on both and what comes back is compared (error classes, messages, the fields of a
view that do not depend on the clock or an id), so the fake the screens are tested against cannot
drift from the services. The rest checks the embedded client alone: only an active admin account
may call, a password is hashed outside the write transaction, and nothing secret is returned.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fakes import FakeClient
from tl_adapters.sqlite.uow import create_schema
from tl_core.auth import accounts, queries
from tl_core.auth import password as pw
from tl_core.auth.errors import ForbiddenError, WeakPasswordError
from tl_core.auth.password import prepare_password
from tl_core.auth.types import AccountView, AgentTokenView
from tl_tui.client import ClientInterface
from tl_tui.embedded import EmbeddedClient

GOOD = "correct horse battery"
OTHER = "another long passphrase"


def make_embedded(tmp_path: Path, actor: str = "user:boss") -> EmbeddedClient:
    db = tmp_path / "tl.db"
    create_schema(db)
    client = EmbeddedClient.for_sqlite(db, actor=actor)
    with client._uow(False) as uow:  # pyright: ignore[reportPrivateUsage]
        accounts.create_account(
            uow, username="boss", display_name="Boss", kind="person", roles=["admin"],
            password=prepare_password(GOOD), by="svc:test",
        )  # fmt: skip
    return client


def make_fake() -> FakeClient:
    client = FakeClient()
    client.seed_account("boss", roles=["admin"])
    return client


def shown(value: Any) -> Any:
    """A result without ids, times and counters: what the two clients must agree on."""
    if isinstance(value, AccountView):
        return ("account", value.username, value.display_name, value.kind, tuple(value.roles),
                value.status, value.locked_until is None)  # fmt: skip
    if isinstance(value, AgentTokenView):
        return ("token", value.label, value.expires_at is None, value.revoked)
    if isinstance(value, tuple):
        return tuple(
            shown(v) if isinstance(v, (AccountView, AgentTokenView)) else "<secret>" for v in value
        )
    if isinstance(value, list):
        return [shown(v) for v in value]  # pyright: ignore[reportUnknownVariableType]
    return value


def outcome(call: Callable[[], Any]) -> tuple[Any, ...]:
    try:
        return ("ok", shown(call()))
    except Exception as exc:
        return ("error", type(exc).__name__, str(exc))


def script(client: ClientInterface) -> list[tuple[Any, ...]]:
    """Every call once, successes and refusals, in an order that depends only on earlier steps."""
    out: list[tuple[Any, ...]] = []

    def step(call: Callable[[], Any]) -> None:
        out.append(outcome(call))

    def ident(name: str) -> str:
        return next(a.account_id for a in client.list_accounts() if a.username == name)

    step(lambda: client.list_accounts())
    step(lambda: client.create_account("amy", "Amy A", password=GOOD))
    step(lambda: client.create_account("AMY", "Again", password=GOOD))  # taken
    step(lambda: client.create_account("zed", "Zed", password="short"))  # weak
    step(lambda: client.create_account("bot", "Bot", kind="agent", password=GOOD))
    step(lambda: client.create_account("bot", "Bot", kind="agent"))
    step(lambda: client.create_account("sim-1", "Sim", kind="sim", roles=["admin"]))
    step(lambda: client.create_account("x y", "Bad name"))
    step(lambda: client.create_account("kim", "Kim", roles=["owner"]))
    step(lambda: client.create_account("kim", "  ", password=GOOD))
    step(lambda: client.get_account(ident("amy")))
    step(lambda: client.get_account("nope"))
    step(lambda: client.set_roles(ident("amy"), ["admin", "user"], reason="lead"))
    step(lambda: client.set_roles(ident("amy"), ["user", "admin"]))  # the same roles
    step(lambda: client.set_roles(ident("amy"), []))
    step(lambda: client.set_roles(ident("amy"), ["user"]))  # boss is still an admin
    step(lambda: client.set_roles(ident("boss"), ["user"]))  # the last admin
    step(lambda: client.disable_account(ident("boss")))  # the last admin again
    step(lambda: client.disable_account(ident("amy"), reason="x" * 600))
    step(lambda: client.disable_account(ident("bot")))
    step(lambda: client.disable_account(ident("bot")))  # twice
    step(lambda: client.enable_account(ident("bot")))
    step(lambda: client.enable_account(ident("bot")))  # twice
    step(lambda: client.reset_password(ident("amy"), OTHER))
    step(lambda: client.reset_password(ident("amy"), "short"))
    step(lambda: client.reset_password(ident("bot"), OTHER))
    step(lambda: client.reset_password("nope", OTHER))
    step(lambda: client.issue_agent_token(ident("amy"), "mcp"))  # not an agent
    step(lambda: client.issue_agent_token(ident("bot"), "mcp"))
    step(lambda: client.issue_agent_token(ident("bot"), "forever", expires_in_days=None))
    step(lambda: client.issue_agent_token(ident("bot"), "  "))
    step(lambda: client.issue_agent_token("nope", "x"))
    step(lambda: client.list_agent_tokens())
    step(lambda: client.list_agent_tokens(ident("bot")))
    step(lambda: client.list_agent_tokens(ident("amy")))
    token_id = client.list_agent_tokens()[0].token_id
    step(lambda: client.revoke_agent_token(token_id, reason="done"))
    step(lambda: client.revoke_agent_token(token_id))  # twice
    step(lambda: client.revoke_agent_token("nope"))
    step(lambda: client.list_agent_tokens(include_revoked=False))
    step(lambda: client.list_accounts())
    return out


def test_the_fake_and_the_embedded_client_agree_on_every_step(tmp_path: Path) -> None:
    on_embedded = script(make_embedded(tmp_path))
    on_fake = script(make_fake())
    assert len(on_embedded) == len(on_fake) >= 35
    for number, (real, fake) in enumerate(zip(on_embedded, on_fake, strict=True)):
        assert real == fake, f"step {number}"
    kinds = {step[0] for step in on_embedded}
    assert kinds == {"ok", "error"}  # the script exercises both


def test_only_an_active_admin_account_may_call_and_everything_else_is_forbidden(
    tmp_path: Path,
) -> None:
    boss = make_embedded(tmp_path)
    with boss._uow(False) as uow:  # pyright: ignore[reportPrivateUsage]
        accounts.create_account(
            uow, username="amy", display_name="Amy", kind="person", roles=["user"],
            password=prepare_password(GOOD), by="svc:test",
        )  # fmt: skip
    db = tmp_path / "tl.db"
    for actor in ("user:amy", "user:dev", "user:ghost", "svc:importer"):
        client = EmbeddedClient.for_sqlite(db, actor=actor)
        for call in (
            lambda c=client: c.list_accounts(),
            lambda c=client: c.get_account("x"),
            lambda c=client: c.create_account("zed", "Zed", password=GOOD),
            lambda c=client: c.set_roles("x", ["user"]),
            lambda c=client: c.disable_account("x"),
            lambda c=client: c.enable_account("x"),
            lambda c=client: c.reset_password("x", OTHER),
            lambda c=client: c.list_agent_tokens(),
            lambda c=client: c.issue_agent_token("x", "l"),
            lambda c=client: c.revoke_agent_token("x"),
        ):
            with pytest.raises(ForbiddenError, match="needs the admin role"):
                call()
    assert len(boss.list_accounts()) == 2  # nothing was created


def test_a_disabled_admin_is_no_longer_an_admin(tmp_path: Path) -> None:
    boss = make_embedded(tmp_path)
    amy = boss.create_account("amy", "Amy", roles=["admin"], password=GOOD)
    other = EmbeddedClient.for_sqlite(tmp_path / "tl.db", actor="user:amy")
    assert len(other.list_accounts()) == 2
    boss.disable_account(amy.account_id)
    with pytest.raises(ForbiddenError):
        other.list_accounts()


def test_the_event_names_the_acting_admin_and_holds_no_secret(tmp_path: Path) -> None:
    client = make_embedded(tmp_path)
    amy = client.create_account("amy", "Amy", password=GOOD)
    client.reset_password(amy.account_id, OTHER)
    bot = client.create_account("bot", "Bot", kind="agent")
    view, token = client.issue_agent_token(bot.account_id, "mcp")
    assert token.startswith("tla_") and token not in repr(view)
    with client._uow(True) as uow:  # pyright: ignore[reportPrivateUsage]
        events = (
            uow.conn()
            .exec_driver_sql(
                "SELECT event_type, actor, payload FROM events WHERE event_type LIKE 'Account.%' "
                "OR event_type LIKE 'AgentToken.%' ORDER BY seq"
            )
            .all()
        )
    joined = " ".join(str(e[2]) for e in events)
    assert GOOD not in joined and OTHER not in joined and token not in joined
    assert "scrypt" not in joined
    assert {e[1] for e in events if e[0] != "Account.Created" or "boss" not in str(e[2])} == {
        "user:boss"
    }


def test_the_password_is_hashed_before_the_write_transaction_opens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = make_embedded(tmp_path)
    amy = client.create_account("amy", "Amy", password=GOOD)
    inside: list[bool] = []
    real = pw._scrypt  # pyright: ignore[reportPrivateUsage]
    writing = threading.local()
    factory = client._uow  # pyright: ignore[reportPrivateUsage]

    def spy_factory(readonly: bool) -> Any:
        cm = factory(readonly)

        class Wrapper:
            def __enter__(self) -> Any:
                writing.on = not readonly
                return cm.__enter__()

            def __exit__(self, *exc: Any) -> Any:
                try:
                    return cm.__exit__(*exc)
                finally:
                    writing.on = False

        return Wrapper()

    def spying(password: str, salt: bytes, params: pw.ScryptParams) -> bytes:
        inside.append(bool(getattr(writing, "on", False)))
        return real(password, salt, params)

    monkeypatch.setattr(client, "_uow", spy_factory)
    monkeypatch.setattr(pw, "_scrypt", spying)
    client.create_account("bob", "Bob", password=GOOD)
    client.reset_password(amy.account_id, OTHER)
    assert inside and not any(inside)


def test_a_weak_password_names_the_rules_and_changes_nothing(tmp_path: Path) -> None:
    client = make_embedded(tmp_path)
    with pytest.raises(WeakPasswordError) as raised:
        client.create_account("amy", "Amy", password="short")
    assert raised.value.issues and "short" not in str(raised.value)
    assert [a.username for a in client.list_accounts()] == ["boss"]


def test_it_satisfies_the_client_interface_for_admin(tmp_path: Path) -> None:
    typed: ClientInterface = make_embedded(tmp_path)
    assert [a.username for a in typed.list_accounts()] == ["boss"]
    typed_fake: ClientInterface = make_fake()
    assert [a.username for a in typed_fake.list_accounts()] == ["boss"]


def test_the_listing_agrees_with_the_services(tmp_path: Path) -> None:
    client = make_embedded(tmp_path)
    client.create_account("amy", "Amy", password=GOOD)
    with client._uow(True) as uow:  # pyright: ignore[reportPrivateUsage]
        assert client.list_accounts() == queries.list_accounts(uow.conn())


def test_the_fake_can_play_a_non_admin_and_records_calls_without_secrets() -> None:
    fake = make_fake()
    fake.create_account("amy", "Amy", password=GOOD)
    assert ("create_account", {"username": "amy", "kind": "person", "roles": ["user"]}) in (
        fake.admin_calls
    )
    assert all(GOOD not in str(call) for call in fake.admin_calls)
    fake.is_admin = False
    with pytest.raises(ForbiddenError):
        fake.list_accounts()
