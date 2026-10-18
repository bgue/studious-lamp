"""Test support other packages share: a ledger and the correspondence module's commands.

``CorrWorld`` wraps a ledger target and offers one call per thing a test does. Every call opens its
own unit of work, like a real command. ``forge_item`` writes an item with raw events when a test
must not depend on the command that makes it; it is not registered anywhere and never runs in
production. ``frozen_today`` sets the day the module's handlers see (the module reads time only
through ``handlers.common.today``).
"""

from __future__ import annotations

import json
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow
from tl_core import confidentiality as cf
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.records import create_module_record

from tl_mod_correspondence import registry
from tl_mod_correspondence.handlers import common
from tl_mod_correspondence.handlers.clocks import (
    CancelClock,
    MeetClock,
    PauseClock,
    RestartClock,
    ResumeClock,
    StartClock,
    SweepClocks,
    handle_cancel_clock,
    handle_meet_clock,
    handle_pause_clock,
    handle_restart_clock,
    handle_resume_clock,
    handle_start_clock,
    handle_sweep_clocks,
)
from tl_mod_correspondence.names import CLOCK, CORR_DEFINED, CORRESPONDENCE

PROJECT = "project:P123"
BASE: dict[str, Any] = {"actor": "user:u", "source": "test", "scope": PROJECT}


@contextmanager
def frozen_today(day: str | date) -> Generator[None]:
    """The module's handlers see ``day`` as today for the duration of the block."""
    chosen = day if isinstance(day, date) else date.fromisoformat(day)
    moment = datetime(chosen.year, chosen.month, chosen.day, 9, 0, tzinfo=UTC)
    original = common.now
    common.now = lambda: moment
    try:
        yield
    finally:
        common.now = original


class CorrWorld:
    def __init__(self, db: DbTarget) -> None:
        self.db = db

    # --- reads -----------------------------------------------------------------------------

    def scalar(self, sql: str, **params: Any) -> Any:
        with open_uow(self.db, readonly=True) as uow:
            return uow.conn().execute(text(sql), params).scalar_one()

    def rows(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        with open_uow(self.db, readonly=True) as uow:
            return [dict(r) for r in uow.conn().execute(text(sql), params).mappings()]

    def item(self, number: str) -> registry.ItemRow:
        with open_uow(self.db, readonly=True) as uow:
            found = registry.find_item(uow.conn(), PROJECT, number)
        assert found is not None, number
        return found

    def clock(self, clock_id: str) -> registry.ClockRow:
        with open_uow(self.db, readonly=True) as uow:
            found = registry.get_clock(uow.conn(), clock_id)
        assert found is not None, clock_id
        return found

    def clocks(self, number: str) -> list[registry.ClockRow]:
        item = self.item(number)
        with open_uow(self.db, readonly=True) as uow:
            return registry.clocks_of(uow.conn(), item.id)

    def events_of(self, stream_id: str) -> list[tuple[str, dict[str, Any]]]:
        with open_uow(self.db, readonly=True) as uow:
            return [
                (r.event_type, r.payload if isinstance(r.payload, dict) else _load(r.payload))
                for r in uow.conn().execute(
                    text(
                        "SELECT event_type, payload FROM events WHERE stream_id = :s "
                        "ORDER BY stream_version"
                    ),
                    {"s": stream_id},
                )
            ]

    # --- writes ----------------------------------------------------------------------------

    def forge_item(
        self,
        number: str = "P123-COR-0001",
        *,
        subject: str = "Revised programme",
        direction: str = "in",
        state: str = "Received",
        confidentiality: str = "internal",
        **more: Any,
    ) -> str:
        """An item written with raw events (no command rules); returns its id.

        ``state`` is one of Draft or Received here (a test that needs another state moves the item
        with the command that does it).
        """
        payload: dict[str, Any] = {
            "number": number,
            "direction": direction,
            "medium": "letter",
            "received_via": "upload",
            "to": [],
            "cc": [],
            "confidentiality": confidentiality,
            "received_on": "2026-10-17",
            **more,
        }
        cmd = _Forge(**BASE)
        with cf.system_view(), open_uow(self.db) as uow:
            made = create_module_record(
                uow,
                cmd,
                record_type=CORRESPONDENCE,
                title=subject,
                key=number,
                extra_events=[NewEvent(event_type=CORR_DEFINED, payload=payload)],
            )
            if state == "Received":
                common.transition(uow, cmd, made.stream_id, "receive")
            elif state != "Draft":
                raise ValueError("forge_item makes a Draft or a Received item")
        return made.stream_id

    def forge_clock_event(self, clock_id: str, event_type: str, payload: dict[str, Any]) -> None:
        """Append a clock event without the checks of the commands (a forged or damaged history)."""
        with open_uow(self.db) as uow:
            common.append(
                uow,
                _Forge(**BASE),
                clock_id,
                CLOCK,
                [NewEvent(event_type=event_type, payload=payload)],
            )

    def start_clock(self, item_id: str, **more: Any) -> CommandResult:
        fields: dict[str, Any] = {
            "item_id": item_id,
            "label": "Reply due",
            "duration_days": 14,
            "day_type": "calendar",
            "warn_days": [7, 3, 1],
        }
        with open_uow(self.db) as uow:
            return handle_start_clock(uow, StartClock(**{**BASE, **fields, **more}))

    def pause(self, clock_id: str, **more: Any) -> CommandResult:
        with open_uow(self.db) as uow:
            return handle_pause_clock(
                uow, PauseClock(**{**BASE, "clock_id": clock_id, "reason": "waiting", **more})
            )

    def resume(self, clock_id: str, **more: Any) -> CommandResult:
        with open_uow(self.db) as uow:
            return handle_resume_clock(uow, ResumeClock(**{**BASE, "clock_id": clock_id, **more}))

    def restart(self, clock_id: str, **more: Any) -> CommandResult:
        with open_uow(self.db) as uow:
            return handle_restart_clock(
                uow, RestartClock(**{**BASE, "clock_id": clock_id, "reason": "extended", **more})
            )

    def meet(self, clock_id: str, **more: Any) -> CommandResult:
        with open_uow(self.db) as uow:
            return handle_meet_clock(uow, MeetClock(**{**BASE, "clock_id": clock_id, **more}))

    def cancel(self, clock_id: str, **more: Any) -> CommandResult:
        with open_uow(self.db) as uow:
            return handle_cancel_clock(
                uow, CancelClock(**{**BASE, "clock_id": clock_id, "reason": "not needed", **more})
            )

    def sweep(self, **more: Any) -> CommandResult:
        with open_uow(self.db) as uow:
            return handle_sweep_clocks(uow, SweepClocks(**{**BASE, **more}))


def _load(raw: Any) -> dict[str, Any]:
    return json.loads(raw) if isinstance(raw, str) else raw


class _Forge(Command):
    """A command carrier for ``forge_item`` (the helpers read only its envelope fields)."""
