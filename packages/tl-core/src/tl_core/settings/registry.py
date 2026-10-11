"""The setting definitions in force: the platform file plus what extension types register.

Definitions are data (P0-I8 decision D1). ``schema/settings/platform.yaml`` lists the platform's
keys under a top-level ``settings:``; an extension type package ships a ``settings.yaml`` in the
same shape and registers it with :func:`register_definitions`. Both are checked against
:class:`~tl_core.settings.types.SettingDefinition` (a test keeps it in agreement with the LinkML
class ``SettingDefinition`` in ``schema/core/settings.yaml``) and against
:func:`~tl_core.settings.values.check_definition`: a coherent definition whose default is a valid
value.

The registry is process-wide. The platform file is read on first use (``TL_SETTINGS_PLATFORM_FILE``
names another file). :func:`use_definitions` swaps it for a block, which tests rely on.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import ValidationError

from tl_core.extypes.names import snake_case
from tl_core.services.errors import UnknownSettingError
from tl_core.settings.types import SettingDefinition
from tl_core.settings.values import check_definition

PLATFORM_FILE_ENV = "TL_SETTINGS_PLATFORM_FILE"
PLATFORM_OWNER = "platform"
_REPO_ROOT = Path(__file__).resolve().parents[5]
DEFAULT_PLATFORM_FILE = _REPO_ROOT / "schema" / "settings" / "platform.yaml"


class SettingDefinitionError(ValueError):
    """A definition file or a registration is not acceptable. The message names the key."""


def parse_definitions(
    text: str, *, source: str = "<string>", owner: str = PLATFORM_OWNER
) -> list[SettingDefinition]:
    """The definitions in a YAML document ``{settings: [ {key: ..., ...}, ... ]}``.

    Each entry becomes a ``SettingDefinition`` with ``owner`` filled in when the entry names none.
    Raises ``SettingDefinitionError`` (message starts with ``source``) for invalid YAML, a document
    that is not that shape, an unknown field, a field that fails validation, an incoherent
    definition or a repeated key.
    """
    try:
        document: Any = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SettingDefinitionError(f"{source}: invalid YAML: {exc}") from exc
    shape = cast("dict[str, Any]", document) if isinstance(document, dict) else {}
    if not isinstance(shape.get("settings"), list):
        raise SettingDefinitionError(f"{source}: expected a mapping with a `settings:` list")
    listed = cast("list[Any]", shape["settings"])
    known = set(SettingDefinition.model_fields)
    found: list[SettingDefinition] = []
    seen: set[str] = set()
    for index, entry in enumerate(listed):
        where = f"{source}: settings[{index}]"
        if not isinstance(entry, dict):
            raise SettingDefinitionError(f"{where} is not a mapping")
        data = {str(k): v for k, v in cast("dict[Any, Any]", entry).items()}
        unknown = sorted(set(data) - known)
        if unknown:
            raise SettingDefinitionError(f"{where} ({data.get('key')}): unknown fields {unknown}")
        data.setdefault("owner", owner)
        try:
            defn = SettingDefinition.model_validate(data)
            check_definition(defn)
        except ValidationError as exc:
            problems = "; ".join(
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
            )
            raise SettingDefinitionError(f"{where} ({data.get('key')}): {problems}") from exc
        except ValueError as exc:
            raise SettingDefinitionError(f"{where}: {exc}") from exc
        if defn.key in seen:
            raise SettingDefinitionError(f"{where}: the key {defn.key} is defined twice")
        seen.add(defn.key)
        found.append(defn)
    return found


def load_definitions(path: Path, *, owner: str = PLATFORM_OWNER) -> list[SettingDefinition]:
    """:func:`parse_definitions` of a file."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SettingDefinitionError(f"{path}: cannot read the file: {exc.strerror}") from exc
    return parse_definitions(text, source=str(path), owner=owner)


def platform_file() -> Path:
    configured = os.environ.get(PLATFORM_FILE_ENV, "").strip()
    return Path(configured) if configured else DEFAULT_PLATFORM_FILE


class _Registry:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.platform: dict[str, SettingDefinition] | None = None
        self.extensions: dict[str, dict[str, SettingDefinition]] = {}

    def platform_defs(self) -> dict[str, SettingDefinition]:
        if self.platform is None:
            self.platform = {d.key: d for d in load_definitions(platform_file())}
        return self.platform


_registry = _Registry()


