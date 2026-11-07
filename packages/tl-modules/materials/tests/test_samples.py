"""The sample files: items, locations, PO lines (T01a)."""

from __future__ import annotations

import inspect
from collections.abc import Callable

import acc_t01a
import pytest

CHECKS: list[Callable[[], None]] = [
    f
    for n, f in inspect.getmembers(acc_t01a, inspect.isfunction)
    if n.startswith("check_") and not inspect.signature(f).parameters
]


def test_every_sample_check_is_collected() -> None:
    assert len(CHECKS) == 26


@pytest.mark.parametrize("check", CHECKS, ids=lambda f: f.__name__)
def test_sample_file(check: Callable[[], None]) -> None:
    check()
