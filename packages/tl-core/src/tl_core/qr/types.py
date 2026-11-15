"""Scan-card contract for the QR work face (ADR-0030; `docs/build-spec/specs/qr-workface.md`).

Frozen once merged: change only by orchestrator decision.

A scan of a printed QR opens a *status card* that the target record's own module supplies.
Providers are plugins found through the entry-point group SCAN_CARD_ENTRY_POINT; each entry point
names a zero-argument callable that returns an object satisfying ScanCardProvider, one per record
type. The qr module never imports the module that ships a provider.

A provider is a pure read: it gets a connection, never writes, never raises for a bad or hidden
record (it answers None), answers None for a record the viewer cannot see, and never opens the
network. Every list and text it returns stays inside the bounds below; ScanCard refuses anything
past them.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Connection

from tl_core.confidentiality import Viewer

SCAN_CARD_ENTRY_POINT = "throughline.scan_cards"

MAX_LINES = 8
MAX_LABEL_CHARS = 24
MAX_VALUE_CHARS = 80
MAX_BANNER_CHARS = 40
MAX_TITLE_CHARS = 120
MAX_PROVIDERS = 32

#: Where a scan lands, and the only return address a sign-in bounce may carry.
SCAN_PATH_PREFIX = "/web/q/"
SCAN_NEXT_PATTERN = r"^/web/q/[A-Z0-9]{16}$"

#: The web area every card link stays inside.
WEB_PREFIX = "/web/"

Tone = Literal["go", "caution", "stop", "neutral"]

_SCAN_NEXT = re.compile(SCAN_NEXT_PATTERN)


def is_scan_next(path: str) -> bool:
    """True when ``path`` is exactly a scan path (the only legal sign-in return address)."""
    return _SCAN_NEXT.fullmatch(path) is not None


class ScanLine(BaseModel):
    """One label and value of a card."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(max_length=MAX_LABEL_CHARS)
    value: str = Field(max_length=MAX_VALUE_CHARS)


class ScanCard(BaseModel):
    """What a scan shows for one record."""

    model_config = ConfigDict(extra="forbid")

    record_type: str
    key: str
    title: str = Field(max_length=MAX_TITLE_CHARS)
    banner: str = Field(max_length=MAX_BANNER_CHARS)
    tone: Tone
    as_of: datetime
    valid_until: datetime | None = None
    lines: list[ScanLine] = Field(default_factory=list[ScanLine], max_length=MAX_LINES)
    open_path: str | None = None

    @field_validator("as_of")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("as_of must be timezone aware")
        return value

    @field_validator("open_path")
    @classmethod
    def _inside_web(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.startswith(WEB_PREFIX) or "//" in value or ".." in value:
            raise ValueError("open_path must start with /web/ and hold no // or ..")
        return value


@runtime_checkable
class ScanCardProvider(Protocol):
    """A plugin that answers one record type's card.

    Rules: a pure read; never writes; never raises for a bad or hidden record (answers ``None``);
    answers ``None`` for a record the viewer cannot see; never opens the network.
    """

    #: The record type the provider answers for, e.g. "quality.PunchItem".
    record_type: str
    #: The access word the viewer needs to read the record.
    view_word: str

    def card(
        self, conn: Connection, record_id: str, viewer: Viewer, now: datetime
    ) -> ScanCard | None:
        """The card for ``record_id`` as ``viewer`` sees it at ``now``, or ``None``."""
        ...
