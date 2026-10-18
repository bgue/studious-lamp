"""The reserved-identifier walk over every thread entry point that takes client input (FANOUT D2,
P1-I7 WS-B): a client cannot name a source, a correlation or causation id, a link source or an
``enrich.`` pset that only the server sets, on any of them."""

from __future__ import annotations

from typing import Any

import pytest
from harness import SCOPE, Harness
from test_api_threads import make_account, switch_on
from tl_core.integration.contract import (
    RESERVED_CORRELATION_PREFIXES,
    RESERVED_LINK_SOURCES,
    RESERVED_SOURCE_PREFIXES,
)

#: (method, path template) of every thread route with a body.
ENTRY_POINTS = {
    ("post", "/commands/PostThreadMessage"),
    ("post", "/commands/EditThreadMessage"),
    ("post", "/commands/RetractThreadMessage"),
    ("post", "/records/{record_id}/thread/preview"),
    ("post", "/records/{record_id}/thread/dispatch"),
}


def thread_routes(h: Harness) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for path, methods in h.app.openapi()["paths"].items():
        if "ThreadMessage" in path or "/thread/" in path:
            found.update((method, path) for method, op in methods.items() if "requestBody" in op)
    return found


def bodies(rid: str) -> dict[str, dict[str, Any]]:
    token = "0" * 64
    return {
        "/commands/PostThreadMessage": {"scope": SCOPE, "record_id": rid, "body": "hello"},
        "/commands/EditThreadMessage": {
            "scope": SCOPE,
            "record_id": rid,
            "message_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
            "body": "hello",
        },
        "/commands/RetractThreadMessage": {
            "scope": SCOPE,
            "record_id": rid,
            "message_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
            "reason": "typo",
        },
        "/records/{record_id}/thread/preview": {"text": "/link P123-REC-0002"},
        "/records/{record_id}/thread/dispatch": {"text": "/link P123-REC-0002", "token": token},
    }


def extras() -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    values += [{"source": f"{prefix}x"} for prefix in RESERVED_SOURCE_PREFIXES]
    values += [{"correlation_id": f"{prefix}x"} for prefix in RESERVED_CORRELATION_PREFIXES]
    values += [{"causation_id": f"{prefix}x"} for prefix in RESERVED_CORRELATION_PREFIXES]
    values += [{"link_source": name} for name in sorted(RESERVED_LINK_SOURCES)]
    values += [{"psets": {"enrich.classifier": {"label": "x"}}}, {"enrich": {"label": "x"}}]
    return values


def test_the_walk_lists_every_thread_entry_point(harness: Harness) -> None:
    found = thread_routes(harness)
    assert found == ENTRY_POINTS
    assert len(found) == 5
    assert ("post", "/commands/PostThreadMessage") in found
    assert ("post", "/records/{record_id}/thread/dispatch") in found
    assert len(extras()) >= 20


def test_every_thread_entry_point_refuses_what_only_the_server_sets(harness: Harness) -> None:
    switch_on(harness)
    make_account(harness, "alice")
    rid = harness.create_record("P123-REC-0001").stream_id
    harness.create_record("P123-REC-0002")
    before = len(harness.client.get("/events").json()["events"])
    for _, template in sorted(ENTRY_POINTS):
        path = template.format(record_id=rid)
        for extra in extras():
            body = {**bodies(rid)[template], **extra}
            refused = harness.client.post(path, json=body)
            assert refused.status_code == 422, (path, extra, refused.text)
    assert len(harness.client.get("/events").json()["events"]) == before


@pytest.mark.parametrize("name", ["source", "correlation_id", "causation_id"])
def test_a_command_route_names_the_reserved_identifier_in_its_refusal(
    harness: Harness, name: str
) -> None:
    rid = harness.create_record("P123-REC-0001").stream_id
    body = {**bodies(rid)["/commands/PostThreadMessage"], name: "dispatch:x"}
    if name == "source":
        body[name] = "thread:x"
    refused = harness.client.post("/commands/PostThreadMessage", json=body)
    assert refused.status_code == 422 and refused.json()["error"] == "reserved_identifier"
