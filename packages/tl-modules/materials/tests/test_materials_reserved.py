"""The readiness check materials_reserved (T03), with the Q7 pins."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from pathlib import Path

import acc_t03
import pytest

CHECKS: list[Callable[[], None]] = [
    f
    for n, f in inspect.getmembers(acc_t03, inspect.isfunction)
    if n.startswith("check_") and n not in {"check_object"} and not inspect.signature(f).parameters
]


def test_every_readiness_check_is_collected() -> None:
    assert len(CHECKS) == 9


@pytest.mark.parametrize("check", CHECKS, ids=lambda f: f.__name__)
def test_materials_reserved(
    check: Callable[[], None], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(acc_t03, "ROOT", tmp_path)
    check()
