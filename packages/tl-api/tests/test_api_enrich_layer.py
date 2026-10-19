"""The API refuses a record command that writes the `enrich` or `src` layer (second security
review, finding 1)."""

from __future__ import annotations

from harness import SCOPE, Harness


def test_create_and_update_record_refuse_a_pset_under_a_read_only_root(harness: Harness) -> None:
    refused = harness.client.post(
        "/commands/CreateRecord",
        json={
            "scope": SCOPE, "record_type": "core.Record", "title": "T", "key": "X-1",
            "psets": {"enrich.doc_classifier": {"doc_type": "DRW"}},
        },
    )  # fmt: skip
    assert refused.status_code in (409, 422), refused.text
    made = harness.client.post(
        "/commands/CreateRecord",
        json={"scope": SCOPE, "record_type": "core.Record", "title": "T", "key": "X-2"},
    )
    assert made.status_code == 200, made.text
    forged = harness.client.post(
        "/commands/UpdateRecord",
        json={
            "scope": SCOPE, "stream_id": made.json()["stream_id"], "expected_version": 1,
            "changes": {"psets": {"src.import": {"a": 1}}},
        },
    )  # fmt: skip
    assert forged.status_code in (409, 422), forged.text
    assert "not writable" in forged.text
