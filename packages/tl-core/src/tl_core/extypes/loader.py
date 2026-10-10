"""Load a registered type back from its package files, verified (brief 31.1, 27.3).

A registration holds metadata only; the compiled class comes from the files at ``location_uri``.
``TypeLoader.load`` re-reads them, checks that they still hash to the registered ``content_hash``
and compile to the registered ``schema_hash``, and caches the result by those hashes ("compiled
artefacts are cached by hash"). A type whose files moved or changed is *unavailable*, with the
reason: it leaves the effective schema and takes no new instances, until the files are restored or
a new version is registered. Existing records stay readable.

Only ``file://`` locations are read in v0; an ``s3://`` prefix comes with the bucket watcher.
"""

from __future__ import annotations

import threading
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

from tl_schema.packages import PackageDoc

from tl_core.extypes.compile import compile_type, to_package_doc
from tl_core.extypes.lock import compute_lock, content_hash
from tl_core.extypes.model import CompiledType
from tl_core.extypes.names import LayoutError, parse_type_ref
from tl_core.extypes.types import TypeRegistration


@dataclass(frozen=True)
class LoadedType:
    registration: TypeRegistration
    compiled: CompiledType
    document: PackageDoc


@dataclass(frozen=True)
class Unavailable:
    registration: TypeRegistration
    reason: str


def package_path(location_uri: str) -> Path | None:
    """The directory a ``file://`` location names, or ``None`` for any other scheme."""
    parts = urllib.parse.urlsplit(location_uri)
    if parts.scheme != "file":
        return None
    return Path(urllib.parse.unquote(parts.path))


class TypeLoader:
    """Thread-safe cache of loaded types, keyed by type ref, content hash and schema hash."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loaded: dict[tuple[str, str, str], LoadedType] = {}

    def load(self, registration: TypeRegistration) -> LoadedType | Unavailable:
        key = (registration.type_ref, registration.content_hash, registration.schema_hash)
        with self._lock:
            hit = self._loaded.get(key)
        if hit is not None:
            return hit
        result = self._read(registration)
        if isinstance(result, LoadedType):
            with self._lock:
                self._loaded[key] = result
        return result

    def forget(self) -> None:
        with self._lock:
            self._loaded.clear()

    @staticmethod
    def _read(registration: TypeRegistration) -> LoadedType | Unavailable:
        def gone(reason: str) -> Unavailable:
            return Unavailable(registration, reason)

        path = package_path(registration.location_uri)
        if path is None:
            return gone(f"location {registration.location_uri!r} is not a file:// location")
        if not path.is_dir():
            return gone("the package directory is missing")
        files, issues = compute_lock(path)
        if issues:
            return gone(f"{issues[0].path}: {issues[0].detail}")
        if content_hash(files) != registration.content_hash:
            return gone("the package files changed since they were registered")
        try:
            coords = parse_type_ref(registration.type_ref)
        except LayoutError as exc:
            return gone(str(exc))
        compiled, problems = compile_type(path, coords, lint=False)
        if compiled is None:
            return gone(f"does not compile: {problems[0].detail if problems else 'unknown'}")
        if compiled.schema_hash() != registration.schema_hash:
            return gone("the compiled class differs from the registered schema hash")
        return LoadedType(registration, compiled, to_package_doc(compiled))


_default = TypeLoader()


def default_loader() -> TypeLoader:
    """The process-wide loader the schema provider and the record services share."""
    return _default
