"""`tl derive open|content|start|ls|jobs|cancel|worker` (P1-I3-T14b). Provided; do not edit."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from auth_support import run as tl
from derivecli_support import (
    FACTORY,
    KEY,
    ROWS,
    as_admin,
    csv_file,
    derive_env,
    runtime,
    schema_file,
    seed,
)
from tl_adapters.db import DbTarget
from typer.testing import Result as RunResult

P = ["--project", "P123"]


@pytest.fixture
def env(
    new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[dict[str, str]]:
    values = derive_env(new_db, monkeypatch, tmp_path)
    made = seed(values, tmp_path)
    with runtime(made):
        as_admin(values)
        assert (
            tl(
                values, "derive", "schema", "register", str(schema_file(tmp_path)), "--company"
            ).exit_code
            == 0
        )
        yield values


def derive(env: dict[str, str], *args: str, ok: bool = True) -> RunResult:
    result = tl(env, "derive", *args)
    assert (result.exit_code == 0) is ok, result.output
    return result


def test_open_is_idempotent_and_prints_the_key_and_id(env: dict[str, str]) -> None:
    first = derive(env, "open", "ISD-001", "A", "--schema", "instrument-index", *P).stdout.split()
    assert first[0] == "opened" and first[1] == KEY and len(first[2]) == 26
    again = derive(env, "open", "ISD-001", "A", "--schema", "instrument-index", *P).stdout.split()
    assert again == first
    listed = derive(env, "ls", *P).stdout
    assert listed.startswith(f"{KEY}  Pending  pass 0  rows -  errors -  instrument-index@1.0.0")


def test_open_names_what_is_missing(env: dict[str, str]) -> None:
    out = derive(env, "open", "ISD-009", "A", "--schema", "instrument-index", *P, ok=False)
    assert "no revision 'A' of document 'ISD-009'" in out.output
    out = derive(env, "open", "ISD-001", "A", "--schema", "nope", *P, ok=False)
    assert "error:" in out.output


def test_content_start_worker_and_ls_take_a_csv_to_valid(
    env: dict[str, str], tmp_path: Path
) -> None:
    derive(env, "open", "ISD-001", "A", "--schema", "instrument-index", *P)
    attached = derive(env, "content", KEY, str(csv_file(tmp_path, ROWS)), *P).stdout.split()
    assert attached[:2] == ["attached", "index.csv"] and len(attached[2]) == 26
    queued = derive(env, "start", KEY, *P).stdout.strip()
    assert queued.startswith("queued ") and queued.endswith(f" for {KEY}")
    jobs = derive(env, "jobs", *P).stdout.splitlines()
    assert len(jobs) == 1 and f"extract  queued  attempt 0/3  {KEY}" in jobs[0]
    assert "Processing" in derive(env, "ls", *P).stdout
    ran = derive(env, "worker", "--once", "--factory", FACTORY).stdout.splitlines()
    assert ran[0].endswith(" extract done") and ran[0].startswith("ran ")
    assert ran[-1] == "worker done: ran=1"
    assert f"{KEY}  Valid  pass 1  rows 3  errors 0" in derive(env, "ls", *P).stdout
    assert "succeeded" in derive(env, "jobs", *P, "--state", "succeeded").stdout
    assert derive(env, "jobs", *P, "--state", "queued").stdout.strip() == ""


def test_start_can_open_from_a_document_and_a_revision(env: dict[str, str], tmp_path: Path) -> None:
    derive(env, "open", "ISD-001", "A", "--schema", "instrument-index", *P)
    derive(env, "content", KEY, str(csv_file(tmp_path, ROWS)), *P)
    out = derive(
        env, "start", "--doc", "ISD-001", "--rev", "A", "--schema", "instrument-index", *P
    ).stdout
    assert out.startswith("queued ") and out.strip().endswith(f"for {KEY}")


def test_start_wants_exactly_one_way_to_name_the_target(env: dict[str, str]) -> None:
    assert "give a derived document, or --doc" in derive(env, "start", *P, ok=False).output
    both = derive(
        env, "start", KEY, "--doc", "ISD-001", "--rev", "A", "--schema", "x", *P, ok=False
    )
    assert "give a derived document, or --doc" in both.output


def test_a_second_start_while_a_job_waits_is_refused_and_cancel_frees_it(
    env: dict[str, str], tmp_path: Path
) -> None:
    derive(env, "open", "ISD-001", "A", "--schema", "instrument-index", *P)
    derive(env, "content", KEY, str(csv_file(tmp_path, ROWS)), *P)
    derive(env, "start", KEY, *P)
    assert "error:" in derive(env, "start", KEY, *P, ok=False).output
    job_id = tl(env, "derive", "jobs", *P).stdout  # the key is not the id: read it from the ledger
    from sqlalchemy import text
    from tl_adapters.db import as_target, open_uow

    with open_uow(as_target(env["TL_DB"]), readonly=True) as uow:
        job_id = str(
            uow.conn().execute(text("SELECT id FROM v_documents_processing_job")).scalar_one()
        )
    cancelled = derive(env, "cancel", job_id, *P, "--reason", "wrong file").stdout
    assert cancelled.startswith("cancelled ")
    assert "cancelled" in derive(env, "jobs", *P).stdout
    assert "error:" in derive(env, "cancel", job_id, *P, ok=False).output  # no longer queued
    derive(env, "start", KEY, *P)  # free again


def test_a_pdf_alone_is_read_for_metadata_and_the_document_stays_pending(
    env: dict[str, str],
) -> None:
    derive(env, "start", "--doc", "ISD-001", "--rev", "A", "--schema", "instrument-index", *P)
    ran = derive(env, "worker", "--once", "--factory", FACTORY).stdout
    assert " extract done" in ran
    assert f"{KEY}  Pending  pass 1  rows 0" in derive(env, "ls", *P).stdout


def test_worker_without_a_file_service_says_so(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TL_OBJECT_STORE", "s3")
    monkeypatch.delenv("TL_S3_BUCKET", raising=False)
    result = tl(env | {"TL_OBJECT_STORE": "s3"}, "derive", "worker", "--once")
    assert result.exit_code == 1 and "TL_S3_BUCKET" in result.output


def test_requeue_restores_jobs_the_queue_lost(env: dict[str, str], tmp_path: Path) -> None:
    from sqlalchemy import text
    from tl_adapters.db import as_target, open_uow

    derive(env, "open", "ISD-001", "A", "--schema", "instrument-index", *P)
    derive(env, "content", KEY, str(csv_file(tmp_path, ROWS)), *P)
    derive(env, "start", KEY, *P)
    with open_uow(as_target(env["TL_DB"])) as uow:
        uow.conn().execute(text("DELETE FROM job_queue"))
    ran = derive(env, "worker", "--once", "--requeue", "--factory", FACTORY).stdout.splitlines()
    assert ran[0] == "requeued 1" and ran[-1] == "worker done: ran=1"
    assert "Valid" in derive(env, "ls", *P).stdout
