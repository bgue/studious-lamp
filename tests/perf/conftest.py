"""tests/perf builds a four-minute ledger, so it runs only when asked: the path is named on the
command line (``just gate tests/perf``, ``pytest tests/perf``) or ``TL_PERF=1`` is set. A run of
``tests/`` or of the whole suite skips it."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from perf_gate import perf_requested  # noqa: E402  # pyright: ignore[reportMissingImports]


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if perf_requested([str(a) for a in config.args], os.environ):
        return
    skip = pytest.mark.skip(reason="tests/perf runs when named by path or with TL_PERF=1")
    for item in items:
        if item.get_closest_marker("perf") is not None:
            item.add_marker(skip)
