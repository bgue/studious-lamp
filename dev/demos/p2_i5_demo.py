"""Driver for dev/demos/P2-I5.sh: the clauses of the demo that are not a `tl` command.

Modes (first argument):

* ``landing NUMBER``: clause 9: the TUI opens as the foreman (user:frank) on the IWP log with the
  mine filter; the summary names the foreman.
* ``grid``: clause 9: with ``tui.landing=default`` set for the foreman, the TUI opens on the grid.
* ``recount WEEK PPC CONSTRAINT_FREE``: clause 5: the PPC and the percent constraint-free that the
  CLI and the report print are checked against a recount made with SQL on the ledger tables.
* ``agent WEEK IWP ITEM``: clause 10: the agent's MCP session files ``propose_progress`` and
  ``propose_week_commitment``; both are pending; their ids go to TL_DEMO_STATE.
* ``refusals``: clause 10: the agent's API calls for ClearConstraint and CloseWeek are refused
  ``agent_must_propose``.
* ``week-counts WEEK``: clause 10: the same week's commitments over the API, the TUI client and MCP.

Reads TL_DB (SQLite path or postgresql:// URL), TL_DEMO_URL (the API), TL_DEMO_AGENT_TOKEN and
TL_DEMO_STATE. Every expectation is an assert: a failing check exits non-zero. Nothing printed holds
a password or a token.
"""

from __future__ import annotations

import asyncio
import io
import os
import sys
from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
DEMO_PASSWORD = "demo"  # the documented dev account (ADR-0009 section 9)
SIZE = (170, 44)
FOREMAN = "user:frank"


def say(text: str) -> None:
    print(f"   {text}")


def plain(renderable: Any) -> str:
    """The text a Rich renderable shows, without colour."""
    from rich.console import Console

    buffer = io.StringIO()
    Console(file=buffer, width=SIZE[0], color_system=None, legacy_windows=False).print(renderable)
    return buffer.getvalue()


def agent_session(name: str | None, arguments: dict[str, Any] | None = None) -> Any:
    """Open the agent's MCP session; with ``name`` call that tool, else return the tool list."""
    from mcp import Client, StdioServerParameters

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "tl_mcp"],
        env={
            "TL_AGENT_TOKEN": os.environ["TL_DEMO_AGENT_TOKEN"],
            "TL_DB": os.environ["TL_DB"],
            "TL_ENV": os.environ.get("TL_ENV", "dev"),
            "TL_OBJECT_ROOT": os.environ["TL_OBJECT_ROOT"],
            "PATH": os.environ.get("PATH", ""),
        },
    )

    async def session() -> Any:
        async with Client(params) as mcp:
            tools = {t.name: t for t in (await mcp.list_tools()).tools}
            if name is None:
                return tools
            result = await mcp.call_tool(name, arguments or {})
            return result

    return asyncio.run(session())


# --- clause 9: the TUI as the foreman ------------------------------------------------------------


async def _foreman_app(check: Callable[[Any, Any], Any]) -> Any:
    from tl_tui.app import TlApp
    from tl_tui.embedded import EmbeddedClient

    client = EmbeddedClient.for_target(os.environ["TL_DB"], actor=FOREMAN)
    try:
        app = TlApp(client, scope=SCOPE, actor=FOREMAN, is_admin=False)
        async with app.run_test(size=SIZE) as pilot:
            for _ in range(20):
                await pilot.pause(0.05)
            found = check(app, pilot)
            if asyncio.iscoroutine(found):
                found = await found
            return found
    finally:
        client.close()


def landing(number: str) -> None:
    from tl_tui.widgets.iwp_register import IwpRegisterScreen

    def check(app: Any, pilot: Any) -> dict[str, Any]:
        screen = app.screen
        return {
            "screen": type(screen).__name__,
            "is_log": isinstance(screen, IwpRegisterScreen),
            "summary": screen.summary_text() if isinstance(screen, IwpRegisterScreen) else "",
            "mine": getattr(screen, "mine", None),
        }

    found = asyncio.run(_foreman_app(check))
    assert found["is_log"], f"the foreman opened {found['screen']}, not the IWP log"
    assert found["mine"] is True, "the IWP log is not filtered to the foreman's IWPs"
    name = FOREMAN.removeprefix("user:")
    assert f"foreman {name}" in found["summary"], (
        f"the summary names no foreman: {found['summary']}"
    )
    say(f"TUI as {FOREMAN}: the IWP log, mine filter on; {found['summary']}")


