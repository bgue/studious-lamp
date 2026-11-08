"""Acceptance for P2-I2-T09b: the IWP and readiness MCP tools (four reads, one proposal), as
``dev/accept/P2-I1/T06.py`` does for the awp tools. The constraint tools are not in this ticket
(an agent holds no ``core.constraint.*`` word; ADR-0027).

The world is the T04a seed (``t04a_checks``): IWPs i1 and i2 visible, i3 and its CWP restricted
(hidden from the lowest clearance an MCP agent reads as); readiness rows for i1 and i3 written as
T04c1 writes them. The servers run on a copy of the seed in a temporary directory. Nothing is sent
over a network.

Prints one ``PASS <check>`` line per check, then ``T09b ok``. Exits 1 on the first failure.
Run: ``uv run python dev/accept/P2-I2/T09b.py``.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parents[3] / "packages/tl-modules/awp/tests"))
sys.path.insert(0, str(Path(__file__).parent))

import t04a_checks as t  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402
from sqlalchemy import text  # noqa: E402
from tl_adapters.db import as_target, make_uow_factory, open_uow  # noqa: E402
from tl_core.auth.errors import ForbiddenError  # noqa: E402
from tl_core.auth.module_roles import holder_for_actor  # noqa: E402
from tl_core.services import proposals  # noqa: E402
from tl_mcp.identity import MCP_ACTIONS  # noqa: E402
from tl_mcp.iwp_tools import IWP_MCP_ACTIONS  # noqa: E402
from tl_mcp.server import build_server  # noqa: E402
from tl_mod_awp import iwp_views  # noqa: E402
from tl_mod_awp.names import READINESS_CHECK_TABLE, READINESS_TABLE  # noqa: E402
from tl_mod_awp.projectors._common import ddl_for  # noqa: E402

PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
LOW_AGENT = "agent:triage"  # the actor the agent server runs as
READER = "user:uma"  # a person's server, for the reads a low clearance cannot make
HEX32 = re.compile(r"\b[0-9a-f]{32}\b")
MADE_UP_IWP = "P123-IWP-CIV-9999"
HIDDEN_TOKEN = "FACTSHASH"


class Failed(Exception):
    pass


def passed(check: str) -> None:
    print(f"PASS {check}", flush=True)


def need(ok: bool, what: str) -> None:
    if not ok:
        raise Failed(what)


def tail(message: str) -> str:
    """The error text without the tool's name (``Error executing tool X: ``)."""
    return message.split(": ", 1)[1]


def refuses(call: Callable[[], Any]) -> str:
    try:
        call()
    except ToolError as exc:
        return str(exc)
    raise Failed("expected the tool to refuse")


def scope_count(db: Path, iwp_key: str) -> int:
    with open_uow(as_target(str(db)), readonly=True) as uow:
        return len(iwp_views.iwp_scope(uow.conn(), SCOPE, iwp_key) or [])


def seed_readiness(db: Path, i1: str, i2: str, i3: str) -> None:
    """Readiness rows for i1 (blocked, refs i2 and the hidden i3) and i3 (blocked, ref i1)."""
    with open_uow(as_target(str(db))) as uow:
        conn = uow.conn()
        for table in (READINESS_TABLE, READINESS_CHECK_TABLE):
            for statement in ddl_for(table, "sqlite"):
                conn.execute(text(statement))
        for n, (iwp, refs) in enumerate([(i1, [i2, i3]), (i3, [i1])]):
            conn.execute(
                text(
                    f"INSERT INTO {READINESS_TABLE} (iwp_id, scope, evaluated_at, today, ready, "
                    "facts_hash, as_of_seq) VALUES (:i, :s, 't', 'd', 0, :h, 1)"
                ),
                {"i": iwp, "s": SCOPE, "h": HIDDEN_TOKEN},
            )
            conn.execute(
                text(
                    f"INSERT INTO {READINESS_CHECK_TABLE} (row_id, scope, iwp_id, name, version, "
                    "state, detail, count_ok, count_total, resolve_via_json, as_of_seq) VALUES "
                    "(:r, :s, :i, 'constraints_cleared', '1', 'blocked', 'x', 1, 3, :v, 1)"
                ),
                {
                    "r": f"row{n}",
                    "s": SCOPE,
                    "i": iwp,
                    "v": json.dumps(
                        [{"record_id": r, "record_type": "awp.IWP", "key": r} for r in refs]
                    ),
                },
            )


