"""Entry point: ``tl-tui`` / ``python -m tl_tui`` runs the TUI in embedded mode (brief 4)."""

from __future__ import annotations

import os
from pathlib import Path

from tl_tui.app import TlApp
from tl_tui.embedded import EmbeddedClient

DEFAULT_DB = "./dev/data/tl.db"
DEFAULT_PROJECT = "P123"


def build_app(db: str | Path, project: str = DEFAULT_PROJECT) -> TlApp:
    """The app over the SQLite dev ledger at ``db``, showing project ``project``."""
    return TlApp(EmbeddedClient.for_sqlite(db), scope=f"project:{project}")


def main() -> None:
    db = os.environ.get("TL_DB", DEFAULT_DB)
    project = os.environ.get("TL_PROJECT", DEFAULT_PROJECT)
    build_app(db, project).run()
