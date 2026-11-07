"""Acceptance for P2-I2-S2: IWP, scope item, constraint commands. ``--keep PATH`` seeds PATH."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "packages/tl-modules/awp/tests"))
import s2_checks as s2  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep")
    keep = parser.parse_args().keep
    s2.checks(*s2.build(Path(tempfile.mkdtemp()) / "s2.db"))
    if keep:
        Path(keep).parent.mkdir(parents=True, exist_ok=True)
        Path(keep).unlink(missing_ok=True)
        s2.seed(*s2.build(Path(keep)))
        print(f"PASS seed kept at {keep}")
    print("S2 ok")
