"""Reference read routes (P0-I4-T42): relations, key detection, workflow, forms, conformance."""

from __future__ import annotations

from harness import SCOPE, Harness


def test_relations_are_the_vocabulary_in_display_order(harness: Harness) -> None:
    response = harness.client.get("/relations")
    assert response.status_code == 200
    relations = response.json()
    codes = [r["code"] for r in relations]
    assert "requires" in codes and "references" in codes and len(codes) == len(set(codes))
    requires = next(r for r in relations if r["code"] == "requires")
    assert set(requires) == {"code", "label", "inverse_code", "inverse_label"}
    assert requires["label"] and requires["inverse_label"] != requires["label"]


def test_default_relation_for_a_pair_of_types(harness: Harness) -> None:
    got = harness.client.get(
        "/relations/default", params={"from_type": "core.Record", "to_type": "core.Record"}
    )
    assert got.status_code == 200
    assert got.json()["relation"] in [r["code"] for r in harness.client.get("/relations").json()]
    assert harness.client.get("/relations/default", params={"from_type": "x"}).status_code == 422


def test_detect_keys_resolves_chips_to_records(harness: Harness) -> None:
    known = harness.create_record("P123-REC-0001", "Known record")
    text = "see P123-REC-0001 and P123-REC-0099 please"
    response = harness.client.post("/keys/detect", json={"scope": SCOPE, "text": text})
    assert response.status_code == 200, response.text
    chips = response.json()
    assert [c["key"] for c in chips] == ["P123-REC-0001", "P123-REC-0099"]
    assert chips[0]["record_id"] == known.stream_id and chips[0]["title"] == "Known record"
    assert chips[1]["record_id"] is None
    assert text[chips[0]["start"] : chips[0]["end"]] == "P123-REC-0001"
    own = harness.client.post(
        "/keys/detect", json={"scope": SCOPE, "text": text, "linked_to": known.stream_id}
    ).json()
    assert [c["key"] for c in own] == ["P123-REC-0099"]  # the record itself is not suggested
    assert harness.client.post("/keys/detect", json={"scope": SCOPE}).status_code == 422


def test_workflow_status_lists_transitions_with_guard_results(harness: Harness) -> None:
    record = harness.create_record("W-1")
    response = harness.client.get(f"/records/{record.stream_id}/workflow")
    assert response.status_code == 200, response.text
    status = response.json()
    assert status["state"] == "Draft" and status["version"] == 1 and status["workflow"]
    assert [o["transition"] for o in status["options"]] == ["submit"]
    assert status["options"][0]["allowed"] is True and status["options"][0]["to_state"] == "Review"


def test_roles_decide_a_role_guard(harness: Harness) -> None:
    record = harness.create_record("W-2")
    sid = record.stream_id
    # Draft -> Review -> Approved needs the expected link; reach Approved by satisfying it.
    other = harness.create_record("W-3")
    harness.client.post(
        "/commands/AddLink",
        json={"scope": SCOPE, "from_id": sid, "to_id": other.stream_id, "relation": "references"},
    )
    version = 1  # a link is its own stream: the record's version does not move
    for transition in ("submit", "approve"):
        done = harness.client.post(
            "/commands/TransitionWorkflow",
            json={
                "scope": SCOPE,
                "stream_id": sid,
                "expected_version": version,
                "transition": transition,
            },
        )
        assert done.status_code == 200, done.text
        version = done.json()["version"]
    options = lambda **p: harness.client.get(f"/records/{sid}/workflow", params=p).json()["options"]  # noqa: E731
    issue = next(o for o in options() if o["transition"] == "issue")
    assert issue["allowed"] is False
    issue = next(o for o in options(role="manager") if o["transition"] == "issue")
    assert issue["allowed"] is True


def test_workflow_status_of_an_unknown_record_is_404(harness: Harness) -> None:
    response = harness.client.get("/records/01NOSUCHRECORD/workflow")
    assert response.status_code == 404 and response.json()["error"] == "record_not_found"


def test_form_metadata_for_a_record_type(harness: Harness) -> None:
    response = harness.client.get(
        "/schema/forms", params={"scope": SCOPE, "record_type": "core.Record"}
    )
    assert response.status_code == 200, response.text
    meta = response.json()
    assert meta["record_type"] == "core.Record" and meta["effective_schema_hash"]
    assert "title" in {f["path"] for f in meta["core_fields"]}
    assert isinstance(meta["psets"], list)
    assert harness.client.get("/schema/forms", params={"scope": SCOPE}).status_code == 422


def test_conformance_of_a_record(harness: Harness) -> None:
    record = harness.create_record("C-1")
    response = harness.client.get(f"/records/{record.stream_id}/conformance")
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["status"] == "ok" and report["issues"] == []
    assert report["effective_schema_hash"]
    missing = harness.client.get("/records/01NOSUCHRECORD/conformance")
    assert missing.status_code == 404


def test_every_reference_route_needs_a_token(harness: Harness) -> None:
    record = harness.create_record("T-1")
    anon = harness.client_for(None)
    for path in (
        "/relations",
        "/relations/default?from_type=a&to_type=b",
        f"/records/{record.stream_id}/workflow",
        f"/schema/forms?scope={SCOPE}&record_type=core.Record",
        f"/records/{record.stream_id}/conformance",
    ):
        assert anon.get(path).status_code == 401, path
    assert anon.post("/keys/detect", json={"scope": SCOPE, "text": "x"}).status_code == 401
