"""Feed routes: the page, one post, completion, the four feed commands and their errors."""

from __future__ import annotations

from harness import SCOPE, Harness


def post(h: Harness, body: str, scope: str = SCOPE, **extra: object) -> str:
    response = h.client.post("/commands/PostToFeed", json={"scope": scope, "body": body, **extra})
    assert response.status_code == 200, response.text
    return response.json()["stream_id"]


def test_a_post_is_listed_with_its_author_and_the_token_actor(harness: Harness) -> None:
    post_id = post(harness, "Hello #hold")
    page = harness.client.get("/feed", params={"scope": SCOPE, "item_type": "post"})
    assert page.status_code == 200
    items = page.json()["items"]
    assert [(i["id"], i["actor"], i["summary"], i["importance"]) for i in items] == [
        (post_id, "user:alice", "Hello #hold", "high")
    ]
    assert page.json()["next_before"] is None


def test_the_body_cannot_set_the_actor(harness: Harness) -> None:
    response = harness.client.post(
        "/commands/PostToFeed", json={"scope": SCOPE, "body": "hi", "actor": "user:mallory"}
    )
    assert response.status_code == 422


def test_a_post_that_names_a_record_suggests_a_link_and_offers_a_constraint(
    harness: Harness,
) -> None:
    record_id = harness.create_record("P123-REC-0001", "Spool").stream_id
    created = harness.client.post(
        "/commands/PostToFeed", json={"scope": SCOPE, "body": "Spool #P123-REC-0001 on #hold"}
    )
    assert [e["event_type"] for e in created.json()["events"]] == ["Feed.Posted", "Link.Suggested"]
    page = harness.client.get("/feed", params={"scope": SCOPE, "record_id": record_id}).json()
    post_id = page["items"][0]["id"]
    assert page["labels"][record_id] == "P123-REC-0001"
    assert page["suggestions"][post_id][0]["kind"] == "constraint"


def test_parameters_are_validated(harness: Harness) -> None:
    for params in (
        {"scope": SCOPE, "limit": 0},
        {"scope": SCOPE, "limit": 201},
        {"scope": SCOPE, "item_type": "nope"},
        {"scope": SCOPE, "tag": "x" * 201},
        {"scope": ""},
        {},
    ):
        assert harness.client.get("/feed", params=params).status_code == 422, params
    bad = harness.client.get("/feed/complete", params={"scope": SCOPE, "sigil": "$"})
    assert bad.status_code == 422


def test_one_post_and_the_error_for_an_unknown_or_foreign_one(harness: Harness) -> None:
    post_id = post(harness, "mine")
    found = harness.client.get(f"/feed/posts/{post_id}", params={"scope": SCOPE})
    assert found.status_code == 200 and found.json()["summary"] == "mine"
    other = harness.client.get(f"/feed/posts/{post_id}", params={"scope": "project:P999"})
    assert other.status_code == 404 and other.json()["error"] == "post_not_found"
    missing = harness.client.post(
        "/commands/EditPost", json={"scope": SCOPE, "post_id": "01NOSUCH", "body": "x"}
    )
    assert missing.status_code == 404 and missing.json()["error"] == "post_not_found"


def test_service_errors_use_the_table(harness: Harness) -> None:
    company = harness.client.post("/commands/PostToFeed", json={"scope": "company", "body": "x"})
    assert company.status_code == 422 and company.json()["error"] == "invalid_scope"
    blank = harness.client.post("/commands/PostToFeed", json={"scope": SCOPE, "body": "  "})
    assert blank.status_code == 422 and blank.json()["error"] == "validation_error"
    post_id = post(harness, "to retract")
    done = harness.client.post(
        "/commands/RetractPost", json={"scope": SCOPE, "post_id": post_id, "reason": "mistake"}
    )
    assert done.status_code == 200
    again = harness.client.post(
        "/commands/EditPost", json={"scope": SCOPE, "post_id": post_id, "body": "x"}
    )
    assert again.status_code == 409 and again.json()["error"] == "post_retracted"


def test_reading_the_feed_needs_a_token(harness: Harness) -> None:
    anon = harness.client_for(None)
    for path in ("/feed", "/feed/complete", "/feed/posts/x"):
        assert anon.get(path, params={"scope": SCOPE}).status_code == 401, path


def test_pages_follow_next_before(harness: Harness) -> None:
    for n in range(3):
        post(harness, f"post {n}")
    first = harness.client.get("/feed", params={"scope": SCOPE, "item_type": "post", "limit": 2})
    assert [i["summary"] for i in first.json()["items"]] == ["post 2", "post 1"]
    rest = harness.client.get(
        "/feed",
        params={
            "scope": SCOPE,
            "item_type": "post",
            "limit": 2,
            "before_seq": first.json()["next_before"],
        },
    )
    assert [i["summary"] for i in rest.json()["items"]] == ["post 0"]
