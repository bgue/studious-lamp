"""A setting as a screen, a table or an API answer shows it: the definition and its effective state.

Every surface (CLI, API, MCP, TUI) lists settings the same way, so the pairing lives here:
``SettingView`` holds the definition (type, description, risk, effect, scopes) next to the
:class:`~tl_core.settings.types.EffectiveSetting` for the project and user being looked at.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import Connection

from tl_core.settings.instants import to_us
from tl_core.settings.layers import parse_layer
from tl_core.settings.registry import definitions, get_definition
from tl_core.settings.resolver import load_snapshot, resolve_from
from tl_core.settings.types import EffectiveSetting, SettingDefinition
from tl_core.util import utcnow


class SettingView(BaseModel):
    definition: SettingDefinition
    effective: EffectiveSetting


def _at(at: datetime | None) -> int:
    return to_us(at if at is not None else utcnow())


def get_view(
    conn: Connection,
    key: str,
    *,
    project: str | None = None,
    user: str | None = None,
    at: datetime | None = None,
) -> SettingView:
    """One setting with its definition. Raises ``UnknownSettingError``."""
    defn = get_definition(key)
    snapshot = load_snapshot(conn, [key])
    return SettingView(
        definition=defn,
        effective=resolve_from(defn, snapshot, project=project, user=user, at_us=_at(at)),
    )


def view_at(conn: Connection, key: str, layer: str) -> SettingView:
    """``key`` as seen at ``layer``: the project or user the layer names (company: neither).

    ``layer`` is ``company``, ``project:<id>`` or ``user:<id>``; anything else raises
    ``SettingScopeError``. What a write answers with, so the caller sees the value it set.
    """
    ref = parse_layer(layer)
    return get_view(
        conn,
        key,
        project=ref.ident if ref.kind == "project" else None,
        user=ref.ident if ref.kind == "user" else None,
    )


def list_views(
    conn: Connection,
    *,
    project: str | None = None,
    user: str | None = None,
    prefix: str | None = None,
    modified_only: bool = False,
    at: datetime | None = None,
) -> list[SettingView]:
    """Every setting (or those starting with ``prefix``), sorted by key.

    ``modified_only`` keeps those set at the viewed layer (the ● marker), as about:config's
    "modified" filter does.
    """
    snapshot = load_snapshot(conn)
    when = _at(at)
    found: list[SettingView] = []
    for key, defn in definitions().items():
        if prefix is not None and not key.startswith(prefix):
            continue
        effective = resolve_from(defn, snapshot, project=project, user=user, at_us=when)
        if modified_only and not effective.modified_here:
            continue
        found.append(SettingView(definition=defn, effective=effective))
    return found
