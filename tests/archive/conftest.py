"""Fixtures for the archive tests: an in-memory write-once store, crash injection, a seeded ledger.

Helpers are fixtures because pytest runs in importlib mode (a test cannot import a sibling file).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine
from tl_adapters.sqlite.engine import make_engine
from tl_adapters.sqlite.ledger import SqliteLedger
from tl_core.archive import ArchiveExistsError, Ed25519Signer, generate_signer
from tl_core.ledger import NewEvent


class Crash(Exception):
    """Raised by :class:`MemoryStore` to simulate the process dying between two files."""


class MemoryStore:
    """A write-once ArchiveStore in a dict; after ``fail_after`` puts, ``put_bytes`` raises."""

    def __init__(self, fail_after: int | None = None) -> None:
        self.files: dict[str, bytes] = {}
        self.fail_after = fail_after
        self.puts: list[str] = []

    def put_bytes(self, key: str, data: bytes) -> None:
        if key in self.files:
            raise ArchiveExistsError(key)
        if self.fail_after is not None and len(self.puts) >= self.fail_after:
            raise Crash(key)
        self.files[key] = data
        self.puts.append(key)

    def get_bytes(self, key: str) -> bytes:
        return self.files[key]

    def exists(self, key: str) -> bool:
        return key in self.files

    def list_keys(self, prefix: str) -> list[str]:
        return sorted(k for k in self.files if k.startswith(prefix))

    def copy(self) -> MemoryStore:
        clone = MemoryStore()
        clone.files = dict(self.files)
        return clone

    def overwrite(self, key: str, data: bytes) -> None:
        """Tamper with a copy: replace bytes (the real store refuses this)."""
        self.files[key] = data

    def remove(self, key: str) -> None:
        del self.files[key]


@pytest.fixture
def signer() -> Ed25519Signer:
    return generate_signer()


@pytest.fixture
def memory_store() -> Callable[..., MemoryStore]:
    return MemoryStore


SCOPES = ("company", "project:P1", "project:P2")


class Ledgerbox:
    """A SQLite ledger file that tests append plain events to."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.engine: Engine = make_engine(path)
        self.ledger = SqliteLedger(self.engine)
        self.ledger.create_schema()
        self.count = 0

    def add(self, n: int, *, tag: str = "x") -> None:
        """Append ``n`` events, one stream each, rotating through the three scopes."""
        for _ in range(n):
            self.count += 1
            scope = SCOPES[self.count % len(SCOPES)]
            self.ledger.append(
                stream_id=f"{tag}-{self.count}",
                stream_type="test.Thing",
                scope=scope,
                expected_version=0,
                events=[
                    NewEvent(
                        event_type="Thing.Created",
                        payload={"n": self.count, "tag": tag, "text": "café"},
                    )
                ],
                actor="user:u-1",
                source="test",
                correlation_id=f"c-{self.count}",
            )


@pytest.fixture
def make_box(tmp_path: Path) -> Iterator[Callable[[str], Ledgerbox]]:
    boxes: list[Ledgerbox] = []

    def make(name: str = "a") -> Ledgerbox:
        box = Ledgerbox(tmp_path / f"{name}.db")
        boxes.append(box)
        return box

    yield make
    for box in boxes:
        box.engine.dispose()
