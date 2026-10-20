"""Plugins for the integration tests (the name is unique on purpose: L-P1-I0A-1).

``FakeEnricher`` is deterministic and independent of the shipped classifier: it proposes the first
word of the title as ``label`` and a fixed ``score``.
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Iterator
from typing import Any

from tl_core.files.types import ObjectNotFound
from tl_core.integration.contract import (
    EnrichmentResult,
    EnrichmentSubject,
    ProposedLink,
    ProposedValue,
)


class FakeEnricher:
    name = "fake"
    version = "1.0.0"
    model_ref: str | None = None

    #: What the next ``enrich`` proposes: (property, value, confidence); tests change it.
    plan: list[tuple[str, object, float]] = [("label", "alpha", 0.95)]
    links: list[tuple[str, float]] = []
    status = "ok"

    def accepts(self, subject: EnrichmentSubject) -> bool:
        return bool(subject.title.strip())

    def enrich(self, subject: EnrichmentSubject) -> EnrichmentResult:
        return EnrichmentResult(
            enricher=self.name,
            enricher_version=self.version,
            status=self.status,  # type: ignore[arg-type]
            values=[
                ProposedValue(property=p, value=v, confidence=c)  # type: ignore[arg-type]
                for p, v, c in type(self).plan
            ],
            links=[ProposedLink(to_key=k, confidence=c) for k, c in type(self).links],
            notes=["a fake for tests"],
        )


class ModelEnricher(FakeEnricher):
    name = "model_based"
    model_ref: str | None = "some-model@abc"


def reset() -> None:
    FakeEnricher.plan = [("label", "alpha", 0.95)]
    FakeEnricher.links = []
    FakeEnricher.status = "ok"


class MemStore:
    """An in-memory ``ObjectStore`` that can list its keys (like the fs and s3 backends)."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, data: Any, *, size: int, sha256: str, content_type: str) -> None:
        body = data.read(size + 1)
        assert len(body) == size and hashlib.sha256(body).hexdigest() == sha256
        self.objects[key] = body

    def get(self, key: str) -> Any:
        if key not in self.objects:
            raise ObjectNotFound(key)
        return io.BytesIO(self.objects[key])

    def exists(self, key: str) -> bool:
        return key in self.objects

    def iter_keys(self) -> Iterator[str]:
        return iter(sorted(self.objects))

    def presign_put(self, key: str, *, expires_s: int) -> str:
        raise NotImplementedError

    def presign_get(self, key: str, *, expires_s: int) -> str:
        raise NotImplementedError
