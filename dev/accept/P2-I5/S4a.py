"""Acceptance for P2-I5-S4a: weekly plan commands, commitments, outcomes and PPC.

SQLite, dialect-neutral. One ``PASS <check>`` line each, then ``S4a ok``.
Run: ``uv run python dev/accept/P2-I5/S4a.py``.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "packages/tl-modules/awp/tests"))
import progress_world as pw  # noqa: E402

if __name__ == "__main__":
    pw.week_checks(pw.build_week(Path(tempfile.mkdtemp()) / "s4a.db"))
    print("S4a ok")
