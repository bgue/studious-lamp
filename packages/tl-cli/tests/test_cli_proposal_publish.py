"""`tl proposal accept` of a publication proposal reads the stored rows (P1-I3 demo, clause 6).

The CLI process must configure the derivation module's file service itself: the demo found that
accepting an agent's `propose_import` failed with "no file service for derived data" because only
`tl derive` did.
"""

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
from tl_adapters.db import DbTarget, open_uow
from tl_core.services import proposals
from tl_mod_documents.derivation import store, views
from tl_mod_documents.derivation.publish import PublishDerivedTags

P = ["--project", "P123"]


@pytest.fixture
def env(
    new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[dict[str, str]]:
    values = derive_env(new_db, monkeypatch, tmp_path)
    made = seed(values, tmp_path)
    with runtime(made):
        as_admin(values)
        registered = tl(
            values, "derive", "schema", "register", str(schema_file(tmp_path)), "--company"
        )
        assert registered.exit_code == 0
        yield values


def run(env: dict[str, str], *args: str) -> str:
    result = tl(env, *args)
    assert result.exit_code == 0, result.output
    return result.stdout


def test_an_admin_accepts_a_publication_proposal_in_a_process_that_configured_nothing(
    env: dict[str, str], tmp_path: Path
) -> None:
    run(env, "derive", "open", "ISD-001", "A", "--schema", "instrument-index", *P)
    run(env, "derive", "content", KEY, str(csv_file(tmp_path, ROWS, "rows.csv")), *P)
    run(env, "derive", "start", KEY, *P)
    run(env, "derive", "worker", "--once", "--factory", FACTORY)
    with open_uow(env["TL_DB"], readonly=True) as uow:
        derived = views.find_derived(uow.conn(), "project:P123", KEY)
    command = PublishDerivedTags(
        actor="agent:triage",
        source="mcp:triage",
        scope="project:P123",
        derived_id=derived.id,
        expected_content_rev=derived.content_rev,
    )
    with open_uow(env["TL_DB"]) as uow:
        pid = proposals.propose(
            uow, tool="propose_import_tags", agent="agent:triage", command=command, summary="s"
        ).proposal_id
    store.configure(None)  # this process has said nothing: only `proposal accept` can
    assert f"accepted {pid}" in run(env, "proposal", "accept", pid)
    assert "state Published" in run(env, "derive", "show", KEY, *P)
