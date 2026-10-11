"""Fixes from the D6 security review of S2b and S2c (items 1, 2, 3, 6 and 8 of the review)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import timedelta
from typing import Any

import pytest
from authworld import GOOD, OTHER, World
from sqlalchemy import text
from tl_core.auth import accounts, audit, seed, sessions
from tl_core.auth import password as pw
from tl_core.auth.errors import (
    AccountLockedError,
    AuthBusyError,
    InvalidAccountError,
    InvalidCredentialsError,
    WeakPasswordError,
)
from tl_core.auth.tokens import token_hash
from tl_core.uow import UnitOfWork

WRONG = "this is not the password"


# --- item 3: no hashing while a write transaction is open ---------------------------------


class Tracker:
    """Wraps a unit-of-work factory and counts the write transactions that are open right now."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.open_writes = 0

    def __call__(self, readonly: bool = False) -> AbstractContextManager[UnitOfWork]:
        @contextmanager
        def tracked() -> Iterator[UnitOfWork]:
            if not readonly:
                self.open_writes += 1
            try:
                with self.inner(readonly) as uow:
                    yield uow
            finally:
                if not readonly:
                    self.open_writes -= 1

        return tracked()


@pytest.fixture
def tracked(world: World, monkeypatch: pytest.MonkeyPatch) -> Tracker:
    tracker = Tracker(world.factory)
    real = pw._scrypt  # pyright: ignore[reportPrivateUsage]
    ran: list[int] = []

    def checking(password: str, salt: bytes, params: pw.ScryptParams) -> bytes:
        assert tracker.open_writes == 0, "a password hash ran inside a write transaction"
        ran.append(1)
        return real(password, salt, params)

    monkeypatch.setattr(pw, "_scrypt", checking)
    tracker.ran = ran  # type: ignore[attr-defined]
    return tracker


def test_no_sign_in_path_hashes_inside_a_write_transaction(world: World, tracked: Tracker) -> None:
    world.create("alice")
    ran: list[int] = tracked.ran  # type: ignore[attr-defined]
    for name, password in (("alice", GOOD), ("alice", WRONG), ("ghost", WRONG)):
        try:
            sessions.sign_in(tracked, username=name, password=password, clock=world.clock)
        except InvalidCredentialsError:
            pass
    assert len(ran) >= 3


def test_a_rehash_is_computed_before_the_write_transaction(world: World, tracked: Tracker) -> None:
    previous = pw.configure(pw.ScryptParams(log2_n=3, r=1, p=1))
    try:
        world.create("alice")
    finally:
        pw.configure(previous)
    sessions.sign_in(tracked, username="alice", password=GOOD, clock=world.clock)
    [(stored,)] = world.rows("SELECT password_hash FROM auth_credential")
    assert stored.startswith("scrypt$4$")


def test_changing_a_password_hashes_outside_the_write_transaction(
    world: World, tracked: Tracker
) -> None:
    bob = world.create("bob")
    sessions.change_own_password(
        tracked, account_id=bob.account_id, current_password=GOOD, new_password=OTHER,
        clock=world.clock,
    )  # fmt: skip
    prepared = pw.prepare_password(OTHER + "x")
    with tracked() as uow:
        accounts.change_password(
            uow, account_id=bob.account_id, new_password=prepared, by="user:root"
        )


