"""A client cannot pose as a publication: reserved correlation ids and sources (ADR-0014)."""

from __future__ import annotations

import pytest
from harness import SCOPE, Harness
from tl_core.services import proposals
from tl_core.services.commands import CreateRecord
from tl_core.services.errors import ReservedIdentifierError

BODY = {"scope": SCOPE, "number": "ISO-9001", "title": "A document"}


@pytest.mark.parametrize(
    "extra",
    [
        {"correlation_id": "derive:01J9Z6Q4W3X2Y1V0T9S8R7Q6PB"},
        {"causation_id": "derive:anything"},
        {"source": "import:derived-01J9Z6Q4W3X2Y1V0T9S8R7Q6PB"},
        {"source": "compensation:01J9Z6Q4W3X2Y1V0T9S8R7Q6PB"},
    ],
)
def test_a_client_command_with_a_reserved_identifier_is_refused_and_writes_nothing(
    harness: Harness, extra: dict[str, str]
) -> None:
    refused = harness.client.post("/commands/RegisterDocument", json={**BODY, **extra})
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"] == "reserved_identifier"
    listed = harness.client.get("/projects/P123/documents").json()
    assert listed == []


def test_ordinary_identifiers_still_pass(harness: Harness) -> None:
    ok = harness.client.post(
        "/commands/RegisterDocument",
        json={**BODY, "correlation_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PB", "source": "tui"},
    )
    assert ok.status_code == 200, ok.text


def test_a_proposal_cannot_carry_one_either(harness: Harness) -> None:
    command = CreateRecord(
        actor="agent:triage",
        source="mcp:triage",
        scope=SCOPE,
        correlation_id="derive:x",
        record_type="core.Record",
        title="t",
        key="P123-REC-1",
    )
    with pytest.raises(ReservedIdentifierError):
        proposals.submit(
            harness.backend,
            tool="create_record",
            agent="agent:triage",
            command=command,
            summary="s",
        )
