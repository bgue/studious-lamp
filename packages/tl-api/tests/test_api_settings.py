"""The /settings routes and POST /commands/ChangeSetting (P0-I8-T03). Provided; do not edit."""

from __future__ import annotations

from typing import Any

import yaml
from fastapi.testclient import TestClient
from harness import ALICE, BOB, Harness
from tl_api.tokens import add_token
from tl_core.proposals.types import ProposalView
from tl_core.services import proposals
from tl_core.services.settings import ChangeSetting

AGENT = "agent:triage"
KEY = "feed.reactions.enabled"


def put(h: Harness, key: str, layer: str, value: Any, **extra: Any) -> Any:
    return h.client.put(f"/settings/{key}", json={"layer": layer, "value": value, **extra})


def as_agent(h: Harness) -> TestClient:
    token = add_token(h.settings.tokens_path, AGENT)
    client = TestClient(h.app, raise_server_exceptions=False)
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


# --- reads --------------------------------------------------------------------------------------


def test_the_list_has_every_platform_key_with_its_definition_and_state(harness: Harness) -> None:
    got = harness.client.get("/settings")
    assert got.status_code == 200
    rows = got.json()
    keys = [r["effective"]["key"] for r in rows]
    assert keys == sorted(keys) and len(keys) == 16
    first = next(r for r in rows if r["effective"]["key"] == KEY)
    assert first["definition"]["type"] == "bool" and first["definition"]["default"] is True
    assert first["effective"] == {
        "key": KEY,
        "value": True,
        "origin": "default",
        "modified_here": False,
        "locked": False,
        "bounds": None,
        "scheduled": [],
        "pending_effect": None,
    }


def test_the_list_can_be_narrowed_and_viewed_as_a_project(harness: Harness) -> None:
    assert put(harness, KEY, "project:P1", False).status_code == 200
    rows = harness.client.get("/settings", params={"project": "P1", "prefix": "feed."}).json()
    assert [r["effective"]["key"] for r in rows] == [KEY, "feed.signal_tags"]
    assert rows[0]["effective"]["origin"] == "project" and rows[0]["effective"]["modified_here"]
    mine = harness.client.get("/settings", params={"project": "P1", "modified": True}).json()
    assert [r["effective"]["key"] for r in mine] == [KEY]
    other = harness.client.get("/settings", params={"project": "P2", "modified": True}).json()
    assert other == []


def test_one_setting_and_an_unknown_one(harness: Harness) -> None:
    got = harness.client.get(f"/settings/{KEY}")
    assert got.status_code == 200 and got.json()["definition"]["key"] == KEY
    missing = harness.client.get("/settings/no.such")
    assert missing.status_code == 404 and missing.json()["error"] == "unknown_setting"


# --- writes -------------------------------------------------------------------------------------


def test_put_sets_a_key_and_answers_with_the_layer_as_seen(harness: Harness) -> None:
    got = put(harness, KEY, "project:P1", False)
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["effective"]["value"] is False and body["effective"]["origin"] == "project"
    assert body["effective"]["modified_here"] is True
    assert harness.client.get(f"/settings/{KEY}").json()["effective"]["value"] is True
    seen = harness.client.get(f"/settings/{KEY}", params={"project": "P1"}).json()
    assert seen["effective"]["value"] is False
    events = harness.client.get("/events", params={"type": "Setting.Changed"}).json()
    rows = events["events"] if isinstance(events, dict) else events
    assert rows[-1]["actor"] == ALICE and rows[-1]["source"] == "api"


def test_put_refuses_with_the_stable_error_codes(harness: Harness) -> None:
    cases: list[tuple[str, str, Any, dict[str, Any], int, str]] = [
        (KEY, "project:P1", "yes", {}, 422, "invalid_setting_value"),
        (KEY, "elsewhere", True, {}, 422, "setting_scope"),
        ("ui.tui.keymap", "company", "vim", {}, 422, "setting_scope"),
        ("no.such", "company", 1, {}, 404, "unknown_setting"),
        ("webhooks.retry.max_hours", "company", 48, {}, 422, "reason_required"),
        (
            "webhooks.egress.allowlist",
            "company",
            ["a.example.com"],
            {"reason": "r"},
            422,
            "risk_not_accepted",
        ),
        (
            KEY,
            "company",
            True,
            {"applies_at": "2001-01-01T00:00:00Z"},
            422,
            "invalid_setting_value",
        ),
    ]
    for key, layer, value, extra, status, code in cases:
        got = put(harness, key, layer, value, **extra)
        assert (got.status_code, got.json()["error"]) == (status, code), (key, layer, got.text)


def test_a_dangerous_key_takes_a_reason_and_the_risk(harness: Harness) -> None:
    got = put(
        harness,
        "webhooks.egress.allowlist",
        "company",
        ["a.example.com"],
        reason="partner hub",
        accept_risk=True,
    )
    assert got.status_code == 200 and got.json()["effective"]["value"] == ["a.example.com"]


