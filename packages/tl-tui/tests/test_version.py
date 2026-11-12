"""`tl-tui --version` prints the release version from the installed tl-tui metadata (P2-REL-T01)."""

from __future__ import annotations

import re
from importlib.metadata import version

import pytest
from tl_tui.main import main


def test_version_flag_prints_the_package_metadata_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert out == f"throughline {version('tl-tui')}\n"
    assert re.fullmatch(r"throughline \d+\.\d+\.\d+\n", out)
