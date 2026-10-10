"""The real subprocess path of ``McpClientCaller``: a server process, a missing ledger, a hang."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from mcp import StdioServerParameters
from tl_adapters.sqlite.uow import create_schema
from tl_sim.mcp_caller import (
    McpClientCaller,
    McpUnavailableError,
    ProposalRefusedError,
    stdio_caller,
)
from tl_sim.state import RunError

ASSISTANT = "agent:sim-assistant"


def test_stdio_caller_starts_the_server_on_a_ledger_and_returns_a_tool_result(
    tmp_path: Path,
) -> None:
    db = tmp_path / "tl.db"
    create_schema(db)
    caller = stdio_caller(ASSISTANT, db)
    result = caller.call_tool("search_records", {"scope": "project:sim-r1"})
    assert result["total"] == 0 and result["records"] == []


def test_a_proposal_over_the_real_process_is_pending_and_a_bad_record_is_a_refusal(
    tmp_path: Path,
) -> None:
    db = tmp_path / "tl.db"
    create_schema(db)
    caller = stdio_caller(ASSISTANT, db)
    with pytest.raises(ProposalRefusedError) as raised:
        caller.call_tool(
            "link_records",
            {"scope": "project:sim-r1", "from_record": "NOPE-1", "to_record": "NOPE-2"},
        )
    assert "no record" in str(raised.value) and not raised.value.is_duplicate_link


def test_a_missing_ledger_is_one_run_error_that_carries_the_servers_own_words(
    tmp_path: Path,
) -> None:
    caller = stdio_caller(ASSISTANT, tmp_path / "missing" / "tl.db")
    with pytest.raises(McpUnavailableError) as raised:
        caller.call_tool("search_records", {"scope": "project:sim-r1"})
    assert isinstance(raised.value, RunError)
    assert "cannot reach the MCP server" in str(raised.value)
    assert "no ledger at" in str(raised.value) and "run `uv run tl init` first" in str(raised.value)


def test_a_server_that_never_answers_times_out_instead_of_blocking_forever() -> None:
    hang = StdioServerParameters(
        command=sys.executable, args=["-c", "import sys; sys.stdin.read()"]
    )
    caller = McpClientCaller(hang, timeout_s=1.0)
    with pytest.raises(McpUnavailableError, match="did not answer search_records within 1 s"):
        caller.call_tool("search_records", {})


def test_a_command_that_does_not_exist_is_unavailable_not_a_traceback() -> None:
    gone = StdioServerParameters(command="/nonexistent/server", args=[])
    with pytest.raises(McpUnavailableError, match="cannot reach the MCP server"):
        McpClientCaller(gone, timeout_s=5.0).call_tool("search_records", {})


def test_only_a_duplicate_link_is_the_refusal_a_day_shrugs_off() -> None:
    dup = ProposalRefusedError(
        "Error executing tool link_records: a references link already exists between these "
        "records (active, 01ABC)"
    )
    assert dup.is_duplicate_link
    for text in ("agent:x has used its 500 proposals today", "no record 'K'", "scope: bad"):
        assert not ProposalRefusedError(text).is_duplicate_link
