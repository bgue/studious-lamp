"""A restored database has accounts but no passwords or token secrets (ADR-0009 section 10, D1).

Hashes are operational state outside the ledger, so a restore brings back who exists and what roles
they have, and nobody can sign in until an admin acts: the first admin through
``tl admin bootstrap``, the rest through a reset, agents through new tokens.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from tl_adapters.db import DbTarget, create_schema, make_engine, make_uow_factory, read_tx
from tl_adapters.restore import restore_from_archive
from tl_core.archive import generate_signer, seal_segment
from tl_core.auth import accounts, queries, seed, sessions
from tl_core.auth.errors import InvalidCredentialsError

GOOD = "correct horse battery"
NEW = "a brand new passphrase"


def populate(db: DbTarget) -> dict[str, str]:
    factory = make_uow_factory(db)
    try:
        with factory() as uow:
            boss = accounts.create_account(
                uow, username="boss", display_name="Boss", kind="person", roles=["admin"],
                password=GOOD, by="user:boss",
            )  # fmt: skip
            bob = accounts.create_account(
                uow, username="bob", display_name="Bob", kind="person", roles=["user"],
                password=GOOD, by="user:boss",
            )  # fmt: skip
            bot = accounts.create_account(
                uow, username="triage", display_name="Triage", kind="agent", roles=["user"],
                password=None, by="user:boss",
            )  # fmt: skip
            accounts.issue_agent_token(
                uow, account_id=bot.account_id, label="t", expires_at=None, by="user:boss"
            )
            gone = accounts.create_account(
                uow, username="gone", display_name="Gone", kind="person", roles=["user"],
                password=GOOD, by="user:boss",
            )  # fmt: skip
            accounts.disable(uow, account_id=gone.account_id, by="user:boss", reason="left")
        return {"boss": boss.account_id, "bob": bob.account_id}
    finally:
        factory.dispose()


@pytest.fixture
def restored(
    new_db: Callable[[], DbTarget], memory_store: Callable[..., Any]
) -> tuple[DbTarget, dict[str, str], list[str]]:
    original = new_db()
    create_schema(original)
    ids = populate(original)
    signer = generate_signer()
    store = memory_store()
    engine = make_engine(original)
    try:
        with read_tx(engine) as conn:
            assert seal_segment(conn, store, signer) is not None
    finally:
        engine.dispose()
    target = new_db()
    result = restore_from_archive(store, target, public_key=signer.public_key)
    return target, ids, list(result.warnings)


def test_accounts_come_back_but_nobody_can_sign_in(
    restored: tuple[DbTarget, dict[str, str], list[str]],
) -> None:
    target, ids, _ = restored
    factory = make_uow_factory(target)
    try:
        with factory(readonly=True) as uow:
            listed = {a.username: a for a in queries.list_accounts(uow.conn())}
        assert set(listed) == {"boss", "bob", "triage", "gone"}
        assert listed["boss"].roles == ["admin"] and listed["boss"].account_id == ids["boss"]
        assert listed["gone"].status == "disabled"
        for name in ("boss", "bob"):
            with pytest.raises(InvalidCredentialsError):
                sessions.sign_in(factory, username=name, password=GOOD)
    finally:
        factory.dispose()


def test_the_restore_says_how_to_get_back_in(
    restored: tuple[DbTarget, dict[str, str], list[str]],
) -> None:
    _, _, warnings = restored
    [people, tokens] = warnings
    assert "2 account(s) have no password after the restore" in people
    assert "tl admin bootstrap --username boss" in people
    assert "tl admin user reset-password <username>" in people
    assert "1 agent token(s) have no secret after the restore" in tokens
    assert "tl admin token issue" in tokens
    assert all(GOOD not in w for w in warnings)


def test_bootstrap_gets_the_admin_back_and_the_admin_resets_the_rest(
    restored: tuple[DbTarget, dict[str, str], list[str]],
) -> None:
    target, ids, _ = restored
    factory = make_uow_factory(target)
    try:
        view = seed.bootstrap_admin(factory, username="boss", password=NEW)
        assert view.account_id == ids["boss"]
        principal, _ = sessions.sign_in(factory, username="boss", password=NEW)
        assert principal.is_admin
        with factory() as uow:
            accounts.change_password(
                uow, account_id=ids["bob"], new_password=NEW, by=principal.actor
            )
        sessions.sign_in(factory, username="bob", password=NEW)
    finally:
        factory.dispose()


def test_restored_agent_tokens_authenticate_nothing(
    restored: tuple[DbTarget, dict[str, str], list[str]],
) -> None:
    target, _, _ = restored
    factory = make_uow_factory(target)
    try:
        with factory(readonly=True) as uow:
            assert (
                uow.conn().exec_driver_sql("SELECT COUNT(*) FROM auth_token_secret").scalar() == 0
            )
            assert uow.conn().exec_driver_sql("SELECT COUNT(*) FROM cur_agent_token").scalar() == 1
    finally:
        factory.dispose()
