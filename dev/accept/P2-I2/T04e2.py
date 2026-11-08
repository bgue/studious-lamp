"""Acceptance for P2-I2-T04e2: `tl constraint raise|assign|clear|withdraw` on the C2 ledger.

SQLite only. Exit 0, one ``PASS <check>`` line per check, then ``T04e2 ok``. Run:
``uv run python dev/accept/P2-I2/T04e2.py``. The checks are in ``t04e2_checks.py``.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import t04e2_checks as t  # noqa: E402

if __name__ == "__main__":
    t.checks(*t.c2.build(Path(tempfile.mkdtemp()) / "t04e2.db"))
    print("T04e2 ok")
