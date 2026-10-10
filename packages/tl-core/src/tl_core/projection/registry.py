"""A plain in-memory projector registry."""

from __future__ import annotations

from collections.abc import Iterable

from tl_core.projection.types import Projector


def handles_all(projector: Projector) -> bool:
    """Whether ``projector`` wants every event, whatever its type.

    A projector opts in with a class or instance attribute ``handles_all = True`` (the outbox
    does). The attribute is optional on the ``Projector`` Protocol, so projectors written before it
    existed keep working: a projector without it handles only the types in ``handles``.
    """
    return bool(getattr(projector, "handles_all", False))


class InMemoryRegistry:
    """Projectors in registration order. Names are unique.

    ``for_event`` returns the projectors whose ``handles`` contains the type **and** those with
    ``handles_all`` set, merged in registration order. Register a ``handles_all`` projector last
    when it reads the rows other projectors write for the same event (the outbox does).
    """

    def __init__(self, projectors: Iterable[Projector] = ()) -> None:
        self._projectors: list[Projector] = []
        for projector in projectors:
            self.register(projector)

    def register(self, projector: Projector) -> None:
        if any(p.name == projector.name for p in self._projectors):
            raise ValueError(f"projector already registered: {projector.name}")
        self._projectors.append(projector)

    def for_event(self, event_type: str) -> list[Projector]:
        return [p for p in self._projectors if handles_all(p) or event_type in p.handles]

    def all(self) -> list[Projector]:
        return list(self._projectors)

    def named(self, names: Iterable[str]) -> list[Projector]:
        """Registered projectors with these names, in registration order; unknown names raise."""
        wanted = set(names)
        unknown = wanted - {p.name for p in self._projectors}
        if unknown:
            raise KeyError(f"unknown projector(s): {', '.join(sorted(unknown))}")
        return [p for p in self._projectors if p.name in wanted]
