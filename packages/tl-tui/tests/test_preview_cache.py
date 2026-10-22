"""The page-1 picture cache: names, bounds, eviction, hostile names (P1-UX2-S4)."""

from __future__ import annotations

import os
import struct
import zlib
from collections.abc import Callable
from pathlib import Path

import pytest
from tl_tui.preview import cache

GOOD = "a" * 64


def png(pages: int | None = None) -> bytes:
    """A 1x1 PNG, with a ``pages`` text chunk when given."""

    def chunk(kind: bytes, body: bytes) -> bytes:
        crc = zlib.crc32(kind + body) & 0xFFFFFFFF
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    out = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
    if pages is not None:
        out += chunk(b"tEXt", b"pages\x00" + str(pages).encode())
    out += chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))
    return out + chunk(b"IEND", b"")


def writer(data: bytes) -> Callable[[Path], None]:
    def fill(target: Path) -> None:
        target.write_bytes(data)

    return fill


def put(root: Path, name: str, data: bytes, age: float = 0) -> Path:
    path = root / name
    path.write_bytes(data)
    if age:
        stamp = path.stat().st_mtime - age
        os.utime(path, (stamp, stamp))
    return path


def test_only_64_lower_case_hex_digits_name_an_entry() -> None:
    assert cache.valid_hash(GOOD)
    for bad in (
        "",
        "a" * 63,
        "a" * 65,
        "A" * 64,
        "g" * 64,
        "../" + "a" * 61,
        GOOD + "\n",
        "a/" * 32,
    ):
        assert not cache.valid_hash(bad)
        assert cache.entry_path(Path("/x"), bad) is None


def test_a_hostile_name_is_never_read_or_written(tmp_path: Path) -> None:
    secret = tmp_path / "secret.png"
    secret.write_bytes(png(3))
    root = cache.ensure_dir(tmp_path / "cache")
    hostile = "../secret"
    assert cache.lookup(root, hostile) is None
    with pytest.raises(ValueError):
        cache.write_entry(root, hostile, writer(b"x"))
    assert secret.read_bytes() == png(3)
    assert sorted(p.name for p in root.iterdir()) == []


def test_the_directory_is_private_and_a_link_in_its_place_is_refused(tmp_path: Path) -> None:
    root = cache.ensure_dir(tmp_path / "a" / "cache")
    assert root.stat().st_mode & 0o777 == 0o700
    wide = tmp_path / "wide"
    wide.mkdir(mode=0o755)
    os.chmod(wide, 0o755)
    assert cache.ensure_dir(wide).stat().st_mode & 0o777 == 0o700  # narrowed
    link = tmp_path / "link"
    link.symlink_to(root)
    with pytest.raises(OSError):
        cache.ensure_dir(link)


def test_the_cache_dir_follows_xdg_then_home() -> None:
    assert cache.cache_dir({"XDG_CACHE_HOME": "/var/c"}) == Path("/var/c/throughline/preview")
    assert cache.cache_dir({"XDG_CACHE_HOME": "relative"}).parts[-3:] == (
        ".cache", "throughline", "preview",
    )  # fmt: skip


def test_write_is_atomic_and_leaves_one_entry(tmp_path: Path) -> None:
    root = cache.ensure_dir(tmp_path / "c")
    target = cache.write_entry(root, GOOD, writer(png(2)))
    assert target == root / f"{GOOD}.png" and target.stat().st_mode & 0o777 == 0o600
    assert [p.name for p in root.iterdir()] == [f"{GOOD}.png"]
    assert cache.lookup(root, GOOD) == target
    assert cache.read_pages(target) == 2


def test_a_failed_fill_leaves_nothing_behind(tmp_path: Path) -> None:
    root = cache.ensure_dir(tmp_path / "c")

    def broken(target: Path) -> None:
        target.write_bytes(b"half")
        raise RuntimeError("disk full")

    with pytest.raises(RuntimeError):
        cache.write_entry(root, GOOD, broken)
    assert list(root.iterdir()) == []


def test_lookup_ignores_a_link_and_an_empty_file(tmp_path: Path) -> None:
    root = cache.ensure_dir(tmp_path / "c")
    outside = tmp_path / "outside.png"
    outside.write_bytes(png())
    (root / f"{GOOD}.png").symlink_to(outside)
    assert cache.lookup(root, GOOD) is None
    (root / f"{GOOD}.png").unlink()
    put(root, f"{GOOD}.png", b"")
    assert cache.lookup(root, GOOD) is None


def test_pages_are_read_from_the_png_text_chunk_only(tmp_path: Path) -> None:
    assert cache.read_pages(put(tmp_path, "a.png", png(7))) == 7
    assert cache.read_pages(put(tmp_path, "b.png", png())) is None
    assert cache.read_pages(put(tmp_path, "c.png", b"not a png")) is None
    assert cache.read_pages(tmp_path / "missing.png") is None


def test_the_oldest_entries_go_first_when_there_are_too_many(tmp_path: Path) -> None:
    root = cache.ensure_dir(tmp_path / "c")
    names = [f"{c * 64}.png" for c in "abcd"]
    for age, name in zip((400, 300, 200, 100), names, strict=True):
        put(root, name, png(), age=age)
    removed = cache.evict(root, max_entries=2)
    assert sorted(removed) == sorted(names[:2])
    assert sorted(p.name for p in root.iterdir()) == sorted(names[2:])


def test_the_oldest_entries_go_first_when_the_bytes_are_over_the_cap(tmp_path: Path) -> None:
    root = cache.ensure_dir(tmp_path / "c")
    old, new = f"{'a' * 64}.png", f"{'b' * 64}.png"
    put(root, old, b"x" * 600, age=100)
    put(root, new, b"x" * 600)
    assert cache.evict(root, max_bytes=1000) == [old]
    assert (root / new).exists()


def test_eviction_leaves_foreign_files_alone_and_clears_stale_temp_files(tmp_path: Path) -> None:
    root = cache.ensure_dir(tmp_path / "c")
    keep = put(root, "notes.txt", b"mine", age=9999)
    badly_named = put(root, f"{'A' * 64}.png", b"x", age=9999)
    stale = put(root, ".tmp-old.png", b"x", age=7200)
    fresh = put(root, ".tmp-new.png", b"x")
    cache.evict(root, max_entries=0, max_bytes=0)
    assert keep.exists() and badly_named.exists() and fresh.exists() and not stale.exists()


def test_the_caps_are_the_documented_ones() -> None:
    assert cache.MAX_ENTRIES == 200 and cache.MAX_TOTAL_BYTES == 64 * 1024 * 1024
