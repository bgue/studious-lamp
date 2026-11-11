"""Puts this directory and the tl-api tests on ``sys.path`` so ``test_twin_walk`` can import its
helper (``twin_world``) and the API harness (pytest runs in importlib mode, L-P0-I2-B1)."""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).parent
for _path in (_HERE, _HERE.parents[1] / "packages" / "tl-api" / "tests"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
