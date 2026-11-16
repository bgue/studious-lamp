"""Fixtures of the QR module tests: the root conftest gives ``new_engine``, ``new_db`` and
``dialect``; ``world`` is a ledger with people, the public address set and the fake provider."""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Connection
from tl_adapters.db import DbTarget, create_schema
from tl_core.qr import registry
from tl_core.settings import resolver
from tl_mod_qr import service

sys.path.insert(0, str(Path(__file__).parent))

from qr_world import SECRET, FakeProvider, World, providers_of  # noqa: E402


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> FakeProvider:
    """The fake provider for ``quality.PunchItem``, installed in place of the entry points."""
    fake = FakeProvider()
    monkeypatch.setattr(
        registry, "load_scan_cards", lambda *a, **k: providers_of(fake, FakeProvider(SECRET))
    )
    return fake


@pytest.fixture
def bare(new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    """People, no public address (``api.public_base_url`` is a platform default only: the world
    holds the value the service reads for it)."""
    target = new_db()
    create_schema(target)
    made = World(target)
    made.people()
    real = resolver.value_of

    def value_of(conn: Connection, key: str, **kwargs: Any) -> Any:
        return made.public if key == service.BASE_URL else real(conn, key, **kwargs)

    monkeypatch.setattr(service, "value_of", value_of)
    yield made


@pytest.fixture
def world(bare: World, provider: FakeProvider) -> World:
    """People, the public address and the provider."""
    del provider
    bare.base()
    return bare
