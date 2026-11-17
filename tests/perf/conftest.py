"""tests/perf builds a four-minute ledger, so it runs only when asked: the path is named on the
command line (``just gate tests/perf``, ``pytest tests/perf``) or ``TL_PERF=1`` is set. A run of
``tests/`` or of the whole suite skips it."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent


def perf_requested(args: Sequence[str], env: dict[str, str] | os._Environ[str]) -> bool:
    """True when ``TL_PERF=1`` or an argument names a path inside ``tests/perf``."""
    if env.get("TL_PERF") == "1":
        return True
    for arg in args:
        path = Path(arg.split("::", 1)[0]).resolve()
        if path == HERE or HERE in path.parents:
            return True
    return False


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if perf_requested([str(a) for a in config.args], os.environ):
        return
    skip = pytest.mark.skip(reason="tests/perf runs when named by path or with TL_PERF=1")
    for item in items:
        if item.get_closest_marker("perf") is not None:
            item.add_marker(skip)
