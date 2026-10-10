"""Changing settings: set, reset, lock and revert, with every check (brief 30.2, 30.3).

All four write inside the caller's unit of work (``with open_uow(...) as uow``), raise a
``SettingError`` subclass to refuse, and append one event on the key's stream
(``setting:<layer>:<key>``): ``Setting.Changed`` for a set, reset or revert, ``Setting.Locked`` for
a lock. They never commit. Nothing is appended when nothing would change, so re-running an import
is quiet.

The checks, in order, and the error each gives:

* the key has a definition (``UnknownSettingError``) and is not ``secret``
  (``SecretSettingUnavailableError``: a vault is a human gate, P0-I5 D15);
* the layer is well formed and the key may be set there (``SettingScopeError``): the definition's
  ``scopes`` must list it, and the user layer is for ``ui.*`` keys only;
* the value fits the definition (``InvalidSettingValueError``);
* for a project or user layer, the company has not locked the key (``SettingLockedError``) and the
  value keeps to the company's bounds (``SettingOutOfBoundsError``);
* an ``advanced`` or ``dangerous`` key needs a reason (``ReasonRequiredError``), and a ``dangerous``
  key also needs ``accept_risk`` (``RiskNotAcceptedError``).

Who may do this is the permission model, a human gate (ADR-0005, D3): this module applies the
mechanism (reason, accept_risk), not role checks. The rule that an agent never changes a setting
directly is enforced at the API (403 ``agent_must_propose``) and by MCP having only a proposing
tool; the accepting person runs :func:`tl_core.services.settings.handle_change_setting`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, text

from tl_core.ledger import AppendResult, Event, NewEvent
from tl_core.services.errors import (
    InvalidSettingValueError,
    ReasonRequiredError,
    RiskNotAcceptedError,
    SecretSettingUnavailableError,
    SettingChangeNotFoundError,
    SettingLockedError,
    SettingNotLockableError,
)
from tl_core.settings.instants import to_us, to_z
from tl_core.settings.layers import (
    COMPANY,
    SETTING_STREAM_TYPE,
    LayerRef,
    parse_layer,
    require_layer,
    stream_id,
)
from tl_core.settings.registry import get_definition
from tl_core.settings.resolver import (
    NO_LOCK,
    Snapshot,
    in_force,
    load_snapshot,
    resolve_from,
)
from tl_core.settings.types import (
    SETTING_CHANGED,
    SETTING_LOCKED,
    EffectiveSetting,
    SettingDefinition,
)
from tl_core.settings.values import check_bounds, check_bounds_shape, normalise
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid, utcnow

MAX_REASON = 1000


@dataclass(frozen=True)
class Outcome:
    """What a change did: the key as seen at the layer, the events appended (none when nothing
    needed to change) and the version of the key's stream afterwards."""

    effective: EffectiveSetting
    events: list[Event]
    version: int


def _version(uow: UnitOfWork, sid: str) -> int:
    """The stream's version **inside this transaction** (0 for a new stream)."""
    found = uow.conn().execute(
        text("SELECT COALESCE(MAX(stream_version), 0) FROM events WHERE stream_id = :s"), {"s": sid}
    )
    return int(found.scalar_one())


def _clean_reason(reason: str | None) -> str | None:
    if reason is None or not reason.strip():
        return None
    clean = reason.strip()
    if len(clean) > MAX_REASON:
        raise InvalidSettingValueError(f"the reason is longer than {MAX_REASON} characters")
    return clean


def _writable(key: str, layer: str) -> tuple[SettingDefinition, LayerRef]:
    defn = get_definition(key)
    if defn.sensitivity == "secret":
        raise SecretSettingUnavailableError(
            f"{key} is secret; secrets need a vault, which is not available yet (a human gate)"
        )
    ref = parse_layer(layer)
    require_layer(defn, ref)
    return defn, ref


def _check_risk(defn: SettingDefinition, reason: str | None, accept_risk: bool) -> None:
    if defn.risk != "normal" and reason is None:
        raise ReasonRequiredError(f"{defn.key} is {defn.risk}: say why you are changing it")
    if defn.risk == "dangerous" and not accept_risk:
        raise RiskNotAcceptedError(
            f"{defn.key} is dangerous: confirm that you accept the risk (accept_risk)"
        )


def _view(conn: Connection, defn: SettingDefinition, ref: LayerRef) -> EffectiveSetting:
    """The key as seen at ``ref`` right now (read in the caller's transaction)."""
    snapshot = load_snapshot(conn, [defn.key])
    return resolve_from(
        defn,
        snapshot,
        project=ref.ident if ref.kind == "project" else None,
        user=ref.ident if ref.kind == "user" else None,
        at_us=to_us(utcnow()),
    )


