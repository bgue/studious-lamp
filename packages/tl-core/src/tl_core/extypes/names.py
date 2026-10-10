"""Names of extension types: type refs, record types, pset names, stream ids (brief 31, FANOUT D7).

``co.acme.LiftPlan@1.0.0`` is a *type ref* (a registered version). ``co.acme.LiftPlan`` is the
*type name*: what ``CreateRecord.record_type`` and a record's ``type`` hold. The index fields of an
instance live in the pset ``co_acme_lift_plan``, named for the type, so the query language
filters them like any pset value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tl_schema.packages import version_tuple

#: Dotted lower-case segments, for example ``co.acme``. No underscores, so pset names never
#: contain a double underscore.
NAMESPACE_PATTERN = re.compile(r"[a-z][a-z0-9]*(?:\.[a-z][a-z0-9]*)*")
#: UpperCamelCase, for example ``LiftPlan``.
NAME_PATTERN = re.compile(r"[A-Z][A-Za-z0-9]*")
VERSION_PATTERN = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
_TYPE_NAME = re.compile(
    r"(?P<namespace>[a-z][a-z0-9]*(?:\.[a-z][a-z0-9]*)*)\.(?P<name>[A-Z][A-Za-z0-9]*)"
)
_TYPE_REF = re.compile(
    r"(?P<type_name>[a-z][a-z0-9]*(?:\.[a-z][a-z0-9]*)*\.[A-Z][A-Za-z0-9]*)"
    r"@(?P<version>(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))"
)
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

#: Namespaces the platform keeps for itself; a package cannot register a type in them.
RESERVED_NAMESPACES = frozenset({"core", "tl", "throughline"})

STREAM_TYPE = "core.TypeRegistration"
STREAM_PREFIX = "type:"
#: Registrations are company-wide: a type is registered once and its instances live in any scope.
REGISTRY_SCOPE = "company"


class LayoutError(ValueError):
    """A package directory is not ``<namespace>/<Name>/<version>/``."""


@dataclass(frozen=True)
class Coordinates:
    namespace: str
    name: str
    version: str

    @property
    def type_name(self) -> str:
        return f"{self.namespace}.{self.name}"

    @property
    def type_ref(self) -> str:
        return f"{self.namespace}.{self.name}@{self.version}"


def snake_case(name: str) -> str:
    """``LiftPlan`` becomes ``lift_plan``; ``HTTPServer`` becomes ``http_server``."""
    return _CAMEL_BOUNDARY.sub("_", name).lower()


def pset_name(namespace: str, name: str) -> str:
    """The pset that holds the index fields of ``namespace.name``: ``co_acme_lift_plan``."""
    return f"{namespace.replace('.', '_')}_{snake_case(name)}"


def stream_id(type_ref: str) -> str:
    """The ledger stream of a registration: ``type:co.acme.LiftPlan@1.0.0``."""
    return f"{STREAM_PREFIX}{type_ref}"


def coordinates(namespace: str, name: str, version: str) -> Coordinates:
    """Validated coordinates; raises ``LayoutError`` naming the bad part."""
    if NAMESPACE_PATTERN.fullmatch(namespace) is None:
        raise LayoutError(
            f"namespace {namespace!r} must be dotted lower-case segments such as 'co.acme'"
        )
    if namespace.split(".")[0] in RESERVED_NAMESPACES:
        raise LayoutError(f"namespace {namespace!r} is reserved for the platform")
    if NAME_PATTERN.fullmatch(name) is None:
        raise LayoutError(f"type name {name!r} must be UpperCamelCase such as 'LiftPlan'")
    if VERSION_PATTERN.fullmatch(version) is None:
        raise LayoutError(f"version {version!r} must be MAJOR.MINOR.PATCH")
    return Coordinates(namespace, name, version)


def parse_type_ref(type_ref: str) -> Coordinates:
    """``co.acme.LiftPlan@1.0.0`` to its coordinates; raises ``LayoutError`` when malformed."""
    found = _TYPE_REF.fullmatch(type_ref)
    if found is None:
        raise LayoutError(f"{type_ref!r} is not a type ref such as 'co.acme.LiftPlan@1.0.0'")
    namespace, name = split_type_name(found["type_name"])
    return Coordinates(namespace, name, found["version"])


def split_type_name(type_name: str) -> tuple[str, str]:
    """``co.acme.LiftPlan`` to ``("co.acme", "LiftPlan")``; ``LayoutError`` when malformed."""
    found = _TYPE_NAME.fullmatch(type_name)
    if found is None:
        raise LayoutError(f"{type_name!r} is not a type name such as 'co.acme.LiftPlan'")
    return found["namespace"], found["name"]


def package_coordinates(root: Path, path: Path) -> Coordinates:
    """Coordinates of the package at ``path`` below ``root`` (``<namespace>/<Name>/<version>``)."""
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError:
        raise LayoutError(f"{path} is not below {root}") from None
    parts = relative.parts
    if len(parts) != 3:
        raise LayoutError(
            f"{relative.as_posix()}: a package sits at <namespace>/<Name>/<version>, "
            f"not {len(parts)} levels below the root"
        )
    return coordinates(parts[0], parts[1], parts[2])


def invalid_ref(root: Path, path: Path) -> str:
    """The stand-in type ref of a package whose path is not a package path."""
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        relative = path.name
    return f"invalid:{relative}"


def version_key(version: str) -> tuple[int, int, int]:
    return version_tuple(version)
