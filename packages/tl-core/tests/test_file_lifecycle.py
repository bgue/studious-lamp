"""The file quarantine lifecycle table (P0-I4-B)."""

from __future__ import annotations

import pytest
from tl_core.files.lifecycle import FILE_EVENT_TYPES, FILE_STATUSES, FileStatus, next_file_status
from tl_core.services.errors import InvalidFileTransitionError

ALLOWED: dict[tuple[FileStatus | None, str], FileStatus] = {
    (None, "File.Uploaded"): "quarantined",
    ("quarantined", "File.Processed"): "available",
    ("quarantined", "File.Rejected"): "rejected",
    ("available", "File.Rejected"): "rejected",
}


@pytest.mark.parametrize("current", [None, *FILE_STATUSES])
@pytest.mark.parametrize("event_type", sorted(FILE_EVENT_TYPES))
def test_every_pair_is_allowed_exactly_when_the_table_says(
    current: FileStatus | None, event_type: str
) -> None:
    expected = ALLOWED.get((current, event_type))
    if expected is None:
        with pytest.raises(InvalidFileTransitionError):
            next_file_status(current, event_type)
    else:
        assert next_file_status(current, event_type) == expected


def test_rejected_is_terminal() -> None:
    for event_type in FILE_EVENT_TYPES:
        with pytest.raises(InvalidFileTransitionError):
            next_file_status("rejected", event_type)


def test_a_non_file_event_is_refused() -> None:
    with pytest.raises(InvalidFileTransitionError, match="not a file event"):
        next_file_status(None, "Record.Created")