def accept(db: Path, proposal_id: str) -> Any:
    with open_uow(as_target(str(db))) as uow:
        return proposals.accept_proposal(
            uow,
            proposal_id=proposal_id,
            by="user:uma",
            holds=lambda level: level == "user",
            holder=holder_for_actor(uow.conn(), "user:uma"),
        )


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="t09b-"))
    seed_db = work / "t09b.db"
    w, ctx = t.build(seed_db)
    ids = t.seed(w, ctx)
    t.classed(w, {ids["i3"], ids["cwp"]})
    seed_readiness(seed_db, ids["i1"], ids["i2"], ids["i3"])
    extra = w.items(["4.0", "4.0"])  # unscoped items, for the scope proposal
    extra_keys = [w.column("cur_core_record", "key", item) for item in extra]
    i1_key = w.column("cur_core_record", "key", ids["i1"])
    i2_key = w.column("cur_core_record", "key", ids["i2"])
    i3_key = w.column("cur_core_record", "key", ids["i3"])

    db = work / "mcp.db"
    shutil.copy(seed_db, db)
    target = as_target(str(db))
    reader = build_server(make_uow_factory(target), actor=READER, lake_dir=work / "lake")
    agent = build_server(make_uow_factory(target), actor=LOW_AGENT, lake_dir=work / "lake")

    def call(server: Any, tool: str, **arguments: Any) -> Any:
        result = asyncio.run(server.call_tool(tool, arguments))
        assert result.structured_content is not None
        return result.structured_content

    def rows(body: Any) -> list[Any]:
        return body["result"] if isinstance(body, dict) and "result" in body else body

    seen: list[str] = []  # every read result body, for the no-ids check

    # --- the four reads --------------------------------------------------------------------
    iwps = call(reader, "list_iwps", project=PROJECT)
    numbers = [row["number"] for row in rows(iwps)]
    seen.append(json.dumps(iwps))
    need(i3_key not in numbers and len(numbers) == 2, f"list_iwps shows {numbers}")
    passed(f"list_iwps {len(numbers)}")

    detail = call(reader, "get_iwp", project=PROJECT, number=i1_key)
    need(detail["number"] == i1_key and "scope_by_type" in detail, "get_iwp shape")
    seen.append(json.dumps(detail))
    passed(f"get_iwp {i1_key}")

    scope = call(reader, "list_iwp_scope", project=PROJECT, number=i1_key)
    scope_rows = rows(scope)
    need(len(scope_rows) > 0, "list_iwp_scope empty")
    seen.append(json.dumps(scope))
    passed(f"list_iwp_scope {len(scope_rows)}")

    readiness = call(reader, "get_iwp_readiness", project=PROJECT, number=i1_key)
    need(readiness["ready"] is False and len(readiness["checks"]) == 1, "readiness shape")
    seen.append(json.dumps(readiness))
    passed(f"get_iwp_readiness checks {len(readiness['checks'])}")

    # --- hidden looks like missing -----------------------------------------------------------
    hidden_iwp = refuses(lambda: call(reader, "get_iwp", project=PROJECT, number=i3_key))
    missing_iwp = refuses(lambda: call(reader, "get_iwp", project=PROJECT, number=MADE_UP_IWP))
    hidden_scope = refuses(lambda: call(reader, "list_iwp_scope", project=PROJECT, number=i3_key))
    hidden_ready = refuses(
        lambda: call(reader, "get_iwp_readiness", project=PROJECT, number=i3_key)
    )
    missing_ready = refuses(
        lambda: call(reader, "get_iwp_readiness", project=PROJECT, number=MADE_UP_IWP)
    )
    need(
        tail(hidden_iwp).replace(i3_key, "KEY") == tail(missing_iwp).replace(MADE_UP_IWP, "KEY"),
        "iwp",
    )
    need(
        tail(hidden_scope).replace(i3_key, "KEY") == tail(missing_iwp).replace(MADE_UP_IWP, "KEY"),
        "scope",
    )
    need(
        tail(hidden_ready).replace(i3_key, "KEY")
        == tail(missing_ready).replace(MADE_UP_IWP, "KEY"),
        "ready",
    )
    passed("hidden (IWP, scope, readiness) answers the same error as missing")

    # --- no ids, no facts hash -----------------------------------------------------------------
    body = "\n".join(seen)
    need(HIDDEN_TOKEN not in body and "facts_hash" not in body, "facts hash in a read")
    need(HEX32.search(body) is None, f"a 32-hex id: {HEX32.search(body)}")
    need(i3_key not in json.dumps(readiness) and ids["i3"] not in body, "hidden ref in readiness")
    passed("no-ids (no facts_hash, no 32-hex id, hidden refs absent from readiness)")

    # --- propose: pending, nothing written, accepted by a person ---------------------------
    scope_before = scope_count(db, i2_key)
    made_scope = call(
        agent,
        "propose_iwp_scope",
        project=PROJECT,
        iwp=i2_key,
        items=extra_keys,
    )
    scope_proposal = made_scope["proposal"]
    need(scope_proposal["status"] == "pending", f"scope status {scope_proposal['status']}")
    need(scope_count(db, i2_key) == scope_before, "scope moved")
    accepted_scope = accept(db, scope_proposal["proposal_id"])
    need(accepted_scope.status == "accepted", f"scope accepted {accepted_scope.status}")
    need(
        scope_count(db, i2_key) == scope_before + len(extra_keys),
        "accepting did not add the scope items",
    )
    passed("propose_iwp_scope (pending, nothing until accepted, then the items are scoped)")

    # --- closed: the five words, and an action not listed is refused ---------------------------
    need(len(IWP_MCP_ACTIONS) == 5 and IWP_MCP_ACTIONS <= MCP_ACTIONS, "action words")
    passed("closed (the five words are in MCP_ACTIONS)")

    allowed_but_iwp = frozenset(MCP_ACTIONS - IWP_MCP_ACTIONS)

    def closed_hook(actor: str, action: str, resource: str) -> None:
        if action not in allowed_but_iwp:
            raise ForbiddenError(f"{action} is not listed for agents")

    closed = build_server(
        make_uow_factory(target),
        actor=LOW_AGENT,
        authorize_hook=closed_hook,
        lake_dir=work / "lake",
    )
    message = refuses(lambda: call(closed, "list_iwps", project=PROJECT))
    need("not listed" in message, message)
    passed("closed (a tool whose word is not listed is refused)")


if __name__ == "__main__":
    try:
        main()
        print("T09b ok")
    except Failed as exc:
        print(f"FAIL {exc}")
        sys.exit(1)
