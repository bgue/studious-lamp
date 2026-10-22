"""PrivateTemp: a 0700 folder, 0600 files, no links followed, cleaned up (P1-UX2-S4)."""

from __future__ import annotations

import atexit
import os
from pathlib import Path

import pytest
from tl_tui.preview import temp
from tl_tui.preview.temp import PrivateTemp, UnsafeTempError


def make_file(folder: Path, name: str = "a.pdf", mode: int = 0o600) -> Path:
    path = folder / name
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    os.write(fd, b"x")
    os.close(fd)
    os.chmod(path, mode)
    return path


def test_the_folder_is_private_and_under_the_given_base(tmp_path: Path) -> None:
    with PrivateTemp(tmp_path) as box:
        folder = box.directory
        assert folder.parent == tmp_path
        assert folder.stat().st_mode & 0o777 == 0o700
        assert folder.name.startswith(temp.PREFIX)
    assert not folder.exists()  # leaving the block cleans up


def test_the_default_base_is_the_system_temporary_folder() -> None:
    import tempfile

    with PrivateTemp() as box:
        assert box.directory.parent == Path(tempfile.gettempdir())


def test_verify_accepts_a_plain_0600_file_of_ours(tmp_path: Path) -> None:
    with PrivateTemp(tmp_path) as box:
        path = make_file(box.directory)
        assert box.verify(path) == path


def test_verify_refuses_a_wide_file_a_foreign_path_and_a_link(tmp_path: Path) -> None:
    outside = make_file(tmp_path, "outside.pdf")
    with PrivateTemp(tmp_path) as box:
        with pytest.raises(UnsafeTempError):
            box.verify(make_file(box.directory, "wide.pdf", 0o644))
        with pytest.raises(UnsafeTempError):
            box.verify(outside)  # not in the folder
        link = box.directory / "link.pdf"
        link.symlink_to(outside)  # a symlink put in place of the file
        with pytest.raises(UnsafeTempError):
            box.verify(link)
        assert outside.read_bytes() == b"x"


def test_a_folder_swapped_for_a_link_is_refused_and_cleanup_drops_only_the_link(
    tmp_path: Path,
) -> None:
    victim = tmp_path / "victim"
    victim.mkdir()
    precious = make_file(victim, "precious.txt")
    box = PrivateTemp(tmp_path)
    folder = box.directory
    folder.rmdir()
    folder.symlink_to(victim)
    with pytest.raises(UnsafeTempError):
        _ = box.directory
    box.cleanup()
    assert precious.exists() and victim.is_dir()  # nothing behind the link was touched
    assert not folder.is_symlink()


def test_a_widened_folder_is_refused(tmp_path: Path) -> None:
    box = PrivateTemp(tmp_path)
    os.chmod(box.directory, 0o755)
    with pytest.raises(UnsafeTempError):
        _ = box.directory
    box.cleanup()


def test_cleanup_removes_everything_and_does_not_follow_links_inside(tmp_path: Path) -> None:
    keep = make_file(tmp_path, "keep.txt")
    box = PrivateTemp(tmp_path)
    make_file(box.directory, "one.pdf")
    make_file(box.directory, "two.pdf")
    (box.directory / "pointer").symlink_to(keep)
    folder = box.directory
    box.cleanup()
    assert not folder.exists()
    assert keep.exists()
    box.cleanup()  # twice is fine


def test_the_exit_hook_is_registered_once_and_removes_what_is_left(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[object] = []
    monkeypatch.setattr(temp, "_hooked", False)
    monkeypatch.setattr(atexit, "register", lambda fn, *a, **k: calls.append(fn))
    first, second = PrivateTemp(tmp_path), PrivateTemp(tmp_path)
    folders = [first.directory, second.directory]
    assert calls == [temp._cleanup_all]
    temp._cleanup_all()
    assert not any(folder.exists() for folder in folders)
