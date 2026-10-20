"""The document register loader target: create-only, restricted when asked, voided on rollback."""

from __future__ import annotations

from pathlib import Path

import pytest
from tl_core import confidentiality as cf
from tl_mod_documents.testing import DocumentsWorld
from tl_mod_legacy.errors import CompensationRefusedError
from tl_mod_legacy.model import use_loaders
from tl_mod_legacy.testing import ADMIN, DOC_FILE, PROJECT, LegacyWorld, document_loader

DATA = DOC_FILE.read_bytes()
CONTROLLER = cf.Viewer(actor=ADMIN, level=1, account=ADMIN)


def test_a_register_loads_its_valid_rows_and_counts_the_rest(world: LegacyWorld) -> None:
    run = world.through_plan("test-docs", "register.csv", DATA)
    assert (run.plan_new, run.plan_existing, run.plan_invalid) == (9, 0, 7)
    outcome = world.service.load(PROJECT, run.key, actor=ADMIN)
    assert (outcome.created, outcome.skipped_invalid) == (9, 7)
    docs = world.rows(
        "SELECT d.number, r.description FROM cur_documents_document d "
        "JOIN cur_core_record r ON r.id = d.id ORDER BY d.number"
    )
    assert len(docs) == 9
    assert any((d["description"] or "").startswith("Legacy register: revision") for d in docs)
    first = world.rows(
        "SELECT source FROM events WHERE stream_id = :i AND event_type = 'Record.Created'",
        i=world.run(run.key).record_ids[0],
    )[0]
    assert first["source"] == "legacy:dms"
    _, report = world.service.reconcile(PROJECT, run.key, actor=ADMIN)
    assert report["problems"] == []
    assert report["mismatches"] == 0 and report["matched"] == 9 and report["invalid_rows"] == 7


def test_the_documents_of_a_loader_can_be_restricted(world: LegacyWorld) -> None:
    # registering a restricted document is a controller's act: the viewer must be one
    with (
        use_loaders({"test-docs": document_loader(confidentiality="restricted")}),
        cf.use_viewer(CONTROLLER),
    ):
        run = world.loaded("test-docs", "register.csv", DATA)
        assert len(world.run(run.key).record_ids) == 9
        assert world.service.preview_compensation(PROJECT, run.key) == []
    classes = {
        r["confidentiality"]
        for r in world.rows("SELECT confidentiality FROM cur_documents_document")
    }
    assert classes == {"restricted"}


def test_compensation_voids_the_documents_the_run_registered(world: LegacyWorld) -> None:
    run = world.loaded("test-docs", "register.csv", DATA)
    assert world.service.preview_compensation(PROJECT, run.key) == []
    outcome = world.service.compensate(PROJECT, run.key, actor=ADMIN, reason="wrong register")
    assert outcome.reversed == 9
    voided = world.scalar(
        "SELECT count(*) FROM cur_core_record WHERE type = 'documents.Document' AND voided"
    )
    assert voided == 9
    assert world.run(run.key).state == "Compensated"


def test_a_document_with_a_revision_cannot_be_taken_back(
    world: LegacyWorld, tmp_path: Path
) -> None:
    run = world.loaded("test-docs", "register.csv", DATA)
    other = DocumentsWorld(world.db, tmp_path / "doc-objects")
    other.create_revision("ISO-0101")
    problems = world.service.preview_compensation(PROJECT, run.key)
    assert len(problems) == 1 and problems[0].startswith("ISO-0101:")
    with pytest.raises(CompensationRefusedError):
        world.service.compensate(PROJECT, run.key, actor=ADMIN, reason="undo")
    assert world.run(run.key).state == "Loaded"
    assert (
        world.scalar(
            "SELECT count(*) FROM cur_core_record WHERE type = 'documents.Document' AND voided"
        )
        == 0
    )
