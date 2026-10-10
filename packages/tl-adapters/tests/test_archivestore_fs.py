"""The filesystem ArchiveStore: write-once, atomic, safe keys (P0-I7-T01)."""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest
from tl_adapters.archivestore import FsArchiveStore
from tl_core.archive import ArchiveExistsError, ArchiveStore


@pytest.fixture
def store(tmp_path: Path) -> FsArchiveStore:
    return FsArchiveStore(tmp_path / "archive")


def test_put_get_exists_roundtrip(store: FsArchiveStore) -> None:
    assert not store.exists("segments/a/events.ndjson")
    store.put_bytes("segments/a/events.ndjson", b"one\ntwo\n")
    assert store.exists("segments/a/events.ndjson")
    assert store.get_bytes("segments/a/events.ndjson") == b"one\ntwo\n"
    store.put_bytes("empty", b"")
    assert store.get_bytes("empty") == b""


def test_it_satisfies_the_archive_store_protocol(store: FsArchiveStore) -> None:
    as_protocol: ArchiveStore = store
    as_protocol.put_bytes("k", b"v")
    assert as_protocol.list_keys("") == ["k"]


def test_the_root_is_created_and_exposed(tmp_path: Path) -> None:
    root = tmp_path / "deep" / "archive"
    made = FsArchiveStore(root)
    assert made.root == root and root.is_dir()


def test_a_key_is_never_overwritten_even_with_the_same_bytes(store: FsArchiveStore) -> None:
    store.put_bytes("k/file", b"first")
    with pytest.raises(ArchiveExistsError):
        store.put_bytes("k/file", b"second")
    with pytest.raises(ArchiveExistsError):
        store.put_bytes("k/file", b"first")
    assert store.get_bytes("k/file") == b"first"


def test_a_missing_key_raises_key_error(store: FsArchiveStore) -> None:
    with pytest.raises(KeyError):
        store.get_bytes("nope/nothing")
    assert not store.exists("nope/nothing")


def test_list_keys_is_sorted_filtered_by_prefix_and_uses_slashes(store: FsArchiveStore) -> None:
    for key in ("segments/b/manifest.json", "segments/a/events.ndjson", "other/x", "segments/a/m"):
        store.put_bytes(key, b"x")
    assert store.list_keys("") == [
        "other/x",
        "segments/a/events.ndjson",
        "segments/a/m",
        "segments/b/manifest.json",
    ]
    assert store.list_keys("segments/") == [
        "segments/a/events.ndjson",
        "segments/a/m",
        "segments/b/manifest.json",
    ]
    assert store.list_keys("segments/a/e") == ["segments/a/events.ndjson"]
    assert store.list_keys("missing/") == []


@pytest.mark.parametrize(
    "key",
    ["", "/abs", "../x", "a/../b", "a//b", "a/./b", "a\\b", "a/b/", "x\0y", "a/.tmp-1/b"],
)
def test_unsafe_keys_are_refused_everywhere(store: FsArchiveStore, key: str) -> None:
    with pytest.raises(ValueError):
        store.put_bytes(key, b"x")
    with pytest.raises(ValueError):
        store.get_bytes(key)
    with pytest.raises(ValueError):
        store.exists(key)


def test_nothing_outside_the_root_is_written(tmp_path: Path, store: FsArchiveStore) -> None:
    with pytest.raises(ValueError):
        store.put_bytes("../escaped", b"x")
    assert not (tmp_path / "escaped").exists()


def test_files_are_read_only(store: FsArchiveStore) -> None:
    store.put_bytes("k/file", b"x")
    mode = (store.root / "k" / "file").stat().st_mode
    assert mode & 0o222 == 0


def test_a_failure_while_publishing_leaves_no_key_and_no_temp_file(
    store: FsArchiveStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_link(src: str, dst: str) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "link", broken_link)
    with pytest.raises(OSError, match="disk full"):
        store.put_bytes("k/file", b"x")
    monkeypatch.undo()
    assert not store.exists("k/file")
    assert store.list_keys("") == []
    assert [p.name for p in (store.root / "k").iterdir()] == []  # the temp file is gone
    store.put_bytes("k/file", b"y")  # and the key is still free
    assert store.get_bytes("k/file") == b"y"


def test_a_temp_file_left_by_a_crash_is_not_a_key(store: FsArchiveStore) -> None:
    (store.root / "k").mkdir()
    (store.root / "k" / ".tmp-abc").write_bytes(b"half")
    assert store.list_keys("") == []
    store.put_bytes("k/file", b"whole")
    assert store.list_keys("") == ["k/file"]


def test_concurrent_writers_of_one_key_have_exactly_one_winner(store: FsArchiveStore) -> None:
    results: list[str] = []
    start = threading.Event()

    def worker(n: int) -> None:
        start.wait()
        try:
            store.put_bytes("race/key", f"writer-{n}".encode() * 1000)
            results.append(f"ok-{n}")
        except ArchiveExistsError:
            results.append("exists")

    threads = [threading.Thread(target=worker, args=(n,), daemon=True) for n in range(8)]
    for thread in threads:
        thread.start()
    start.set()
    for thread in threads:
        thread.join(timeout=10)
    winners = [r for r in results if r.startswith("ok-")]
    assert len(winners) == 1 and results.count("exists") == 7
    number = winners[0].split("-")[1]
    assert store.get_bytes("race/key") == f"writer-{number}".encode() * 1000
    assert store.list_keys("") == ["race/key"]
