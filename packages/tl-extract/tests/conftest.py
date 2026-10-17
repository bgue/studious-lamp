"""Fixtures of the tl-extract tests.

pytest imports test files by path here, so this directory and ``tests/contract`` (home of
``check_extractor_contract``) are put on ``sys.path``; pyright finds them through ``extraPaths``.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

for path in (HERE, ROOT / "tests" / "contract"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
