"""The resolver: one exit for every miss, the lookup first, never a write."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from typing import Any

import pytest
from qr_world import NOW, FakeProvider, World
from sqlalchemy import Connection, event, text
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.qr import registry
from tl_core.qr.types import ScanCard
from tl_core.util import utcnow
from tl_mod_qr import service
from tl_mod_qr.codes import code_hash, grouped, new_code
from tl_mod_qr.resolve import resolve

USER = cf.Viewer(actor="user:uma", level=0, account="user:uma")
NO_WORD = cf.Viewer(actor="agent:bot", level=0, account="")  # an agent with no role holds no word
SKIPPED = ("BEGIN", "COMMIT", "ROLLBACK")


@contextmanager
def counted(conn: Connection) -> Iterator[list[str]]:
    """The SQL statements run on ``conn``'s engine in the block (transaction control ignored)."""
    seen: list[str] = []

    def listener(_c: object, _cur: object, statement: str, *_a: object) -> None:
        if not statement.lstrip().upper().startswith(SKIPPED):
            seen.append(statement)

    event.listen(conn.engine, "before_cursor_execute", listener)
    try:
        yield seen
    finally:
        event.remove(conn.engine, "before_cursor_execute", listener)


def resolved(world: World, code: str, viewer: cf.Viewer = USER) -> ScanCard | None:
    with open_uow(world.db, readonly=True) as uow:
        return resolve(uow.conn(), code, viewer, NOW)


def code_for(world: World, **more: Any) -> tuple[str, str]:
    target = world.record()
    made = world.serve(service.issue, "uma", "IssueScanCode", target_id=target, **more)
    return made.code, made.result.stream_id


def test_a_live_code_resolves_to_the_card_typed_or_scanned(world: World) -> None:
    code, _ = code_for(world)
    card = resolved(world, code)
    assert card is not None and card.title == "Fake card"
    assert resolved(world, grouped(code).lower()) == card
    assert resolved(world, code, cf.LOWEST) is None  # no actor holds the view word


def test_every_miss_is_the_same_value(world: World, provider: FakeProvider) -> None:
    live, _ = code_for(world)
    revoked, revoked_id = code_for(world)
    world.call("ada", "RevokeScanCode", code_id=revoked_id, reason="lost")
    expired, expired_id = code_for(world)
    with open_uow(world.db) as uow:
        uow.conn().execute(
            text("UPDATE cur_qr_scan_code SET expires_on = :d WHERE id = :i"),
            {"d": (utcnow().date() - timedelta(days=2)).isoformat(), "i": expired_id},
        )
    secret = world.hidden_record()
    hidden = world.serve(service.issue, "dora", "IssueScanCode", target_id=secret).code
    misses = [
        resolved(world, "not a code"),
        resolved(world, ""),
        resolved(world, new_code()),
        resolved(world, revoked),
        resolved(world, expired),
        resolved(world, hidden),
        resolved(world, live, NO_WORD),
    ]
    assert misses == [None] * len(misses)
    assert resolved(world, live) is not None
    assert provider.calls >= 1


def test_a_hidden_target_is_a_miss_for_the_low_reader_and_a_hit_for_the_cleared(
    world: World,
) -> None:
    secret = world.hidden_record()
    code = world.serve(service.issue, "dora", "IssueScanCode", target_id=secret).code
    assert resolved(world, code, USER) is None
    cleared = cf.Viewer(actor="user:dora", level=1, account="user:dora")
    assert resolved(world, code, cleared) is not None


def test_no_provider_for_the_type_is_a_miss(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    code, _ = code_for(world)
    monkeypatch.setattr(registry, "load_scan_cards", lambda *a, **k: {})
    assert resolved(world, code) is None


def test_a_provider_that_raises_is_a_miss_and_writes_nothing(
    world: World, provider: FakeProvider
) -> None:
    code, _ = code_for(world)
    provider.raises = True
    before = world.rows("SELECT COUNT(*) AS n FROM events")
    assert resolved(world, code) is None
    assert world.rows("SELECT COUNT(*) AS n FROM events") == before


def test_a_missing_view_word_is_a_miss_before_the_provider_is_asked(
    world: World, provider: FakeProvider
) -> None:
    code, _ = code_for(world)
    provider.calls = 0
    assert resolved(world, code, NO_WORD) is None
    assert provider.calls == 0


def test_a_malformed_code_runs_no_statement(world: World) -> None:
    with open_uow(world.db, readonly=True) as uow:
        with counted(uow.conn()) as seen:
            for text_ in ("", "short", "I" * 16, "0O1I" * 4, "\x00" * 16):
                assert resolve(uow.conn(), text_, USER, NOW) is None
    assert seen == []


def test_the_first_statement_of_a_hit_is_the_hash_lookup(world: World) -> None:
    code, _ = code_for(world)
    with open_uow(world.db, readonly=True) as uow:
        with counted(uow.conn()) as seen:
            assert resolve(uow.conn(), code, USER, NOW) is not None
    assert len(seen) > 1
    assert "code_hash" in seen[0] and "cur_qr_scan_code" in seen[0]
    # and the lookup of an unknown code is the only statement it runs
    with open_uow(world.db, readonly=True) as uow:
        with counted(uow.conn()) as seen:
            assert resolve(uow.conn(), new_code(), USER, NOW) is None
    assert len(seen) == 1 and "code_hash" in seen[0]
    assert code_hash(code) != code  # the lookup binds the hash, never the code


def test_the_resolver_never_writes(world: World) -> None:
    code, _ = code_for(world)
    with open_uow(world.db, readonly=True) as uow:
        with counted(uow.conn()) as seen:
            resolve(uow.conn(), code, USER, NOW)
    assert not [s for s in seen if s.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))]
