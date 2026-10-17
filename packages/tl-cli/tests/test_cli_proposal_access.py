"""`tl proposal accept` needs the access the proposed command needs (ADR-0014 section 8)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from tl_adapters.db import DbTarget, open_uow
from tl_cli.main import app
from tl_core.services import proposals
from tl_mod_documents.derivation.publish import PublishDerivedTags
from typer.testing import CliRunner

runner = CliRunner()
AGENT = "agent:triage"


@pytest.fixture
def env(
    new_db: Callable[[], DbTarget], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[dict[str, str]]:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    values = {"TL_DB": str(new_db())}
    assert runner.invoke(app, ["init"], env=values).exit_code == 0
    yield values


def test_without_an_admin_session_a_tag_publication_proposal_stays_pending(
    env: dict[str, str],
) -> None:
    command = PublishDerivedTags(
        actor=AGENT,
        source="mcp:triage",
        scope="project:P123",
        derived_id="NOSUCH",
        expected_content_rev=1,
    )
    with open_uow(env["TL_DB"]) as uow:
        pid = proposals.propose(
            uow, tool="propose_import_tags", agent=AGENT, command=command, summary="publish"
        ).proposal_id
    result = runner.invoke(app, ["proposal", "accept", pid], env=env)
    assert result.exit_code == 1, result.output
    assert "needs the admin role" in result.output
    listed = runner.invoke(app, ["proposal", "ls", "--project", "P123"], env=env)
    assert pid in listed.output
