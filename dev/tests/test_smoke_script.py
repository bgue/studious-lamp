"""dev/release/smoke.sh: syntax and the pinned step names only (P2-REL-T05).

The real run (dev/release/smoke.sh <release dir>) is the acceptance.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "dev" / "release" / "smoke.sh"
STEPS = ["install", "try-it", "real-server", "session-file"]


def test_script_parses_with_bash() -> None:
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


def test_step_names_are_pinned() -> None:
    out = subprocess.run([str(SCRIPT), "--list"], check=True, capture_output=True, text=True).stdout
    assert out.split() == STEPS
