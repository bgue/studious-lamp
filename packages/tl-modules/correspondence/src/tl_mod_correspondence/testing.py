"""Test support other packages share: a ledger and the correspondence module's commands.

``CorrWorld`` wraps a ledger target and offers one call per thing a test does. Every call opens its
own unit of work, like a real command. ``forge_item`` writes an item with raw events when a test
must not depend on the command that makes it; it is not registered anywhere and never runs in
production. ``frozen_today`` sets the day the module's handlers see (the module reads time only
through ``handlers.common.today``).
"""

from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow
from tl_adapters.objectstore.fs import FsObjectStore
from tl_core import confidentiality as cf
from tl_core.files.service import CompleteUpload, FileResult, FileService, RegisterUpload
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.records import create_module_record

from tl_mod_correspondence import registry
from tl_mod_correspondence.handlers import common
from tl_mod_correspondence.handlers.clauses import (
    DefineClause,
    RetireClause,
    handle_define_clause,
    handle_retire_clause,
)
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
from tl_mod_correspondence.handlers.confidentiality import (
    GrantClearance,
    SetCorrespondenceConfidentiality,
    WithdrawClearance,
    handle_grant_clearance,
    handle_set_confidentiality,
    handle_withdraw_clearance,
)
from tl_mod_correspondence.handlers.issue import IssueCorrespondence, handle_issue_correspondence
from tl_mod_correspondence.handlers.items import (
    ReceiveCorrespondence,
    UpdateCorrespondence,
    handle_receive_correspondence,
    handle_update_correspondence,
)
from tl_mod_correspondence.handlers.parties import (
    AddContact,
    EndContact,
    RegisterParty,
    RetireParty,
    handle_add_contact,
    handle_end_contact,
    handle_register_party,
    handle_retire_party,
)
from tl_mod_correspondence.handlers.responses import (
    CloseCorrespondence,
    DraftCorrespondence,
    RecordResponse,
    VoidCorrespondence,
    VoidDraft,
    handle_close_correspondence,
    handle_draft_correspondence,
    handle_record_response,
    handle_void_correspondence,
    handle_void_draft,
)
from tl_mod_correspondence.handlers.threads import (
    AssignThread,
    SupersedeCorrespondence,
    handle_assign_thread,
    handle_supersede_correspondence,
)
from tl_mod_correspondence.handlers.triage import (
    ConfirmTriage,
    ReclassifyCorrespondence,
    handle_confirm_triage,
    handle_reclassify_correspondence,
)
from tl_mod_correspondence.names import (
    CLAUSE,
    CLAUSE_DEFINED,
    CLOCK,
    CORR_DEFINED,
    CORR_TRIAGED,
    CORRESPONDENCE,
    PARTY,
    PARTY_DEFINED,
)

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
    """A ledger, an object store and a file service, with one call per thing a test does."""

    def __init__(self, db: DbTarget, objects: Path | None = None) -> None:
        self.db = db
        self.files: FileService | None = None
        if objects is not None:
            self.files = FileService(FsObjectStore(objects, secret=b"s"), secret=b"s")

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

        ``state`` is Draft, Received, Triaged, Issued or Responded here (Closed and Void are
        reached with the commands that do it).
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
            if state in ("Received", "Triaged", "Responded"):
                common.transition(uow, cmd, made.stream_id, "receive")
            if state in ("Triaged", "Responded"):
                common.append(
                    uow,
                    cmd,
                    made.stream_id,
                    CORRESPONDENCE,
                    [
                        NewEvent(
                            event_type=CORR_TRIAGED,
                            payload={
                                "domain": "general",
                                "subtype": "letter",
                                "referenced_ids": [],
                                "clock_ids": [],
                                "triaged_on": "2026-10-17",
                                "suggestion": None,
                            },
                        )
                    ],
                )
                common.transition(uow, cmd, made.stream_id, "triage")
            if state == "Issued":
                common.transition(uow, cmd, made.stream_id, "issue")
            if state == "Responded":
                common.transition(uow, cmd, made.stream_id, "respond")
            if state not in ("Draft", "Received", "Triaged", "Issued", "Responded"):
                raise ValueError("forge_item: Draft, Received, Triaged, Issued or Responded only")
        return made.stream_id

    def forge_clause(self, contract: str = "CT-1", number: str = "20.1") -> str:
        """A contract clause written with raw events; returns its id."""
        with cf.system_view(), open_uow(self.db) as uow:
            made = create_module_record(
                uow,
                _Forge(**BASE),
                record_type=CLAUSE,
                title=f"{contract} clause {number}",
                key=f"{contract}/{number}",
                extra_events=[
                    NewEvent(
                        event_type=CLAUSE_DEFINED,
                        payload={
                            "contract": contract,
                            "clause_number": number,
                            "time_bar_days": 28,
                            "time_bar_day_type": "calendar",
                            "required_recipients": [],
                            "domains": [],
                        },
                    )
                ],
            )
        return made.stream_id

    def forge_party(self, code: str = "MER", name: str = "Meridian Energy") -> str:
        """A party written with raw events (no command rules); returns its id."""
        with cf.system_view(), open_uow(self.db) as uow:
            made = create_module_record(
                uow,
                _Forge(**BASE),
                record_type=PARTY,
                title=name,
                key=code,
                extra_events=[
                    NewEvent(
                        event_type=PARTY_DEFINED,
                        payload={
                            "code": code,
                            "project_role": "client",
                            "email_domains": ["meridian.example"],
                            "contacts": [],
                        },
                    )
                ],
            )
        return made.stream_id

    # --- the commands, one call each ------------------------------------------------------

    def run(self, model: type[Command], handler: Any, /, **fields: Any) -> CommandResult:
        """Run one command in its own unit of work, as the test actor (fields override BASE)."""
        with open_uow(self.db) as uow:
            return handler(uow, model(**{**BASE, **fields}))

    def receive(self, subject: str = "Revised programme", **more: Any) -> CommandResult:
        fields: dict[str, Any] = {
            "subject": subject,
            "from_name": "Meridian Energy",
            "body": "Please confirm the revised programme.",
            **more,
        }
        return self.run(ReceiveCorrespondence, handle_receive_correspondence, **fields)

    def update(self, item_id: str, **more: Any) -> CommandResult:
        return self.run(
            UpdateCorrespondence, handle_update_correspondence, stream_id=item_id, **more
        )

    def draft(self, subject: str = "Reply: revised programme", **more: Any) -> CommandResult:
        fields: dict[str, Any] = {
            "subject": subject,
            "body": "We confirm the programme.",
            "to": [{"name": "Meridian Energy", "email": "pm@meridian.example"}],
        }
        return self.run(DraftCorrespondence, handle_draft_correspondence, **{**fields, **more})

    def triage(
        self, item_id: str, domain: str = "general", subtype: str = "letter", **more: Any
    ) -> CommandResult:
        return self.run(
            ConfirmTriage,
            handle_confirm_triage,
            stream_id=item_id,
            domain=domain,
            subtype=subtype,
            **more,
        )

    def reclassify(self, item_id: str, domain: str, subtype: str, **more: Any) -> CommandResult:
        fields: dict[str, Any] = {"reason": "wrong domain", **more}
        return self.run(
            ReclassifyCorrespondence,
            handle_reclassify_correspondence,
            stream_id=item_id,
            domain=domain,
            subtype=subtype,
            **fields,
        )

    def issue(self, item_id: str, **more: Any) -> CommandResult:
        return self.run(IssueCorrespondence, handle_issue_correspondence, stream_id=item_id, **more)

    def respond(self, item_id: str, response_id: str, **more: Any) -> CommandResult:
        return self.run(
            RecordResponse,
            handle_record_response,
            stream_id=item_id,
            response_id=response_id,
            **more,
        )

    def close(self, item_id: str, **more: Any) -> CommandResult:
        return self.run(CloseCorrespondence, handle_close_correspondence, stream_id=item_id, **more)

    def void_draft(self, item_id: str, reason: str = "made in error") -> CommandResult:
        return self.run(VoidDraft, handle_void_draft, stream_id=item_id, reason=reason)

    def void(self, item_id: str, reason: str = "filed in error") -> CommandResult:
        return self.run(
            VoidCorrespondence, handle_void_correspondence, stream_id=item_id, reason=reason
        )

    def assign(self, item_id: str, **more: Any) -> CommandResult:
        return self.run(AssignThread, handle_assign_thread, stream_id=item_id, **more)

    def supersede(self, item_id: str, by: str, reason: str = "corrected") -> CommandResult:
        return self.run(
            SupersedeCorrespondence,
            handle_supersede_correspondence,
            stream_id=item_id,
            superseded_by_id=by,
            reason=reason,
        )

    def set_class(self, item_id: str, to_class: str, **more: Any) -> CommandResult:
        fields: dict[str, Any] = {"reason": "commercial terms", **more}
        return self.run(
            SetCorrespondenceConfidentiality,
            handle_set_confidentiality,
            stream_id=item_id,
            to_class=to_class,
            **fields,
        )

    def grant(self, item_id: str, account: str, reason: str = "counsel") -> CommandResult:
        return self.run(
            GrantClearance,
            handle_grant_clearance,
            stream_id=item_id,
            account=account,
            reason=reason,
        )

    def withdraw(self, item_id: str, account: str, reason: str = "matter closed") -> CommandResult:
        return self.run(
            WithdrawClearance,
            handle_withdraw_clearance,
            stream_id=item_id,
            account=account,
            reason=reason,
        )

    def party(self, code: str = "MER", name: str = "Meridian Energy", **more: Any) -> CommandResult:
        fields: dict[str, Any] = {
            "code": code,
            "name": name,
            "project_role": "client",
            "email_domains": ["meridian.example"],
            **more,
        }
        return self.run(RegisterParty, handle_register_party, **fields)

    def add_contact(self, party_id: str, **contact: Any) -> CommandResult:
        fields: dict[str, Any] = {"name": "Pat Jones", **contact}
        return self.run(AddContact, handle_add_contact, party_id=party_id, contact=fields)

    def end_contact(self, party_id: str, position: int, **more: Any) -> CommandResult:
        return self.run(
            EndContact, handle_end_contact, party_id=party_id, position=position, **more
        )

    def retire_party(self, party_id: str, reason: str = "merged") -> CommandResult:
        return self.run(RetireParty, handle_retire_party, party_id=party_id, reason=reason)

    def clause(self, contract: str = "CT-1", number: str = "20.1", **more: Any) -> CommandResult:
        fields: dict[str, Any] = {
            "contract": contract,
            "clause_number": number,
            "time_bar_days": 28,
            "time_bar_day_type": "calendar",
            **more,
        }
        return self.run(DefineClause, handle_define_clause, **fields)

    def retire_clause(self, clause_id: str, reason: str = "superseded") -> CommandResult:
        return self.run(RetireClause, handle_retire_clause, clause_id=clause_id, reason=reason)

    def upload(
        self,
        item_id: str,
        slot: str = "original",
        data: bytes = b"%PDF-1.7 a letter",
        name: str = "letter.pdf",
    ) -> FileResult:
        """Upload ``data`` into a slot of the item through the file service."""
        assert self.files is not None, "make the world with an objects directory"
        declared = RegisterUpload(
            **BASE,
            record_id=item_id,
            slot=slot,
            filename=name,
            content_type="application/pdf",
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )
        with open_uow(self.db) as uow:
            ticket = self.files.register_upload(uow, declared)
        with open_uow(self.db) as uow:
            return self.files.complete_upload(
                uow, CompleteUpload(**BASE, upload_id=ticket.upload_id), io.BytesIO(data)
            )

    def forge_item_event(self, item_id: str, event_type: str, payload: dict[str, Any]) -> None:
        """Append an item event without the checks of the commands (a damaged or old history)."""
        with cf.system_view(), open_uow(self.db) as uow:
            common.append(
                uow,
                _Forge(**BASE),
                item_id,
                CORRESPONDENCE,
                [NewEvent(event_type=event_type, payload=payload)],
            )

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
