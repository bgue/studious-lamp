"""Acceptance for P2-I2-C2: core constraint commands, guard and confidentiality join. SQLite only.

Exit 0, one ``PASS <check>`` line per check, then ``C2 ok``. ``--keep PATH`` seeds PATH (S2 seed + 3
constraints). Run: ``uv run python dev/accept/P2-I2/C2.py``. The checks are in ``c2_checks.py``.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import c2_checks as c2  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep")
    keep = parser.parse_args().keep
    c2.checks(*c2.build(Path(tempfile.mkdtemp()) / "c2.db"))
    if keep:
        Path(keep).parent.mkdir(parents=True, exist_ok=True)
        Path(keep).unlink(missing_ok=True)
        c2.seed(*c2.build(Path(keep)))
        print(f"PASS seed kept at {keep}")
    print("C2 ok")
