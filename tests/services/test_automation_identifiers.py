"""Identifiers only the server sets for automation (P1-I7, FANOUT D2, ADR-0017).

A rule, an inbound endpoint, an action, an enricher and a thread dispatch stamp their own events
with a source, a correlation id and a link source. A client command that carries one is refused,
and the narrow ``system_source`` keyword that automation uses lifts that one link source and
nothing else.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Connection
from tl_adapters.db import DbTarget, create_schema, open_uow
from tl_core.integration.contract import (
    RESERVED_CORRELATION_PREFIXES as AUTOMATION_CORRELATION,
)
from tl_core.integration.contract import RESERVED_LINK_SOURCES
from tl_core.integration.contract import RESERVED_SOURCE_PREFIXES as AUTOMATION_SOURCE
from tl_core.ledger import Event
from tl_core.modules import ModuleSpec, use_modules
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_core.services.commands import Command, CreateRecord
from tl_core.services.errors import (
    ReservedIdentifierError,
    ReservedLinkSourceError,
    UnsupportedRecordTypeError,
)
from tl_core.services.links import (
    SYSTEM_LINK_SOURCES,
    AddLink,
    SuggestLink,
    handle_add_link,
    handle_suggest_link,
)
from tl_core.services.records import create_module_record, handle_create_record
from tl_core.services.reserved import (
    RESERVED_CORRELATION_PREFIXES,
    RESERVED_SOURCE_PREFIXES,
    refuse_reserved,
    refuse_reserved_fields,
)

FIXTURES = Path(__file__).resolve().parents[2] / "schema" / "fixtures"
SCOPE = "project:P123"
THING = "fake.Thing"
BASE: dict[str, Any] = {"actor": "user:u", "source": "test", "scope": SCOPE}


def test_the_reserved_sets_hold_every_prefix_of_the_contract() -> None:
    assert set(AUTOMATION_SOURCE) <= set(RESERVED_SOURCE_PREFIXES)
    assert set(AUTOMATION_CORRELATION) <= set(RESERVED_CORRELATION_PREFIXES)
    # the derivation pipeline's own are still there
    assert "compensation:" in RESERVED_SOURCE_PREFIXES
    assert "derive:" in RESERVED_CORRELATION_PREFIXES
    assert set(RESERVED_LINK_SOURCES) == set(SYSTEM_LINK_SOURCES)


@pytest.mark.parametrize("prefix", AUTOMATION_SOURCE)
def test_a_client_source_with_an_automation_prefix_is_refused(prefix: str) -> None:
    with pytest.raises(ReservedIdentifierError):
        refuse_reserved_fields(source=f"{prefix}x@1/d0")
    command = Command(actor="user:u", source=f"{prefix}x", scope=SCOPE)
    with pytest.raises(ReservedIdentifierError):
        refuse_reserved(command)


@pytest.mark.parametrize("prefix", AUTOMATION_CORRELATION)
def test_a_client_correlation_or_causation_id_with_an_automation_prefix_is_refused(
    prefix: str,
) -> None:
    with pytest.raises(ReservedIdentifierError):
        refuse_reserved_fields(correlation_id=f"{prefix}01J9Z6Q4W3X2Y1V0T9S8R7Q6PB")
    with pytest.raises(ReservedIdentifierError):
        refuse_reserved_fields(causation_id=f"{prefix}01J9Z6Q4W3X2Y1V0T9S8R7Q6PB")


@pytest.mark.parametrize("source", ["api", "tui", "cli", "mcp:triage", "agent_x", "review"])
def test_ordinary_sources_and_ids_still_pass(source: str) -> None:
    refuse_reserved_fields(source=source, correlation_id="01J9Z6Q4W3X2Y1V0T9S8R7Q6PB")
    refuse_reserved_fields(causation_id="01J9Z6Q4W3X2Y1V0T9S8R7Q6PB")


# --- the narrow link-source keyword -------------------------------------------------------------


class FakeProjector:
    name = "fake_thing_auto"
    handles = frozenset({"Thing.Defined"})

    def ddl(self, dialect: str) -> list[str]:
        return []

    def apply(self, conn: Connection, event: Event) -> None:
        return None

    def reset(self, conn: Connection) -> None:
        return None


def closed_spec() -> ModuleSpec:
    """A module whose Thing allows no generic command at all."""
    return ModuleSpec(
        name="fake",
        record_types=frozenset({THING}),
        projectors=lambda: [FakeProjector()],
        generic_commands={THING: frozenset()},
    )


@pytest.fixture(autouse=True)
def fixture_schemas() -> Iterator[None]:
    with use_provider(DirectorySchemaProvider(FIXTURES)):
        yield


@pytest.fixture
def db(new_db: Callable[[], DbTarget]) -> DbTarget:
    target = new_db()
    create_schema(target)
    return target


def plain(db: DbTarget, key: str) -> str:
    with open_uow(db) as uow:
        made = handle_create_record(
            uow, CreateRecord(**BASE, record_type="core.Record", title=key, key=key)
        )
    return made.stream_id


def test_system_source_lifts_that_one_link_source_only(db: DbTarget) -> None:
    one, two, three = plain(db, "A-1"), plain(db, "A-2"), plain(db, "A-3")
    with open_uow(db) as uow, pytest.raises(ReservedLinkSourceError):
        handle_add_link(uow, AddLink(**BASE, from_id=one, to_id=two, link_source="rule"))
    with open_uow(db) as uow, pytest.raises(ReservedLinkSourceError):
        handle_add_link(
            uow,
            AddLink(**BASE, from_id=one, to_id=two, link_source="enricher"),
            system_source="rule",
        )
    with open_uow(db) as uow:
        made = handle_add_link(
            uow,
            AddLink(**BASE, from_id=one, to_id=two, link_source="rule"),
            system_source="rule",
        )
    assert made.events[0].payload["source"] == "rule"
    with open_uow(db) as uow:
        suggested = handle_suggest_link(
            uow,
            SuggestLink(**BASE, from_id=one, to_id=three, link_source="enricher"),
            system_source="enricher",
        )
    assert suggested.events[0].payload["source"] == "enricher"


def test_system_source_keeps_the_module_allow_list(db: DbTarget) -> None:
    """The narrow keyword is not ``by_module``: a closed module record stays closed."""
    with use_modules([closed_spec()]):
        with open_uow(db) as uow:
            closed = create_module_record(
                uow, Command(**BASE), record_type=THING, title="T", key="T-1"
            ).stream_id
        other = plain(db, "B-1")
        with open_uow(db) as uow, pytest.raises(UnsupportedRecordTypeError):
            handle_add_link(
                uow,
                AddLink(**BASE, from_id=closed, to_id=other, link_source="rule"),
                system_source="rule",
            )
        with open_uow(db) as uow:  # the module's own path is unchanged
            made = handle_add_link(
                uow,
                AddLink(**BASE, from_id=closed, to_id=other, link_source="rule"),
                by_module=True,
            )
        assert made.events[0].event_type == "Link.Added"
