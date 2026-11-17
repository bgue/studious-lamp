"""V3-P1: the per-row hidden-record statement stays small (it was 106 KB: one copy of the two-hop
subject chain in each of ~30 parts). No ledger: the text is built from the sources."""

from __future__ import annotations

import pytest
from tl_core import confidentiality as cf

#: The cap on the per-row statement, bytes of SQL.
STATEMENT_CAP = 20_000


@pytest.mark.parametrize("level", [0, 1])
@pytest.mark.parametrize("account", ["", "user:treyes"])
def test_the_per_row_hidden_statement_stays_small(level: int, account: str) -> None:
    viewer = cf.Viewer(actor=account or "agent:x", level=level, account=account)
    sql = cf.hidden_sql(viewer, only="hr.id = l.id")
    assert sql is not None
    assert len(sql) <= STATEMENT_CAP, f"{len(sql)} bytes"
