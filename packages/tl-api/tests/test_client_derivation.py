"""HTTP client: the derivation pipeline, reads and commands (P1-I3)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from harness import SCOPE, Harness
from tl_api.client import ApiClient
from tl_core.auth import accounts, sessions
from tl_core.auth.password import prepare_password
from tl_core.derivation.registry import use_extractors
from tl_core.derivation.testing import make_extractors
from tl_mod_documents.derivation.derived import OpenDerivedDocument, StartExtraction
from tl_mod_documents.derivation.publish import PublishDerivedTags
from tl_mod_documents.errors import DerivedNotFoundError, PublishRefusedError
from tl_mod_documents.testing import INDEX_MAPPING, INDEX_SCHEMA, DocumentsWorld, index_csv

PASSWORD = "correct horse battery"
PROJECT = "P123"
ONE = [("47-FV-1001", "Feed", "CV", "4"), ("47-FV-1002", "Return", "HV", "6")]
TWO = [*ONE[:1], ("47-FV-1002", "Return", "HV", "8"), ("47-HV-2001", "Vent", "PSV", "2")]


@pytest.fixture
def world(harness: Harness) -> Iterator[DocumentsWorld]:
    found = DocumentsWorld(harness.db, harness.root / "unused")
    found.store, found.files = harness.store, harness.service
    with use_extractors(make_extractors()):
        found.register("ISD-001", doc_type="IDX")
        found.create_revision("ISD-001")
        found.attach("ISD-001", "A")
        yield found


def admin_api(harness: Harness) -> ApiClient:
    """A client signed in as an admin (publication and schemas are admin acts)."""
    with harness.backend() as uow:
        accounts.create_account(
            uow, username="boss", display_name="boss", kind="person", roles=["admin"],
            password=prepare_password(PASSWORD), by="svc:test",
        )  # fmt: skip
    _, token = sessions.sign_in(harness.backend, username="boss", password=PASSWORD)
    return ApiClient("http://testserver", token, http=harness.client_for(None))


def test_the_client_runs_the_pipeline_and_reads_every_stage(
    harness: Harness, world: DocumentsWorld
) -> None:
    api = admin_api(harness)
    from tl_mod_documents.derivation.schemas import RegisterDocumentSchema

    api.register_document_schema(
        RegisterDocumentSchema(
            actor="x",
            source="test",
            scope="company",
            code="instrument-index",
            semver="1.0.0",
            title="Instrument index",
            json_schema=INDEX_SCHEMA,
            key_column="tag",
            target_kind="tags",
            mapping=INDEX_MAPPING,
        )
    )
    assert [s.key for s in api.list_document_schemas(PROJECT)] == ["instrument-index@1.0.0"]
    assert api.get_document_schema(PROJECT, "instrument-index").key_column == "tag"
    revision = world.revision("ISD-001", "A")
    opened = api.open_derived_document(
        OpenDerivedDocument(
            actor="x",
            source="test",
            scope=SCOPE,
            revision_id=revision.id,
            schema_code="instrument-index",
        )  # fmt: skip
    )
    derived_id = opened.stream_id
    world.upload_content(derived_id, index_csv(ONE))
    api.start_extraction(
        StartExtraction(actor="x", source="test", scope=SCOPE, derived_id=derived_id)
    )
    queued = api.list_processing_jobs(PROJECT, state="queued")
    assert [j.kind for j in queued] == ["extract"]
    world.run_jobs()
    view = api.get_derived_document(PROJECT, derived_id)
    assert view.state == "Valid" and view.active_job is None
    assert api.list_derived_documents(PROJECT, state="Valid")[0].id == derived_id
    assert api.get_derived_rows(PROJECT, view.key).total == 2
    assert api.get_derived_report(PROJECT, view.key).status == "valid"
    assert api.check_derived_document(PROJECT, view.key).status == "valid"
    assert api.get_publish_preview(PROJECT, view.key).counts["create"] == 2
    assert api.get_compensation_preview(PROJECT, view.key).can_compensate is False
    world.upload_content(derived_id, index_csv(TWO), name="two.csv")
    world.start_extraction(derived_id=derived_id)
    world.run_jobs()
    assert api.get_derived_diff(PROJECT, view.key).added == ["47-HV-2001"]


def test_errors_come_back_as_the_modules_exceptions(
    harness: Harness, world: DocumentsWorld
) -> None:
    api = admin_api(harness)
    with pytest.raises(DerivedNotFoundError):
        api.get_derived_document(PROJECT, "ISD-001@Z/none")
    refused = PublishDerivedTags(
        actor="x", source="test", scope=SCOPE, derived_id="NOSUCH", expected_content_rev=1
    )
    with pytest.raises(DerivedNotFoundError):
        api.publish_derived_tags(refused)
    assert PublishRefusedError  # raised for a derived document that is not Valid (publish tests)
