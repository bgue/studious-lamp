"""The file quarantine lifecycle: which event may happen in which status (brief 20.2).

The single statement of the rules. The upload service calls ``next_file_status`` to refuse an
impossible event before anything is appended; the projector calls it while applying an event.
Rejected is terminal, and so is a file once it left quarantine except for a later rejection (a
rescan finds malware in a file that was released).

======================  ==============================  ===============
Event                   Allowed in                      New status
======================  ==============================  ===============
``File.Uploaded``       (no file yet)                   ``quarantined``
``File.Processed``      ``quarantined``                 ``available``
``File.Rejected``       ``quarantined``, ``available``  ``rejected``
======================  ==============================  ===============
"""

from __future__ import annotations

from typing import Literal, get_args

from tl_core.services.errors import InvalidFileTransitionError

FileStatus = Literal["quarantined", "available", "rejected"]
FILE_STATUSES: tuple[FileStatus, ...] = get_args(FileStatus)

FILE_STREAM_TYPE = "core.File"
FILE_EVENT_TYPES: frozenset[str] = frozenset({"File.Uploaded", "File.Processed", "File.Rejected"})

_ALLOWED: dict[str, tuple[frozenset[FileStatus | None], FileStatus]] = {
    "File.Uploaded": (frozenset({None}), "quarantined"),
    "File.Processed": (frozenset({"quarantined"}), "available"),
    "File.Rejected": (frozenset({"quarantined", "available"}), "rejected"),
}


def next_file_status(current: FileStatus | None, event_type: str) -> FileStatus:
    """The status after ``event_type`` happens to a file in status ``current``.

    ``current`` is ``None`` before the file exists. Raises ``InvalidFileTransitionError`` when the
    event is not allowed in that status, or when ``event_type`` is not a file event.
    """
    rule = _ALLOWED.get(event_type)
    if rule is None:
        raise InvalidFileTransitionError(f"{event_type!r} is not a file event")
    allowed, new_status = rule
    if current not in allowed:
        where = "a new file" if current is None else f"a {current} file"
        raise InvalidFileTransitionError(f"{event_type} is not allowed for {where}")
    return new_status
