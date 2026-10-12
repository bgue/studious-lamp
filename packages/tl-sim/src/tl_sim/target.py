"""The ledger a run's MCP server opens: a SQLite file or a Postgres URL, carried and never opened.

The simulator stays outside the ledger (brief 29.1): it hands the target to the MCP child process
in the child's environment, and the child (``tl_mcp``) checks and opens it.
"""

from __future__ import annotations

from pathlib import Path

LedgerTarget = str | Path
"""A SQLite file (a ``Path``) or a ``postgresql://`` URL (text)."""


def ledger_target(text: str) -> LedgerTarget:
    """A ``TL_DB`` value as a target: anything with ``scheme://`` stays text, the rest is a file.

    The MCP child validates it (``tl_adapters.db.as_target``); the simulator only carries it.
    """
    return text if "://" in text else Path(text)
