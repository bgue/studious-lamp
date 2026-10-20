"""The file `tl comm export --out` writes is private and is made, not followed (P1-I6)."""

from __future__ import annotations

from pathlib import Path

import pytest
import typer
from tl_cli.comm import _write_private  # pyright: ignore[reportPrivateUsage]


def test_a_new_file_is_private(tmp_path: Path) -> None:
    out = tmp_path / "changes.csv"
    _write_private(out, "a,b\n", force=False)
    assert out.read_text() == "a,b\n" and out.stat().st_mode & 0o777 == 0o600


def test_a_file_replaced_with_force_is_private_again(tmp_path: Path) -> None:
    out = tmp_path / "changes.csv"
    out.write_text("old")
    out.chmod(0o644)
    _write_private(out, "new", force=True)
    assert out.read_text() == "new" and out.stat().st_mode & 0o777 == 0o600


def test_an_existing_file_is_kept_without_force(tmp_path: Path) -> None:
    out = tmp_path / "changes.csv"
    out.write_text("keep")
    with pytest.raises(typer.BadParameter, match="use --force"):
        _write_private(out, "new", force=False)
    assert out.read_text() == "keep"


def test_a_link_is_never_followed(tmp_path: Path) -> None:
    target = tmp_path / "elsewhere.txt"
    target.write_text("not mine")
    link = tmp_path / "link.csv"
    link.symlink_to(target)
    for force in (False, True):
        with pytest.raises(typer.BadParameter):
            _write_private(link, "new", force=force)
    assert target.read_text() == "not mine"
