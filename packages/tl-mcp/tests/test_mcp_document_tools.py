"""The document control read tools: documents, links, reviews, transmittals (P1-I2-T10b)."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp_harness import McpHarness
from tl_adapters.db import open_uow
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_mod_documents.handlers.reviews import (
    OpenReviewCycle,
    ReviewerRequest,
    handle_open_review_cycle,
)
from tl_mod_documents.handlers.transmittals import (
    CreateTransmittal,
    Recipient,
    handle_create_transmittal,
)
from tl_mod_documents.testing import BASE, DocumentsWorld

NAMES = (
    "list_documents",
    "get_document",
    "get_document_diff",
    "list_stale_links",
    "list_overdue_reviews",
    "list_transmittals",
    "get_transmittal",
)


@pytest.fixture
def h(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[McpHarness]:
    """ISO-1234 (A IFR and B IFC issued, a link pinned to A, a draft transmittal of B),
    ISO-2000 (a draft in review by Ana, due in January) and ISO-3000 (registered only)."""
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    with use_provider(DirectorySchemaProvider()):
        harness = McpHarness.build(tmp_path)
        try:
            made = DocumentsWorld(harness.db, tmp_path / "objects")
            made.people("u", "ana")
            made.issued_document("ISO-1234", "IFR")
            made.link(made.tag(), "ISO-1234", "A")
            made.create_revision("ISO-1234", purpose="For construction")
            made.attach("ISO-1234", "B", data=b"%PDF-1.7 b", name="b.pdf")
            made.issue("ISO-1234", "B", "IFC")
            made.register("ISO-2000", discipline="ELE")
            made.create_revision("ISO-2000")
            made.attach("ISO-2000", "A", data=b"%PDF-1.7 spec", name="spec.pdf")
            made.register("ISO-3000")
            with open_uow(harness.db) as uow:
                handle_create_transmittal(
                    uow,
                    CreateTransmittal(
                        **BASE,
                        subject="To site",
                        purpose="for_construction",
                        recipients=[Recipient(name="Site")],
                        revision_ids=[made.revision("ISO-1234", "B").id],
                    ),
                )
                handle_open_review_cycle(
                    uow,
                    OpenReviewCycle(
                        **BASE,
                        revision_id=made.revision("ISO-2000", "A").id,
                        reviewers=[ReviewerRequest(reviewer="user:ana")],
                        due_date="2026-01-31",
                    ),
                )
            yield harness
        finally:
            harness.close()


def test_the_seven_tools_are_registered_read_only_and_described(h: McpHarness) -> None:
    tools = {t.name: t for t in asyncio.run(h.server.list_tools())}
    for name in NAMES:
        annotations = tools[name].annotations
        assert annotations is not None and annotations.read_only_hint is True
        assert annotations.destructive_hint is False and tools[name].description
        assert "project" in tools[name].input_schema["properties"]
    assert set(tools["list_documents"].input_schema["properties"]) == {
        "project",
        "state",
        "doc_type",
        "discipline",
        "include_void",
    }
    assert set(tools["get_document_diff"].input_schema["required"]) == {
        "project",
        "number",
        "from_code",
        "to_code",
    }


def test_list_documents_gives_the_register_without_revisions(h: McpHarness) -> None:
    rows = h.structured("list_documents", project="P123")["result"]
    assert [r["number"] for r in rows] == ["ISO-1234", "ISO-2000", "ISO-3000"]
    first = rows[0]
    assert (first["state"], first["current_revision_code"], first["revisions"]) == (
        "Issued",
        "B",
        [],
    )
    only = h.structured("list_documents", project="P123", discipline="ELE")["result"]
    assert [r["number"] for r in only] == ["ISO-2000"]
    issued = h.structured("list_documents", project="P123", state="Issued")["result"]
    assert [r["number"] for r in issued] == ["ISO-1234"]
    assert h.structured("list_documents", project="OTHER")["result"] == []


def test_get_document_has_revisions_renditions_and_the_state_of_each_pin(h: McpHarness) -> None:
    doc = h.structured("get_document", project="P123", number="ISO-1234")
    assert [r["code"] for r in doc["revisions"]] == ["A", "B"]
    assert doc["revisions"][1]["renditions"][0]["filename"] == "b.pdf"
    (link,) = doc["links"]
    assert (link["pin"], link["pin_state"], link["current_code"]) == ("A", "stale", "B")
    assert link["newer_codes"] == ["B"] and link["from_key"] == "47-FV-1001"


def test_get_document_diff_says_what_changed(h: McpHarness) -> None:
    diff: dict[str, Any] = h.structured(
        "get_document_diff", project="P123", number="ISO-1234", from_code="A", to_code="B"
    )
    assert diff["summary"][0] == "ISO-1234: A (IFR) to B (IFC)"
    assert (diff["from_status"], diff["to_status"]) == ("IFR", "IFC")
    with pytest.raises(ToolError, match="'Z' is not an issued revision of ISO-1234"):
        h.call("get_document_diff", project="P123", number="ISO-1234", from_code="A", to_code="Z")


def test_stale_links_and_overdue_reviews_are_the_report_rows(h: McpHarness) -> None:
    stale = h.structured("list_stale_links", project="P123")["result"]
    assert [(s["document_number"], s["pinned_code"], s["current_code"]) for s in stale] == [
        ("ISO-1234", "A", "B")
    ]
    late = h.structured("list_overdue_reviews", project="P123", on="2026-03-01")["result"]
    assert [(x["document_number"], x["reviewer"], x["days_overdue"]) for x in late] == [
        ("ISO-2000", "user:ana", 29)
    ]
    assert h.structured("list_overdue_reviews", project="P123", on="2026-01-01")["result"] == []


def test_transmittals_are_listed_and_one_is_read_with_its_items(h: McpHarness) -> None:
    rows = h.structured("list_transmittals", project="P123")["result"]
    assert [(r["state"], r["items"]) for r in rows] == [("Draft", [])]
    assert h.structured("list_transmittals", project="P123", state="Issued")["result"] == []
    one = h.structured("get_transmittal", project="P123", number=rows[0]["number"])
    assert [(i["document_number"], i["revision_code"]) for i in one["items"]] == [("ISO-1234", "B")]
    assert one["recipients"][0]["name"] == "Site"


def test_unknown_numbers_and_bad_arguments_are_tool_errors(h: McpHarness) -> None:
    with pytest.raises(ToolError, match="no document 'NOPE-1' in scope 'project:P123'"):
        h.call("get_document", project="P123", number="NOPE-1")
    with pytest.raises(ToolError, match="no transmittal 'NOPE-1' in scope 'project:P123'"):
        h.call("get_transmittal", project="P123", number="NOPE-1")
    with pytest.raises(ToolError):
        h.call("get_document", project="", number="x")
    with pytest.raises(ToolError):
        h.call("list_overdue_reviews", project="P123", on="soon")
