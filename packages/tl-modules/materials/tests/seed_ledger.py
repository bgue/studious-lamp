"""The seed ledger the screens, the CLI and the clients read (the S3 acceptance ``seed``)."""

from __future__ import annotations

from pathlib import Path

import acc_s3
from tl_adapters.db import as_target, create_schema


def build_seed(path: Path) -> Path:
    """A SQLite ledger at ``path`` with project P123: 50 items, 9 locations, 15 PO lines, an
    accepted receipt of two flange lines with its MTR, and an MTO of three lines."""
    target = as_target(path)
    create_schema(target)
    world = acc_s3.World(target, path.parent / "p2-i3-objects")
    world.project = "project:P123"
    world.number = "P123"
    acc_s3.seed(world)
    return path