def test_a_scheduled_change_is_listed_and_not_yet_in_force(harness: Harness) -> None:
    got = put(harness, KEY, "company", False, applies_at="2099-01-01T00:00:00Z")
    assert got.status_code == 200
    effective = got.json()["effective"]
    assert effective["value"] is True
    assert effective["scheduled"] == [
        {"applies_at": "2099-01-01T00:00:00.000000Z", "new_value": False, "seq": 1}
    ]


def test_bodies_are_checked(harness: Harness) -> None:
    path = f"/settings/{KEY}"
    assert harness.client.put(path, json={"value": True}).status_code == 422  # no layer
    assert harness.client.put(path, json={"layer": "company"}).status_code == 422  # no value
    assert (
        harness.client.put(path, json={"layer": "company", "value": 1, "actor": "x"}).status_code
        == 422
    )
    assert put(harness, KEY, "company", True, reason="x" * 1001).status_code == 422
    assert put(harness, KEY, "x" * 129, True).status_code == 422


def test_reset_and_the_marker(harness: Harness) -> None:
    put(harness, KEY, "company", False)
    put(harness, KEY, "project:P1", True)
    got = harness.client.post(f"/settings/{KEY}/reset", json={"layer": "project:P1"})
    assert got.status_code == 200
    effective = got.json()["effective"]
    assert (effective["value"], effective["origin"], effective["modified_here"]) == (
        False,
        "company",
        False,
    )
    again = harness.client.post(f"/settings/{KEY}/reset", json={"layer": "project:P1"})
    assert again.status_code == 200
    assert harness.client.post(f"/settings/{KEY}/reset", json={}).status_code == 422


def test_lock_bounds_and_the_conflict_it_causes(harness: Harness) -> None:
    locked = harness.client.post(f"/settings/{KEY}/lock", json={"locked": True, "reason": "policy"})
    assert locked.status_code == 200 and locked.json()["effective"]["locked"] is True
    blocked = put(harness, KEY, "project:P1", False)
    assert blocked.status_code == 409 and blocked.json()["error"] == "setting_locked"
    assert harness.client.post(f"/settings/{KEY}/lock", json={"locked": True}).status_code == 422
    bad = harness.client.post(
        "/settings/ai.agents.daily_proposals/lock", json={"locked": True, "reason": "r"}
    )
    assert bad.status_code == 422 and bad.json()["error"] == "setting_not_lockable"
    bounded = harness.client.post(
        "/settings/project.mode/lock",
        json={"locked": False, "bounds": {"choices": ["live"]}, "reason": "policy"},
    )
    assert bounded.json()["effective"]["bounds"] == {"choices": ["live"]}
    out = put(harness, "project.mode", "project:P1", "sandbox", reason="r")
    assert out.status_code == 422 and out.json()["error"] == "setting_out_of_bounds"


def test_history_and_revert(harness: Harness) -> None:
    put(harness, "feed.signal_tags", "project:P1", ["a"])
    put(harness, "feed.signal_tags", "project:P1", ["b"])
    rows = harness.client.get("/settings/feed.signal_tags/history").json()
    assert [(r["seq"], r["layer"], r["new_value"], r["actor"]) for r in rows] == [
        (1, "project:P1", ["a"], ALICE),
        (2, "project:P1", ["b"], ALICE),
    ]
    assert (
        harness.client.get("/settings/feed.signal_tags/history", params={"layer": "company"}).json()
        == []
    )
    done = harness.client.post(
        "/settings/feed.signal_tags/revert", json={"layer": "project:P1", "seq": 2}
    )
    assert done.status_code == 200 and done.json()["effective"]["value"] == ["a"]
    missing = harness.client.post(
        "/settings/feed.signal_tags/revert", json={"layer": "project:P1", "seq": 99}
    )
    assert missing.status_code == 404 and missing.json()["error"] == "setting_change_not_found"


def test_diff_between_layers(harness: Harness) -> None:
    put(harness, KEY, "company", False)
    rows = harness.client.get(
        "/settings/diff", params={"left": "default", "right": "company"}
    ).json()
    assert [r["key"] for r in rows] == [KEY]
    assert (rows[0]["left"]["value"], rows[0]["right"]["value"]) == (True, False)
    bad = harness.client.get("/settings/diff", params={"left": "default", "right": "nowhere"})
    assert bad.status_code == 422 and bad.json()["error"] == "setting_scope"
    assert harness.client.get("/settings/diff", params={"left": "default"}).status_code == 422


def test_export_and_import(harness: Harness) -> None:
    put(harness, KEY, "project:P1", False)
    exported = harness.client.get("/settings/export", params={"layer": "project:P1"})
    assert exported.status_code == 200 and exported.headers["content-type"].startswith("text/yaml")
    assert yaml.safe_load(exported.text)["settings"] == {KEY: False}
    done = harness.client.post(
        "/settings/import", json={"layer": "project:P2", "document": exported.text}
    )
    assert done.status_code == 200 and done.json() == {"layer": "project:P2", "keys": [KEY]}
    seen = harness.client.get(f"/settings/{KEY}", params={"project": "P2"}).json()
    assert seen["effective"]["value"] is False
    bad = harness.client.post("/settings/import", json={"layer": "company", "document": "x: ["})
    assert bad.status_code == 422 and bad.json()["error"] == "settings_document"
    nope = harness.client.post(
        "/settings/import",
        json={"layer": "company", "document": yaml.safe_dump({"settings": {"no.such": 1}})},
    )
    assert nope.status_code == 404
    unknown_layer = harness.client.get("/settings/export", params={"layer": "nowhere"})
    assert unknown_layer.status_code == 422


