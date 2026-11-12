"""``GET /records/{id}/activity`` as five kinds of reader, and what a call costs (P2-INS-S1).

The seed is the one of the confidentiality walk. A hidden record answers exactly as an id that names
nothing (status and body, the id aside); an agent is refused the route (closed until allowed); no
body holds the text or the id of anything the reader may not read. The statement-count tests run on
both adapters through the parity fixture. The five-reader walk runs on SQLite only: its seed (the
one of the confidentiality walk) does not build on Postgres in this environment.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from harness import Harness
from sqlalchemy import event as sa_event
from tl_api_walk import (  # pyright: ignore[reportMissingImports]
    FAKE_ID,
    MAY_READ,
    Seed,
    hidden_markers,
    seed,
)
from tl_core import confidentiality as cf
from tl_core import settings
from tl_core.insights.activity import record_activity
from tl_core.services import proposals
from tl_core.services.links import AddLink, handle_add_link
from tl_core.threads.messages import PostThreadMessage, handle_post_thread_message

SCOPE = "project:P123"


@pytest.fixture
def seeded(harness: Harness, tmp_path: Path) -> Seed:
    return seed(harness, tmp_path)


@pytest.mark.parametrize("reader", sorted(MAY_READ))
def test_the_activity_route_shows_each_reader_only_what_they_may_read(
    harness: Harness, seeded: Seed, reader: str
) -> None:
    client = harness.client_for(None)
    headers = {"Authorization": f"Bearer {seeded.tokens[reader]}"}
    tokens, hidden_ids = hidden_markers(seeded, reader)
    nothing = client.get(f"/records/{FAKE_ID}/activity", headers=headers)
    assert nothing.status_code == (403 if reader == "bot" else 404)
    readable = 0
    for kind, record_id in sorted(seeded.ids.items()):
        found = client.get(f"/records/{record_id}/activity", headers=headers)
        if reader == "bot":  # no agent action names the route: denied by default, hidden or not
            assert found.status_code == 403, (reader, kind)
            assert found.text.replace(record_id, FAKE_ID) == nothing.text, (reader, kind)
            continue
        if record_id in hidden_ids:
            assert found.status_code == 404, (reader, kind)
            assert found.text.replace(record_id, FAKE_ID) == nothing.text, (reader, kind)
            assert sorted(found.headers) == sorted(nothing.headers), (reader, kind)
            continue
        readable += 1
        assert found.status_code == 200, (reader, kind, found.text)
        assert found.json()["rows"], (reader, kind)
        for marker in [*tokens, *hidden_ids]:
            assert marker not in found.text, (reader, kind, marker)
    assert readable >= 2 or reader == "bot"  # the reader does read some, so the check can fail


def test_the_route_pages_and_the_clients_answer_what_the_route_does(
    harness: Harness, seeded: Seed
) -> None:
    open_id = seeded.ids["open"]
    headers = {"Authorization": f"Bearer {seeded.tokens['bob']}"}
    whole = harness.client_for(None).get(f"/records/{open_id}/activity", headers=headers).json()
    paged = (
        harness.client_for(None)
        .get(f"/records/{open_id}/activity", headers=headers, params={"limit": 1})
        .json()
    )
    assert len(paged["rows"]) == 1 and paged["rows"][0] == whole["rows"][0]
    assert paged["next_before_seq"] == whole["rows"][0]["event"]["seq"]
    for bad in ({"limit": 0}, {"limit": 201}, {"before_seq": 0}):
        got = harness.client_for(None).get(
            f"/records/{open_id}/activity", headers=headers, params=bad
        )
        assert got.status_code == 422, bad
    revisions = (
        harness.client_for(None)
        .get(f"/records/{open_id}/activity", headers=headers, params={"revisions_only": "true"})
        .json()
    )
    assert {r["event"]["stream_id"] for r in revisions["rows"]} == {open_id}
    # the HTTP client decodes the same page; a hidden or unknown record is an empty page
    client = type(harness.api())(
        "http://testserver", seeded.tokens["bob"], http=harness.client_for(None)
    )
    assert [r.event.seq for r in client.activity(open_id).rows] == [
        r["event"]["seq"] for r in whole["rows"]
    ]
    assert client.activity(seeded.ids["restricted"]).rows == []
    assert client.activity(FAKE_ID).rows == [] and client.activity(FAKE_ID).next_before_seq is None


# --- what a call costs --------------------------------------------------------------------


def grow(h: Harness, record: str, *, posts: int, links: int, proposed: int, tag: str) -> None:
    """More activity on ``record``: thread posts, links with a record each, proposals."""
    with h.backend(False) as uow:
        for key, value in (("threads.enabled", True), ("threads.enabled_types", ["core.Record"])):
            settings.set_setting(
                uow, key=key, layer="company", value=value, actor="user:a", source="t", reason="t"
            )
        for n in range(posts):
            handle_post_thread_message(
                uow,
                PostThreadMessage(
                    actor="user:seed", source="t", scope=SCOPE, record_id=record, body=f"{tag} {n}"
                ),
            )
    for n in range(links + proposed):
        other = h.create_record(f"{tag}-{n}", "other").stream_id
        with h.backend(False) as uow:
            if n < links:
                cmd = AddLink(
                    actor="user:seed", source="t", scope=SCOPE, from_id=other, to_id=record,
                    relation="references",
                )  # fmt: skip
                handle_add_link(uow, cmd)
                continue
            agent = "agent:triage"
            cmd = AddLink(
                actor=agent, source="mcp:triage", scope=SCOPE, from_id=record, to_id=other,
                relation="references",
            )  # fmt: skip
            view = proposals.propose(
                uow, tool="link_records", agent=agent, command=cmd, summary="s", budget=1000
            )
            if n % 2:
                proposals.accept_proposal(uow, proposal_id=view.proposal_id, by="user:seed")


def statements(h: Harness, record: str, **kw: Any) -> tuple[list[str], int]:
    verbs: list[str] = []
    with h.backend(True) as uow, cf.use_viewer(cf.LOWEST):
        engine = uow.conn().engine

        def count(conn: Any, cursor: Any, statement: str, *a: Any) -> None:
            verbs.append(statement.lstrip().split(None, 1)[0].upper())

        sa_event.listen(engine, "before_cursor_execute", count)
        try:
            page = record_activity(uow, record, **kw)
        finally:
            sa_event.remove(engine, "before_cursor_execute", count)
    return verbs, len(page.rows)


#: Measured on the data below: the record row (1), the three id lookups (constraints, links to the
#: record, proposals), the far-end read (5 so far); then one round: the own candidates, the ledger
#: read, the viewer filter (2 lookups of streams and threads, 5 of links, files, feed tags,
#: enrichment values and action targets, 1 of the ids the payloads name: 15). A record with linked
#: records adds the far end's candidate read (16).
STATEMENTS = 15


def test_a_call_issues_a_fixed_number_of_selects_however_many_rows_it_returns(
    parity_harness: Harness,
) -> None:
    harness = parity_harness  # SQLite, and Postgres under --adapters
    record = harness.create_record("ACT-1", "busy").stream_id
    grow(harness, record, posts=250, links=20, proposed=10, tag="a")
    first, rows = statements(harness, record)
    assert rows == 120 and set(first) == {"SELECT"}  # no write, no telemetry
    assert len(first) == STATEMENTS, len(first)
    grow(harness, record, posts=250, links=20, proposed=10, tag="b")  # 500 own events, 40 links
    second, rows = statements(harness, record)
    assert rows == 120 and len(second) == len(first)
    bigger, rows = statements(harness, record, limit=200)
    assert rows == 200 and len(bigger) == len(first)
    own, _ = statements(harness, record, revisions_only=True)
    assert set(own) == {"SELECT"} and len(own) < len(first)