def _future(applies_at: datetime | None) -> datetime | None:
    if applies_at is None:
        return None
    if applies_at.tzinfo is None:
        raise InvalidSettingValueError("applies_at needs a timezone (use UTC, with a Z)")
    if applies_at <= utcnow():
        raise InvalidSettingValueError(
            "applies_at is not in the future; leave it out to change the setting now"
        )
    return applies_at


def _append_change(
    uow: UnitOfWork,
    *,
    defn: SettingDefinition,
    ref: LayerRef,
    snapshot: Snapshot,
    new_value: Any,
    reset: bool,
    actor: str,
    source: str,
    reason: str | None,
    accept_risk: bool,
    applies_at: datetime | None,
    correlation_id: str | None,
    causation_id: str | None,
) -> AppendResult:
    here = in_force(snapshot.entries.get(defn.key, ()), ref.name, to_us(utcnow()))
    held = here is not None and not here.reset
    sid = stream_id(ref, defn.key)
    return uow.append(
        stream_id=sid,
        stream_type=SETTING_STREAM_TYPE,
        scope=ref.scope,
        expected_version=_version(uow, sid),
        events=[
            NewEvent(
                event_type=SETTING_CHANGED,
                payload={
                    "key": defn.key,
                    "layer": ref.name,
                    "old_value": here.value if held and here is not None else None,
                    "old_set": held,
                    "new_value": None if reset else new_value,
                    "reset": reset,
                    "reason": reason,
                    "applies_at": None if applies_at is None else to_z(applies_at),
                    "accept_risk": accept_risk,
                },
            )
        ],
        actor=actor,
        source=source,
        correlation_id=correlation_id or new_ulid(),
        causation_id=causation_id,
    )


