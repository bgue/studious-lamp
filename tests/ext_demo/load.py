"""Load the `ext_demo` fixture module (never installed; tests and the demo use this loader).

Consumers put this directory on `sys.path` and call `ext_demo_spec()`::

    sys.path.insert(0, str(EXT_DEMO))
    from load import ext_demo_spec
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

from tl_core.modules import ModuleSpec

SRC = Path(__file__).resolve().parent / "src"


def ext_demo_spec() -> ModuleSpec:
    """Put `src` on `sys.path` once, import the module and return its spec."""
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    module = importlib.import_module("tl_mod_ext_demo.module")
    spec: ModuleSpec = module.spec()
    return spec
