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


def test_events_hide_a_shadow_proposal_from_a_person_and_show_it_to_an_admin(
    harness: Harness,
) -> None:
    """The proposal of a shadow value carries the value (second security review, re-check)."""
    from tl_core.auth import accounts, sessions
    from tl_core.auth.password import prepare_password
    from tl_core.ledger import NewEvent

    with harness.backend() as uow:
        for name, roles in (("boss", ["admin"]), ("bob", ["user"])):
            accounts.create_account(
                uow, username=name, display_name=name, kind="person", roles=roles,
                password=prepare_password("correct horse battery"), by="svc:test",
            )  # fmt: skip
        uow.append(
            stream_id="V-SHADOW", stream_type="core.EnrichmentValue", scope=SCOPE,
            expected_version=0, actor="svc:enricher-e", source="enricher:e@1",
            correlation_id="C" * 26,
            events=[
                NewEvent(
                    event_type="Enrichment.Proposed",
                    payload={
                        "value_id": "V-SHADOW",
                        "target": {"id": "r1", "record_type": "core.Record"},
                        "property_path": "enrich.e.p",
                        "value": "alpha",
                        "enricher": "e",
                        "enricher_version": "1",
                        "confidence": 0.5,
                        "inputs": [],
                        "model_ref": None,
                        "produced_at": "2026-10-19T00:00:00Z",
                        "acceptance_state": "shadow",
                    },
                )
            ],
        )  # fmt: skip

    def seen(username: str) -> list[str]:
        _, token = sessions.sign_in(
            harness.backend, username=username, password="correct horse battery"
        )
        client = harness.client_for(None)
        client.headers.update({"Authorization": f"Bearer {token}"})
        found = client.get("/events", params={"type": "Enrichment.*"}).json()["events"]
        return [e["payload"]["value"] for e in found]

    assert seen("boss") == ["alpha"]
    assert seen("bob") == []