def test_a_flood_of_hashes_is_a_503_style_busy_error_and_does_not_block_other_writes(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.create("alice")
    monkeypatch.setattr(pw, "GATE_TIMEOUT_S", 0.05)
    taken = [pw._gate.acquire() for _ in range(pw.MAX_CONCURRENT_HASHES)]  # pyright: ignore[reportPrivateUsage]
    try:
        with pytest.raises(AuthBusyError):
            world.sign_in("alice", GOOD)
        world.create("carol", password=None)  # an unrelated write is not held up
    finally:
        for _ in taken:
            pw._gate.release()  # pyright: ignore[reportPrivateUsage]
    world.sign_in("alice", GOOD)


# --- item 6: NUL, lone surrogates and giant input ------------------------------------------

BAD_TEXT = ["a\x00b", "\ud800", "ali\udfffce", "x" * 100_000]


@pytest.mark.parametrize("bad", BAD_TEXT)
def test_unstorable_input_is_invalid_credentials_and_the_connection_still_works(
    world: World, bad: str
) -> None:
    world.create("alice")
    for username, password in ((bad, GOOD), ("alice", bad), (bad, bad)):
        with pytest.raises(InvalidCredentialsError) as raised:
            world.sign_in(username, password)
        assert str(raised.value) == "invalid username or password"
    assert world.rows("SELECT COUNT(*) FROM auth_attempt") == [(0,)]
    world.sign_in("alice", GOOD)  # the pooled connection is intact


@pytest.mark.parametrize("bad", BAD_TEXT)
def test_unstorable_input_costs_one_scrypt_like_any_failure(
    world: World, monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    calls: list[int] = []
    real = pw._scrypt  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(pw, "_scrypt", lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    with pytest.raises(InvalidCredentialsError):
        world.sign_in(bad, GOOD)
    assert len(calls) == 1


@pytest.mark.parametrize("bad", ["a\x00b", "\ud800", "x" * 5000])
def test_unstorable_passwords_and_usernames_are_refused_when_creating(
    world: World, bad: str
) -> None:
    with pytest.raises(WeakPasswordError):
        pw.prepare_password(bad)
    with pytest.raises(InvalidAccountError):
        world.create(bad)
    assert world.rows("SELECT COUNT(*) FROM cur_account") == [(0,)]


def test_usernames_are_never_stripped(world: World) -> None:
    world.create("bob")
    for variant in (" bob", "bob ", "bob\n", "\tbob"):
        with pytest.raises(InvalidCredentialsError):
            world.sign_in(variant, GOOD)


# --- item 2: the demo account only where TL_ENV allows it ----------------------------------


@pytest.mark.parametrize("env", ["prod", "production", "", "ci", "staging"])
def test_demo_does_not_authenticate_outside_dev_demo_and_test(
    world: World, monkeypatch: pytest.MonkeyPatch, env: str
) -> None:
    assert seed.seed_demo(world.factory, env="dev") is not None
    _, token = world.sign_in("demo", "demo")  # in dev it works
    monkeypatch.setenv("TL_ENV", env)
    with pytest.raises(InvalidCredentialsError):
        world.sign_in("demo", "demo")
    with pytest.raises(InvalidCredentialsError):  # a session made earlier stops too
        sessions.principal_for_bearer(world.factory, token)
    monkeypatch.setenv("TL_ENV", "demo")
    sessions.principal_for_bearer(world.factory, token)


def test_demo_in_prod_costs_one_scrypt_and_counts_as_a_failure(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed.seed_demo(world.factory, env="dev")
    monkeypatch.setenv("TL_ENV", "prod")
    for _ in range(5):
        with pytest.raises(InvalidCredentialsError):
            world.sign_in("demo", "demo")
    with pytest.raises(AccountLockedError):
        world.sign_in("demo", "demo")


def test_the_username_demo_cannot_be_created_by_hand_in_prod(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TL_ENV", "prod")
    with pytest.raises(InvalidAccountError, match="reserved"):
        world.create("demo")
    with pytest.raises(InvalidAccountError, match="reserved"):
        seed.bootstrap_admin(world.factory, username="demo", password=GOOD)


# --- item 1: the audit table ---------------------------------------------------------------


def events(world: World) -> list[tuple[str, ...]]:
    return [
        (str(a), str(b), str(c))
        for a, b, c in world.rows(
            "SELECT event, username_key, detail FROM auth_audit ORDER BY at, audit_id"
        )
    ]


def test_the_audit_records_sign_ins_failures_locks_sign_outs_and_tokens(world: World) -> None:
    world.admin("boss")
    bot = world.create("bot", kind="agent")
    _, token = world.sign_in("boss")
    sessions.sign_out(world.factory, token=token, clock=world.clock)
    for _ in range(5):
        with pytest.raises(InvalidCredentialsError):
            world.sign_in("ghost", WRONG)
    with world.factory() as uow:
        view, secret = accounts.issue_agent_token(
            uow, account_id=bot.account_id, label="t", expires_at=None, by="user:boss"
        )
        accounts.revoke_agent_token(uow, token_id=view.token_id, by="user:boss", reason=None)
        accounts.unlock(uow, username="ghost", by="svc:cli")
    names = [e[0] for e in events(world)]
    assert names == [
        "sign_in_ok",
        "sign_out",
        *["sign_in_failed"] * 5,
        "locked",
        "token_issued",
        "token_revoked",
        "unlocked",
    ]
    dump = " ".join(str(row) for row in world.rows("SELECT * FROM auth_audit"))
    for secret_text in (GOOD, WRONG, token, secret, token_hash(token), "scrypt"):
        assert secret_text not in dump


def test_audit_rows_older_than_90_days_are_pruned_and_hidden(world: World) -> None:
    with pytest.raises(InvalidCredentialsError):
        world.sign_in("ghost", WRONG)
    world.clock.advance(days=91)
    with pytest.raises(InvalidCredentialsError):
        world.sign_in("other", WRONG)
    assert [e[1] for e in events(world)] == ["other"]
    with world.factory(readonly=True) as uow:
        listed = audit.list_audit(uow.conn(), clock=world.clock)
    assert [e.username_key for e in listed] == ["other"]
    assert audit.RETENTION == timedelta(days=90)


def test_list_audit_filters_and_orders_newest_first(world: World) -> None:
    for name in ("one", "two", "three"):
        with pytest.raises(InvalidCredentialsError):
            world.sign_in(name, WRONG)
    with world.factory(readonly=True) as uow:
        everything = audit.list_audit(uow.conn(), clock=world.clock)
        only_two = audit.list_audit(uow.conn(), username_key="two", clock=world.clock)
        newest = audit.list_audit(uow.conn(), limit=1, clock=world.clock)
        with pytest.raises(ValueError):
            audit.list_audit(uow.conn(), limit=0)
    assert [e.username_key for e in everything] == ["three", "two", "one"]
    assert len(only_two) == 1 and newest[0].username_key == "three"


def test_the_audit_is_not_in_the_ledger_or_the_cur_tables(world: World) -> None:
    with pytest.raises(InvalidCredentialsError):
        world.sign_in("ghost", WRONG)
    assert world.events() == []
    assert world.rows("SELECT COUNT(*) FROM auth_audit") == [(1,)]
    with world.factory() as uow:
        with pytest.raises(ValueError):
            audit.record(uow.conn(), "nonsense", now=world.clock())


# --- item 8: the stored hash and token queries ---------------------------------------------


def test_a_session_row_for_an_agent_account_is_never_accepted(world: World) -> None:
    bot = world.create("bot", kind="agent")
    forged = "tls_" + "A" * 43
    with world.factory() as uow:
        uow.conn().execute(
            text(
                "INSERT INTO auth_session (token_hash, account_id, created_at, expires_at) "
                "VALUES (:h, :a, '2026-01-01T00:00:00.000000Z', '2999-01-01T00:00:00.000000Z')"
            ),
            {"h": token_hash(forged), "a": bot.account_id},
        )
    with pytest.raises(InvalidCredentialsError):
        sessions.principal_for_bearer(world.factory, forged)


def test_an_agent_token_row_for_a_person_account_is_never_accepted(world: World) -> None:
    bob = world.create("bob")
    forged = "tla_" + "B" * 43
    with world.factory() as uow:
        conn = uow.conn()
        conn.execute(
            text(
                "INSERT INTO cur_agent_token (token_id, account_id, label, revoked, issued_by, "
                "issued_at, last_seq) VALUES ('T1', :a, 'x', 0, 'u', '2026-01-01', 1)"
            ),
            {"a": bob.account_id},
        )
        conn.execute(
            text(
                "INSERT INTO auth_token_secret (token_hash, token_id, created_at) "
                "VALUES (:h, 'T1', '2026-01-01')"
            ),
            {"h": token_hash(forged)},
        )
    with pytest.raises(InvalidCredentialsError):
        sessions.principal_for_bearer(world.factory, forged)


def test_the_counter_table_has_an_index_on_the_last_failure(world: World) -> None:
    if str(world.db).startswith("postgresql"):
        rows = world.rows("SELECT indexname FROM pg_indexes WHERE tablename = 'auth_attempt'")
    else:
        rows = world.rows(
            "SELECT name FROM sqlite_master WHERE tbl_name = 'auth_attempt' AND type = 'index'"
        )
    assert any("last_failed_at" in str(r[0]) for r in rows)
