"""Documents in the lake: silver, marts and the walking test of confidentiality (P1-I8; ADR-0016).

The lake is read by every user and by agents, so a restricted document must be in no row, no
count and no aggregate of silver or of a mart; a document that is classified or declassified after
a sync must leave or come back at the next sync, with its revisions, and the lake must equal one
built from scratch.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from builder import LedgerBuilder
from lakecheck import do_sync, lake_dump
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_lake import LakeConfig
from tl_lake.doc_marts import ISSUES_TABLE, MARTS, STATUS_TABLE, TURNAROUND_TABLE
from tl_lake.duck import open_lake
from tl_mod_documents.handlers.documents import (
    SetDocumentConfidentiality,
    handle_set_document_confidentiality,
)
from tl_mod_documents.testing import BASE, DocumentsWorld

SILVER = ("cur_core_record", "cur_documents_document", "cur_documents_revision", "pset_values")


@pytest.fixture
def world(ledger: LedgerBuilder, tmp_path: Path) -> DocumentsWorld:
    return DocumentsWorld(ledger.db, tmp_path / "objects")


def seed(world: DocumentsWorld) -> dict[str, str]:
    """ISO-1 internal, ISO-2 restricted, ISO-3 internal; each with an issued revision A.
    The ids of the documents."""
    with cf.system_view():
        for number, extra in (("ISO-1", {}), ("ISO-2", {"confidentiality": "restricted"}),
                              ("ISO-3", {})):  # fmt: skip
            world.register(number, title=f"Title of {number}", **extra)
            world.create_revision(number)
            world.attach(number, "A")
            world.issue(number, "A", "IFR")
        return {n: world.document(n).id for n in ("ISO-1", "ISO-2", "ISO-3")}


def classify(world: DocumentsWorld, document_id: str, value: str | None) -> None:
    with cf.system_view(), open_uow(world.db) as uow:
        handle_set_document_confidentiality(
            uow,
            SetDocumentConfidentiality(
                **{**BASE, "actor": "user:ctl"},
                stream_id=document_id,
                confidentiality=value,
                reason="test",
            ),
        )


def lake_text(config: LakeConfig, *, bronze: bool = False) -> str:
    """All text of the lake's tables; without ``bronze`` the copied events are left out: events
    copied before a reclassification stay until the next rebuild (ADR-0016)."""
    with open_lake(config, write=False) as con:
        names = [
            r[0]
            for r in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchall()
        ]
        parts: list[str] = []
        for name in names:
            if name == "events" and not bronze:
                continue
            for row in con.execute(f'SELECT * FROM "{name}"').fetchall():  # noqa: S608
                parts.append(" ".join(str(v) for v in row))
    return "\n".join(parts)


def column(config: LakeConfig, sql: str) -> list[Any]:
    with open_lake(config, write=False) as con:
        return [r[0] for r in con.execute(sql).fetchall()]


def documents_in_marts(config: LakeConfig) -> dict[str, int]:
    return {
        "status": sum(column(config, f"SELECT documents FROM {STATUS_TABLE}")),
        "turnaround": sum(column(config, f"SELECT documents FROM {TURNAROUND_TABLE}")),
        "issues": sum(column(config, f"SELECT revisions_issued FROM {ISSUES_TABLE}")),
    }


def test_a_restricted_document_is_in_no_silver_row_and_no_mart_cell(
    ledger: LedgerBuilder, lake: LakeConfig, world: DocumentsWorld
) -> None:
    ids = seed(world)
    with cf.system_view():
        revision_ids = {n: world.revision(n, "A").id for n in ids}
    do_sync(ledger, lake)
    everything = lake_text(lake)
    assert "ISO-1" in everything and "Title of ISO-1" in everything
    assert "ISO-2" not in lake_text(lake, bronze=True)  # the events too: never copied
    for hidden in (ids["ISO-2"], revision_ids["ISO-2"], "ISO-2", "Title of ISO-2"):
        assert hidden not in everything, hidden
    assert column(lake, "SELECT count(*) FROM cur_documents_document") == [2]
    assert column(lake, "SELECT count(*) FROM cur_documents_revision") == [2]
    assert documents_in_marts(lake) == {"status": 2, "turnaround": 2, "issues": 2}


def test_a_document_classified_after_the_sync_leaves_and_comes_back_with_its_revision(
    ledger: LedgerBuilder, lake: LakeConfig, world: DocumentsWorld
) -> None:
    ids = seed(world)
    with cf.system_view():
        revision = world.revision("ISO-3", "A").id
    do_sync(ledger, lake)
    assert revision in lake_text(lake)
    assert documents_in_marts(lake)["status"] == 2

    classify(world, ids["ISO-3"], "restricted")
    do_sync(ledger, lake)
    gone = lake_text(lake)
    for hidden in (ids["ISO-3"], revision, "ISO-3", "Title of ISO-3"):
        assert hidden not in gone, hidden
    assert documents_in_marts(lake) == {"status": 1, "turnaround": 1, "issues": 1}

    classify(world, ids["ISO-3"], None)
    do_sync(ledger, lake)
    back = lake_text(lake)
    assert revision in back and "Title of ISO-3" in back
    assert column(lake, "SELECT count(*) FROM cur_documents_revision") == [2]
    assert documents_in_marts(lake) == {"status": 2, "turnaround": 2, "issues": 2}


def test_the_lake_after_reclassifications_equals_one_built_from_scratch(
    ledger: LedgerBuilder,
    lake: LakeConfig,
    world: DocumentsWorld,
    tmp_path: Path,
) -> None:
    ids = seed(world)
    do_sync(ledger, lake)
    classify(world, ids["ISO-3"], "restricted")
    do_sync(ledger, lake)
    classify(world, ids["ISO-2"], None)
    classify(world, ids["ISO-1"], "restricted")
    do_sync(ledger, lake)
    world.register("ISO-4", title="Title of ISO-4")
    do_sync(ledger, lake)

    fresh = LakeConfig.at(tmp_path / "fresh")
    do_sync(ledger, fresh)
    for table in (*SILVER, *MARTS):
        assert lake_dump(lake, table) == lake_dump(fresh, table), table
    # ISO-2 is readable, ISO-1 and ISO-3 are not
    text = lake_text(lake)
    assert "Title of ISO-2" in text and "Title of ISO-4" in text
    assert "Title of ISO-1" not in text and "Title of ISO-3" not in text
