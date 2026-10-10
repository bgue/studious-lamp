"""Link read routes (P0-I4-T41): links, trace, expected links, counts, picker search."""

from __future__ import annotations

from typing import Any

from harness import SCOPE, Harness


def link(h: Harness, a: str, b: str, relation: str = "requires") -> str:
    response = h.client.post(
        "/commands/AddLink",
        json={"scope": SCOPE, "from_id": a, "to_id": b, "relation": relation},
    )
    assert response.status_code == 200, response.text
    return response.json()["stream_id"]


def chain(h: Harness) -> dict[str, str]:
    """A requires B requires C, plus a lone D."""
    ids = {k: h.create_record(k, f"Record {k}").stream_id for k in ("A", "B", "C", "D")}
    link(h, ids["A"], ids["B"])
    link(h, ids["B"], ids["C"])
    return ids


def test_links_of_a_record_read_from_both_ends(harness: Harness) -> None:
    ids = chain(harness)
    mid = harness.client.get(f"/records/{ids['B']}/links")
    assert mid.status_code == 200
    rows = mid.json()
    assert [(r["direction"], r["other_key"], r["relation"]) for r in rows] == [
        ("out", "C", "requires"),
        ("in", "A", "requires"),
    ]
    assert rows[0]["label"] == "requires" and rows[1]["label"] != rows[0]["label"]
    assert rows[0]["status"] == "active" and rows[0]["other_title"] == "Record C"
    assert harness.client.get(f"/records/{ids['D']}/links").json() == []


def test_retracted_links_are_hidden_unless_asked_for(harness: Harness) -> None:
    ids = chain(harness)
    link_id = harness.client.get(f"/records/{ids['A']}/links").json()[0]["link_id"]
    done = harness.client.post(
        "/commands/RetractLink", json={"scope": SCOPE, "link_id": link_id, "reason": "mistake"}
    )
    assert done.status_code == 200, done.text
    assert harness.client.get(f"/records/{ids['A']}/links").json() == []
    shown = harness.client.get(f"/records/{ids['A']}/links", params={"include_retracted": True})
    assert [r["status"] for r in shown.json()] == ["retracted"]


def test_an_unknown_record_is_404_on_every_per_record_route(harness: Harness) -> None:
    for suffix in ("links", "trace", "expected-links"):
        response = harness.client.get(f"/records/01NOSUCHRECORD/{suffix}")
        assert response.status_code == 404, suffix
        assert response.json()["error"] == "record_not_found", suffix


def node_keys(node: dict[str, Any]) -> list[str]:
    return [node["key"]] + [k for child in node["children"] for k in node_keys(child)]


def test_trace_is_a_tree_limited_by_depth_and_direction(harness: Harness) -> None:
    ids = chain(harness)
    get = harness.client.get
    full = get(f"/records/{ids['A']}/trace").json()
    assert full["key"] == "A" and full["depth"] == 0 and full["link_id"] is None
    assert node_keys(full) == ["A", "B", "C"]
    child = full["children"][0]
    assert child["depth"] == 1 and child["direction"] == "out" and child["relation"] == "requires"
    one_hop = get(f"/records/{ids['A']}/trace", params={"depth": 1}).json()
    assert node_keys(one_hop) == ["A", "B"] and one_hop["children"][0]["more"] == 1
    inbound = get(f"/records/{ids['C']}/trace", params={"direction": "in"}).json()
    assert node_keys(inbound) == ["C", "B", "A"]
    outbound_only = get(f"/records/{ids['C']}/trace", params={"direction": "out"}).json()
    assert node_keys(outbound_only) == ["C"]


def test_trace_parameters_are_validated(harness: Harness) -> None:
    ids = chain(harness)
    for params in ({"direction": "sideways"}, {"depth": -1}, {"depth": 9}):
        response = harness.client.get(f"/records/{ids['A']}/trace", params=params)
        assert response.status_code == 422, params


def test_expected_links_lists_what_is_missing(harness: Harness) -> None:
    ids = chain(harness)
    response = harness.client.get(f"/records/{ids['D']}/expected-links")
    assert response.status_code == 200
    (missing,) = response.json()
    assert missing["expectation"]["relation"] == "references"
    assert missing["found"] == 0 and missing["needed"] == 1


def test_link_counts_include_zero_rows(harness: Harness) -> None:
    ids = chain(harness)
    response = harness.client.get(
        "/links/counts",
        params=[("record_id", ids["A"]), ("record_id", ids["B"]), ("record_id", "nope")],
    )
    assert response.status_code == 200
    counts = response.json()
    assert counts[ids["A"]]["active_out"] == 1 and counts[ids["A"]]["active_in"] == 0
    assert counts[ids["B"]]["active_out"] == 1 and counts[ids["B"]]["active_in"] == 1
    assert counts["nope"]["active_out"] == 0
    assert harness.client.get("/links/counts").status_code == 422  # at least one id


def test_search_linkable_matches_key_or_title_in_scope_and_company(harness: Harness) -> None:
    ids = chain(harness)
    harness.create_record("CO-1", "Company wide record", scope="company")
    harness.create_record("ELSE-1", "Elsewhere", scope="project:P999")
    get = harness.client.get
    found = get("/links/search", params={"scope": SCOPE, "q": "record"}).json()
    assert sorted(t["key"] for t in found) == ["A", "B", "C", "CO-1", "D"]
    assert set(found[0]) >= {"id", "key", "type", "title", "status", "scope", "link_total"}
    narrowed = get("/links/search", params={"scope": SCOPE, "q": "record b"}).json()
    assert [t["key"] for t in narrowed] == ["B"]
    without = get("/links/search", params={"scope": SCOPE, "exclude_id": ids["B"], "q": "record"})
    assert "B" not in [t["key"] for t in without.json()]
    limited = get("/links/search", params={"scope": SCOPE, "limit": 2}).json()
    assert len(limited) == 2
    assert get("/links/search", params={"scope": SCOPE, "limit": 0}).status_code == 422
    assert get("/links/search").status_code == 422  # scope is required


def test_every_link_route_needs_a_token(harness: Harness) -> None:
    ids = chain(harness)
    anon = harness.client_for(None)
    for path in (
        f"/records/{ids['A']}/links",
        f"/records/{ids['A']}/trace",
        f"/records/{ids['A']}/expected-links",
        f"/links/counts?record_id={ids['A']}",
        f"/links/search?scope={SCOPE}",
    ):
        assert anon.get(path).status_code == 401, path
