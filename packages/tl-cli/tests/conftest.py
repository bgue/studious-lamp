"""tl-cli test configuration: puts this directory on `sys.path` for sibling helpers.

pytest runs in importlib mode (root pyproject), so sibling helpers are not importable by default
(L-P0-I2-B1). Do not add ``__init__.py`` here.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = str(Path(__file__).parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
