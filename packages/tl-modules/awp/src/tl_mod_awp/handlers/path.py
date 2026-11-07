"""Path of construction commands: define it (version 1) and move an area in it.

There is one path per project, a record whose key the module builds (``P123-POC``). Its steps are
areas in order; every version is kept as rows (``cur_awp_path_step``), and each event carries the
full list. ``MoveCwaInPath`` is the one command that re-sequences: it states the version the
caller read (``expected_version``) and writes version + 1, or is refused as stale. In the new
version only the moved step carries the reason. Fixed messages. All events of a command share one
correlation id.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from tl_core.ledger import NewEvent
from tl_core.services.commands import CommandResult
from tl_core.services.errors import NoChangesError
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork

from tl_mod_awp.common import (
    append,
    correlated,
    require_code,
    require_list_code,
    require_project,
    silent,
)
from tl_mod_awp.errors import PathRuleError, RetiredError, StaleVersionError
from tl_mod_awp.names import (
    CWA,
    CWA_TABLE,
    PATH,
    PATH_DEFINED,
    PATH_RESEQUENCED,
    PATH_STEP_TABLE,
    PATH_TABLE,
)

if TYPE_CHECKING:
    from tl_mod_awp.commands import DefinePathOfConstruction, MoveCwaInPath

MSG_EXISTS = "the project already has a path of construction"
MSG_NO_PATH = "the project has no path of construction"
MSG_TWICE = "an area appears twice in the path"
MSG_NO_AREA = "no area with that code in the project"
MSG_RETIRED = "a retired area cannot join the path"
MSG_NOT_IN_PATH = "the area is not in the path"
MSG_POSITION = "the position is outside the path"
MSG_STALE = "the path changed since it was read; read it again"
MSG_SAME = "the area is already at that position"
TITLE = "Path of construction"
REASON_LIST = "PathReason"  # code list of the standards edition co.acme.awp@1.0.0
REASON_WHAT = "the reason code"

_PATH_SQL = text(f"SELECT id, current_version FROM {PATH_TABLE} WHERE scope = :scope")
_STEPS_SQL = text(
    f"SELECT s.cwa_id, c.code FROM {PATH_STEP_TABLE} s JOIN {CWA_TABLE} c ON c.id = s.cwa_id "
    "WHERE s.path_id = :path AND s.version = :version ORDER BY s.position"
)
_RETIRED_SQL = text(f"SELECT retired FROM {CWA_TABLE} WHERE id = :id")


def path_key(scope: str) -> str:
    """``P123-POC`` for the scope ``project:P123``."""
    return f"{scope.split(':', 1)[1]}-POC"


def handle_define_path_of_construction(
    uow: UnitOfWork, cmd: DefinePathOfConstruction
) -> CommandResult:
    """Create the project's path (``Record.Created``, ``PathOfConstruction.Defined``, version 1).

    Raises ``PathRuleError`` (a path exists, an area twice), ``CodeNotFoundError`` (an unknown
    area), ``UnknownListCodeError`` (a reason code not in ``PathReason``), ``RetiredError``.
    """
    require_project(cmd)
    cmd = correlated(cmd)
    conn = uow.conn()
    if conn.execute(_PATH_SQL, {"scope": cmd.scope}).first() is not None:
        raise PathRuleError(MSG_EXISTS)
    seen: set[str] = set()
    steps: list[dict[str, Any]] = []
    for step in cmd.steps:
        cwa_id = require_code(conn, cmd.scope, CWA, step.cwa_code, "area")
        if step.reason_code is not None:
            require_list_code(conn, cmd.scope, REASON_LIST, step.reason_code, REASON_WHAT)
        if cwa_id in seen:
            raise PathRuleError(MSG_TWICE)
        seen.add(cwa_id)
        if bool(conn.execute(_RETIRED_SQL, {"id": cwa_id}).scalar_one()):
            raise RetiredError(MSG_RETIRED)
        steps.append({"cwa_id": cwa_id, "cwa_code": step.cwa_code, "reason_code": step.reason_code})
    return create_module_record(
        uow,
        cmd,
        record_type=PATH,
        title=TITLE,
        key=path_key(cmd.scope),
        composed_key=True,
        extra_events=[
            NewEvent(event_type=PATH_DEFINED, payload=silent({"version": 1, "steps": steps}))
        ],
    )


def handle_move_cwa_in_path(uow: UnitOfWork, cmd: MoveCwaInPath) -> CommandResult:
    """Move an area to a place in the path: ``PathOfConstruction.Resequenced``, version + 1.

    Raises ``PathRuleError`` (no path, the area is not in it, the place is outside it),
    ``StaleVersionError`` (``expected_version`` is not the current version), ``CodeNotFoundError``,
    ``NoChangesError``.
    """
    require_project(cmd)
    cmd = correlated(cmd)
    conn = uow.conn()
    path = conn.execute(_PATH_SQL, {"scope": cmd.scope}).first()
    if path is None:
        raise PathRuleError(MSG_NO_PATH)
    version = int(path.current_version)
    if cmd.expected_version != version:
        raise StaleVersionError(MSG_STALE)
    cwa_id = require_code(conn, cmd.scope, CWA, cmd.cwa_code, "area")
    require_list_code(conn, cmd.scope, REASON_LIST, cmd.reason_code, REASON_WHAT)
    rows = conn.execute(_STEPS_SQL, {"path": str(path.id), "version": version}).all()
    order = [(str(r.cwa_id), str(r.code)) for r in rows]
    at = next((i for i, (cid, _) in enumerate(order) if cid == cwa_id), None)
    if at is None:
        raise PathRuleError(MSG_NOT_IN_PATH)
    if not 1 <= cmd.to_position <= len(order):
        raise PathRuleError(MSG_POSITION)
    if at == cmd.to_position - 1:
        raise NoChangesError(MSG_SAME)
    moved = order.pop(at)
    order.insert(cmd.to_position - 1, moved)
    steps = [
        {
            "cwa_id": cid,
            "cwa_code": code,
            "reason_code": cmd.reason_code if cid == cwa_id else None,
        }
        for cid, code in order
    ]
    made = append(
        uow,
        cmd,
        str(path.id),
        PATH,
        [
            NewEvent(
                event_type=PATH_RESEQUENCED,
                payload=silent(
                    {
                        "version": version + 1,
                        "steps": steps,
                        "reason_code": cmd.reason_code,
                        "note": cmd.note,
                    }
                ),
            )
        ],
    )
    return CommandResult(
        stream_id=str(path.id),
        key=path_key(cmd.scope),
        version=made.new_version,
        events=made.events,
    )
