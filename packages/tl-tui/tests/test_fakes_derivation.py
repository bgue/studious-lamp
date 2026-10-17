"""The derivation fake behaves like the embedded client where screens rely on it (P1-I3)."""

from __future__ import annotations

from typing import Any

import pytest
from fakes import FakeClient
from tl_core.auth.errors import ForbiddenError
from tl_mod_documents.derivation.derived import CancelJob, StartExtraction
from tl_mod_documents.derivation.publish import (
    CompensatePublication,
    PublishDerivedDocuments,
    PublishDerivedTags,
)
from tl_mod_documents.errors import (
    DerivedNotFoundError,
    DerivedStateError,
    JobNotFoundError,
    JobStateError,
    PublishRefusedError,
)
from tl_tui.client import ClientInterface

P = "P123"
BASE: dict[str, Any] = {"actor": "user:alice", "source": "tui", "scope": "project:P123"}


@pytest.fixture
def client() -> FakeClient:
    found = FakeClient()
    found.seed_derivation(P)
    return found


def key(client: FakeClient, number: str) -> str:
    return f"{number}@A/instrument-index"


def test_the_fake_satisfies_the_interface_and_lists_the_three_documents(client: FakeClient) -> None:
    api: ClientInterface = client
    listed = api.list_derived_documents(P)
    assert {d.source_document_number: d.state for d in listed} == {
        "ISD-001": "Valid",
        "ISD-002": "Invalid",
        "ISD-003": "Processing",
    }
    assert [d.state for d in api.list_derived_documents(P, state="Invalid")] == ["Invalid"]
    one = api.get_derived_document(P, key(client, "ISD-003"))
    assert one.active_job is not None and one.active_job.state == "running"
    with pytest.raises(DerivedNotFoundError):
        api.get_derived_document(P, "ISD-009@A/none")


def test_rows_reports_and_diffs_follow_the_stage(client: FakeClient) -> None:
    good, bad, busy = (key(client, n) for n in ("ISD-001", "ISD-002", "ISD-003"))
    assert client.get_derived_rows(P, good, offset=2).rows[0]["tag"] == "47-HV-2001"
    assert client.get_derived_report(P, bad).error_count == 2
    assert client.get_derived_diff(P, good).added == ["47-HV-2001"]
    with pytest.raises(DerivedStateError, match="no extracted data"):
        client.get_derived_rows(P, busy)
    with pytest.raises(DerivedStateError):
        client.get_derived_diff(P, bad)
    assert [j.state for j in client.list_processing_jobs(P)] == ["running", "failed", "succeeded"]
    with pytest.raises(JobNotFoundError):
        client.get_processing_job(P, "nope")


def test_start_and_cancel_move_the_document_and_its_job(client: FakeClient) -> None:
    good = client.get_derived_document(P, key(client, "ISD-001"))
    made = client.start_extraction(StartExtraction(**BASE, derived_id=good.id))
    assert client.get_derived_document(P, good.id).state == "Processing"
    assert client.get_processing_job(P, made.stream_id).state == "queued"
    with pytest.raises(DerivedStateError):
        client.start_extraction(StartExtraction(**BASE, derived_id=good.id))
    client.cancel_job(CancelJob(**BASE, job_id=made.stream_id))
    assert client.get_derived_document(P, good.id).state == "Valid"
    with pytest.raises(JobStateError):
        client.cancel_job(CancelJob(**BASE, job_id=made.stream_id))
    assert len(client.derivation_commands) == 4


def test_publishing_needs_the_role_and_the_skip_and_can_be_compensated(client: FakeClient) -> None:
    good = client.get_derived_document(P, key(client, "ISD-001"))
    publish = PublishDerivedTags(**BASE, derived_id=good.id, expected_content_rev=2)
    with pytest.raises(PublishRefusedError, match="skip_existing"):
        client.publish_derived_tags(publish)
    client.is_admin = False
    with pytest.raises(ForbiddenError, match="admin role"):
        client.publish_derived_tags(publish.model_copy(update={"skip_existing": True}))
    client.is_admin = True
    client.publish_derived_tags(publish.model_copy(update={"skip_existing": True}))
    after = client.get_derived_document(P, good.id)
    assert (after.state, after.published_count) == ("Published", 2)
    assert client.get_compensation_preview(P, good.id).can_compensate is True
    client.is_admin = False
    undo = CompensatePublication(**BASE, derived_id=good.id, reason="wrong file")
    with pytest.raises(ForbiddenError):
        client.compensate_publication(undo)
    client.is_admin = True
    client.compensate_publication(undo)
    assert client.get_derived_document(P, good.id).state == "Valid"


def test_documents_publication_accepts_a_controller(client: FakeClient) -> None:
    good = client.get_derived_document(P, key(client, "ISD-001"))
    command = PublishDerivedDocuments(
        **BASE, derived_id=good.id, expected_content_rev=2, skip_existing=True
    )
    client.is_admin, client.is_controller = False, False
    with pytest.raises(ForbiddenError, match="document_controller"):
        client.publish_derived_documents(command)
    client.is_controller = True
    client.publish_derived_documents(command)
