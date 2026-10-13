"""`tl doc report register|history|overdue|transmittals|stale` on a temporary ledger (P1-I2-T11b).

The data is made with the module's own test world and handlers (`doccli_support.world`); the
commands under test only read.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from doccli_support import docs_env, world
from tl_adapters.db import DbTarget, open_uow
from tl_cli.main import app
from tl_mod_documents.handlers.reviews import (
    OpenReviewCycle,
    ReviewerRequest,
    handle_open_review_cycle,
)
from tl_mod_documents.handlers.transmittals import (
    CreateTransmittal,
    IssueTransmittal,
    Recipient,
    handle_create_transmittal,
    handle_issue_transmittal,
)
from tl_mod_documents.testing import BASE, DocumentsWorld
from typer.testing import CliRunner
from typer.testing import Result as RunResult

runner = CliRunner()
SINCE = ("--on", "2026-03-01")  # the day the overdue reports judge by


@pytest.fixture
def env(new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    return docs_env(new_db, monkeypatch)


def run(env: dict[str, str], *args: str, ok: bool = True) -> RunResult:
    result = runner.invoke(app, list(args), env=env)
    assert result.exception is None or isinstance(result.exception, SystemExit), result.exception
    assert (result.exit_code == 0) is ok, result.output
    return result


def report(env: dict[str, str], *args: str, ok: bool = True) -> RunResult:
    return run(env, "doc", "report", *args, "--project", "P123", ok=ok)


def rows(result: RunResult) -> list[list[str]]:
    return [line.split("  ") for line in result.stdout.splitlines()]


def call(made: DocumentsWorld, handler: Any, command: Any) -> Any:
    with open_uow(made.db) as uow:
        return handler(uow, command)


@pytest.fixture
def busy(env: dict[str, str], tmp_path: Path) -> DocumentsWorld:
    """ISO-1234 (A issued IFR, B issued IFC, a link pinned to A, a transmittal of B),
    ISO-2000 (a draft A in review by Ana, due long ago) and ISO-3000 (registered only)."""
    made = world(env, tmp_path)
    made.people("u", "ana")
    made.issued_document("ISO-1234", "IFR")
    made.link(made.tag(), "ISO-1234", "A")
    made.create_revision("ISO-1234", purpose="For construction")
    made.attach("ISO-1234", "B", data=b"%PDF-1.7 sheet B", name="b.pdf")
    made.issue("ISO-1234", "B", "IFC")
    sent = call(
        made,
        handle_create_transmittal,
        CreateTransmittal(
            **BASE,
            subject="Isometrics to site",
            purpose="for_construction",
            due_date="2026-01-15",
            recipients=[Recipient(name="Site")],
            revision_ids=[made.revision("ISO-1234", "B").id],
        ),
    )
    call(made, handle_issue_transmittal, IssueTransmittal(**BASE, stream_id=sent.stream_id))
    made.register("ISO-2000", discipline="ELE")
    made.create_revision("ISO-2000")
    made.attach("ISO-2000", "A", data=b"%PDF-1.7 spec", name="spec.pdf")
    call(
        made,
        handle_open_review_cycle,
        OpenReviewCycle(
            **BASE,
            revision_id=made.revision("ISO-2000", "A").id,
            reviewers=[ReviewerRequest(reviewer="user:ana")],
            due_date="2026-01-31",
        ),
    )
    made.register("ISO-3000")
    return made


def test_the_register_lists_documents_by_number_with_counts(
    env: dict[str, str], busy: DocumentsWorld
) -> None:
    out = rows(report(env, "register"))
    assert [r[0] for r in out] == ["ISO-1234", "ISO-2000", "ISO-3000"]
    iso = out[0]
    assert iso[1:8] == ["Issued", "B(IFC)", "ISO", "PIP", "revisions=2", "open=-", "stale=1"]
    assert out[1][1:3] == ["In Review", "-"] and "open=A" in out[1]
    assert out[2][1:3] == ["Registered", "-"]
    only = rows(report(env, "register", "--state", "Issued"))
    assert [r[0] for r in only] == ["ISO-1234"]
    typed = rows(report(env, "register", "--discipline", "ELE"))
    assert [r[0] for r in typed] == ["ISO-2000"]


def test_the_register_as_json(env: dict[str, str], busy: DocumentsWorld) -> None:
    data = json.loads(report(env, "register", "--json").stdout)
    assert [d["number"] for d in data] == ["ISO-1234", "ISO-2000", "ISO-3000"]
    assert data[0]["current_code"] == "B" and data[0]["stale_links"] == 1


def test_the_history_shows_every_revision_with_what_belongs_to_it(
    env: dict[str, str], busy: DocumentsWorld
) -> None:
    out = rows(report(env, "history", "ISO-1234"))
    assert [r[0] for r in out] == ["A", "B"]
    assert out[0][1:4] == ["Issued", "IFR", "review"] and out[0][5] == "current"
    assert out[0][6:] == ["renditions=1", "transmittals=-", "review=-", "superseded_by=-"]
    assert out[1][1:4] == ["Issued", "IFC", "construction"] and out[1][5] == "current"
    assert out[1][7] == "transmittals=" + busy.scalar(
        "SELECT number FROM cur_documents_transmittal"
    )
    as_json = json.loads(report(env, "history", "ISO-1234", "--json").stdout)
    assert [d["code"] for d in as_json] == ["A", "B"]
    ghost = report(env, "history", "NOPE-1", ok=False)
    assert ghost.stderr.startswith("error: ") and "NOPE-1" in ghost.stderr


def test_overdue_reviews_are_the_open_unanswered_ones_past_their_date(
    env: dict[str, str], busy: DocumentsWorld
) -> None:
    out = rows(report(env, "overdue", *SINCE))
    assert out == [["ISO-2000@A", "ISO-2000@A/RC1", "user:ana", "due=2026-01-31", "29d overdue"]]
    assert report(env, "overdue", "--on", "2026-01-01").stdout == ""
    bad = report(env, "overdue", "--on", "tomorrow", ok=False)
    assert bad.stderr.strip() == "error: --on must be a date written YYYY-MM-DD, got 'tomorrow'"
    as_json = json.loads(report(env, "overdue", *SINCE, "--json").stdout)
    assert as_json[0]["reviewer"] == "user:ana" and as_json[0]["days_overdue"] == 29


def test_the_transmittal_log_marks_the_issued_ones_that_wait_past_their_date(
    env: dict[str, str], busy: DocumentsWorld
) -> None:
    number = busy.scalar("SELECT number FROM cur_documents_transmittal")
    (line,) = rows(report(env, "transmittals", *SINCE))
    assert line[:4] == [number, "Issued", "outgoing", "for_construction"]
    assert line[5:] == ["due=2026-01-15", "response=-", "items=1", "overdue"]
    early = rows(report(env, "transmittals", "--on", "2026-01-01"))
    assert early[0][-1] == "items=1"  # not yet overdue
    assert report(env, "transmittals", "--state", "Closed").stdout == ""
    assert report(env, "transmittals", "--direction", "incoming").stdout == ""


def test_stale_pins_name_the_document_the_pin_and_what_replaced_it(
    env: dict[str, str], busy: DocumentsWorld
) -> None:
    (line,) = rows(report(env, "stale"))
    link_id = busy.scalar("SELECT link_id FROM cur_links")
    assert line == ["ISO-1234", "pinned=A", "current=B", "newer=B", "47-FV-1001", link_id]
    data = json.loads(report(env, "stale", "--json").stdout)
    assert data[0]["pinned_code"] == "A" and data[0]["newer_codes"] == ["B"]
