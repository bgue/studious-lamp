"""The schema directory the demo project reads: the fixtures plus the P200 working calendar.

The response clocks of the correspondence module count on ``<project>-default@<n>`` in the schema
directory's ``calendars/`` folder. The committed fixtures hold the P123 calendar only, so the
generator builds ``dev/data/demo-project-schema/`` (symlinks to every fixture, and a ``calendars``
folder that adds ``P200-default@1.yaml``) and points ``TL_SCHEMA_DIR`` at it. A client of the demo
ledger (``tl serve``, the TUI) needs the same ``TL_SCHEMA_DIR`` to read a clock.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from tl_schema.registry import DEFAULT_SCHEMA_DIR

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OVERLAY = ROOT / "dev" / "data" / "demo-project-schema"
CALENDAR = HERE / "data" / "P200-default@1.yaml"


def build_overlay(target: Path = OVERLAY) -> Path:
    """Make (or refresh) the overlay directory and return it."""
    source = Path(DEFAULT_SCHEMA_DIR)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for entry in sorted(source.iterdir()):
        if entry.name != "calendars":
            (target / entry.name).symlink_to(entry.resolve())
    calendars = target / "calendars"
    calendars.mkdir()
    for entry in sorted((source / "calendars").iterdir()):
        (calendars / entry.name).symlink_to(entry.resolve())
    shutil.copyfile(CALENDAR, calendars / CALENDAR.name)
    return target


def use_overlay() -> Path:
    """Build the overlay and make it the schema directory of this process."""
    target = build_overlay()
    os.environ["TL_SCHEMA_DIR"] = str(target)
    return target
