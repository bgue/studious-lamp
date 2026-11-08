"""Acceptance for P2-I2-T04d: the `tl awp iwp` and `tl constraint` CLI reads. SQLite temp ledger.

Exit 0, one ``PASS <check>`` line per check, then ``T04d ok``. The checks are in ``t04d_checks.py``.
Run: ``uv run python dev/accept/P2-I2/T04d.py``.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import c2_checks as c2  # noqa: E402
import t04d_checks as t  # noqa: E402

if __name__ == "__main__":
    work = Path(tempfile.mkdtemp())
    os.environ["TL_SESSION_FILE"] = str(work / "session.json")
    w, docs = c2.build(work / "t04d.db")
    c2.seed(w, docs)
    t.checks(w, w.db)
    print("T04d ok")
