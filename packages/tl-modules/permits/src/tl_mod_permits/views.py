"""Read views of permits (P2-PTW T01 fills the bodies; the interface is fixed here).

Every read takes keyword-only ``viewer=`` (default ``confidentiality.LOWEST``, never widened) and
applies the hidden filter before LIMIT and before counting: a hidden record is absent from lists,
its detail is ``None``, counts never include it. Nothing here reads the clock: ``now`` is a
parameter, and an Active permit whose ``valid_until`` has passed is shown as Lapsed through
``rules.effective_state``. Nothing is written and no access word is checked here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from sqlalchemy import Connection
from tl_core import confidentiality

#: The most rows one list returns.
MAX_LIMIT: Final = 500
#: The states a permit is shown in (Lapsed in place of Active when its validity has passed).
SHOWN_STATES: Final = (
    "Requested",
    "Approved",
    "Active",
    "Lapsed",
    "Suspended",
    "Handed back",
    "Closed",
    "Rejected",
    "Cancelled",
)
#: The states of a permit that is live: on the board.
LIVE_STATES: Final = ("Lapsed", "Suspended", "Active")
EXPORT_FORMATS: Final = ("csv", "jsonl")
#: The columns of an export, in order (the register of design section 8).
EXPORT_COLUMNS: Final = (
    "number",
    "type",
    "state",
    "area",
    "holder",
    "issued",
    "valid_until",
    "revalidations",
    "closed",
)


@dataclass(frozen=True)
class PermitRow:
    id: str  # the record id, for commands; no screen or line prints it
    key: str
    subject: str
    permit_type: str
    state: str  # as shown: Lapsed in place of Active
    area: str | None
    holder: str | None
    issued_at: datetime | None
    valid_until: datetime | None
    revalidation_count: int
    closed_by: str | None
    for_key: str | None  # the key of the record the work is for


@dataclass(frozen=True)
class PermitDetail:
    row: PermitRow
    description: str | None
    location_text: str | None
    requested_by: str | None
    needed_from: str | None
    needed_until: str | None
    approved_by: str | None
    issued_by: str | None
    precautions: list[str]  # the ticked precaution ids
    suspend_reason: str | None
    handback_note: str | None
    reject_reason: str | None
    cancel_reason: str | None
    version: int


@dataclass(frozen=True)
class PermitPage:
    rows: list[PermitRow]
    total: int


@dataclass(frozen=True)
class BoardArea:
    area: str | None
    rows: list[PermitRow]  # Lapsed and Suspended first, then by key


@dataclass(frozen=True)
class PermitBoard:
    areas: list[BoardArea]  # by area name, no area last
    counts: dict[str, int]  # live permits shown, by shown state


@dataclass(frozen=True)
class PermitRef:
    """A permit as readiness and the IWP card read it: the state is the stored one."""

    id: str
    key: str
    permit_type: str
    state: str
    valid_until: datetime | None


def permit_list(
    conn: Connection,
    scope: str,
    *,
    now: datetime,
    state: str | None = None,
    permit_type: str | None = None,
    area: str | None = None,
    holder: str | None = None,
    limit: int = 100,
    offset: int = 0,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> PermitPage:
    """Permits of ``scope`` by key; ``state`` is a shown state (``Lapsed`` and ``Active`` split
    an Active permit at ``now``); ``total`` counts the rows the filters and the viewer leave."""
    raise NotImplementedError


def permit_detail(
    conn: Connection,
    scope: str,
    number: str,
    *,
    now: datetime,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> PermitDetail | None:
    """The permit with key ``number``; ``None`` when it is hidden, absent or in another scope."""
    raise NotImplementedError


def permit_counts(
    conn: Connection,
    scope: str,
    *,
    now: datetime,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> dict[str, int]:
    """Permits of ``scope`` by shown state (every state of ``SHOWN_STATES``, zero included),
    after the hidden filter."""
    raise NotImplementedError


def permit_board(
    conn: Connection,
    scope: str,
    area: str | None = None,
    *,
    now: datetime,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> PermitBoard:
    """The live permits (Lapsed, Suspended, Active) grouped by area, counts after the hidden
    filter; ``area`` narrows to one."""
    raise NotImplementedError


def permits_for(
    conn: Connection,
    record_id: str,
    *,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> list[PermitRef]:
    """The permits whose ``for_record_id`` is ``record_id`` (by key); none when the record is
    hidden from the viewer."""
    raise NotImplementedError


def export_rows(rows: Sequence[PermitRow], fmt: str) -> str:
    """``rows`` as ``csv`` (a header of ``EXPORT_COLUMNS`` then one line per row, ``\\n`` ends,
    times as ISO text) or ``jsonl`` (one JSON object per row with the same keys); another format
    is a ``ValueError``."""
    raise NotImplementedError
