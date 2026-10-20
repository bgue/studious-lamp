"""The embedded client's RFI, Commercial and evidence reads, on a real ledger (P1-I6).

The reads are the module's own functions behind the viewer of the person: a plain person reads the
RFIs and the trail of an RFI, and finds the Commercial register empty (the items are restricted).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from tl_adapters.db import as_target
from tl_adapters.sqlite.factory import SqliteUowFactory
from tl_adapters.sqlite.uow import create_schema
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_mod_correspondence.errors import EvidenceDateError, ItemNotFoundError
from tl_mod_correspondence.testing import CorrWorld, frozen_today
from tl_tui.client import ClientInterface
from tl_tui.embedded import EmbeddedClient

FIXTURES = Path(__file__).resolve().parents[3] / "schema" / "fixtures"
P = "P123"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[ClientInterface]:
    path = tmp_path / "tl.db"
    create_schema(path)
    with use_provider(DirectorySchemaProvider(FIXTURES)):
        world = CorrWorld(as_target(str(path)), tmp_path / "objects")
        with frozen_today("2026-10-19"):
            world.forge_technical("P123-RFI-0001", state="Answered")
            world.forge_commercial("P123-EW-0001", state="Awaiting assessment")
        yield EmbeddedClient(SqliteUowFactory(path), actor="user:kim")


def test_a_plain_person_reads_the_rfi_log_and_one_rfi(client: ClientInterface) -> None:
    log = client.list_rfis(P)
    assert [x.number for x in log.lines] == ["P123-RFI-0001"] and log.total == 1
    assert log.lines[0].state == "Answered"
    view = client.get_rfi(P, "P123-RFI-0001")
    assert view.question and view.answered_on is not None
    with pytest.raises(ItemNotFoundError):
        client.get_rfi(P, "P123-RFI-0099")
    assert client.list_rfis(P, only_open=True).lines == []  # an answered RFI is not open


def test_the_commercial_register_is_empty_and_a_notice_is_not_found_for_a_plain_person(
    client: ClientInterface,
) -> None:
    assert client.list_commercial(P).lines == []
    with pytest.raises(ItemNotFoundError):
        client.get_commercial(P, "P123-EW-0001")


def test_the_evidence_trail_follows_the_day_asked_for(client: ClientInterface) -> None:
    trail = client.get_evidence_trail(P, "P123-RFI-0001", as_of=date.today())
    assert [n.key for n in trail.nodes] == ["P123-RFI-0001"]
    with pytest.raises(ItemNotFoundError):  # the commercial item is not readable
        client.get_evidence_trail(P, "P123-EW-0001")
    with pytest.raises(EvidenceDateError):
        client.get_evidence_trail(P, "P123-RFI-0001", as_of=date(2001, 1, 1))
