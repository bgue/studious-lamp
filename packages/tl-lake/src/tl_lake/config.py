"""Where the lake lives on disk (brief 28.1: a catalog file plus Parquet data files)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ENV_LAKE_DIR = "TL_LAKE_DIR"
DEFAULT_LAKE_DIR = "dev/data/lake"


@dataclass(frozen=True)
class LakeConfig:
    """Paths for one lake. ``lake_dir`` is absolute; everything else derives from it."""

    lake_dir: Path

    @classmethod
    def at(cls, lake_dir: str | Path | None = None) -> LakeConfig:
        """The lake at ``lake_dir``, else ``$TL_LAKE_DIR``, else ``dev/data/lake`` (git-ignored)."""
        chosen = lake_dir or os.environ.get(ENV_LAKE_DIR) or DEFAULT_LAKE_DIR
        return cls(Path(chosen).expanduser().resolve())

    @property
    def catalog_path(self) -> Path:
        """The DuckLake metadata catalog, a DuckDB file."""
        return self.lake_dir / "catalog.ducklake"

    @property
    def data_path(self) -> Path:
        """Parquet data files."""
        return self.lake_dir / "data"

    @property
    def tmp_dir(self) -> Path:
        """Scratch NDJSON files used while loading; emptied after every load."""
        return self.lake_dir / "tmp"

    @property
    def lock_path(self) -> Path:
        return self.lake_dir / ".lake.lock"

    @property
    def audit_log_path(self) -> Path:
        """One JSON line per ``lake_query`` call."""
        return self.lake_dir / "lake_query.log.jsonl"
