"""Record read routes (P0-I4-T40): list and query, count, lookup, one record, history."""

from __future__ import annotations

from typing import Any

import pytest
from harness import SCOPE, Harness
from tl_api.errors import ApiError
from tl_api.routes.records import build_spec, parse_order_by


def keys(response: Any) -> list[str]:
    assert response.status_code == 200, response.text
    return [row["key"] for row in response.json()]


def seed(h: Harness) -> dict[str, str]:
    """Four records in P123, one in P999. Returns key to id."""
    ids = {}
    for key, title in [
        ("R-1", "Gate valve"),
        ("R-2", "Check valve"),
        ("R-3", "Pump skid"),
        ("R-4", "Bevel damage"),
    ]:
        ids[key] = h.create_record(key, title).stream_id
    ids["X-1"] = h.create_record("X-1", "Other project", scope="project:P999").stream_id
    return ids


def test_list_returns_the_scopes_records_in_creation_order(harness: Harness) -> None:
    seed(harness)
    response = harness.client.get("/records", params={"scope": SCOPE})
    assert keys(response) == ["R-1", "R-2", "R-3", "R-4"]
    first = response.json()[0]
    assert first["title"] == "Gate valve" and first["version"] == 1 and first["voided"] is False
    assert set(first) >= {"id", "key", "type", "scope", "psets", "status", "created_at"}


def test_the_scope_is_required(harness: Harness) -> None:
    response = harness.client.get("/records")
    assert response.status_code == 422 and response.json()["error"] == "validation_error"


def test_q_filters_with_the_query_language(harness: Harness) -> None:
    seed(harness)
    get = harness.client.get
    assert keys(get("/records", params={"scope": SCOPE, "q": "valve"})) == ["R-1", "R-2"]
    assert keys(get("/records", params={"scope": SCOPE, "q": "title~gate"})) == ["R-1"]
    assert keys(get("/records", params={"scope": SCOPE, "q": "valve -title~check"})) == ["R-1"]
    assert keys(get("/records", params={"scope": SCOPE, "q": "key=R-3 or key=R-4"})) == [
        "R-3",
        "R-4",
    ]
    assert keys(get("/records", params={"scope": SCOPE, "q": ""})) == ["R-1", "R-2", "R-3", "R-4"]


def test_a_syntax_error_is_400_with_a_position(harness: Harness) -> None:
    response = harness.client.get("/records", params={"scope": SCOPE, "q": "title~gate ("})
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "query_syntax" and isinstance(body["message"], str)
    assert isinstance(body["position"], int) and body["position"] >= 0
    unknown = harness.client.get("/records", params={"scope": SCOPE, "q": "nonesuch:1"})
    assert unknown.status_code == 400 and unknown.json()["error"] == "query_syntax"


def test_status_record_type_and_voided_parameters(harness: Harness) -> None:
    ids = seed(harness)
    moved = harness.client.post(
        "/commands/TransitionWorkflow",
        json={
            "scope": SCOPE,
            "stream_id": ids["R-2"],
            "expected_version": 1,
            "transition": "submit",
        },
    )
    assert moved.status_code == 200, moved.text
    get = harness.client.get
    assert keys(get("/records", params={"scope": SCOPE, "status": "Review"})) == ["R-2"]
    assert keys(get("/records", params={"scope": SCOPE, "status": "Review", "q": "gate"})) == []
    assert keys(get("/records", params={"scope": SCOPE, "record_type": "core.Record"})) == [
        "R-1",
        "R-2",
        "R-3",
        "R-4",
    ]
    assert keys(get("/records", params={"scope": SCOPE, "record_type": "piping.Weld"})) == []


def test_order_by_limit_and_offset(harness: Harness) -> None:
    seed(harness)
    get = harness.client.get
    base = {"scope": SCOPE}
    assert keys(get("/records", params={**base, "order_by": "title:desc"})) == [
        "R-3",
        "R-1",
        "R-2",
        "R-4",
    ]
    assert keys(get("/records", params={**base, "order_by": "title"}))[0] == "R-4"
    assert keys(get("/records", params={**base, "order_by": "title", "limit": 2})) == ["R-4", "R-2"]
    paged = get("/records", params={**base, "order_by": "title", "limit": 2, "offset": 2})
    assert keys(paged) == ["R-1", "R-3"]


def test_bad_paging_and_ordering_are_422(harness: Harness) -> None:
    seed(harness)
    for params in (
        {"limit": 0},
        {"limit": 5001},
        {"offset": -1},
        {"order_by": "nonesuch"},
        {"order_by": "title:sideways"},
        {"order_by": ",title"},
    ):
        response = harness.client.get("/records", params={"scope": SCOPE, **params})
        assert response.status_code == 422, params
        assert response.json()["error"] in ("validation_error", "invalid_argument"), params