def definitions() -> dict[str, SettingDefinition]:
    """Every definition in force, platform and extension types, by key, sorted by key."""
    with _registry.lock:
        merged: dict[str, SettingDefinition] = {}
        for owned in _registry.extensions.values():
            merged.update(owned)
        merged.update(_registry.platform_defs())  # a platform key always wins, as in get_definition
        return dict(sorted(merged.items()))


def get_definition(key: str) -> SettingDefinition:
    """The definition of ``key``; raises ``UnknownSettingError``."""
    with _registry.lock:
        found = _registry.platform_defs().get(key)
        if found is None:
            for owned in _registry.extensions.values():
                found = owned.get(key)
                if found is not None:
                    break
    if found is None:
        raise UnknownSettingError(f"there is no setting {key!r}")
    return found


def namespace_of(owner: str) -> str:
    """``co.acme`` for the extension type ``co.acme.LiftPlan``: the namespace of its keys."""
    head, dot, _ = owner.rpartition(".")
    if not dot or not head:
        raise SettingDefinitionError(f"{owner!r} is not '<namespace>.<TypeName>'")
    return head


def key_prefix(owner: str) -> str:
    """``co.acme.lift_plan.`` for ``co.acme.LiftPlan``: how its keys start (decision D15).

    The type's own name is part of the prefix, so two types of one namespace cannot take each
    other's keys, and a one-segment namespace (``co``) cannot reach ``co.acme.`` keys.
    """
    return f"{namespace_of(owner)}.{snake_case(owner.rpartition('.')[2])}."


def register_definitions(defs: Iterable[SettingDefinition], *, owner: str) -> None:
    """Register an extension type's keys (brief 31.1). ``owner`` is ``<namespace>.<TypeName>``.

    Every key must start with the type's namespace and snake-cased name (``co.acme.lift_plan.``
    for ``co.acme.LiftPlan``, decision D15), and the first segment of a namespace is never a
    platform one (``feed``, ``ui``, ... are reserved type namespaces), so a type's keys can neither
    shadow a platform key nor another type's. A secret definition is refused (a vault is a human
    gate). A key that another owner or the platform already defines raises
    ``SettingDefinitionError`` and nothing is registered.
    Registering an owner again replaces its earlier definitions (a type sync is idempotent).
    ``owner`` ``platform`` is refused: platform keys come from the platform file.
    """
    if owner == PLATFORM_OWNER:
        raise SettingDefinitionError("platform keys come from schema/settings/platform.yaml")
    prefix = key_prefix(owner)
    accepted: dict[str, SettingDefinition] = {}
    for defn in defs:
        claimed = defn.model_copy(update={"owner": owner}) if defn.owner == PLATFORM_OWNER else defn
        if claimed.owner != owner:
            raise SettingDefinitionError(f"{defn.key}: owner {claimed.owner!r} is not {owner!r}")
        if defn.sensitivity == "secret":
            raise SettingDefinitionError(f"{defn.key}: secret settings are not available")
        if not defn.key.startswith(prefix):
            raise SettingDefinitionError(f"{defn.key}: keys of {owner} must start with {prefix!r}")
        try:
            check_definition(claimed)
        except ValueError as exc:
            raise SettingDefinitionError(str(exc)) from exc
        if defn.key in accepted:
            raise SettingDefinitionError(f"{defn.key}: defined twice")
        accepted[defn.key] = claimed
    with _registry.lock:
        taken = set(_registry.platform_defs())
        for other, owned in _registry.extensions.items():
            if other != owner:
                taken |= set(owned)
        clash = sorted(set(accepted) & taken)
        if clash:
            raise SettingDefinitionError(f"already defined by another owner: {clash}")
        _registry.extensions[owner] = accepted


def unregister_definitions(owner: str) -> None:
    """Forget an extension type's keys (it was deprecated or quarantined). Stored values stay."""
    with _registry.lock:
        _registry.extensions.pop(owner, None)


@contextmanager
def use_definitions(
    platform: Iterable[SettingDefinition], *extensions: tuple[str, Iterable[SettingDefinition]]
) -> Generator[None]:
    """Replace the whole registry for a block: ``platform`` keys, then ``(owner, defs)`` pairs."""
    with _registry.lock:
        saved = (_registry.platform, _registry.extensions)
        _registry.platform = {d.key: d for d in platform}
        _registry.extensions = {}
    try:
        for owner, defs in extensions:
            register_definitions(defs, owner=owner)
        yield
    finally:
        with _registry.lock:
            _registry.platform, _registry.extensions = saved
