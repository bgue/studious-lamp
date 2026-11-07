"""Acceptance for P2-I2-T04e1: the `tl awp iwp` write verbs (create, scope, pins, split, sign-off,
issue, hold) on a SQLite ledger, through a throwaway Typer app with ``register``."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "dev/accept/P2-I2"))
import t04e1_checks as t  # noqa: E402

if __name__ == "__main__":
    work = Path(tempfile.mkdtemp())
    t.checks(t.s3.build(work / "t04e1.db"), work)
    print("T04e1 ok")
