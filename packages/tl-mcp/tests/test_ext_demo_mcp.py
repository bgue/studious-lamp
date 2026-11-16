"""`ext_demo`, a module no platform file names, adds an agent tool (P2-X4 S5).

The fixture module lives in `tests/ext_demo/` and is added with `use_modules`. The tool is listed
after `build_server`, closed until `mcp.ext_demo_get_note` is allowed, and then opens only that
tool. An agent reads as the lowest clearance, so a hidden note answers as a missing one.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp_harness import SCOPE, McpHarness
from tl_adapters.db import create_schema
from tl_api.auth import Forbidden
from tl_core.modules import load_modules, use_modules

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests" / "ext_demo"))

from load import ext_demo_spec  # noqa: E402  # pyright: ignore[reportMissingImports]

TOOL = "ext_demo_get_note"
OPEN, HIDDEN, MISSING = "N-OPEN", "N-HIDDEN", "N-NONE"
OPEN_TEXT, HIDDEN_TEXT = "words anyone may read", "words only a clearance may read"
NOT_FOUND = "no such note"


def seed_note(env: McpHarness, key: str, body: str, note_class: str) -> None:
    from tl_mod_ext_demo.commands import ExtDemoAddNote, handle_add_note  # pyright: ignore

    with env.factory(False) as uow:
        handle_add_note(
            uow,
            ExtDemoAddNote(
                actor="user:seed",
                source="test",
                scope=SCOPE,
                key=key,
                title=f"Note {key}",
                body=body,
                note_class=note_class,  # pyright: ignore[reportArgumentType]
            ),
        )


class Rig:
    """The server over a ledger with two notes; ``allowed`` holds the actions the hook opens."""

    def __init__(self, env: McpHarness, allowed: set[str]) -> None:
        self.env = env
        self.allowed = allowed

    def names(self) -> set[str]:
        return {t.name for t in asyncio.run(self.env.server.list_tools())}

    def get(self, key: str) -> dict[str, object]:
        return self.env.structured(TOOL, scope=SCOPE, key=key)


@pytest.fixture
def rig(
    new_db: Callable[[], str | Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[Rig]:
    """An MCP server with ``ext_demo`` added (SQLite, and Postgres under --adapters)."""
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    allowed: set[str] = set()

    def authorizer(actor: str, action: str, resource: str) -> None:
        if action not in allowed:
            raise Forbidden("closed")

    with use_modules([*load_modules(), ext_demo_spec()]):
        target = new_db()
        create_schema(target)
        env = McpHarness.build(tmp_path, authorize_hook=authorizer, target=target)
        try:
            seed_note(env, OPEN, OPEN_TEXT, "internal")
            seed_note(env, HIDDEN, HIDDEN_TEXT, "restricted")
            yield Rig(env, allowed)
        finally:
            env.close()


def test_the_tool_is_listed_after_build_server(rig: Rig) -> None:
    assert TOOL in rig.names()


def test_the_tool_is_closed_until_its_action_is_allowed_and_then_only_it_opens(rig: Rig) -> None:
    with pytest.raises(ToolError, match="not allowed"):
        rig.get(OPEN)
    rig.allowed.add(f"mcp.{TOOL}")
    assert rig.get(OPEN)["body"] == OPEN_TEXT
    # the allow row names one tool: a core tool of the same server is still closed
    with pytest.raises(ToolError, match="not allowed"):
        rig.env.call("get_record", record=OPEN, scope=SCOPE)


def test_a_hidden_note_answers_an_agent_as_a_missing_one(rig: Rig) -> None:
    rig.allowed.add(f"mcp.{TOOL}")
    answers: list[str] = []
    for key in (HIDDEN, MISSING):
        with pytest.raises(ToolError) as caught:
            rig.get(key)
        answers.append(str(caught.value))
    assert answers[0] == answers[1] and NOT_FOUND in answers[0]
    assert HIDDEN_TEXT not in answers[0] and HIDDEN not in answers[0]
    assert rig.get(OPEN)["title"] == f"Note {OPEN}"