def test_count_matches_the_same_filter_and_ignores_paging(harness: Harness) -> None:
    seed(harness)
    get = harness.client.get
    assert get("/records/count", params={"scope": SCOPE}).json() == {"count": 4}
    assert get("/records/count", params={"scope": SCOPE, "q": "valve"}).json() == {"count": 2}
    assert get("/records/count", params={"scope": "project:P999"}).json() == {"count": 1}
    bad = get("/records/count", params={"scope": SCOPE, "q": "("})
    assert bad.status_code == 400 and bad.json()["error"] == "query_syntax"


def test_lookup_by_key_sets_the_etag(harness: Harness) -> None:
    ids = seed(harness)
    found = harness.client.get("/records/lookup", params={"scope": SCOPE, "key": "R-3"})
    assert found.status_code == 200 and found.json()["id"] == ids["R-3"]
    assert found.headers["etag"] == '"1"'
    missing = harness.client.get("/records/lookup", params={"scope": SCOPE, "key": "NOPE"})
    assert missing.status_code == 404 and missing.json()["error"] == "record_not_found"
    wrong_scope = harness.client.get(
        "/records/lookup", params={"scope": "project:P999", "key": "R-3"}
    )
    assert wrong_scope.status_code == 404


def test_get_one_record_and_its_etag_follow_the_version(harness: Harness) -> None:
    ids = seed(harness)
    one = harness.client.get(f"/records/{ids['R-1']}")
    assert one.status_code == 200 and one.json()["key"] == "R-1" and one.headers["etag"] == '"1"'
    harness.client.post(
        "/commands/UpdateRecord",
        json={
            "scope": SCOPE,
            "stream_id": ids["R-1"],
            "expected_version": 1,
            "changes": {"title": "Gate valve 2"},
        },
    )
    again = harness.client.get(f"/records/{ids['R-1']}")
    assert again.json()["title"] == "Gate valve 2" and again.headers["etag"] == '"2"'
    missing = harness.client.get("/records/01NOSUCHRECORD")
    assert missing.status_code == 404 and missing.json()["error"] == "record_not_found"


def test_history_lists_the_streams_events_oldest_first(harness: Harness) -> None:
    ids = seed(harness)
    harness.client.post(
        "/commands/UpdateRecord",
        json={
            "scope": SCOPE,
            "stream_id": ids["R-1"],
            "expected_version": 1,
            "changes": {"title": "New"},
        },
    )
    history = harness.client.get(f"/records/{ids['R-1']}/history")
    assert history.status_code == 200
    events = history.json()
    assert [e["event_type"] for e in events] == ["Record.Created", "Record.Updated"]
    assert [e["stream_version"] for e in events] == [1, 2]
    assert events[1]["payload"]["changes"]["title"] == ["Gate valve", "New"]
    assert harness.client.get("/records/01NOSUCHRECORD/history").status_code == 404


def test_every_record_route_needs_a_token(harness: Harness) -> None:
    ids = seed(harness)
    anon = harness.client_for(None)
    for path in (
        "/records?scope=" + SCOPE,
        "/records/count?scope=" + SCOPE,
        "/records/lookup?scope=" + SCOPE + "&key=R-1",
        f"/records/{ids['R-1']}",
        f"/records/{ids['R-1']}/history",
    ):
        assert anon.get(path).status_code == 401, path


def test_parse_order_by() -> None:
    assert parse_order_by(None) == [] and parse_order_by("  ") == []
    assert parse_order_by("title") == [("title", "asc")]
    assert parse_order_by("title:desc, psets.valve.size_in:ASC") == [
        ("title", "desc"),
        ("psets.valve.size_in", "asc"),
    ]
    for bad in ("title:up", ",title", "title,", ":desc"):
        with pytest.raises(ApiError) as caught:
            parse_order_by(bad)
        assert caught.value.status == 422 and caught.value.error == "invalid_argument"


def test_build_spec_ands_status_with_the_parsed_query() -> None:
    from tl_core.query import And, Compare, Text

    spec = build_spec(SCOPE, "gate", status="Review", limit=10, offset=5, order_by="key:desc")
    assert spec.where == And((Text("gate"), Compare("status", "=", "Review")))
    assert (spec.limit, spec.offset, spec.order_by) == (10, 5, [("key", "desc")])
    assert build_spec(SCOPE, None, status="Review").where == Compare("status", "=", "Review")
    assert build_spec(SCOPE, "").where is None
