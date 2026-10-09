"""Registry adoption edge cases confirmed after T01 review (pins to missing or non-company docs)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from tl_schema.packages import PackageDoc
from tl_schema.registry import PackageError, PackageRegistry

Build = Callable[..., list[PackageDoc]]
Raw = dict[str, dict[str, Any]]


def test_a_pin_to_an_unstored_version_is_an_error(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        raw["x.P123"]["depends"] = {"co.acme.engineering": "9.9.9"}

    registry = PackageRegistry(build_docs(mutate))
    with pytest.raises(PackageError):
        registry.adopted("project:P123")
    with pytest.raises(PackageError) as caught:
        registry.check()
    assert "9.9.9" in str(caught.value)


def test_a_pin_to_a_non_company_package_is_skipped_by_adopt_and_reported_by_check(
    build_docs: Build,
) -> None:
    def mutate(raw: Raw) -> None:
        raw["x.P123"]["depends"]["prj.P123"] = "1.0.0"

    registry = PackageRegistry(build_docs(mutate))
    adopted = [d.key() for d in registry.adopted("project:P123")]
    assert adopted == ["co.acme.engineering@3.2.0", "x.P123@1.4.0", "prj.P123@1.0.0"]
    with pytest.raises(PackageError) as caught:
        registry.check()
    assert "not a company package" in str(caught.value)
