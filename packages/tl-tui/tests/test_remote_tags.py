"""The tag reads over a real API server on loopback (P1-I1): same answers as the embedded client."""

from __future__ import annotations

from typing import Any

import pytest
from harness import Harness
from remote_support import LIVE_TIMEOUT_S, restartable
from tl_adapters.db import open_uow
from tl_mod_engineering.errors import TagNotFoundError
from tl_mod_engineering.handlers.tags import (
    CreateTag,
    RecordTag,
    RenameTag,
    handle_create_tag,
    handle_record_tag,
    handle_rename_tag,
)
from tl_mod_engineering.testing import seed_registry
from tl_tui.remote import RemoteClient

BASE: dict[str, Any] = {"actor": "user:kim", "source": "test", "scope": "project:P123"}


@pytest.fixture
def seeded(harness: Harness) -> Harness:
    seed_registry(harness.db)
    with open_uow(harness.db) as uow:
        first = handle_create_tag(
            uow, CreateTag(**BASE, number="47-FV-1001", class_code="ControlValve")
        )
        handle_create_tag(uow, CreateTag(**BASE, number="10-PT-0001"))
        handle_record_tag(uow, RecordTag(**BASE, number="LEGACY-1"), origin="import")
    with open_uow(harness.db) as uow:
        handle_rename_tag(
            uow, RenameTag(**BASE, stream_id=first.stream_id, new_number="47-FV-1009", reason="r")
        )
    return harness


def test_the_two_calls_round_trip_with_the_modules_error_class(seeded: Harness) -> None:
    with restartable(seeded) as server:
        client = RemoteClient.connect(server.base_url, server.token, timeout=LIVE_TIMEOUT_S)
        listed = client.list_tags("P123")
        assert [v.number for v in listed] == ["10-PT-0001", "47-FV-1009", "LEGACY-1"]
        assert all(v.issues == [] for v in listed)
        assert [v.number for v in client.list_tags("P123", include_ended=True)][:2] == [
            "10-PT-0001",
            "47-FV-1001",
        ]
        assert [v.number for v in client.list_tags("P123", class_code="ControlValve")] == [
            "47-FV-1009"
        ]
        assert [v.number for v in client.list_tags("P123", number_status="violation")] == [
            "LEGACY-1"
        ]
        assert [v.number for v in client.list_tags("P123", limit=1)] == ["10-PT-0001"]
        tag = client.get_tag("P123", "47-FV-1009")
        assert tag.segments == {"area": "47", "mnemonic": "FV", "seq": "1009"}
        assert tag.conformance == "nonconformant"
        assert any("valve_data" in issue.path for issue in tag.issues)
        with pytest.raises(TagNotFoundError, match="47-FV-9999"):
            client.get_tag("P123", "47-FV-9999")
        client.close()


def test_the_code_lists_round_trip_as_the_embedded_client_reads_them(seeded: Harness) -> None:
    with restartable(seeded) as server:
        client = RemoteClient.connect(server.base_url, server.token, timeout=LIVE_TIMEOUT_S)
        assert client.list_code_lists("project:P123") == {"Area": {"10": "10", "47": "47"}}
        assert client.list_code_lists("company") == {"Area": {"10": "10", "47": "47"}}
