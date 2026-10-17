"""The derivation tools: three reads, and two proposals that need a person's acceptance (P1-I3)."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp_harness import ACTOR, SCOPE, McpHarness
from tl_core.derivation.registry import use_extractors
from tl_core.derivation.testing import make_extractors
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_core.services import proposals
from tl_core.services.errors import ProposalAccessError
from tl_mod_documents.derivation.store import use_files
from tl_mod_documents.testing import DocumentsWorld

ROWS = [("47-FV-1001", "Feed", "CV", "4"), ("47-FV-1002", "Return", "HV", "6")]
KEY = "ISD-001@A/instrument-index"
ALICE = "user:alice"


class Env:
    def __init__(self, harness: McpHarness, world: DocumentsWorld) -> None:
        self.h, self.world = harness, world

    def tags(self) -> list[Any]:
        """The Record.Created events of tags (the standards create records of their own)."""
        return [
            e
            for e in self.events("Record.Created")
            if str(e.payload.get("key", "")).startswith("47-")
        ]

    def events(self, event_type: str) -> list[Any]:
        with self.h.factory(True) as uow:
            return [e for e in uow.ledger.read_after(0, limit=5000) if e.event_type == event_type]


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Env]:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    with use_provider(DirectorySchemaProvider()), use_extractors(make_extractors()):
        harness = McpHarness.build(tmp_path)
        try:
            world = DocumentsWorld(harness.db, tmp_path / "objects")
            with use_files(world.files):
                world.load_standards()
                world.register("ISD-001")
                world.create_revision("ISD-001")
                world.attach("ISD-001", "A")
                world.register_schema()
                world.valid_derived(ROWS)
                yield Env(harness, world)
        finally:
            harness.close()


def test_the_five_tools_are_registered_with_the_right_hints(env: Env) -> None:
    tools = {t.name: t for t in asyncio.run(env.h.server.list_tools())}
    for name in ("list_derived_documents", "get_derived_document", "validate_against_schema"):
        assert tools[name].annotations is not None
        assert tools[name].annotations.read_only_hint is True  # type: ignore[union-attr]
    for name in ("start_extraction", "propose_import"):
        assert tools[name].annotations is not None
        assert tools[name].annotations.read_only_hint is False  # type: ignore[union-attr]
        assert "person must accept" in " ".join((tools[name].description or "").split()) or (
            "Accepting needs" in (tools[name].description or "")
        )


def test_the_reads_show_the_derived_document_and_the_stored_report(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    def never(*args: object, **kwargs: object) -> None:
        raise AssertionError("a read must not run a JSON Schema")

    monkeypatch.setattr("tl_mod_documents.derivation.validation_isolated.run_in_envelope", never)
    monkeypatch.setattr("tl_mod_documents.derivation.validation.validate_result", never)
    listed = env.h.structured("list_derived_documents", project="P123")["result"]
    assert [d["key"] for d in listed] == [KEY] and listed[0]["state"] == "Valid"
    assert (
        env.h.structured("list_derived_documents", project="P123", state="Invalid")["result"] == []
    )
    one = env.h.structured("get_derived_document", project="P123", derived=KEY)
    assert one["content_rev"] == 1 and one["active_job"] is None
    report = env.h.structured("validate_against_schema", project="P123", derived=KEY)
    assert report["status"] == "valid" and report["rows_checked"] == 2
    assert len(env.world.contents(one["id"])) == 1
    assert env.events("Proposal.Created") == []
    with pytest.raises(ToolError, match="no derived document"):
        env.h.call("get_derived_document", project="P123", derived="ISD-009@A/none")


def test_start_extraction_proposes_and_a_person_accepting_queues_the_job(env: Env) -> None:
    out = env.h.structured("start_extraction", project="P123", derived=KEY)
    proposal = out["proposal"]
    assert (proposal["status"], proposal["tool"], proposal["agent"]) == (
        "pending",
        "start_extraction",
        ACTOR,
    )
    assert env.world.jobs()[0].state == "succeeded" and len(env.world.jobs()) == 1  # nothing queued
    done = proposals.accept_or_fail(env.h.factory, proposal_id=proposal["proposal_id"], by=ALICE)
    assert done.status == "accepted"
    jobs = env.world.jobs()
    assert [j.state for j in jobs][0] == "queued" and len(jobs) == 2
    assert jobs[0].requested_by == ALICE


def test_propose_import_files_a_tag_proposal_that_needs_the_admin_to_accept(env: Env) -> None:
    out = env.h.structured("propose_import", project="P123", derived=KEY, skip_existing=False)
    proposal = out["proposal"]
    assert proposal["tool"] == "propose_import_tags" and proposal["status"] == "pending"
    assert env.tags() == []
    with pytest.raises(ProposalAccessError, match="admin role"):
        proposals.accept_or_fail(
            env.h.factory, proposal_id=proposal["proposal_id"], by=ALICE, holds=lambda lv: False
        )
    assert env.tags() == []
    done = proposals.accept_or_fail(
        env.h.factory,
        proposal_id=proposal["proposal_id"],
        by=ALICE,
        holds=lambda level: level in ("user", "admin"),
    )
    assert done.status == "accepted"
    created = env.tags()
    assert len(created) == 2 and {e.actor for e in created} == {ALICE}
    (published,) = env.events("DerivedDocument.Published")  # the tags carry the correlation id
    assert published.causation_id == env.events("Proposal.Created")[0].event_id


def test_propose_import_refuses_what_could_not_be_applied(env: Env) -> None:
    with pytest.raises(ToolError, match="no derived document"):
        env.h.call("propose_import", project="P123", derived="ISD-009@A/none")
    with pytest.raises(ToolError, match="newer pass|content revision|expected"):
        env.h.call("propose_import", project="P123", derived=KEY, expected_content_rev=7)
    assert env.events("Proposal.Created") == []


def test_start_extraction_needs_a_target_and_names_one_way(env: Env) -> None:
    with pytest.raises(ToolError):
        env.h.call("start_extraction", project="P123")
    assert SCOPE == "project:P123"
