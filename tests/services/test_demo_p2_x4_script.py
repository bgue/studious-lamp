"""P2-X4 T05c: the demo script calls each driver mode once per backend and ends every clause.

Provided by the supervisor; the ticket copies it byte-identical to
``tests/services/test_demo_p2_x4_script.py``.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "dev" / "demos" / "P2-X4.sh"
CALLS = {
    "driver clause1": "p2_x4_demo.py",
    "driver clause2": "p2_x4_demo.py",
    "driver clause6": "p2_x4_demo.py",
    "ext clause3": "p2_x4_ext_demo.py",
    "ext clause4": "p2_x4_ext_demo.py",
    "ext clause5": "p2_x4_ext_demo.py",
}


def text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_the_script_parses_as_bash() -> None:
    done = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr


def test_each_clause_one_to_seven_is_reported_once() -> None:
    reported = re.findall(r"^\s*clause ([0-9]) ", text(), flags=re.MULTILINE)
    assert reported == ["1", "2", "3", "4", "5", "6", "7"]


def test_each_mode_is_called_once_and_both_drivers_are_named() -> None:
    body = text()
    for call, driver in CALLS.items():
        assert len(re.findall(rf"^\s*{call}\b", body, flags=re.MULTILINE)) == 1, call
        assert driver in body


def test_the_script_runs_both_backends_and_the_compat_gate() -> None:
    body = text()
    assert "TL_DEMO_BACKENDS:-sqlite postgres" in body
    assert "tl_api.openapi --compat" in body
    assert "tl new module" in body
