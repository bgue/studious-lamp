"""Fixtures of the tl-xer tests: this directory goes on ``sys.path`` for ``xersupport``."""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
