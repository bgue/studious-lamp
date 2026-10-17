"""The worker builder: one place that wires kinds, queue and limits for a ledger (S6)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from docworld import World
from tl_adapters.db import open_uow
from tl_core.derivation.registry import use_extractors
from tl_core.derivation.testing import make_extractors
from tl_mod_documents.derivation.store import use_files
from tl_mod_documents.derivation.worker import build_worker, requeue_orphans
from tl_mod_documents.testing import EXTRACTOR_FACTORY, index_csv

ROWS = [("47-FV-1001", "Feed", "CV", "4"), ("47-FV-1002", "Return", "HV", "6")]


@pytest.fixture(autouse=True)
def runtime(world: World) -> Iterator[None]:
    with use_extractors(make_extractors()), use_files(world.files):
        yield


@pytest.fixture
def ready(world: World) -> World:
    world.register("ISD-001", doc_type="IDX")
    world.create_revision("ISD-001")
    world.attach("ISD-001", "A")
    world.register_schema()
    return world


def test_a_built_worker_serves_the_extract_and_validate_jobs(ready: World) -> None:
    derived = ready.open_derived("ISD-001", "A")
    ready.upload_content(derived.id, index_csv(ROWS))
    ready.start_extraction(derived_id=derived.id)
    with build_worker(ready.db, ready.files, worker_id="w1", factory=EXTRACTOR_FACTORY) as worker:
        assert worker.runner.kinds == ("extract", "validate")
        results = worker.runner.run_until_idle()
    assert [(r.kind, r.outcome) for r in results] == [("extract", "done")]
    assert ready.derived_row(derived.id).state == "Valid"
    assert ready.jobs(derived.id)[0].worker == "w1"


def test_requeue_orphans_restores_jobs_the_queue_lost(ready: World) -> None:
    derived = ready.open_derived("ISD-001", "A")
    ready.upload_content(derived.id, index_csv(ROWS))
    ready.start_extraction(derived_id=derived.id)
    with open_uow(ready.db) as uow:
        uow.conn().exec_driver_sql("DELETE FROM job_queue")  # a restore from the archive
    assert requeue_orphans(ready.db) == 1
    assert requeue_orphans(ready.db) == 0
    with build_worker(ready.db, ready.files, factory=EXTRACTOR_FACTORY) as worker:
        assert len(worker.runner.run_until_idle()) == 1
    assert ready.derived_row(derived.id).state == "Valid"
