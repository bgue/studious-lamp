"""Models of the insight reads (P2-INS)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from tl_core.ledger import Event

ActivityKind = Literal["change", "move", "link", "file", "post", "proposal", "constraint", "check"]


class ActivityRow(BaseModel):
    event: Event  # the ledger event (A2 reuses record_text.event_label and event_summary)
    kind: ActivityKind  # from the event type prefix; unknown types are "change"
    related: bool = False  # true for a row of a linked record
    from_id: str | None = None  # the linked record's id when related
    from_key: str | None = None  # its display key (never given for a hidden record)
    why: str | None = None  # None until ADR-0025
    decided_by: str | None = None  # proposal rows: the person who accepted or rejected
    note: str | None = None  # readiness rows: "5 of 7 ready"; None otherwise


class ActivityPage(BaseModel):
    rows: list[ActivityRow]  # newest first
    next_before_seq: int | None  # None when nothing older remains
