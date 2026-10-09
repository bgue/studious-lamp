"""Fixtures for schema tests: raw fixture package dicts and a helper that builds documents."""

from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from tl_schema.compose import compose
from tl_schema.effective import EffectiveSchema
from tl_schema.packages import PackageDoc

FIXTURE_DIR = Path(__file__).resolve().parents[3] / "schema" / "fixtures"

RawPackages = dict[str, dict[str, Any]]


def load_raw() -> RawPackages:
    """The three fixture packages as plain dicts, keyed by package name."""
    raw: RawPackages = {}
    for path in sorted(FIXTURE_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        raw[data["package"]] = data
    return raw


@pytest.fixture
def fixture_dir() -> Path:
    """The directory holding the committed fixture packages (``schema/fixtures``)."""
    return FIXTURE_DIR


@pytest.fixture
def raw_packages() -> RawPackages:
    """A fresh deep copy of the fixture packages, safe to mutate."""
    return copy.deepcopy(load_raw())


@pytest.fixture
def build_docs() -> Callable[..., list[PackageDoc]]:
    """``build_docs(mutate=None)`` mutates fresh raw dicts, then validates them into documents.

    Every call starts from the committed fixtures, so one test may build several variants.
    """

    def build(mutate: Callable[[RawPackages], None] | None = None) -> list[PackageDoc]:
        raw = copy.deepcopy(load_raw())
        if mutate is not None:
            mutate(raw)
        return [PackageDoc.model_validate(data) for data in raw.values()]

    return build


@pytest.fixture
def effective(build_docs: Callable[..., list[PackageDoc]]) -> EffectiveSchema:
    """The fixture packages composed for ``project:P123``."""
    return compose(build_docs(), "project:P123")
