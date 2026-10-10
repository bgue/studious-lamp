"""Driver for dev/demos/P0-I8-B.sh: the MCP tools and the TUI's embedded client on the demo ledger.

    python dev/demos/p0_i8_b_demo.py mcp        # an agent reads the types and a body over MCP
    python dev/demos/p0_i8_b_demo.py tui-edit   # the embedded TUI client edits a body
    python dev/demos/p0_i8_b_demo.py tamper     # overwrite the stored object of LP-1 with junk

Reads TL_DB and the object store variables (TL_OBJECT_ROOT, TL_OBJECT_SECRET). Asserts every
expectation, so a failing demo exits non-zero.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from mcp_types import CallToolResult
from tl_adapters.objectstore import make_object_store
from tl_adapters.sqlite.factory import SqliteUowFactory
from tl_core.extypes import body as bodies
from tl_mcp.server import build_server
from tl_tui.embedded import EmbeddedClient

DB = os.environ["TL_DB"]
SCOPE = "project:P123"
LIFT_REF = "co.acme.LiftPlan@1.0.0"


def say(text: str) -> None:
    print(f"   {text}")


def factory() -> SqliteUowFactory:
    return SqliteUowFactory(DB)


def mcp_call(tool: str, **arguments: Any) -> dict[str, Any]:
    server = build_server(
        factory(),
        actor="agent:triage",
        lake_dir=Path(tempfile.mkdtemp()),
        object_store=make_object_store(),
    )
    result = asyncio.run(server.call_tool(tool, arguments))
    assert isinstance(result, CallToolResult) and not result.is_error, result
    assert result.structured_content is not None
    return dict(result.structured_content)


def mcp() -> None:
    types = mcp_call("list_record_types")["result"]
    refs = sorted(t["type_ref"] for t in types)
    say(f"list_record_types -> {', '.join(refs)}")
    assert LIFT_REF in refs
    detail = mcp_call("get_record_type", type_ref=LIFT_REF)
    fields = [f["name"] for g in detail["form"]["groups"] for f in g["fields"]]
    say(f"get_record_type -> form fields {', '.join(fields)}")
    assert "crane" in fields and "risk_class" in fields
    view = mcp_call("get_record_body", record="LP-1", scope=SCOPE)
    crane, digest = view["body"]["crane"], view["pointer"]["hash"][:12]
    say(f"get_record_body LP-1 -> crane {crane}, hash {digest}")
    assert view["body"]["crane"] == "CR-12"


def tui_edit() -> None:
    client = EmbeddedClient(factory(), object_store=make_object_store())
    record = client.get_record(SCOPE, "LP-1")
    assert record is not None
    before = client.get_record_body(record["id"]).body
    after = {**before, "risk_class": "high", "load_tonnes": 51.0}
    stored = client.put_record_body(
        record["id"], scope=SCOPE, body=after, expected_version=int(record["version"])
    )
    say(
        f"the TUI client stored version {stored.version}: risk_class {before['risk_class']} -> high"
    )
    row = client.get_record(SCOPE, "LP-1")
    assert row is not None and row["psets"]["co_acme_lift_plan"]["risk_class"] == "high"
    say("the index field in the ledger followed: psets.co_acme_lift_plan.risk_class = high")


def tamper() -> None:
    client = EmbeddedClient(factory(), object_store=make_object_store())
    record = client.get_record(SCOPE, "LP-1")
    assert record is not None
    with factory()(True) as uow:
        pointer = bodies.body_pointer(uow.conn(), record["id"])
    assert pointer is not None
    path = make_object_store().path_for(pointer.uri)  # type: ignore[attr-defined]
    path.write_bytes(b'{"crane": "tampered"}')
    say(f"overwrote {pointer.uri} with bytes that do not match its hash")


if __name__ == "__main__":
    {"mcp": mcp, "tui-edit": tui_edit, "tamper": tamper}[sys.argv[1]]()
