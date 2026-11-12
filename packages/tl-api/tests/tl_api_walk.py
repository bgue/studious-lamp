"""The tl-api confidentiality walk's cast and seed, loaded by path under a unique name.

``tl-mcp`` has a test file named ``test_confidentiality_walk``, so a bare import of that name finds
the wrong one when both packages are collected in one pytest session. Tests import from here.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

_NAME = "tl_api_confidentiality_walk"


def _load() -> Any:
    if _NAME not in sys.modules:
        path = Path(__file__).with_name("test_confidentiality_walk.py")
        spec = importlib.util.spec_from_file_location(_NAME, path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[_NAME] = module
        spec.loader.exec_module(module)
    return sys.modules[_NAME]


_WALK = _load()
PASSWORD = _WALK.PASSWORD
FAKE_ID = _WALK.FAKE_ID
MAY_READ = _WALK.MAY_READ
Seed = _WALK.Seed
seed = _WALK.seed
hidden_markers = _WALK.hidden_markers
_person = _WALK._person  # pyright: ignore[reportPrivateUsage]
