"""Compose the effective schema of a scope from adopted package documents (brief 27.3).

``compose`` resolves psets (``tl_schema.compile``), applies project adoption, reads the conformance
settings and stamps the content hash. ``EffectiveCache`` keeps compiled artefacts keyed by that
hash, so a schema that did not change is never recompiled (brief 27.3, "cached by hash").
"""

from __future__ import annotations

import hashlib
import re
import threading
from collections.abc import Callable, Sequence
from importlib.resources import files
from typing import TypeVar, cast

from tl_schema.compile import SchemaCompileError, compile_psets
from tl_schema.effective import (
    EffectiveConformance,
    EffectivePset,
    EffectiveSchema,
    EffectiveWaiver,
    PackageRef,
    resolve_path,
    with_hash,
)
from tl_schema.packages import PackageDoc

T = TypeVar("T")

_SCOPE_PATTERN = re.compile(r"company|project:(?P<project>[A-Za-z0-9_.-]+)")


def core_digest() -> str:
    """Digest of the core schema release: SHA-256 hex of the committed core JSON Schema.

    Any change to ``schema/core`` that alters the generated JSON Schema changes every effective
    schema hash, because psets are composed on top of the core release (brief 27.3).
    """
    resource = files("tl_schema.generated").joinpath("json_schema", "core.schema.json")
    text = resource.read_text("utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def project_of(scope: str) -> str | None:
    """``"project:P123"`` becomes ``"P123"``; ``"company"`` becomes ``None``."""
    match = _SCOPE_PATTERN.fullmatch(scope)
    if match is None:
        raise ValueError(f"scope must be 'company' or 'project:<id>', got {scope!r}")
    return match["project"]


def _adopted(pset: EffectivePset) -> bool:
    """Whether a project gets this pset: mandatory and default psets, extended ones, its own."""
    return pset.layer == "project" or pset.extension is not None or pset.adoption != "optional"


def compose(docs: Sequence[PackageDoc], scope: str, *, core: str | None = None) -> EffectiveSchema:
    """The effective schema of ``scope`` from its adopted package documents.

    ``docs`` is the adopted set (one version per package); selecting it is the registry's job. A
    company scope keeps every pset; a project scope drops optional company psets it does not extend.
    Waiver paths must name existing properties. Raises ``SchemaCompileError``.
    """
    project = project_of(scope)
    for doc in docs:
        if doc.project is not None and doc.project != project:
            raise SchemaCompileError(
                "invalid", f"{doc.key()} belongs to project {doc.project}, not scope {scope}"
            )
    psets = compile_psets(docs)
    if project is not None:
        psets = {name: p for name, p in psets.items() if _adopted(p)}

    conformance = EffectiveConformance()
    declared = [d for d in docs if d.conformance is not None]
    if len(declared) > 1:
        names = ", ".join(sorted(d.key() for d in declared))
        raise SchemaCompileError("duplicate", f"conformance settings declared by {names}")
    if declared and declared[0].conformance is not None:
        settings = declared[0].conformance
        conformance = EffectiveConformance(
            mode=settings.mode,
            lenient_until=settings.lenient_until,
            waivers=[EffectiveWaiver(**w.model_dump()) for w in settings.waivers],
        )

    schema = EffectiveSchema(
        scope=scope,
        packages=sorted(
            (PackageRef(name=d.package, version=d.version) for d in docs), key=_ref_key
        ),
        core_digest=core if core is not None else core_digest(),
        psets=psets,
        conformance=conformance,
    )
    for waiver in conformance.waivers:
        if resolve_path(schema, waiver.path) is None:
            raise SchemaCompileError(
                "unknown_property", f"waiver path {waiver.path} names no property of {scope}"
            )
    return with_hash(schema)


def _ref_key(ref: PackageRef) -> tuple[str, str]:
    return ref.name, ref.version


class EffectiveCache:
    """Compiled artefacts keyed by effective-schema hash. Thread-safe; values are never evicted."""

    def __init__(self) -> None:
        self._items: dict[tuple[str, str], object] = {}
        self._lock = threading.Lock()

    def get_or_build(self, schema: EffectiveSchema, kind: str, build: Callable[[], T]) -> T:
        """The artefact ``kind`` for ``schema.hash``, built once with ``build``."""
        key = (schema.hash, kind)
        with self._lock:
            if key in self._items:
                return cast(T, self._items[key])
        built = build()
        with self._lock:
            return cast(T, self._items.setdefault(key, built))

    def __len__(self) -> int:
        return len(self._items)
