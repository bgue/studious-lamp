"""Acceptance for P2-I2-S3: IWP sign-off, issue and hold. Readiness rows are written by hand."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "packages/tl-modules/awp/tests"))
import s3_checks as s3  # noqa: E402

if __name__ == "__main__":
    s3.checks(s3.build(Path(tempfile.mkdtemp()) / "s3.db"))
    print("S3 ok")
