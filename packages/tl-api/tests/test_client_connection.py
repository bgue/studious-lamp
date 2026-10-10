"""The real ApiClient on one pooled connection to a live server: errors do not break it."""

from __future__ import annotations

import pytest
from harness import SCOPE, Harness
from tl_core.ledger import ConcurrencyError
from tl_core.services.commands import CreateRecord, UpdateRecord
from tl_core.services.errors import DuplicateKeyError, RecordNotFoundError


def test_twenty_sequential_not_found_errors_leave_the_connection_usable(harness: Harness) -> None:
    """The review's HIGH finding, at the client level: no ApiUnavailableError, no ReadError."""
    with harness.live_api() as api:
        for n in range(20):
            with pytest.raises(RecordNotFoundError):
                api.links_of(f"01NOSUCHRECORD{n:02d}")
        assert api.get_record(SCOPE, "NOPE") is None  # 404 handled inside the client
        assert api.list_records(SCOPE) == []  # and the same connection still serves reads


def test_mixed_error_kinds_in_a_row_all_arrive_as_their_exception(harness: Harness) -> None:
    made = harness.create_record("K-1")
    cmd = CreateRecord(
        actor="u", source="tui", scope=SCOPE, record_type="core.Record", title="T", key="K-1"
    )
    stale = UpdateRecord(
        actor="u",
        source="tui",
        scope=SCOPE,
        stream_id=made.stream_id,
        expected_version=9,
        changes={"title": "x"},
    )
    with harness.live_api() as api:
        for _ in range(8):
            with pytest.raises(DuplicateKeyError):
                api.create_record(cmd)
            with pytest.raises(ConcurrencyError):
                api.update_record(stale)
            with pytest.raises(RecordNotFoundError):
                api.trace("01NOSUCHRECORD")
        assert api.get_record(SCOPE, "K-1") is not None
