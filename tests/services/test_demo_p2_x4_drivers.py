"""P2-X4 T05a and T05b: the two demo driver files name the modes the demo script calls.

Provided by the supervisor; the tickets copy it byte-identical to
``tests/services/test_demo_p2_x4_drivers.py``. A file that is not there yet fails its test.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

DEMOS = Path(__file__).resolve().parents[2] / "dev" / "demos"
MODES = {
    "p2_x4_demo.py": ("clause1", "clause2", "clause6"),
    "p2_x4_ext_demo.py": ("clause3", "clause4", "clause5"),
}


def modes_of(path: Path) -> tuple[str, ...]:
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and [
            t.id for t in node.targets if isinstance(t, ast.Name)
        ] == ["MODES"]:
            value = ast.literal_eval(node.value)
            assert isinstance(value, tuple)
            return tuple(str(item) for item in value)  # pyright: ignore[reportUnknownVariableType]
    raise AssertionError(f"{path.name} has no MODES tuple")


@pytest.mark.parametrize("name", sorted(MODES))
def test_the_driver_names_its_modes_in_order(name: str) -> None:
    assert modes_of(DEMOS / name) == MODES[name]


@pytest.mark.parametrize("name", sorted(MODES))
def test_the_driver_has_no_unlisted_clause_mode(name: str) -> None:
    text = (DEMOS / name).read_text(encoding="utf-8")
    others = {m for n, modes in MODES.items() if n != name for m in modes}
    assert not any(f'"{mode}"' in text for mode in others)