# --- who may call -------------------------------------------------------------------------------


def test_an_agent_token_can_read_but_never_change_a_setting(harness: Harness) -> None:
    agent = as_agent(harness)
    assert agent.get("/settings").status_code == 200
    assert agent.get(f"/settings/{KEY}").status_code == 200
    attempts = [
        agent.put(f"/settings/{KEY}", json={"layer": "company", "value": False}),
        agent.post(f"/settings/{KEY}/reset", json={"layer": "company"}),
        agent.post(f"/settings/{KEY}/lock", json={"locked": True, "reason": "r"}),
        agent.post(f"/settings/{KEY}/revert", json={"layer": "company", "seq": 1}),
        agent.post("/settings/import", json={"layer": "company", "document": "settings: {}"}),
        agent.post(
            "/commands/ChangeSetting",
            json={"scope": "company", "key": KEY, "layer": "company", "value": False},
        ),
    ]
    for got in attempts:
        assert got.status_code == 403, got.text
        assert got.json()["error"] == "agent_must_propose"
    assert harness.client.get(f"/settings/{KEY}").json()["effective"]["value"] is True


def test_every_route_needs_a_token(harness: Harness) -> None:
    anonymous = harness.client_for(None)
    assert anonymous.get("/settings").status_code == 401
    assert (
        anonymous.put(f"/settings/{KEY}", json={"layer": "company", "value": False}).status_code
        == 401
    )


# --- the command and proposals ------------------------------------------------------------------


def test_the_change_setting_command_is_a_route(harness: Harness) -> None:
    got = harness.client.post(
        "/commands/ChangeSetting",
        json={"scope": "project:P1", "key": KEY, "layer": "project:P1", "value": False},
    )
    assert got.status_code == 200, got.text
    assert got.json()["stream_id"] == f"setting:project:P1:{KEY}" and got.json()["version"] == 1
    assert (
        harness.client.get(f"/settings/{KEY}", params={"project": "P1"}).json()["effective"][
            "value"
        ]
        is False
    )
    mismatch = harness.client.post(
        "/commands/ChangeSetting",
        json={"scope": "company", "key": KEY, "layer": "project:P1", "value": False},
    )
    assert mismatch.status_code == 422
    with_actor = harness.client.post(
        "/commands/ChangeSetting",
        json={"scope": "company", "key": KEY, "layer": "company", "value": False, "actor": ALICE},
    )
    assert with_actor.status_code == 422


def propose(h: Harness, **kw: Any) -> ProposalView:
    command = ChangeSetting(
        actor=AGENT,
        source="mcp:triage",
        scope="company",
        key=kw.pop("key", "webhooks.egress.allowlist"),
        layer="company",
        value=kw.pop("value", ["hub.example.com"]),
        reason="partner hub",
    )
    return proposals.submit(
        h.backend,
        tool="propose_setting_change",
        agent=AGENT,
        command=command,
        summary="Allow the hub",
    )


def test_accepting_a_dangerous_proposal_takes_the_risk_in_the_accept_body(harness: Harness) -> None:
    first = propose(harness)
    shown = harness.client.get("/proposals", params={"scope": "company"}).json()
    assert shown[0]["setting"]["risk"] == "dangerous"
    assert shown[0]["setting"]["key"] == "webhooks.egress.allowlist"
    refused = harness.client.post(f"/proposals/{first.proposal_id}/accept")
    assert refused.status_code == 422 and refused.json()["error"] == "risk_not_accepted"
    pending = harness.client.get("/proposals", params={"scope": "company"}).json()
    assert [p["proposal_id"] for p in pending] == [first.proposal_id]  # still pending
    accepted = harness.client.post(
        f"/proposals/{first.proposal_id}/accept", json={"accept_risk": True}
    )
    assert accepted.status_code == 200 and accepted.json()["status"] == "accepted"
    value = harness.client.get("/settings/webhooks.egress.allowlist").json()["effective"]["value"]
    assert value == ["hub.example.com"]
    assert harness.client_for(BOB).get("/settings/webhooks.egress.allowlist").status_code == 200


def test_only_the_latest_change_can_be_reverted(harness: Harness) -> None:
    put(harness, "feed.signal_tags", "project:P1", ["a"])
    put(harness, "feed.signal_tags", "project:P1", ["b"])
    old = harness.client.post(
        "/settings/feed.signal_tags/revert", json={"layer": "project:P1", "seq": 1}
    )
    assert old.status_code == 409 and old.json()["error"] == "setting_revert_not_latest"
