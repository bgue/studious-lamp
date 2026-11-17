"""When tests/perf runs: named by path on the command line, or ``TL_PERF=1``."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

HERE = Path(__file__).resolve().parent


def perf_requested(args: Sequence[str], env: Mapping[str, str]) -> bool:
    """True when ``TL_PERF=1`` or an argument names a path inside ``tests/perf``."""
    if env.get("TL_PERF") == "1":
        return True
    for arg in args:
        path = Path(arg.split("::", 1)[0]).resolve()
        if path == HERE or HERE in path.parents:
            return True
    return False
