"""CWA commands: define, revise and retire a construction work area.

An area is a project record (``awp.CWA``) whose key is its code. A new title appends
``Record.Updated`` from the command (never the generic ``UpdateRecord``) before ``CWA.Revised``.
Retiring an area is refused while a package that is not void names it, and asks for a rollup.
Fixed messages. All the events of a command share one correlation id.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tl_core.ledger import NewEvent
from tl_core.services.commands import CommandResult
from tl_core.services.errors import NoChangesError
from tl_core.uow import UnitOfWork

from tl_mod_awp import rollup
from tl_mod_awp.common import (
    MSG_DUPLICATE,
    append,
    correlated,
    create_coded_record,
    cwp_names_cwa,
    get_cwa,
    key_taken,
    load_record,
    require_project,
)
from tl_mod_awp.errors import DuplicateCodeError, InUseError, RetiredError
from tl_mod_awp.names import CWA, CWA_DEFINED, CWA_RETIRED, CWA_REVISED

if TYPE_CHECKING:
    from tl_mod_awp.commands import DefineCwa, RetireCwa, ReviseCwa

MSG_RETIRED = "the area is retired"
MSG_IN_USE = "a package that is not void names the area"
MSG_NOTHING = "the request changes nothing"


def handle_define_cwa(uow: UnitOfWork, cmd: DefineCwa) -> CommandResult:
    """Create an area (``Record.Created``, ``CWA.Defined``). Raises ``DuplicateCodeError``."""
    require_project(cmd)
    cmd = correlated(cmd)
    if key_taken(uow.conn(), cmd.scope, CWA, cmd.code):
        raise DuplicateCodeError(MSG_DUPLICATE)
    made = create_coded_record(
        uow,
        cmd,
        record_type=CWA,
        title=cmd.title,
        code=cmd.code,
        extra_events=[
            NewEvent(
                event_type=CWA_DEFINED,
                payload={"code": cmd.code, "location_text": cmd.location_text},
            )
        ],
    )
    return CommandResult(
        stream_id=made.stream_id, key=cmd.code, version=made.version, events=made.events
    )


def handle_revise_cwa(uow: UnitOfWork, cmd: ReviseCwa) -> CommandResult:
    """Rename an area or change where it is (``location_text`` sent as null clears it).

    Raises ``RecordNotFoundError``, ``NoChangesError``.
    """
    require_project(cmd)
    cmd = correlated(cmd)
    ref = load_record(uow, cmd.scope, cmd.cwa, CWA)
    area = get_cwa(uow.conn(), ref.id)
    assert area is not None
    changes: dict[str, list[Any]] = {}
    events: list[NewEvent] = []
    if cmd.title is not None and cmd.title != ref.title:
        changes["title"] = [ref.title, cmd.title]
        events.append(
            NewEvent(
                event_type="Record.Updated", payload={"changes": {"title": [ref.title, cmd.title]}}
            )
        )
    if "location_text" in cmd.model_fields_set and cmd.location_text != area.location_text:
        changes["location_text"] = [area.location_text, cmd.location_text]
    if not changes:
        raise NoChangesError(MSG_NOTHING)
    events.append(NewEvent(event_type=CWA_REVISED, payload={"changes": changes}))
    made = append(uow, cmd, ref.id, CWA, events)
    return CommandResult(
        stream_id=ref.id, key=area.code, version=made.new_version, events=made.events
    )


def handle_retire_cwa(uow: UnitOfWork, cmd: RetireCwa) -> CommandResult:
    """Retire an area. Refused while a package that is not void names it.

    Raises ``RecordNotFoundError``, ``RetiredError``, ``InUseError``.
    """
    require_project(cmd)
    cmd = correlated(cmd)
    ref = load_record(uow, cmd.scope, cmd.cwa, CWA)
    area = get_cwa(uow.conn(), ref.id)
    assert area is not None
    if area.retired:
        raise RetiredError(MSG_RETIRED)
    if cwp_names_cwa(uow.conn(), area.id):
        raise InUseError(MSG_IN_USE)
    made = append(
        uow, cmd, area.id, CWA, [NewEvent(event_type=CWA_RETIRED, payload={"reason": cmd.reason})]
    )
    rollup.request(uow, cmd.scope)
    return CommandResult(
        stream_id=area.id, key=area.code, version=made.new_version, events=made.events
    )
