"""Thread settings (brief 21.5; ``schema/settings/platform.yaml``).

Every reader goes through these functions, which read the settings in force for a scope inside the
caller's transaction: a change applies to the next call, with no restart. A thread needs
``threads.enabled`` and its record type in ``threads.enabled_types`` (an empty list lists no type).
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import Connection

from tl_core.integration.contract import Access
from tl_core.settings.layers import project_of_scope
from tl_core.settings.resolver import value_of
from tl_core.threads.contract import (
    SETTING_AGENTS_CAN_DISPATCH,
    SETTING_DISPATCH_ENABLED,
    SETTING_DISPATCH_ROLES,
    SETTING_ENABLED,
    SETTING_ENABLED_TYPES,
)


def threads_enabled(conn: Connection, scope: str, record_type: str) -> bool:
    """Whether records of ``record_type`` in ``scope`` have a thread."""
    project = project_of_scope(scope)
    if not bool(value_of(conn, SETTING_ENABLED, project=project)):
        return False
    types = [str(t) for t in value_of(conn, SETTING_ENABLED_TYPES, project=project)]
    return record_type in types


def dispatch_enabled(conn: Connection, scope: str) -> bool:
    return bool(value_of(conn, SETTING_DISPATCH_ENABLED, project=project_of_scope(scope)))


def dispatch_roles(conn: Connection, scope: str) -> tuple[str, ...]:
    """The role names allowed to dispatch; empty means any signed-in person."""
    found = value_of(conn, SETTING_DISPATCH_ROLES, project=project_of_scope(scope))
    return tuple(str(role) for role in found)


def agents_can_dispatch(conn: Connection, scope: str) -> bool:
    """Whether an agent may propose a dispatch (``propose``); ``none`` refuses the tool."""
    value = value_of(conn, SETTING_AGENTS_CAN_DISPATCH, project=project_of_scope(scope))
    return str(value) == "propose"


def role_may_dispatch(roles: tuple[str, ...], holds: Callable[[Access], bool]) -> bool:
    """Whether a caller holding what ``holds`` says may dispatch under ``roles``.

    Empty ``roles`` allows any signed-in person. ``user`` is any signed-in person, ``admin`` is the
    admin role and ``document_controller`` is an admin or a document controller (the same meaning
    ``holds("controller")`` has everywhere else, ADR-0013). The caller's roles are never passed in
    as data: ``holds`` comes from the client layer (ADR-0014 section 8).
    """
    if not roles:
        return True
    return (
        ("user" in roles and holds("user"))
        or ("document_controller" in roles and holds("controller"))
        or ("admin" in roles and holds("admin"))
    )
