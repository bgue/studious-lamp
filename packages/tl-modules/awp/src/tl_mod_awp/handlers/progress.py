"""Progress commands: scope item moves, manual progress, start and field complete of an IWP.

Each state-moving command writes the progress row in its own unit: after the move it computes the
figure over every non-void item (``progress.engine``, whatever the writer may see) and appends
``IWP.ProgressRecorded`` to the IWP's stream when the figure, its edition or the manual credit
changed. A figure already recorded keeps its edition. The handlers never read ``intent`` (ADR-0025).
Fixed messages, never a cell of the input.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from tl_core.ledger import Event, NewEvent, iso_utc
from tl_core.services.commands import Command, CommandResult
from tl_core.uow import UnitOfWork

from tl_mod_awp.common import (
    append,
    correlated,
    load_record,
    move,
    require_project,
    silent,
    version_of,
)
from tl_mod_awp.errors import IwpStateError, ProgressRuleError, StaleVersionError
from tl_mod_awp.handlers.iwp import Iwp, load_iwp
from tl_mod_awp.names import (
    IWP,
    IWP_FIELD_COMPLETED,
    IWP_IN_PROGRESS,
    IWP_ISSUED,
    IWP_PROGRESS_RECORDED,
    IWP_STARTED,
    IWP_TERMINAL,
    MAX_MANUAL,
    RULE_LINK_SOURCE,
    SCOPE_ITEM,
    SCOPE_RELATION,
)
from tl_mod_awp.progress import engine

if TYPE_CHECKING:
    from tl_mod_awp.commands import (
        CompleteIwpField,
        InstallScopeItem,
        RecordManualProgress,
        ReturnScopeItem,
        StartIwpWork,
        VerifyScopeItem,
    )

MSG_STALE = "the record changed since it was read"
MSG_NOT_MEMBER = "a record of the list is not in the scope of this package"
MSG_NOT_MANUAL = "the step is not one that takes a hand entry"
MSG_TOO_MANY = "a package holds at most 500 manual entries"
MSG_CLOSED = "a closed, split or cancelled package takes no progress"

_OWNER_SQL = text(
    "SELECT r.id AS id, r.status AS status FROM cur_links l JOIN cur_core_record r "
    "ON r.id = l.to_id WHERE l.from_id = :item AND l.relation = :relation "
    "AND l.source = :source AND l.status = 'active' AND r.type = :iwp_type "
    "ORDER BY r.key, r.id"
)


def _now() -> datetime:
    return datetime.now(UTC)


def _owner_iwp(uow: UnitOfWork, item_id: str) -> str | None:
    """The IWP that is not finished and holds the item (an item is in at most one)."""
    rows = uow.conn().execute(
        _OWNER_SQL,
        {
            "item": item_id,
            "relation": SCOPE_RELATION,
            "source": RULE_LINK_SOURCE,
            "iwp_type": IWP,
        },
    )
    for row in rows:
        if str(row.status or "Draft") not in IWP_TERMINAL:
            return str(row.id)
    return None


def record_progress(
    uow: UnitOfWork,
    cmd: Command,
    iwp_id: str,
    *,
    manual: list[dict[str, str]] | None = None,
    force: bool = False,
) -> list[Event]:
    """Append ``IWP.ProgressRecorded`` when the figure, the edition or the manual credit differs
    from the row (or there is no row yet); always with ``force``. The events written."""
    conn = uow.conn()
    stored = engine.stored_progress(conn, iwp_id)
    figure = engine.figure_of(conn, iwp_id, manual=manual)
    held = manual if manual is not None else (stored.manual if stored is not None else [])
    pct = engine.figure_text(figure.pct)
    if (
        not force
        and stored is not None
        and stored.pct == pct
        and stored.edition == figure.edition
        and sorted(map(_entry_key, stored.manual)) == sorted(map(_entry_key, held))
    ):
        return []
    at = _now()
    payload: dict[str, Any] = {
        "iwp_id": iwp_id,
        "earned_pct": pct,
        "edition": figure.edition,
        "at": iso_utc(at),
    }
    if held:
        payload["manual"] = sorted(held, key=_entry_key)
    done = append(
        uow,
        cmd,
        iwp_id,
        IWP,
        [NewEvent(event_type=IWP_PROGRESS_RECORDED, payload=silent(payload), effective_at=at)],
    )
    return list(done.events)


def _entry_key(entry: dict[str, str]) -> tuple[str, str]:
    return entry["scope_item_id"], entry["step"]


def _require_fresh(actual: int, expected: int) -> None:
    if actual != expected:
        raise StaleVersionError(MSG_STALE)


def _item_move(uow: UnitOfWork, cmd: Any, transition: str) -> CommandResult:
    require_project(cmd)
    cmd = correlated(cmd)
    ref = load_record(uow, cmd.scope, cmd.record_id, SCOPE_ITEM)
    _require_fresh(version_of(uow, ref.id), cmd.expected_version)
    moved = move(uow, cmd, ref.id, transition)
    events = list(moved.events)
    iwp_id = _owner_iwp(uow, ref.id)
    if iwp_id is not None:
        events.extend(record_progress(uow, cmd, iwp_id))
    return CommandResult(stream_id=ref.id, key=ref.key, version=moved.version, events=events)


def handle_install_scope_item(uow: UnitOfWork, cmd: InstallScopeItem) -> CommandResult:
    """Planned to Installed. Raises ``StaleVersionError``; the workflow refuses any other state."""
    return _item_move(uow, cmd, "install")


def handle_return_scope_item(uow: UnitOfWork, cmd: ReturnScopeItem) -> CommandResult:
    """Installed back to Planned."""
    return _item_move(uow, cmd, "return")


def handle_verify_scope_item(uow: UnitOfWork, cmd: VerifyScopeItem) -> CommandResult:
    """Installed to Verified."""
    return _item_move(uow, cmd, "verify")


def handle_record_manual_progress(uow: UnitOfWork, cmd: RecordManualProgress) -> CommandResult:
    """Mark steps of items done, or not done, by hand (steps whose evidence is ``manual``).

    Raises ``StaleVersionError``, ``IwpStateError`` (finished package), ``ProgressRuleError``
    (an item outside the package, a step that takes no hand entry, too many entries)."""
    require_project(cmd)
    cmd = correlated(cmd)
    iwp = load_iwp(uow, cmd.scope, cmd.iwp_id)
    _require_fresh(iwp.version, cmd.expected_version)
    if iwp.state in IWP_TERMINAL:
        raise IwpStateError(MSG_CLOSED)
    conn = uow.conn()
    stored = engine.stored_progress(conn, iwp.id)
    rules = (
        engine.rules_for(stored.edition)
        if stored is not None
        else engine.edition_for(conn, cmd.scope)
    )
    members = {m.id: m for m in engine.scope_items(conn, iwp.id)}
    held = {_entry_key(e) for e in (stored.manual if stored is not None else [])}
    for entry in cmd.steps:
        load_record(uow, cmd.scope, entry.scope_item_id, SCOPE_ITEM)  # hidden: not found
        member = members.get(entry.scope_item_id)
        if member is None:
            raise ProgressRuleError(MSG_NOT_MEMBER)
        manual_steps = {s.name for s in rules.steps_for(member.commodity) if s.evidence == "manual"}
        if entry.step not in manual_steps:
            raise ProgressRuleError(MSG_NOT_MANUAL)
        key = (entry.scope_item_id, entry.step)
        if entry.done:
            held.add(key)
        else:
            held.discard(key)
    if len(held) > MAX_MANUAL:
        raise ProgressRuleError(MSG_TOO_MANY)
    manual = [{"scope_item_id": i, "step": s} for i, s in sorted(held)]
    events = record_progress(uow, cmd, iwp.id, manual=manual)
    return CommandResult(
        stream_id=iwp.id, key=iwp.key, version=version_of(uow, iwp.id), events=events
    )


def _at(day: date | None) -> datetime:
    if day is None:
        return _now()
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def _field_move(
    uow: UnitOfWork,
    cmd: Any,
    *,
    command: str,
    from_state: str,
    event_type: str,
    transition: str,
    last_progress: bool,
) -> CommandResult:
    require_project(cmd)
    cmd = correlated(cmd)
    iwp: Iwp = load_iwp(uow, cmd.scope, cmd.iwp_id)
    _require_fresh(iwp.version, cmd.expected_version)
    if iwp.state != from_state:
        raise IwpStateError(f"a package that is {iwp.state} does not take {command}")
    at = _at(cmd.at)
    first = append(
        uow,
        cmd,
        iwp.id,
        IWP,
        [NewEvent(event_type=event_type, payload=silent({"at": iso_utc(at)}), effective_at=at)],
    )
    moved = move(uow, cmd, iwp.id, transition)
    events = [*first.events, *moved.events]
    version = moved.version
    if last_progress:
        events.extend(record_progress(uow, cmd, iwp.id, force=True))
        version = version_of(uow, iwp.id)
    return CommandResult(stream_id=iwp.id, key=iwp.key, version=version, events=events)


def handle_start_iwp_work(uow: UnitOfWork, cmd: StartIwpWork) -> CommandResult:
    """Issued to In progress: ``IWP.Started`` then the move ``start`` (guarded by the open blocking
    constraints)."""
    return _field_move(
        uow,
        cmd,
        command="StartIwpWork",
        from_state=IWP_ISSUED,
        event_type=IWP_STARTED,
        transition="start",
        last_progress=False,
    )


def handle_complete_iwp_field(uow: UnitOfWork, cmd: CompleteIwpField) -> CommandResult:
    """In progress to Field complete: ``IWP.FieldCompleted``, the move ``complete`` (guarded by the
    open blocking constraints) and a last ``IWP.ProgressRecorded``."""
    return _field_move(
        uow,
        cmd,
        command="CompleteIwpField",
        from_state=IWP_IN_PROGRESS,
        event_type=IWP_FIELD_COMPLETED,
        transition="complete",
        last_progress=True,
    )


__all__ = [
    "handle_complete_iwp_field",
    "handle_install_scope_item",
    "handle_record_manual_progress",
    "handle_return_scope_item",
    "handle_start_iwp_work",
    "handle_verify_scope_item",
    "record_progress",
]
