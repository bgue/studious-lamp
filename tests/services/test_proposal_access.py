"""Accepting a proposal needs the access its command needs (ADR-0014 section 8; fail closed).

A user cannot approve an agent's publication into tags; an admin can; a document controller can
approve one into documents. A command no one declared access for is never accepted.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, create_schema, open_uow
from tl_core.derivation.registry import use_extractors
from tl_core.derivation.testing import make_extractors
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_core.services import proposals
from tl_core.services.errors import ProposalAccessError
from tl_mod_documents.derivation.publish import PublishDerivedDocuments, PublishDerivedTags
from tl_mod_documents.derivation.store import use_files
from tl_mod_documents.testing import BASE, DocumentsWorld

FIXTURES = Path(__file__).resolve().parents[2] / "schema" / "fixtures"
AGENT = "agent:triage"
TAGS = [("47-FV-1001", "Feed", "CV", "4"), ("47-HV-1002", "Return", "HV", "6")]


def holds_only(*levels: str) -> Callable[[str], bool]:
    return lambda level: level == "user" or level in levels


@pytest.fixture
def world(db: DbTarget, tmp_path: Path) -> Iterator[DocumentsWorld]:
    with use_provider(DirectorySchemaProvider(FIXTURES)), use_extractors(make_extractors()):
        found = DocumentsWorld(db, tmp_path / "objects")
        with use_files(found.files):
            found.load_standards()
            found.register("ISD-001")
            found.create_revision("ISD-001")
            found.attach("ISD-001", "A")
            found.register_schema()
            yield found


def factory(db: DbTarget) -> proposals.Factory:
    def open_one(readonly: bool = False):  # type: ignore[no-untyped-def]
        return open_uow(db, readonly=readonly)

    return open_one


def propose_tags(world: DocumentsWorld) -> str:
    derived = world.valid_derived(TAGS)
    command = PublishDerivedTags(
        **{**BASE, "actor": AGENT, "source": "mcp:triage"},
        derived_id=derived.id,
        expected_content_rev=derived.content_rev,
    )
    view = proposals.submit(
        factory(world.db), tool="propose_import_tags", agent=AGENT, command=command,
        summary="Create the 2 tags of the instrument index",
    )  # fmt: skip
    assert view.status == "pending" and view.command_type == "PublishDerivedTags"
    return view.proposal_id


def tag_count(world: DocumentsWorld) -> int:
    return int(world.scalar("SELECT COUNT(*) FROM cur_engineering_tag"))


def test_a_user_cannot_accept_an_agents_publication_into_tags(world: DocumentsWorld) -> None:
    proposal_id = propose_tags(world)
    for holds in (None, holds_only(), holds_only("controller")):
        with pytest.raises(ProposalAccessError, match="needs the admin role"):
            proposals.accept_or_fail(
                factory(world.db), proposal_id=proposal_id, by="user:bob", holds=holds
            )
    with open_uow(world.db, readonly=True) as uow:
        assert proposals.get_proposal(uow.conn(), proposal_id).status == "pending"
    assert tag_count(world) == 0


def test_an_admin_can_accept_it_and_the_ledger_says_who_and_on_whose_suggestion(
    world: DocumentsWorld,
) -> None:
    proposal_id = propose_tags(world)
    view = proposals.accept_or_fail(
        factory(world.db), proposal_id=proposal_id, by="user:boss", holds=holds_only("admin")
    )
    assert view.status == "accepted"
    assert tag_count(world) == 2
    actors = world.rows("SELECT DISTINCT actor FROM events WHERE stream_type = 'engineering.Tag'")
    assert [a["actor"] for a in actors] == ["user:boss"]  # the accepting person, not the agent
    created = world.scalar(
        "SELECT causation_id FROM events WHERE event_type = 'DerivedDocument.Published'"
    )
    assert created is not None  # points at the Proposal.Created event


def test_a_proposal_to_publish_documents_needs_the_controller_not_the_admin_role_alone(
    world: DocumentsWorld,
) -> None:
    command = PublishDerivedDocuments(
        **{**BASE, "actor": AGENT}, derived_id="X", expected_content_rev=1
    )
    with open_uow(world.db) as uow:
        made = proposals.propose(
            uow, tool="propose_import_documents", agent=AGENT, command=command, summary="docs"
        )
    with pytest.raises(ProposalAccessError, match="controller role"):
        proposals.accept_or_fail(
            factory(world.db), proposal_id=made.proposal_id, by="user:bob", holds=holds_only()
        )
    # a controller passes the gate; the command then fails for its own reasons (no such derived
    # document), which is recorded as a failed proposal, not an access error
    view = proposals.accept_or_fail(
        factory(world.db),
        proposal_id=made.proposal_id,
        by="user:dora",
        holds=holds_only("controller"),
    )
    assert view.status == "failed" and "DerivedNotFoundError" in (view.reason or "")


def test_a_controller_cannot_accept_a_publication_into_tags(world: DocumentsWorld) -> None:
    proposal_id = propose_tags(world)
    with pytest.raises(ProposalAccessError, match="needs the admin role"):
        proposals.accept_or_fail(
            factory(world.db),
            proposal_id=proposal_id,
            by="user:dora",
            holds=holds_only("controller"),
        )
    assert tag_count(world) == 0


def test_starting_an_extraction_may_be_accepted_by_anyone_signed_in(world: DocumentsWorld) -> None:
    from tl_mod_documents.derivation.derived import StartExtraction

    rev = world.revision("ISD-001", "A")
    command = StartExtraction(
        **{**BASE, "actor": AGENT}, revision_id=rev.id, schema_code="instrument-index"
    )
    view = proposals.submit(
        factory(world.db), tool="start_extraction", agent=AGENT, command=command,
        summary="Read the instrument index PDF",
    )  # fmt: skip
    accepted = proposals.accept_or_fail(
        factory(world.db), proposal_id=view.proposal_id, by="user:bob", holds=holds_only()
    )
    assert accepted.status == "accepted"
    assert world.scalar("SELECT COUNT(*) FROM cur_documents_processing_job") == 1


def test_an_agent_can_never_accept(world: DocumentsWorld) -> None:
    from tl_core.services.errors import ProposalDeciderError

    proposal_id = propose_tags(world)
    with pytest.raises(ProposalDeciderError):
        proposals.accept_or_fail(
            factory(world.db), proposal_id=proposal_id, by=AGENT, holds=lambda level: True
        )


def test_a_command_with_no_declared_access_cannot_be_accepted() -> None:
    assert proposals.access_of("Mystery") is None
    with pytest.raises(ProposalAccessError, match="no declared access"):
        proposals._require_access("Mystery", lambda level: True)  # pyright: ignore[reportPrivateUsage]
    assert proposals.access_of("CreateRecord") == "user"
    assert proposals.access_of("PublishDerivedTags") == "admin"
    assert proposals.access_of("PublishDerivedDocuments") == "controller"
    assert proposals.access_of("StartExtraction") == "user"


def test_every_core_proposal_command_declares_its_access() -> None:
    assert set(proposals.COMMANDS) == set(proposals.CORE_ACCESS)
    assert set(proposals.CORE_ACCESS.values()) == {"user"}


def test_the_tools_of_the_modules_are_in_the_proposable_list() -> None:
    tools = proposals.proposable_tools()
    assert tools["start_extraction"] == "StartExtraction"
    assert tools["propose_import_tags"] == "PublishDerivedTags"
    assert tools["propose_import_documents"] == "PublishDerivedDocuments"
    assert {"create_record", "update_psets", "link_records"} <= set(tools)


def test_the_database_has_what_the_tests_assume(db: DbTarget) -> None:
    create_schema(db)
    with open_uow(db, readonly=True) as uow:
        assert uow.conn().execute(text("SELECT COUNT(*) FROM job_queue")).scalar_one() == 0
