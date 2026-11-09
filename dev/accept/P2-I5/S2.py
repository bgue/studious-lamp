"""Acceptance for P2-I5-S2: the rules-of-credit engine, progress commands, IWP field lifecycle.

SQLite, dialect-neutral. One ``PASS <check>`` line each, then ``S2 ok``.
Run: ``uv run python dev/accept/P2-I5/S2.py``.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "packages/tl-modules/awp/tests"))
import progress_world as pw  # noqa: E402

if __name__ == "__main__":
    pw.checks(pw.build(Path(tempfile.mkdtemp()) / "s2.db"))
    print("S2 ok")
