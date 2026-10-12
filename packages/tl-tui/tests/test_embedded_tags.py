"""`FakeClient` tag reads answer like the embedded client (P1-I1): numbers, filters, ended tags."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fakes import FakeClient
from tl_adapters.db import open_uow
from tl_adapters.sqlite.factory import SqliteUowFactory
from tl_adapters.sqlite.uow import create_schema
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_mod_engineering.errors import TagNotFoundError
from tl_mod_engineering.handlers.tags import (
    CreateTag,
    RenameTag,
    handle_create_tag,
    handle_rename_tag,
)
from tl_mod_engineering.testing import seed_registry
from tl_mod_engineering.views import TagView
from tl_tui.client import ClientInterface
from tl_tui.embedded import EmbeddedClient

FIXTURES = Path(__file__).resolve().parents[3] / "schema" / "fixtures"
BASE: dict[str, Any] = {"actor": "user:kim", "source": "test", "scope": "project:P123"}


def shape(view: TagView) -> tuple[Any, ...]:
    return (
        view.number,
        view.class_code,
        view.status,
        view.conformance,
        view.number_status,
        view.area,
        view.mnemonic,
        view.sequence,
        view.segments,
    )


@pytest.fixture
def both(tmp_path: Path) -> Iterator[tuple[ClientInterface, ClientInterface]]:
    """An embedded client over a ledger with five tags, and a fake holding the same five."""
    with use_provider(DirectorySchemaProvider(FIXTURES)):
        path = tmp_path / "tl.db"
        create_schema(path)
        seed_registry(path)
        with open_uow(path) as uow:
            first = handle_create_tag(
                uow, CreateTag(**BASE, number="47-FV-1001", class_code="ControlValve")
            )
            handle_create_tag(uow, CreateTag(**BASE, number="47-FV-1002", class_code="ManualValve"))
            handle_create_tag(uow, CreateTag(**BASE, number="10-PT-0001"))
            handle_create_tag(uow, CreateTag(**BASE, number="LEGACY-1", pattern_policy="record"))
        with open_uow(path) as uow:
            handle_rename_tag(
                uow,
                RenameTag(**BASE, stream_id=first.stream_id, new_number="47-FV-1009", reason="r"),
            )
        factory = SqliteUowFactory(path)
        embedded = EmbeddedClient(factory, actor="user:kim")
        fake = FakeClient()
        for number, cls, status, conformance, nstatus in (
            ("47-FV-1001", "ControlValve", "Superseded", "nonconformant", "ok"),
            ("47-FV-1009", "ControlValve", None, "nonconformant", "ok"),
            ("47-FV-1002", "ManualValve", None, "nonconformant", "ok"),
            ("10-PT-0001", None, None, "ok", "ok"),
            ("LEGACY-1", None, None, "ok", "violation"),
        ):
            fake.add_tag(
                "P123",
                number,
                class_code=cls,
                status=status,
                conformance=conformance,
                number_status=nstatus,
            )
        try:
            yield embedded, fake
        finally:
            factory.dispose()


READS = [
    ("all in service", lambda c: c.list_tags("P123")),
    ("with the ended ones", lambda c: c.list_tags("P123", include_ended=True)),
    ("by class", lambda c: c.list_tags("P123", class_code="ControlValve")),
    ("by a status nothing has", lambda c: c.list_tags("P123", status="Design")),
    ("an ended status asked for by name", lambda c: c.list_tags("P123", status="Superseded")),
    ("violations", lambda c: c.list_tags("P123", number_status="violation")),
    ("a limit", lambda c: c.list_tags("P123", limit=2)),
    ("another project", lambda c: c.list_tags("OTHER")),
]


@pytest.mark.parametrize(("name", "read"), READS, ids=[n for n, _ in READS])
def test_a_listing_is_the_same_on_both(
    both: tuple[ClientInterface, ClientInterface], name: str, read: Any
) -> None:
    embedded, fake = both
    assert [shape(v) for v in read(fake)] == [shape(v) for v in read(embedded)], name
    assert all(v.issues == [] for v in read(embedded))


def test_the_tags_come_by_number_and_the_ended_one_only_on_request(
    both: tuple[ClientInterface, ClientInterface],
) -> None:
    embedded, _ = both
    assert [v.number for v in embedded.list_tags("P123")] == [
        "10-PT-0001",
        "47-FV-1002",
        "47-FV-1009",
        "LEGACY-1",
    ]
    assert "47-FV-1001" in [v.number for v in embedded.list_tags("P123", include_ended=True)]


def test_one_tag_comes_with_its_issues_and_an_unknown_one_is_the_modules_error(
    both: tuple[ClientInterface, ClientInterface],
) -> None:
    embedded, fake = both
    tag = embedded.get_tag("P123", "47-FV-1009")
    assert tag.segments == {"area": "47", "mnemonic": "FV", "seq": "1009"}
    assert tag.conformance == "nonconformant" and tag.issues
    assert any("valve_data" in issue.path for issue in tag.issues)
    for client in (embedded, fake):
        with pytest.raises(TagNotFoundError, match="47-FV-9999"):
            client.get_tag("P123", "47-FV-9999")
