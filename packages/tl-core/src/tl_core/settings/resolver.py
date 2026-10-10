"""Layer resolution of settings (brief 30.2): the effective value, its origin, locks and bounds.

``resolve_from`` is the pure rule; the functions with a ``conn`` read ``cur_setting`` (one row per
``Setting.Changed`` event), ``cur_setting_lock`` and ``setting_effect_applied`` and call it. The
:class:`~tl_core.settings.reader.SettingsReader` calls the same rule over a cached snapshot.

The rules, in the order they apply for a key at time ``t``:

1. **Entries.** At each layer the entry in force is the one with the greatest ``effective_us``
   (then ``seq``) that is not after ``t``. A scheduled change (``applies_at`` in the future) is
   in no layer's force until then: resolution is time-based and no job applies it. A *reset*
   entry in force means the layer holds no value of its own.
2. **Layers.** Most specific first: ``user`` (UI keys only), ``project``, ``company``, then the
   platform default. A layer the definition's ``scopes`` do not allow is ignored.
3. **Locks.** If the company locked the key, the project and user entries are ignored; if the
   company bounded it, an entry outside the bounds is ignored (bounds are enforced when a value is
   set, and again here, so a lock set after a value takes effect at once).
4. **Viewed layer.** ``modified_here`` (the ● marker) and ``scheduled`` describe the most specific
   layer asked for that the key allows: the user layer when ``user`` is given and the key is a UI
   key, else the project layer when ``project`` is given, else the company layer.
5. **Pending effect.** A key whose ``effect`` is not ``live`` owes that effect while one of its
   changes took effect after the effect was last carried out (``setting_effect_applied``).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, text

from tl_core.services.errors import SettingScopeError
from tl_core.settings.instants import from_us, to_us, to_z
from tl_core.settings.layers import allows_layer, parse_layer
from tl_core.settings.registry import definitions, get_definition
from tl_core.settings.types import (
    EffectiveSetting,
    Origin,
    ScheduledChange,
    SettingChange,
    SettingDefinition,
    SettingDiff,
    SettingEffect,
)
from tl_core.settings.values import within_bounds
from tl_core.util import utcnow

_ENTRIES_SQL = (
    "SELECT key, layer, seq, effective_us, reset, value_json, applies_at FROM cur_setting"
)
_LOCKS_SQL = text("SELECT key, locked, bounds_json FROM cur_setting_lock")
_APPLIED_SQL = text("SELECT effect, applied_seq, applied_us FROM setting_effect_applied")
_HISTORY_SQL = (
    "SELECT seq, key, layer, old_value_json, value_json, reset, actor, reason, recorded_at, "
    "applies_at FROM cur_setting WHERE key = :key"
)


@dataclass(frozen=True)
class Entry:
    """One ``Setting.Changed`` as the resolver sees it."""

    layer: str
    seq: int
    effective_us: int
    reset: bool
    value: Any
    applies_at: str | None = None


@dataclass(frozen=True)
class Lock:
    locked: bool = False
    bounds: dict[str, Any] | None = None


NO_LOCK = Lock()


@dataclass(frozen=True)
class Snapshot:
    """Everything the resolver reads, for any number of keys."""

    entries: Mapping[str, Sequence[Entry]] = field(default_factory=lambda: {})
    locks: Mapping[str, Lock] = field(default_factory=lambda: {})
    applied: Mapping[str, tuple[int, int]] = field(default_factory=lambda: {})

    def next_change_us(self, key: str, after_us: int) -> int | None:
        """The earliest instant after ``after_us`` at which a scheduled entry of ``key`` begins."""
        later = [e.effective_us for e in self.entries.get(key, ()) if e.effective_us > after_us]
        return min(later) if later else None


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, (str, bytes, bytearray)) else value


def load_snapshot(conn: Connection, keys: Sequence[str] | None = None) -> Snapshot:
    """Read the setting tables (all keys, or only ``keys``) into a :class:`Snapshot`."""
    params: dict[str, Any] = {}
    sql = _ENTRIES_SQL
    if keys is not None:
        marks = ", ".join(f":k{i}" for i in range(len(keys)))
        if not keys:
            return Snapshot()
        sql += f" WHERE key IN ({marks})"
        params = {f"k{i}": key for i, key in enumerate(keys)}
    rows = conn.execute(text(sql + " ORDER BY seq"), params).all()
    entries: dict[str, list[Entry]] = {}
    for row in rows:
        entries.setdefault(row.key, []).append(
            Entry(
                layer=row.layer,
                seq=int(row.seq),
                effective_us=int(row.effective_us),
                reset=bool(row.reset),
                value=_json(row.value_json),
                applies_at=None if row.applies_at is None else to_z(str(row.applies_at)),
            )
        )
    locks: dict[str, Lock] = {}
    for row in conn.execute(_LOCKS_SQL).all():
        if keys is None or row.key in keys:
            bounds = _json(row.bounds_json) if row.bounds_json is not None else None
            locks[row.key] = Lock(bool(row.locked), bounds if isinstance(bounds, dict) else None)  # pyright: ignore[reportUnknownArgumentType]
    applied = {
        str(row.effect): (int(row.applied_seq), int(row.applied_us))
        for row in conn.execute(_APPLIED_SQL).all()
    }
    return Snapshot(entries, locks, applied)


def in_force(entries: Sequence[Entry], layer: str, at_us: int) -> Entry | None:
    """The entry of ``layer`` that is in force at ``at_us``, or None (a reset is an entry too)."""
    found: Entry | None = None
    for entry in entries:
        if entry.layer != layer or entry.effective_us > at_us:
            continue
        if found is None or (entry.effective_us, entry.seq) > (found.effective_us, found.seq):
            found = entry
    return found


def _usable(
    defn: SettingDefinition, lock: Lock, entry: Entry | None, project_or_user: bool
) -> bool:
    """Whether the entry in force gives its layer a value (it is not a reset, a lock or bounds)."""
    if entry is None or entry.reset:
        return False
    if project_or_user and (lock.locked or not within_bounds(defn, lock.bounds, entry.value)):
        return False
    return True


def pending_effect(
    defn: SettingDefinition,
    entries: Sequence[Entry],
    applied: Mapping[str, tuple[int, int]],
    at_us: int,
) -> SettingEffect | None:
    """The effect ``defn`` still owes, or None (a live key, or the effect was carried out)."""
    if defn.effect == "live":
        return None
    seq_done, us_done = applied.get(defn.effect, (0, 0))
    # a `rebuild` also reindexes, so it satisfies a `reindex` key
    if defn.effect == "reindex" and "rebuild" in applied:
        seq_done = max(seq_done, applied["rebuild"][0])
        us_done = max(us_done, applied["rebuild"][1])
    for entry in entries:
        if entry.effective_us <= at_us and (entry.seq > seq_done or entry.effective_us > us_done):
            return defn.effect
    return None


def viewed_layer(defn: SettingDefinition, project: str | None, user: str | None) -> str | None:
    """The layer ``modified_here`` and ``scheduled`` describe (rule 4), or None for none."""
    if user is not None and allows_layer(defn, "user"):
        return f"user:{user}"
    if project is not None and allows_layer(defn, "project"):
        return f"project:{project}"
    if allows_layer(defn, "company"):
        return "company"
    return None


def resolve_from(
    defn: SettingDefinition,
    snapshot: Snapshot,
    *,
    project: str | None = None,
    user: str | None = None,
    at_us: int,
) -> EffectiveSetting:
    """The effective setting of ``defn`` in ``snapshot`` at ``at_us`` (see the module docstring)."""
    entries = snapshot.entries.get(defn.key, ())
    lock = snapshot.locks.get(defn.key, NO_LOCK)
    candidates: list[tuple[str, Origin, bool]] = []
    if user is not None and allows_layer(defn, "user"):
        candidates.append((f"user:{user}", "user", True))
    if project is not None and allows_layer(defn, "project"):
        candidates.append((f"project:{project}", "project", True))
    if allows_layer(defn, "company"):
        candidates.append(("company", "company", False))
    value: Any = defn.default
    origin: Origin = "default"
    for layer, kind, lower in candidates:
        entry = in_force(entries, layer, at_us)
        if _usable(defn, lock, entry, lower):
            assert entry is not None
            value, origin = entry.value, kind
            break
    viewed = viewed_layer(defn, project, user)
    modified_here = False
    scheduled: list[ScheduledChange] = []
    if viewed is not None:
        here = in_force(entries, viewed, at_us)
        modified_here = _usable(defn, lock, here, viewed != "company")
        later = sorted(
            (e for e in entries if e.layer == viewed and e.effective_us > at_us),
            key=lambda e: (e.effective_us, e.seq),
        )
        scheduled = [
            ScheduledChange(
                applies_at=e.applies_at or to_z(from_us(e.effective_us)),
                new_value=None if e.reset else e.value,
                seq=e.seq,
            )
            for e in later
        ]
    return EffectiveSetting(
        key=defn.key,
        value=value,
        origin=origin,
        modified_here=modified_here,
        locked=lock.locked,
        bounds=lock.bounds if lock.bounds else None,
        scheduled=scheduled,
        pending_effect=pending_effect(defn, entries, snapshot.applied, at_us),
    )


def _at_us(at: datetime | None) -> int:
    return to_us(at if at is not None else utcnow())


def resolve(
    conn: Connection,
    key: str,
    *,
    project: str | None = None,
    user: str | None = None,
    at: datetime | None = None,
) -> EffectiveSetting:
    """The effective setting of ``key`` for ``project`` and ``user`` at ``at`` (default now).

    Raises ``UnknownSettingError`` for a key with no definition.
    """
    defn = get_definition(key)
    snapshot = load_snapshot(conn, [key])
    return resolve_from(defn, snapshot, project=project, user=user, at_us=_at_us(at))


def value_of(
    conn: Connection,
    key: str,
    *,
    project: str | None = None,
    user: str | None = None,
    at: datetime | None = None,
) -> Any:
    """Just the effective value of :func:`resolve`."""
    return resolve(conn, key, project=project, user=user, at=at).value


def resolve_all(
    conn: Connection,
    *,
    project: str | None = None,
    user: str | None = None,
    prefix: str | None = None,
    at: datetime | None = None,
) -> list[EffectiveSetting]:
    """Every setting (or those whose key starts with ``prefix``), sorted by key."""
    snapshot = load_snapshot(conn)
    when = _at_us(at)
    return [
        resolve_from(defn, snapshot, project=project, user=user, at_us=when)
        for key, defn in definitions().items()
        if prefix is None or key.startswith(prefix)
    ]


def history(conn: Connection, key: str, *, layer: str | None = None) -> list[SettingChange]:
    """Every change of ``key`` (at ``layer``, when given), oldest first.

    A scheduled change shows here from the moment it is recorded, with its ``applies_at``.
    Raises ``UnknownSettingError``, and ``SettingScopeError`` for a malformed ``layer``.
    """
    get_definition(key)
    sql = _HISTORY_SQL
    params: dict[str, Any] = {"key": key}
    if layer is not None:
        params["layer"] = parse_layer(layer).name
        sql += " AND layer = :layer"
    rows = conn.execute(text(sql + " ORDER BY seq"), params).all()
    return [
        SettingChange(
            seq=int(row.seq),
            key=row.key,
            layer=row.layer,
            old_value=_json(row.old_value_json),
            new_value=_json(row.value_json),
            reset=bool(row.reset),
            actor=row.actor,
            reason=row.reason,
            recorded_at=to_z(str(row.recorded_at)),
            applies_at=None if row.applies_at is None else to_z(str(row.applies_at)),
        )
        for row in rows
    ]


def _view_of(layer: str) -> tuple[bool, str | None, str | None]:
    """``(use_company_layer, project, user)`` for a layer name of :func:`diff`."""
    if layer == "default":
        return False, None, None
    ref = parse_layer(layer)
    if ref.kind == "company":
        return True, None, None
    if ref.kind == "project":
        return True, ref.ident, None
    return True, None, ref.ident


def diff(conn: Connection, *, left: str, right: str) -> list[SettingDiff]:
    """The keys whose effective value differs between two layers, sorted by key.

    A layer is ``default`` (the platform defaults), ``company``, ``project:<id>`` (the project
    with the company beneath it) or ``user:<id>``. Raises ``SettingScopeError`` for any other.
    """
    snapshot = load_snapshot(conn)
    when = _at_us(None)
    views: list[tuple[bool, str | None, str | None]] = []
    for name in (left, right):
        try:
            views.append(_view_of(name))
        except SettingScopeError:
            raise SettingScopeError(
                f"{name!r} is not a layer: use default, company, project:<id> or user:<id>"
            ) from None
    found: list[SettingDiff] = []
    for defn in definitions().values():
        sides: list[EffectiveSetting] = []
        for use_company, project, user in views:
            source = snapshot if use_company else Snapshot(locks=snapshot.locks)
            sides.append(resolve_from(defn, source, project=project, user=user, at_us=when))
        if sides[0].value != sides[1].value:
            found.append(SettingDiff(key=defn.key, left=sides[0], right=sides[1]))
    return found