def grid() -> None:
    from tl_tui.widgets.iwp_register import IwpRegisterScreen

    def check(app: Any, pilot: Any) -> dict[str, Any]:
        return {
            "screen": type(app.screen).__name__,
            "is_log": isinstance(app.screen, IwpRegisterScreen),
        }

    found = asyncio.run(_foreman_app(check))
    assert not found["is_log"], "with tui.landing=default the foreman still opened the IWP log"
    say(f"TUI as {FOREMAN} with tui.landing=default: opened {found['screen']} (the grid)")


# --- clause 5: the recount -----------------------------------------------------------------------


def _number_on(text: str, label: str) -> Decimal:
    """The first decimal figure on the line that names ``label``."""
    import re

    for line in text.splitlines():
        if label in line:
            found = re.search(r"-?\d+(?:\.\d+)?", line.split(label, 1)[1])
            if found:
                return Decimal(found.group(0))
    raise AssertionError(f"no figure next to {label!r} in: {text!r}")


def recount(week: str, ppc_text: str, free_text: str) -> None:
    from tl_adapters.db import open_uow
    from tl_mod_awp.actions import IWP_LIVE_STATES

    with open_uow(os.environ["TL_DB"], readonly=True) as uow:
        conn = uow.conn()
        scope = SCOPE
        plans = conn.execute(
            _sql(
                "SELECT id, week FROM cur_awp_weekly_plan WHERE scope = :scope "
                "AND closed_at IS NOT NULL ORDER BY week_start DESC"
            ),
            {"scope": scope},
        ).fetchall()
        plans = plans[:4]
        done = committed = 0
        for plan_id, _ in plans:
            rows = conn.execute(
                _sql("SELECT outcome FROM cur_awp_week_commitment WHERE plan_id = :plan"),
                {"plan": plan_id},
            ).fetchall()
            committed += len(rows)
            done += sum(1 for (outcome,) in rows if outcome == "done")
        live = conn.execute(
            _sql(
                "SELECT r.id, w.state FROM cur_core_record AS r "
                "JOIN cur_workflow_state AS w ON w.record_id = r.id "
                "WHERE r.scope = :scope AND r.type = 'awp.IWP' AND NOT r.voided"
            ),
            {"scope": scope},
        ).fetchall()
        live_ids = [rid for rid, state in live if state in IWP_LIVE_STATES]
        free = 0
        for rid in live_ids:
            (open_blocking,) = conn.execute(
                _sql(
                    "SELECT COUNT(*) FROM cur_core_constraint AS c "
                    "JOIN cur_core_record AS r ON r.id = c.id "
                    "WHERE c.subject_id = :iwp AND c.severity = 'blocking' AND NOT r.voided "
                    "AND COALESCE(r.status, 'Open') IN ('Open', 'Assigned')"
                ),
                {"iwp": rid},
            ).one()
            free += 1 if open_blocking == 0 else 0
    ppc_expected = (
        Decimal(done * 100 / committed).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        if committed
        else None
    )
    free_expected = (
        Decimal(free * 100 / len(live_ids)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        if live_ids
        else None
    )
    say(f"recount {week}: {done} of {committed} done, {len(plans)} closed weeks -> {ppc_expected}")
    say(f"recount: {free} of {len(live_ids)} live IWPs free of blocking -> {free_expected}")
    assert ppc_expected is not None and _number_on(ppc_text, "ppc") == ppc_expected, (
        "PPC differs from the recount"
    )
    assert (
        free_expected is not None and _number_on(free_text, "kpi_constraint_free") == free_expected
    ), "the constraint-free KPI differs from the recount"


def _sql(text: str) -> Any:
    from sqlalchemy import text as sql_text

    return sql_text(text)


# --- clause 10: agents over MCP and the same week everywhere -------------------------------------


def tools() -> None:
    names = set(agent_session(None))
    wanted = {
        "propose_progress",
        "propose_week_commitment",
        "propose_iwp_scope",
        "list_weekly_plans",
    }
    missing = sorted(wanted - names)
    assert not missing, f"MCP lists no tool {missing}"
    tool_map = agent_session(None)
    for name in sorted(wanted):
        schema = tool_map[name].input_schema if name in tool_map else {}
        say(
            f"MCP tool {name}: present; arguments {sorted((schema.get('properties') or {}).keys())}"
        )
    cycle = sorted(n for n in names if "week" in n or "progress" in n or "constraint" in n)
    say(f"MCP tools of the weekly cycle: {', '.join(cycle)}")
    excluded = {"clear_constraint", "close_week", "propose_clear_constraint", "propose_close_week"}
    assert not (excluded & names), (
        f"MCP lists a tool for an act an agent may not do: {excluded & names}"
    )
    say("MCP lists no tool for ClearConstraint or CloseWeek")


def agent(week: str, iwp: str, item: str) -> None:
    """The agent files two proposals; nothing is recorded until a person accepts them."""
    progress = agent_session(
        "propose_progress",
        {
            "project": PROJECT,
            "iwp": iwp,
            "steps": [{"scope_item": item, "step": "Material received", "done": True}],
        },
    )
    assert not progress.is_error, progress
    commit = agent_session(
        "propose_week_commitment",
        {"project": PROJECT, "week": week, "iwp": iwp, "committed_hours": "12.0"},
    )
    assert not commit.is_error, commit
    ids = []
    for result in (progress, commit):
        proposal = (result.structured_content or {})["proposal"]
        assert proposal["status"] == "pending", proposal
        ids.append(proposal["proposal_id"])
    Path(os.environ["TL_DEMO_STATE"]).write_text(" ".join(ids))
    say(f"the agent's proposals {ids[0]} and {ids[1]} are pending; nothing is recorded yet")


def _dummy(schema: dict[str, Any], defs: dict[str, Any]) -> Any:
    """A value of the JSON schema's type (enough to pass request validation, not to succeed)."""
    if "$ref" in schema:
        return _dummy(defs[schema["$ref"].rsplit("/", 1)[1]], defs)
    if "enum" in schema:
        return schema["enum"][0]
    if "anyOf" in schema:
        options = [o for o in schema["anyOf"] if o.get("type") != "null"]
        return _dummy(options[0], defs)
    kind = schema.get("type")
    if kind == "integer":
        return 1
    if kind == "boolean":
        return False
    if kind == "array":
        return []
    if kind == "object":
        return {}
    if "pattern" in schema:
        return SCOPE
    return "x"


def refusals() -> None:
    """An agent's ClearConstraint and CloseWeek are refused over the API: the agent must propose."""
    import httpx

    headers = {"Authorization": f"Bearer {os.environ['TL_DEMO_AGENT_TOKEN']}"}
    with httpx.Client(base_url=os.environ["TL_DEMO_URL"], headers=headers, timeout=60) as http:
        doc = http.get("/openapi.json").json()
        defs = doc["components"]["schemas"]
        for name in ("ClearConstraint", "CloseWeek"):
            ref = doc["paths"][f"/commands/{name}"]["post"]["requestBody"]["content"][
                "application/json"
            ]["schema"]["$ref"]
            model = defs[ref.rsplit("/", 1)[1]]
            required = set(model.get("required", []))
            body = {
                key: _dummy(prop, defs)
                for key, prop in model["properties"].items()
                if key in required or key == "scope"
            }
            response = http.post(f"/commands/{name}", json=body)
            found = response.json()
            assert response.status_code == 403, (name, response.status_code)
            assert found.get("error") == "agent_must_propose", (name, found.get("error"))
            say(f"{name} by the agent is refused: {found['error']}")


def week_counts(week: str) -> None:
    from tl_api.client import ApiClient
    from tl_api.client.auth import sign_in
    from tl_tui.embedded import EmbeddedClient

    url = os.environ["TL_DEMO_URL"]
    api = ApiClient(url, sign_in(url, "demo", DEMO_PASSWORD).token)
    try:
        api_count = len(api.get_weekly_plan(PROJECT, week).commitments)
    finally:
        api.close()
    tui = EmbeddedClient.for_target(os.environ["TL_DB"], actor="user:demo")
    try:
        tui_count = len(tui.get_weekly_plan(PROJECT, week).commitments)
    finally:
        tui.close()
    body = agent_session("get_weekly_plan", {"project": PROJECT, "week": week})
    assert not body.is_error, body
    mcp_count = len((body.structured_content or {}).get("commitments", []))
    say(f"commitments of {week}: API {api_count}, TUI client {tui_count}, MCP {mcp_count}")
    assert api_count == tui_count == mcp_count, "the four surfaces disagree on the week"


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "landing":
        landing(sys.argv[2])
    elif mode == "grid":
        grid()
    elif mode == "recount":
        recount(sys.argv[2], sys.argv[3], sys.argv[4])
    elif mode == "tools":
        tools()
    elif mode == "agent":
        agent(sys.argv[2], sys.argv[3], sys.argv[4])
    elif mode == "refusals":
        refusals()
    elif mode == "week-counts":
        week_counts(sys.argv[2])
    else:
        sys.exit(f"unknown mode {mode!r}")


if __name__ == "__main__":
    main()
