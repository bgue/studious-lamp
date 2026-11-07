"""T04g review F4: the follower moves its in-memory position only after the unit of work commits."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "dev" / "accept" / "P2-I2"))
import s4_world as sw  # noqa: E402  # pyright: ignore[reportMissingImports]
from awp_world import World  # noqa: E402
from tl_adapters.db import make_uow_factory  # noqa: E402
from tl_mod_awp.readiness.follow import CURSOR_NAME, Follower  # noqa: E402


class FailingCommit:
    """A unit-of-work factory whose ``fail_at``-th use raises after its body ran (a failed commit,
    so the unit of work rolls back)."""

    def __init__(self, factory: Any) -> None:
        self.factory = factory
        self.opened = 0
        self.fail_at = 0

    @contextmanager
    def __call__(self) -> Iterator[Any]:
        self.opened += 1
        mine = self.opened
        with self.factory() as uow:
            yield uow
            if mine == self.fail_at:
                raise RuntimeError("commit failed")


def stored(w: World) -> int | None:
    rows = w.rows("SELECT last_seq FROM rule_cursor WHERE name = :n", n=CURSOR_NAME)
    return int(rows[0]["last_seq"]) if rows else None


def test_a_failing_commit_leaves_the_stored_cursor_and_the_memory_position_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tl_adapters.sqlite.uow as sqlite_uow

    w = sw.build(tmp_path / "f4.db")
    monkeypatch.setattr(sqlite_uow, "default_registry", lambda: sw.registry())
    opener = FailingCommit(make_uow_factory(w.db, registry=sw.registry()))
    follower = Follower(opener, sw.checks())
    assert follower.poll() == 0  # starts at the head and writes the cursor
    start = stored(w)
    assert start is not None and follower._seq == start

    i = w.iwp()
    w.set_status(i, "Constraint check")
    w.call("uma", "AddIwpScope", iwp=i, items=w.items(["10.0"]))  # new outbox events

    opener.fail_at = opener.opened + 2  # use 1 reads the batch, use 2 handles the first event
    follower.poll()  # the failure is logged, not raised
    assert follower._seq == start
    assert stored(w) == start

    opener.fail_at = 0
    follower.poll()
    after = stored(w)
    assert after is not None and after > start and follower._seq == after
