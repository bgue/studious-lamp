"""Export and import of one layer's settings as YAML (brief 30.4: templates and reviews).

The document::

    version: 1
    layer: project:P123
    settings:
      feed.reactions.enabled: false
      webhooks.retry.max_hours: 48
    locks:                      # company layer only
      ai.agents.default_mode: {bounds: null, locked: true}

``export_yaml`` writes the values the layer holds of its own (in force now; scheduled changes are
not exported) and, for the company, the locks and bounds. ``import_yaml`` sets every listed key at a
layer, in the caller's unit of work, so one refused key refuses the whole file once the caller's
block rolls back. The file's own ``layer`` is informational: a project's export is a template that
may be imported into another project. Keys already holding the listed value are left alone, so
importing an export back changes nothing.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, cast

import yaml
from sqlalchemy import Connection

from tl_core.services.errors import SettingsDocumentError
from tl_core.settings.instants import to_us
from tl_core.settings.layers import parse_layer
from tl_core.settings.registry import definitions, get_definition
from tl_core.settings.resolver import in_force, load_snapshot
from tl_core.settings.service import lock_setting, set_setting
from tl_core.settings.types import EffectiveSetting
from tl_core.uow import UnitOfWork
from tl_core.util import utcnow

FORMAT_VERSION = 1
MAX_DOCUMENT_CHARS = 262_144
MAX_KEYS = 1000
_TOP_KEYS = frozenset({"version", "layer", "settings", "locks"})
_LOCK_KEYS = frozenset({"locked", "bounds"})


def export_yaml(conn: Connection, *, layer: str) -> str:
    """The settings ``layer`` holds, and for the company its locks, as a YAML document.

    Keys are sorted, so two exports of the same state are identical text. Raises
    ``SettingScopeError`` for a malformed layer.
    """
    ref = parse_layer(layer)
    snapshot = load_snapshot(conn)
    now_us = to_us(utcnow())
    held: dict[str, Any] = {}
    for key in definitions():
        entry = in_force(snapshot.entries.get(key, ()), ref.name, now_us)
        if entry is not None and not entry.reset:
            held[key] = entry.value
    document: dict[str, Any] = {"version": FORMAT_VERSION, "layer": ref.name, "settings": held}
    if ref.kind == "company":
        locks = {
            key: {"locked": lock.locked, "bounds": lock.bounds}
            for key, lock in sorted(snapshot.locks.items())
            if key in definitions() and (lock.locked or lock.bounds)
        }
        if locks:
            document["locks"] = locks
    return yaml.safe_dump(document, sort_keys=True, allow_unicode=True, default_flow_style=False)


MAX_DEPTH = 12


def _refuse_aliases(text: str) -> None:
    """Raise ``SettingsDocumentError`` if the YAML uses an anchor or an alias.

    An alias lets a few hundred bytes expand to millions of items before any size check runs, and
    a settings file has no use for sharing structure.
    """
    try:
        events = cast("Iterator[Any]", yaml.parse(text, Loader=yaml.SafeLoader))  # pyright: ignore[reportUnknownMemberType]
        for event in events:
            if isinstance(event, yaml.AliasEvent) or getattr(event, "anchor", None) is not None:
                raise SettingsDocumentError("the settings file may not use YAML anchors or aliases")
    except yaml.YAMLError as exc:
        raise SettingsDocumentError(f"the settings file is not valid YAML: {exc}") from exc


def _json_only(where: str, value: Any, depth: int = 0) -> None:
    """Raise ``SettingsDocumentError`` unless ``value`` is plain JSON.

    YAML also makes dates, sets and bytes, which no setting holds.
    """
    if depth > MAX_DEPTH:
        raise SettingsDocumentError(f"{where} is nested deeper than {MAX_DEPTH} levels")
    if value is None or isinstance(value, (bool, str, int)):
        return
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise SettingsDocumentError(f"{where} is not a finite number")
        return
    if isinstance(value, list):
        for index, item in enumerate(cast("list[Any]", value)):
            _json_only(f"{where}[{index}]", item, depth + 1)
        return
    if isinstance(value, dict):
        for name, item in cast("dict[Any, Any]", value).items():
            if not isinstance(name, str):
                raise SettingsDocumentError(f"{where} has a key that is not text: {name!r}")
            _json_only(f"{where}.{name}", item, depth + 1)
        return
    raise SettingsDocumentError(
        f"{where} is a {type(value).__name__}, not JSON data; quote dates and times as text"
    )


def _document(text: str) -> dict[str, Any]:
    if len(text) > MAX_DOCUMENT_CHARS:
        raise SettingsDocumentError(
            f"the settings file is longer than {MAX_DOCUMENT_CHARS} characters"
        )
    _refuse_aliases(text)
    try:
        loaded: Any = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SettingsDocumentError(f"the settings file is not valid YAML: {exc}") from exc
    except (RecursionError, ValueError, OverflowError) as exc:
        # Nesting thousands of levels deep, or an integer of more than 4300 digits.
        raise SettingsDocumentError(
            f"the settings file cannot be read ({type(exc).__name__}): too deep or too large"
        ) from exc
    if not isinstance(loaded, dict):
        raise SettingsDocumentError("the settings file must be a mapping with a `settings:` key")
    document: dict[str, Any] = dict(loaded)  # pyright: ignore[reportUnknownArgumentType]
    unknown = sorted(str(k) for k in set(document) - _TOP_KEYS)
    if unknown:
        raise SettingsDocumentError(f"the settings file has unknown top-level keys: {unknown}")
    version = document.get("version", FORMAT_VERSION)
    if version != FORMAT_VERSION:
        raise SettingsDocumentError(f"unsupported settings file version {version!r}")
    for part in ("settings", "locks"):
        found = document.get(part)
        if found is not None and not isinstance(found, dict):
            raise SettingsDocumentError(f"`{part}:` must be a mapping")
    if len(document.get("settings") or {}) + len(document.get("locks") or {}) > MAX_KEYS:
        raise SettingsDocumentError(f"more than {MAX_KEYS} keys in one file")
    for part in ("settings", "locks"):
        mapping = cast("dict[Any, Any]", document.get(part) or {})
        for name, item in mapping.items():
            if not isinstance(name, str):
                raise SettingsDocumentError(f"`{part}:` has a key that is not text: {name!r}")
            _json_only(f"{part}.{name}", item)
    return document


def import_yaml(
    uow: UnitOfWork,
    text: str,
    *,
    layer: str,
    actor: str,
    source: str,
    reason: str | None = None,
    accept_risk: bool = False,
) -> list[EffectiveSetting]:
    """Apply a document to ``layer`` inside ``uow``; return the keys it names as seen at the layer.

    ``reason`` and ``accept_risk`` apply to every key and lock that needs them (an advanced or
    dangerous key, any lock). The first refusal raises (``SettingsDocumentError`` for a bad file,
    otherwise the error :func:`~tl_core.settings.service.set_setting` gives, which names the key)
    and the caller's block rolls back every earlier key of the file.
    """
    ref = parse_layer(layer)
    document = _document(text)
    values: dict[str, Any] = dict(document.get("settings") or {})
    locks: dict[str, Any] = dict(document.get("locks") or {})
    if locks and ref.kind != "company":
        raise SettingsDocumentError("locks can only be imported into the company layer")
    applied: list[EffectiveSetting] = []
    for key in sorted(str(k) for k in values):
        applied.append(
            set_setting(
                uow,
                key=key,
                layer=ref.name,
                value=values[key],
                actor=actor,
                source=source,
                reason=reason,
                accept_risk=accept_risk,
            )
        )
    for key in sorted(str(k) for k in locks):
        if not isinstance(locks[key], dict):
            raise SettingsDocumentError(f"locks.{key} must be a mapping with `locked` and `bounds`")
        spec = cast("dict[str, Any]", locks[key])
        if set(spec) - _LOCK_KEYS:
            raise SettingsDocumentError(f"locks.{key} must be a mapping with `locked` and `bounds`")
        get_definition(key)
        applied.append(
            lock_setting(
                uow,
                key=key,
                locked=bool(spec.get("locked", False)),
                bounds=spec.get("bounds"),
                actor=actor,
                source=source,
                reason=reason or "",
            )
        )
    return applied
