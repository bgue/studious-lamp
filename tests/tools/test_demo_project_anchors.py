"""The demo project's anchor tags and documents exist with their fixed properties (P2-SEED-T05).

One generator run (a child process, as in ``test_demo_project.py``) builds a fresh ledger; the
tests read it back. The names come from ``dev/seed/demo_project/anchors.py``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from tl_adapters.db import open_uow

ROOT = Path(__file__).resolve().parents[2]
# The fixed names (dev/seed/demo_project/anchors.py); written out here so the test checks them.
ANCHOR_TAGS = ("200-V-1027", "300-T-101")
ANCHOR_DOCUMENTS = ("P200-200-PID-4701", "P200-200-PID-4702")


def rows(db: Path, sql: str, **params: object) -> list[dict[str, object]]:
    with open_uow(db, readonly=True) as uow:
        return [dict(r) for r in uow.conn().execute(text(sql), params).mappings()]


@pytest.fixture(scope="module")
def ledger(tmp_path_factory: pytest.TempPathFactory) -> Path:
    base = tmp_path_factory.mktemp("demo-anchors")
    db = base / "p200.db"
    env = {**os.environ, "TL_ENV": "dev", "PYTHONPATH": str(ROOT)}
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "dev.seed.demo_project",
            "--db",
            str(db),
            "--objects",
            str(base / "objects"),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    return db


def test_the_anchor_constants_match_the_fixed_names() -> None:
    constants = (ROOT / "dev" / "seed" / "demo_project" / "anchors.py").read_text()
    for name in (*ANCHOR_TAGS, *ANCHOR_DOCUMENTS):
        assert f'"{name}"' in constants


def test_the_anchor_tags_exist_with_their_text(ledger: Path) -> None:
    found = {
        str(r["key"]): r
        for r in rows(
            ledger,
            "SELECT key, title, description FROM cur_core_record "
            "WHERE type = 'engineering.Tag' AND key IN (:a, :b)",
            a=ANCHOR_TAGS[0],
            b=ANCHOR_TAGS[1],
        )
    }
    assert set(found) == set(ANCHOR_TAGS)
    assert found["200-V-1027"]["title"] == "Reactor feed valve"
    assert found["300-T-101"]["title"] == "Crude tank"
    assert found["300-T-101"]["description"] == "Crude oil storage tank in the HT-2 tank farm."


def test_the_crude_tank_breaks_the_pattern_and_the_reactor_valve_does_not(ledger: Path) -> None:
    found = {
        str(r["number"]): r
        for r in rows(
            ledger,
            "SELECT number, number_status FROM cur_engineering_tag WHERE number IN (:a, :b)",
            a=ANCHOR_TAGS[0],
            b=ANCHOR_TAGS[1],
        )
    }
    assert found["200-V-1027"]["number_status"] == "ok"
    assert found["300-T-101"]["number_status"] == "violation"


def test_the_restricted_p_and_id_has_three_sheets_and_one_issued_revision(ledger: Path) -> None:
    doc = rows(
        ledger,
        "SELECT id, confidentiality FROM cur_documents_document WHERE number = :n",
        n=ANCHOR_DOCUMENTS[0],
    )
    assert len(doc) == 1
    assert doc[0]["confidentiality"] == "restricted"
    revisions = rows(
        ledger,
        "SELECT code, issue_status FROM cur_documents_revision WHERE document_id = :d",
        d=doc[0]["id"],
    )
    assert [(r["code"], r["issue_status"]) for r in revisions] == [("A", "IFC")]
    sheets = rows(
        ledger,
        "SELECT page_count FROM cur_documents_rendition WHERE document_id = :d AND is_current = 1",
        d=doc[0]["id"],
    )
    assert [r["page_count"] for r in sheets] == [3]


def test_the_second_p_and_id_has_revisions_a_and_b_with_a_superseded_by_b(ledger: Path) -> None:
    doc = rows(
        ledger,
        "SELECT id, confidentiality FROM cur_documents_document WHERE number = :n",
        n=ANCHOR_DOCUMENTS[1],
    )
    assert len(doc) == 1
    assert doc[0]["confidentiality"] is None
    revisions = {
        str(r["code"]): r
        for r in rows(
            ledger,
            "SELECT code, is_current, superseded_by, issue_status FROM cur_documents_revision "
            "WHERE document_id = :d",
            d=doc[0]["id"],
        )
    }
    assert set(revisions) == {"A", "B"}
    assert revisions["B"]["is_current"] == 1
    assert revisions["A"]["superseded_by"] is not None
    assert revisions["A"]["is_current"] == 0
