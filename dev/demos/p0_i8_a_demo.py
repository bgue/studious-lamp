"""Driver for dev/demos/P0-I8-A.sh: about:config settings over MCP, HTTP and the TUI.

Modes (first argument):

* ``agent``: an in-process MCP server acting as ``agent:triage``. It reads the settings
  (``get_settings``), proposes a change of a safe key and of a dangerous key, and shows that the
  settings did not change and that the tool takes no risk acceptance.
* ``api PROPOSAL_ID``: over HTTP, the agent's token may read settings but every write is refused
  (403 ``agent_must_propose``); a person's token changes a setting, and accepts a dangerous
  proposal only with the risk accepted.
* ``tui OUT.svg``: the about:config screen of the TUI on the demo ledger, saved as an SVG.

Reads TL_DB, TL_DEMO_URL, TL_DEMO_TOKEN and TL_DEMO_AGENT_TOKEN from the environment. Every
expectation is an assert, so a failing demo exits non-zero.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

from mcp_types import CallToolResult
from tl_adapters.sqlite.factory import SqliteUowFactory
from tl_api.client import ApiClient
from tl_api.errors import ApiError
from tl_core.services.errors import RiskNotAcceptedError

AGENT = "agent:triage"
KEY = "feed.reactions.enabled"
DANGER = "webhooks.egress.allowlist"


def say(text: str) -> None:
    print(f"   {text}")


def agent_session() -> None:
    from tl_mcp.server import build_server

    factory = SqliteUowFactory(os.environ["TL_DB"])
    server = build_server(factory, actor=AGENT)

    def call(tool: str, **arguments: Any) -> dict[str, Any]:
        result = asyncio.run(server.call_tool(tool, arguments))
        assert isinstance(result, CallToolResult) and result.structured_content is not None
        return result.structured_content

    tools = sorted(t.name for t in asyncio.run(server.list_tools()))
    say("tools: " + ", ".join(tools))
    assert "get_settings" in tools and "propose_setting_change" in tools
    assert "set_setting" not in tools  # there is no tool that sets a value
    seen = call("get_settings", prefix="feed.")
    keys = [row["effective"]["key"] for row in seen["result"]]
    print(f"agent reads {', '.join(keys)}")
    first = call("propose_setting_change", key=KEY, layer="project:P123", value=False)
    print(f"proposed {first['proposal']['proposal_id']} pending {first['proposal']['summary']}")
    danger = call(
        "propose_setting_change",
        key=DANGER,
        layer="company",
        value=["hub.example.com"],
        reason="partner hub",
        accept_risk=True,  # not a declared argument: ignored, the person must accept the risk
    )
    print(f"proposed {danger['proposal']['proposal_id']} pending {danger['proposal']['summary']}")
    one = call("get_settings", key=KEY, project="P123")
    value = one["result"][0]["effective"]["value"]
    print(f"{KEY} for P123 is still {str(value).lower()}")
    assert value is True  # a proposal changes nothing
    factory.close()


def over_http(dangerous_id: str) -> None:
    url = os.environ["TL_DEMO_URL"]
    person = ApiClient(url, os.environ["TL_DEMO_TOKEN"])
    robot = ApiClient(url, os.environ["TL_DEMO_AGENT_TOKEN"])
    say(f"the agent reads {len(robot.list_settings())} settings")
    try:
        robot.set_setting(KEY, layer="company", value=False)
    except ApiError as exc:
        print(f"agent write refused: {exc.status} {exc.error}")
        assert (exc.status, exc.error) == (403, "agent_must_propose")
    else:
        raise AssertionError("an agent token changed a setting")
    done = person.set_setting("ai.agents.daily_proposals", layer="company", value=50, reason="pilot")
    print(f"alice set {done.effective.key} to {done.effective.value} at {done.effective.origin}")
    try:
        person.accept_proposal(dangerous_id)
    except RiskNotAcceptedError as exc:
        print(f"accept without the risk refused: {exc}")
    else:
        raise AssertionError("a dangerous proposal was accepted without the risk")
    assert person.get_proposal(dangerous_id, "company").status == "pending"
    print("the proposal is still pending")
    import httpx2

    body = {"roles": [], "accept_risk": True}
    reply = httpx2.post(
        f"{url}/proposals/{dangerous_id}/accept",
        json=body,
        headers={"Authorization": f"Bearer {os.environ['TL_DEMO_TOKEN']}"},
    )
    assert reply.status_code == 200 and reply.json()["status"] == "accepted", reply.text
    print("accepted with the risk accepted by alice")
    got = person.get_setting(DANGER)
    print(f"{DANGER} is now {got.effective.value}")
    assert got.effective.value == ["hub.example.com"]


def tui_snapshot(out: str) -> None:
    from textual.widgets import Input
    from tl_tui.app import TlApp
    from tl_tui.embedded import EmbeddedClient
    from tl_tui.widgets.settings_screen import SettingsScreen

    client = EmbeddedClient.for_sqlite(os.environ["TL_DB"], actor="user:alice")
    app = TlApp(client, scope="project:P123", actor="user:alice")

    async def run() -> str:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("f9")
            await pilot.pause()
            assert isinstance(app.screen, SettingsScreen)
            app.screen.query_one("#settings-filter", Input).value = "feed."
            await pilot.pause()
            return app.export_screenshot(title="about:config")

    svg = asyncio.run(run())
    with open(out, "w", encoding="utf-8") as handle:
        handle.write(svg)
    client.close()
    print(f"saved {out} ({len(svg)} bytes)")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "agent"
    if mode == "agent":
        agent_session()
    elif mode == "api":
        over_http(sys.argv[2])
    elif mode == "tui":
        tui_snapshot(sys.argv[2])
    else:
        raise SystemExit(f"unknown mode {mode!r}")


if __name__ == "__main__":
    main()
