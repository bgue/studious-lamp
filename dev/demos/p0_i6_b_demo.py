"""Driver for dev/demos/P0-I6-B.sh: an MCP agent proposes, a person decides.

Modes (first argument):

* ``agent``: an in-process MCP server acting as ``agent:triage`` over the demo ledger. It proposes
  two records, posts to the feed, proposes a third and is refused a fourth (the shell sets the
  daily budget to 3), then shows that no record exists yet.
* ``provenance KEY``: who made the record ``KEY`` and on whose suggestion, read from the ledger.
* ``api PROPOSAL_ID``: over HTTP, the agent's token is refused when it tries to accept and a
  person's token accepts.

Reads TL_DB, TL_DEMO_URL, TL_DEMO_TOKEN and TL_DEMO_AGENT_TOKEN from the environment. Every
expectation is an assert, so a failing demo exits non-zero.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import CallToolResult
from sqlalchemy import text
from tl_adapters.sqlite.factory import SqliteUowFactory
from tl_api.client import ApiClient
from tl_core.services.errors import ProposalDeciderError
from tl_mcp.server import build_server

SCOPE = "project:P123"
AGENT = "agent:triage"


def say(text: str) -> None:
    print(f"   {text}")


def agent_session() -> None:
    factory = SqliteUowFactory(os.environ["TL_DB"])
    server = build_server(factory, actor=AGENT)

    def call(tool: str, **arguments: Any) -> dict[str, Any]:
        result = asyncio.run(server.call_tool(tool, arguments))
        assert isinstance(result, CallToolResult) and result.structured_content is not None
        return result.structured_content

    tools = sorted(t.name for t in asyncio.run(server.list_tools()))
    say("tools: " + ", ".join(tools))
    assert "accept_proposal" not in tools  # an agent cannot decide: there is no such tool
    for title in ("Weld NCR W-12: cracked bevel", "Duplicate weld NCR W-12"):
        out = call("create_record", scope=SCOPE, title=title)
        proposal = out["proposal"]
        print(f"proposed {proposal['proposal_id']} {proposal['status']} {proposal['summary']}")
        assert proposal["status"] == "pending" and proposal["agent"] == AGENT
    posted = call("post_feed", scope=SCOPE, body="Found a cracked bevel at weld W-12 #hold")
    print(f"posted {posted['post_id']} by {posted['author']}")
    third = call("create_record", scope=SCOPE, title="Re-inspect weld W-12 after repair")
    print(f"proposed {third['proposal']['proposal_id']} pending {third['proposal']['summary']}")
    try:
        call("create_record", scope=SCOPE, title="A fourth proposal today")
    except ToolError as exc:
        print(f"refused {exc}")
    else:
        raise AssertionError("the fourth proposal was not refused")
    seen = call("search_records", scope=SCOPE)
    print(f"records visible in {SCOPE}: {seen['total']}")
    assert seen["total"] == 0  # nothing has changed: proposals are not records
    factory.close()


def provenance(key: str) -> None:
    factory = SqliteUowFactory(os.environ["TL_DB"])
    with factory(True) as uow:
        row = (
            uow.conn()
            .execute(text("SELECT id FROM cur_core_record WHERE key = :key"), {"key": key})
            .first()
        )
        assert row is not None, f"no record {key}"
        (made,) = uow.ledger.read_stream(row[0])
        cause = [e for e in uow.ledger.read_after(0, limit=1000) if e.event_id == made.causation_id]
    assert len(cause) == 1 and cause[0].event_type == "Proposal.Created"
    print(f"{key} created by {made.actor} source {made.source}")
    print(f"caused by {cause[0].event_type} {cause[0].stream_id} from {cause[0].actor}")
    factory.close()


def over_http(proposal_id: str) -> None:
    url = os.environ["TL_DEMO_URL"]
    person = ApiClient(url, os.environ["TL_DEMO_TOKEN"])
    robot = ApiClient(url, os.environ["TL_DEMO_AGENT_TOKEN"])
    queue = person.list_proposals(SCOPE, status=None)
    say("queue: " + ", ".join(f"{p.status}" for p in queue))
    try:
        robot.accept_proposal(proposal_id)
    except ProposalDeciderError as exc:
        print(f"agent refused: {exc}")
    else:
        raise AssertionError("an agent token accepted a proposal")
    done = person.accept_proposal(proposal_id)
    print(f"accepted over HTTP by {done.decided_by}: {done.summary}")
    assert done.status == "accepted"
    assert [p.status for p in person.list_proposals(SCOPE)] == []
    again = person.list_proposals(SCOPE, status="accepted")
    print(f"accepted so far: {len(again)}")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "agent"
    if mode == "agent":
        agent_session()
    elif mode == "provenance":
        provenance(sys.argv[2])
    elif mode == "api":
        over_http(sys.argv[2])
    else:
        raise SystemExit(f"unknown mode {mode!r}")


if __name__ == "__main__":
    main()
