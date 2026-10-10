"""A filesystem without hard links gives a clear backup error (P0-I7 orchestrator ruling)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from tl_adapters.sqlite.backup import BackupError, backup_database
from tl_adapters.sqlite.uow import create_schema


def test_a_filesystem_without_hard_links_leaves_nothing_and_says_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "tl.db"
    create_schema(db)
    dest = tmp_path / "out" / "snap.db"

    def no_links(src: str, dst: str) -> None:
        raise OSError(1, "Operation not permitted")

    monkeypatch.setattr(os, "link", no_links)
    with pytest.raises(BackupError, match="does not support hard links"):
        backup_database(db, dest)
    monkeypatch.undo()
    assert not dest.exists()
    assert list(dest.parent.iterdir()) == []
