"""The Textual-free twins of the awp screens import without Textual (D27, WEB1).

The web face reads the same text modules, so none of them may import ``textual``: each is imported
in a fresh interpreter whose ``textual`` entry is ``None``, which makes any import of it fail.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
MODULES = (
    "tl_tui.awp_text",
    "tl_tui.details.awp",
    "tl_tui.wbs_text",
    "tl_tui.cwa_text",
    "tl_tui.path_text",
    "tl_tui.package_text",
)


@pytest.mark.parametrize("module", MODULES)
def test_a_text_module_imports_without_textual(module: str) -> None:
    code = f"import sys; sys.modules['textual'] = None\nimport {module}\nprint('imported')"
    done = subprocess.run(
        [sys.executable, "-I", "-c", code], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr
    assert "imported" in done.stdout


def test_the_check_can_fail() -> None:
    """A module that does import Textual fails the same probe (the screens themselves do)."""
    code = "import sys; sys.modules['textual'] = None\nimport tl_tui.widgets.wbs_screen"
    done = subprocess.run(
        [sys.executable, "-I", "-c", code], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert done.returncode != 0
