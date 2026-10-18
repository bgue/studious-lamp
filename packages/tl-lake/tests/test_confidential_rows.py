"""The lake holds nothing of a record that is not `internal` (ADR-0016, brief 18.10).

The lake is read by every user and by agents, so an item of any other class (restricted,
privileged, an unknown class), its clock and thread, and the numbering events that name it are
redacted like account events: the row stays so ``seq`` has no gap, and says nothing.
"""

from __future__ import annotations

from builder import SCOPE, LedgerBuilder
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.services.commands import Command
from tl_lake import LakeConfig, read_snapshot, sync_lake
from tl_lake.duck import open_lake
from tl_mod_correspondence.handlers.create import create_item
from tl_mod_correspondence.testing import CorrWorld, frozen_today


class _Cmd(Command):
    """A command carrier for seeding."""


def all_text(lake: LakeConfig) -> str:
    with open_lake(lake, write=False) as con:
        tables = [
            r[0]
            for r in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchall()
        ]
        parts: list[str] = []
        for name in tables:
            for row in con.execute(f'SELECT * FROM "{name}"').fetchall():  # noqa: S608
                parts.append(" ".join(str(v) for v in row))
    return "\n".join(parts)


def test_the_lake_has_no_row_of_a_hidden_item(ledger: LedgerBuilder, lake: LakeConfig) -> None:
    cmd = _Cmd(actor="user:seed", source="test", scope=SCOPE)
    made: dict[str, tuple[str, str]] = {}
    corr = CorrWorld(ledger.db)
    with frozen_today("2026-10-19"), cf.system_view():
        for kind in ("internal", "restricted", "privileged", "bogus"):
            with open_uow(ledger.db) as uow:
                result = create_item(
                    uow,
                    cmd,
                    subject=f"{kind.upper()}LAKESUBJECT",
                    direction="in",
                    medium="letter",
                    received_via="manual",
                    confidentiality=kind,
                    received_on="2026-10-19",
                    received=True,
                )
            made[kind] = (result.stream_id, result.key or "")
            corr.start_clock(result.stream_id, label=f"{kind.upper()}LAKECLOCK")
    engine = ledger.engine()
    try:
        with read_snapshot(engine) as conn:
            sync_lake(lake, conn)
    finally:
        engine.dispose()
    everything = all_text(lake)
    assert "INTERNALLAKESUBJECT" in everything and made["internal"][1] in everything
    for kind in ("restricted", "privileged", "bogus"):
        item_id, number = made[kind]
        assert item_id not in everything, kind
        assert number not in everything, kind
        assert f"{kind.upper()}LAKESUBJECT" not in everything, kind
        assert f"{kind.upper()}LAKECLOCK" not in everything, kind
    with open_lake(lake, write=False) as con:  # the rows stay, so seq has no gap
        seqs = [r[0] for r in con.execute("SELECT seq FROM events ORDER BY seq").fetchall()]
    assert seqs == list(range(1, len(seqs) + 1))
