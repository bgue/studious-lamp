"""Fixtures of the thread tests.

pytest imports test files by path here, so this directory and ``tests/contract`` (home of
``check_parser_contract`` and ``check_preview_shape``) are put on ``sys.path``; pyright finds them
through ``extraPaths``.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

for path in (HERE, ROOT / "tests" / "contract"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from collections.abc import Callable  # noqa: E402

import pytest  # noqa: E402
from thread_world import thread_db  # noqa: E402
from tl_adapters.db import DbTarget  # noqa: E402


@pytest.fixture
def db(new_db: Callable[[], DbTarget]) -> DbTarget:
    return thread_db(new_db())
