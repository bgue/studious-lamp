"""Acceptance for P2-I2-T04a2: owner filter and review groups (core). SQLite only.

Exit 0, one ``PASS <check>`` line per check, then ``T04a2 ok``. The checks are in
``t04a2_checks.py``.
Run: ``uv run python dev/accept/P2-I2/T04a2.py``.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import c2_checks as c2  # noqa: E402
import t04a2_checks as t  # noqa: E402

if __name__ == "__main__":
    w, docs = c2.build(Path(tempfile.mkdtemp()) / "t04a2.db")
    c2.seed(w, docs)
    t.checks(w, docs)
    print("T04a2 ok")