def change_setting(
    uow: UnitOfWork,
    *,
    key: str,
    layer: str,
    value: Any = None,
    reset: bool = False,
    actor: str,
    source: str,
    reason: str | None = None,
    accept_risk: bool = False,
    applies_at: datetime | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> Outcome:
    """Set ``key`` to ``value`` at ``layer``, or (``reset=True``) take the layer's own value away.

    This is :func:`set_setting` and :func:`reset_setting` in one, returning the events as well
    (the ``ChangeSetting`` command handler uses it). See the module docstring for the checks.
    """
    defn, ref = _writable(key, layer)
    clean = None if reset else normalise(defn, value)
    note = _clean_reason(reason)
    snapshot = load_snapshot(uow.conn(), [key])
    if not reset and ref.kind != "company":
        lock = snapshot.locks.get(key, NO_LOCK)
        if lock.locked:
            raise SettingLockedError(f"{key} is locked by the company; projects cannot change it")
        check_bounds(defn, lock.bounds, clean)
    _check_risk(defn, note, accept_risk)
    when = _future(applies_at)
    here = in_force(snapshot.entries.get(key, ()), ref.name, to_us(utcnow()))
    holds = here is not None and not here.reset
    if reset:
        needed = holds or when is not None
    else:
        needed = when is not None or not (holds and here is not None and here.value == clean)
    sid = stream_id(ref, key)
    if not needed:
        return Outcome(_view(uow.conn(), defn, ref), [], _version(uow, sid))
    result = _append_change(
        uow,
        defn=defn,
        ref=ref,
        snapshot=snapshot,
        new_value=clean,
        reset=reset,
        actor=actor,
        source=source,
        reason=note,
        accept_risk=accept_risk,
        applies_at=when,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    return Outcome(_view(uow.conn(), defn, ref), list(result.events), result.new_version)


def set_setting(
    uow: UnitOfWork,
    *,
    key: str,
    layer: str,
    value: Any,
    actor: str,
    source: str,
    reason: str | None = None,
    accept_risk: bool = False,
    applies_at: datetime | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> EffectiveSetting:
    """Set ``key`` to ``value`` at ``layer``; return the key as seen at that layer afterwards.

    ``applies_at`` (timezone-aware, in the future) schedules the change: it is recorded now and
    takes effect then. Nothing is appended when the layer already holds exactly ``value`` and the
    change is not scheduled.
    """
    return change_setting(
        uow,
        key=key,
        layer=layer,
        value=value,
        actor=actor,
        source=source,
        reason=reason,
        accept_risk=accept_risk,
        applies_at=applies_at,
        correlation_id=correlation_id,
        causation_id=causation_id,
    ).effective


def reset_setting(
    uow: UnitOfWork,
    *,
    key: str,
    layer: str,
    actor: str,
    source: str,
    reason: str | None = None,
    accept_risk: bool = False,
    applies_at: datetime | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> EffectiveSetting:
    """Take ``layer``'s own value away so it inherits again; return the key as seen there.

    Nothing is appended when the layer holds no value of its own (and the reset is not
    scheduled). The risk rules apply as for :func:`set_setting`, because the effective value
    changes.
    """
    return change_setting(
        uow,
        key=key,
        layer=layer,
        reset=True,
        actor=actor,
        source=source,
        reason=reason,
        accept_risk=accept_risk,
        applies_at=applies_at,
        correlation_id=correlation_id,
        causation_id=causation_id,
    ).effective


def lock_setting(
    uow: UnitOfWork,
    *,
    key: str,
    locked: bool,
    bounds: dict[str, Any] | None,
    actor: str,
    source: str,
    reason: str,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> EffectiveSetting:
    """Lock ``key`` for the projects (or unlock it) and/or bound the values projects may use.

    Only the company layer does this, and only for a ``lockable`` definition
    (``SettingNotLockableError``). ``bounds`` is ``None`` or a mapping of ``minimum``,
    ``maximum`` and ``choices`` (``InvalidSettingValueError`` when it does not fit the type).
    A reason is always required (``ReasonRequiredError``). Returns the key as seen at the company
    layer. Nothing is appended when the lock and bounds are already as asked.
    """
    defn = get_definition(key)
    if not defn.lockable:
        raise SettingNotLockableError(f"{key} cannot be locked or bounded by the company")
    note = _clean_reason(reason)
    if note is None:
        raise ReasonRequiredError(f"say why you are changing the lock on {key}")
    clean = check_bounds_shape(defn, bounds) if bounds else None
    snapshot = load_snapshot(uow.conn(), [key])
    current = snapshot.locks.get(key, NO_LOCK)
    if not (current.locked == locked and (current.bounds or None) == (clean or None)):
        sid = stream_id(COMPANY, key)
        uow.append(
            stream_id=sid,
            stream_type=SETTING_STREAM_TYPE,
            scope=COMPANY.scope,
            expected_version=_version(uow, sid),
            events=[
                NewEvent(
                    event_type=SETTING_LOCKED,
                    payload={
                        "key": key,
                        "layer": COMPANY.name,
                        "locked": locked,
                        "bounds": clean or None,
                        "reason": note,
                    },
                )
            ],
            actor=actor,
            source=source,
            correlation_id=correlation_id or new_ulid(),
            causation_id=causation_id,
        )
    return _view(uow.conn(), defn, COMPANY)


def revert_setting(
    uow: UnitOfWork,
    *,
    key: str,
    layer: str,
    seq: int,
    actor: str,
    source: str,
    reason: str | None = None,
    accept_risk: bool = False,
) -> EffectiveSetting:
    """Undo the change at ``seq`` (a row of :func:`~tl_core.settings.resolver.history`).

    The layer goes back to what that change replaced: the old value, or inheriting if the layer
    held none. A change that has not taken effect yet (scheduled) is cancelled by recording the
    old state for the same instant, which wins the tie because it was recorded later. The risk
    rules apply as for :func:`set_setting`. Raises ``SettingChangeNotFoundError``.
    """
    _, ref = _writable(key, layer)
    row = (
        uow.conn()
        .execute(
            text(
                "SELECT old_value_json, old_set, effective_us, applies_at FROM cur_setting "
                "WHERE key = :key AND layer = :layer AND seq = :seq"
            ),
            {"key": key, "layer": ref.name, "seq": seq},
        )
        .first()
    )
    if row is None:
        raise SettingChangeNotFoundError(f"{key} has no change at seq {seq} on layer {ref.name}")
    pending = int(row.effective_us) > to_us(utcnow())
    when = datetime.fromisoformat(str(row.applies_at)) if pending else None
    if bool(row.old_set):
        old = row.old_value_json
        return set_setting(
            uow,
            key=key,
            layer=layer,
            value=json.loads(old) if isinstance(old, (str, bytes, bytearray)) else old,
            actor=actor,
            source=source,
            reason=reason,
            accept_risk=accept_risk,
            applies_at=when,
        )
    return reset_setting(
        uow,
        key=key,
        layer=layer,
        actor=actor,
        source=source,
        reason=reason,
        accept_risk=accept_risk,
        applies_at=when,
    )
