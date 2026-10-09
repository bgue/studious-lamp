"""tl-tui test configuration.

pytest runs in importlib mode (root pyproject), so sibling test helpers are not importable by
default. Putting this directory on `sys.path` lets tests write `from fakes import FakeClient`;
pyright resolves the same import from the file's own directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = str(Path(__file__).parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
