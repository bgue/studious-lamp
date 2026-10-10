"""Setting definitions of extension types, kept in the settings registry (brief 31.1, 30).

A package may ship ``settings.yaml``: keys that start with the type's namespace (``co.acme.``).
``validate`` checks the file (``read_settings``); this module puts the keys of the registered types
into the process-wide settings registry (``tl_core.settings.registry``), under the type name as
owner, so ``tl config``, the API and the TUI list and validate them like platform keys.

The registry holds the keys of the *newest usable version of each type whose files still match the
registration*. ``refresh`` makes it so: it registers what is there, replaces what changed and
unregisters the types that left (deprecated and then gone, quarantined, files edited). A key that
another owner already defines is never registered: at ``sync`` the package is quarantined with a
``settings`` issue (``clash_issues``); if one appears at refresh (two registrations that predate the
check), it is logged and that type's settings are left out.

Stored values of a departed type stay in the ledger; they apply again when the type returns.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from tl_core.extypes.loader import package_path
from tl_core.extypes.names import Coordinates, LayoutError, parse_type_ref
from tl_core.extypes.types import TypeIssue, TypeRegistration, TypeView
from tl_core.extypes.validate import read_settings
from tl_core.settings.registry import (
    SettingDefinitionError,
    definitions,
    register_definitions,
    unregister_definitions,
)
from tl_core.settings.types import SettingDefinition

if TYPE_CHECKING:
    from tl_core.extypes.registry import UowFactory

log = logging.getLogger("tl_core.extypes")

_lock = threading.Lock()
_owners: set[str] = set()  # the type names this module has registered keys for

#: ``None`` when the files match the registration, else why not (``TypeLoader.verify``).
Verify = Callable[[TypeRegistration], str | None]


def _version_key(registration: TypeRegistration) -> tuple[int, ...]:
    return tuple(int(p) if p.isdigit() else 0 for p in registration.version.split("."))


def _newest(views: Iterable[TypeView]) -> dict[str, TypeRegistration]:
    """The newest version of each type name among ``views``."""
    newest: dict[str, TypeRegistration] = {}
    for view in views:
        registration = view.registration
        name = f"{registration.namespace}.{registration.name}"
        held = newest.get(name)
        if held is None or _version_key(registration) > _version_key(held):
            newest[name] = registration
    return newest


def _read(registration: TypeRegistration, verify: Verify) -> list[SettingDefinition]:
    """The definitions of one registered version; none when its files do not match or are bad."""
    problem = verify(registration)
    path = package_path(registration.location_uri)
    if problem is not None or path is None:
        return []
    try:
        coords = parse_type_ref(registration.type_ref)
    except LayoutError:
        return []
    found, issues = read_settings(path, coords)
    if issues:
        log.warning("%s: settings.yaml not registered: %s", registration.type_ref, issues[0].detail)
        return []
    return found


def refresh(views: Iterable[TypeView], verify: Verify) -> None:
    """Make the settings registry hold the keys of ``views``' newest versions, and no others."""
    desired = {name: _read(registration, verify) for name, registration in _newest(views).items()}
    with _lock:
        for owner in sorted(_owners - set(desired)):
            unregister_definitions(owner)
            _owners.discard(owner)
        for owner, found in sorted(desired.items()):
            if not found:
                unregister_definitions(owner)
                _owners.discard(owner)
                continue
            try:
                register_definitions(found, owner=owner)
            except SettingDefinitionError as exc:
                log.warning("%s: settings not registered: %s", owner, exc)
                unregister_definitions(owner)
                _owners.discard(owner)
            else:
                _owners.add(owner)


def refresh_from_ledger(factory: UowFactory, verify: Verify) -> None:
    """``refresh`` over the usable registrations of a ledger; a ledger that cannot be read changes
    nothing (an old ledger without the registry tables has no types, and no keys to remove)."""
    from tl_core.extypes import registry  # registry imports this module

    try:
        with factory(readonly=True) as uow:
            views = registry.usable_types(uow.conn())
    except Exception as exc:
        log.debug("extension type settings unavailable: %s", exc)
        return
    refresh(views, verify)


def clash_issues(package: Path, coords: Coordinates) -> list[TypeIssue]:
    """``settings`` issues for keys of ``package`` that another owner (or the platform) defines."""
    found, _ = read_settings(package, coords)
    owner = coords.type_name
    taken = {key: d.owner for key, d in definitions().items() if d.owner != owner}
    return [
        TypeIssue(
            kind="settings",
            path="settings.yaml",
            detail=f"key {d.key!r} is already defined by {taken[d.key]}",
        )
        for d in found
        if d.key in taken
    ]


def forget_all() -> None:
    """Unregister every key this module registered (tests)."""
    with _lock:
        for owner in sorted(_owners):
            unregister_definitions(owner)
        _owners.clear()
