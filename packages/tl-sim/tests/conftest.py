"""Puts this directory on ``sys.path`` (importlib mode) and provides the ``suite`` fixture."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

_HERE = str(Path(__file__).parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from suite import Suite, build_suite, close_suite  # noqa: E402


@pytest.fixture
def suite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Suite]:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)  # the repository's fixture schema
    built = build_suite(tmp_path)
    try:
        yield built
    finally:
        close_suite(built)
