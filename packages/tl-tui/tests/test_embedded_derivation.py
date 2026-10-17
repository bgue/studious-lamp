"""The embedded client's derivation methods over a real ledger (P1-I3; ADR-0014).

Reads answer what the pipeline stored; starting an extraction is open to any signed-in person;
publishing into tags and compensating need the admin role, publishing into documents the document
controller role (or admin); a command that names another actor than the client's is refused.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from tl_adapters.db import open_uow
from tl_adapters.sqlite.factory import SqliteUowFactory
from tl_adapters.sqlite.uow import create_schema
from tl_core.auth import accounts
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.password import prepare_password
from tl_core.derivation.registry import use_extractors
from tl_core.derivation.testing import make_extractors
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_mod_documents.derivation.derived import StartExtraction
from tl_mod_documents.derivation.publish import (
    CompensatePublication,
    PublishDerivedDocuments,
    PublishDerivedTags,
)
from tl_mod_documents.derivation.store import use_files
from tl_mod_documents.errors import DerivedNotFoundError
from tl_mod_documents.testing import BASE, DocumentsWorld
from tl_tui.embedded import EmbeddedClient

FIXTURES = Path(__file__).resolve().parents[3] / "schema" / "fixtures"
GOOD = "correct horse battery"
PROJECT = "P123"
ROWS = [("47-FV-1001", "Feed", "CV", "4"), ("47-FV-1002", "Return", "HV", "6")]


class Ledger:
    def __init__(self, path: Path, world: DocumentsWorld, derived_id: str, key: str) -> None:
        self.path, self.world, self.derived_id, self.key = path, world, derived_id, key

    def client(self, actor: str) -> EmbeddedClient:
        return EmbeddedClient(SqliteUowFactory(self.path), actor=actor)

    def tags(self) -> int:
        return self.world.scalar("SELECT COUNT(*) FROM cur_core_record WHERE key LIKE '47-%'")


@pytest.fixture
def ledger(tmp_path: Path) -> Iterator[Ledger]:
    with use_provider(DirectorySchemaProvider(FIXTURES)), use_extractors(make_extractors()):
        path = tmp_path / "tl.db"
        create_schema(path)
        world = DocumentsWorld(path, tmp_path / "objects")
        with use_files(world.files):
            world.load_standards()
            world.register("ISD-001")
            world.create_revision("ISD-001")
            world.attach("ISD-001", "A")
            world.register_schema()
            with open_uow(path) as uow:
                for name, roles in (
                    ("boss", ["admin"]),
                    ("dora", ["user", "document_controller"]),
                    ("ursula", ["user"]),
                ):
                    accounts.create_account(
                        uow, username=name, display_name=name, kind="person", roles=roles,
                        password=prepare_password(GOOD, username=name), by="svc:test",
                    )  # fmt: skip
            derived = world.valid_derived(ROWS)
            yield Ledger(path, world, derived.id, derived.key)


def test_reads_answer_what_the_pipeline_stored(ledger: Ledger) -> None:
    client = ledger.client("user:ursula")
    view = client.get_derived_document(PROJECT, ledger.key)
    assert view.state == "Valid" and view.id == ledger.derived_id
    assert [d.id for d in client.list_derived_documents(PROJECT)] == [ledger.derived_id]
    assert client.get_derived_rows(PROJECT, ledger.derived_id).total == 2
    assert client.get_derived_report(PROJECT, ledger.key).status == "valid"
    assert client.get_publish_preview(PROJECT, ledger.key).counts["create"] == 2
    assert [j.state for j in client.list_processing_jobs(PROJECT)] == ["succeeded"]
    assert client.get_compensation_preview(PROJECT, ledger.key).can_compensate is False
    with pytest.raises(DerivedNotFoundError):
        client.get_derived_document(PROJECT, "ISD-009@A/none")


def test_any_signed_in_person_may_start_an_extraction(ledger: Ledger) -> None:
    command = StartExtraction(**{**BASE, "actor": "user:ursula"}, derived_id=ledger.derived_id)
    done = ledger.client("user:ursula").start_extraction(command)
    assert done.stream_id
    assert [j.state for j in ledger.client("user:ursula").list_processing_jobs(PROJECT)][0] == (
        "queued"
    )


def publish_tags(ledger: Ledger, actor: str) -> PublishDerivedTags:
    return PublishDerivedTags(
        **{**BASE, "actor": actor}, derived_id=ledger.derived_id, expected_content_rev=1
    )


def publish_documents(ledger: Ledger, actor: str) -> PublishDerivedDocuments:
    return PublishDerivedDocuments(
        **{**BASE, "actor": actor}, derived_id=ledger.derived_id, expected_content_rev=1
    )


def test_publishing_tags_needs_the_admin_role(ledger: Ledger) -> None:
    for actor in ("user:ursula", "user:dora", "user:nobody"):
        with pytest.raises(ForbiddenError, match="admin role"):
            ledger.client(actor).publish_derived_tags(publish_tags(ledger, actor))
    with pytest.raises(ForbiddenError, match="other than the signed-in"):
        ledger.client("user:boss").publish_derived_tags(publish_tags(ledger, "user:ursula"))
    assert ledger.tags() == 0
    boss = ledger.client("user:boss")
    boss.publish_derived_tags(publish_tags(ledger, "user:boss"))
    assert ledger.tags() == 2
    assert boss.get_derived_document(PROJECT, ledger.key).state == "Published"
    assert boss.get_compensation_preview(PROJECT, ledger.key).can_compensate is True


def test_publishing_documents_needs_the_controller_and_compensating_the_admin(
    ledger: Ledger,
) -> None:
    with pytest.raises(ForbiddenError, match="document_controller or admin"):
        ledger.client("user:ursula").publish_derived_documents(
            publish_documents(ledger, "user:ursula")
        )
    ledger.client("user:boss").publish_derived_tags(publish_tags(ledger, "user:boss"))
    undo = CompensatePublication(
        **{**BASE, "actor": "user:dora"}, derived_id=ledger.derived_id, reason="wrong file"
    )
    with pytest.raises(ForbiddenError, match="admin role"):
        ledger.client("user:dora").compensate_publication(undo)
    ledger.client("user:boss").compensate_publication(
        undo.model_copy(update={"actor": "user:boss"})
    )
    assert ledger.client("user:boss").get_derived_document(PROJECT, ledger.key).state == "Valid"
