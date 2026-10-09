"""Tests for the in-memory projector registry (P0-I1-T07)."""

from __future__ import annotations

import pytest
from tl_core.projection import InMemoryRegistry
from tl_core.projection.defaults import default_registry
from tl_core.projection.testing import CounterProjector


class OtherProjector(CounterProjector):
    name = "other"
    handles = frozenset({"Test.Bumped", "Test.Other"})


def test_for_event_returns_handlers_in_registration_order() -> None:
    counter, other = CounterProjector(), OtherProjector()
    registry = InMemoryRegistry([counter, other])
    assert registry.for_event("Test.Bumped") == [counter, other]
    assert registry.for_event("Test.Other") == [other]
    assert registry.for_event("Nope") == []
    assert registry.all() == [counter, other]


def test_duplicate_names_are_rejected() -> None:
    registry = InMemoryRegistry([CounterProjector()])
    with pytest.raises(ValueError, match="already registered"):
        registry.register(CounterProjector())


def test_named_selects_and_rejects_unknown() -> None:
    counter, other = CounterProjector(), OtherProjector()
    registry = InMemoryRegistry([counter, other])
    assert registry.named(["other"]) == [other]
    with pytest.raises(KeyError, match="missing"):
        registry.named(["missing"])


def test_default_registry_is_fresh_each_call() -> None:
    first, second = default_registry(), default_registry()
    assert first is not second
    first.register(CounterProjector())
    assert all(p.name != "test_counter" for p in second.all())
