"""C1: the core constraint schema, workflow words and event types (P2-I2-C1).

Each test runs one step of the acceptance script ``dev/accept/P2-I2/C1.py`` (written from the spec,
not from generated files); a failed step exits with ``FAIL <what>``, which pytest reports.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ACCEPT = Path(__file__).resolve().parents[3] / "dev" / "accept" / "P2-I2"
sys.path.insert(0, str(ACCEPT))
import C1 as c1  # noqa: E402  # pyright: ignore[reportMissingImports]


def _run(step: object) -> None:
    try:
        step()  # type: ignore[operator]
    except SystemExit as exc:  # the script's need() exits with 1 and prints FAIL
        pytest.fail(f"acceptance step {getattr(step, '__name__', step)} failed ({exc.code})")


@pytest.mark.parametrize(
    "step",
    [c1.labels, c1.table, c1.events, c1.workflow, c1.relation, c1.words, c1.guards, c1.bad_phase],
    ids=lambda s: s.__name__,
)
def test_c1_step(step: object) -> None:
    _run(step)


def test_c1_numbering(tmp_path: Path) -> None:
    _run(lambda: c1.numbering(tmp_path))
