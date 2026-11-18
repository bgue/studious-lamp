"""V3-F2 walk: the forms MCP tools as five kinds of reader, byte for byte.

Readers: an agent (``agent:triage``) and four people (``uma`` author, ``rob``, ``dora`` document
controller, ``ada`` admin) each get a server of their own. An MCP tool reads at the lowest clearance
(``guarded``), so every reader gets the same answer. A hidden submission (privileged class, or a
restricted subject), a draft and a key that never existed answer with the one error text, byte for
byte; lists and counts leave them out; a draft is read by no tool, by its id either. A proposal for
an unpublished or unknown template or a hidden or unknown record is refused like a missing one.
Nothing in the tool results carries a hidden key, id or answer text.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import CallToolResult

_ROOT = Path(__file__).resolve().parents[2]
for _extra in (
    _ROOT / "packages/tl-mcp/tests",
    _ROOT / "packages/tl-modules/forms/tests",
):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from forms_world import World, answer, two_fields  # noqa: E402
from mcp_harness import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    McpHarness,
    grant_filing,
)
from sqlalchemy import text  # noqa: E402
from tl_adapters.db import open_uow  # noqa: E402
from tl_mcp.server import build_server  # noqa: E402

PROJECT = "P123"
MISSING = "P123-FRM-9999"
FAKE_ULID = "01J000000000000000000000"
READERS = ("agent:triage", "user:uma", "user:rob", "user:dora", "user:ada")
SECRET_TEXT = "zq-secret-answer-5521"


class Rig:
    def __init__(self, env: McpHarness, world: World) -> None:
        self.env = env
        self.world = world
        self.keys: dict[str, str] = {}
        self.ids: dict[str, str] = {}

    def call(self, actor: str, tool: str, **arguments: Any) -> tuple[bool, str]:
        """``(ok, bytes)`` of one call: the result's JSON, or the refusal text."""
        server = build_server(self.env.factory, actor=actor)
        try:
            result = asyncio.run(server.call_tool(tool, arguments))
        except ToolError as exc:
            return False, str(exc)
        assert isinstance(result, CallToolResult)
        return not result.is_error, json.dumps(result.structured_content, sort_keys=True)

    def ok(self, actor: str, tool: str, **arguments: Any) -> Any:
        good, body = self.call(actor, tool, **arguments)
        assert good, body
        return json.loads(body)


@pytest.fixture(scope="module")
def rig(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Rig]:
    env = McpHarness.build(tmp_path_factory.mktemp("forms-mcp-walk"))
    world = World(env.db)
    world.people()
    with env.factory(False) as uow:
        grant_filing(uow, "triage")
    r = Rig(env, world)
    plain = world.template(fields=two_fields())
    secret = world.template(fields=two_fields(), answer_class="privileged")
    unpublished = world.template(publish=False, fields=two_fields())
    r.ids.update(plain=plain, secret=secret, unpublished=unpublished)
    r.keys["open"] = str(world.submit("uma", plain).key)
    r.keys["secret"] = str(world.submit("uma", secret, answers=[answer("topic", SECRET_TEXT)]).key)
    r.ids["draft"] = str(world.save("uma", plain).stream_id)
    r.ids["hidden_record"] = world.hidden_record("restricted")
    r.keys["hidden_record"] = str(world.key(r.ids["hidden_record"]))
    r.keys["via_subject"] = str(world.submit("dora", plain, subject_id=r.ids["hidden_record"]).key)
    r.keys["template"] = str(world.key(plain))
    r.keys["unpublished"] = str(world.key(unpublished))
    yield r
    env.close()


def test_a_hidden_submission_a_draft_and_a_missing_key_answer_alike(rig: Rig) -> None:
    for reader in READERS:
        ok, missing = rig.call(reader, "get_form_submission", project=PROJECT, key=MISSING)
        assert not ok
        for ref in (
            rig.keys["secret"],
            rig.keys["via_subject"],
            rig.ids["draft"],
            FAKE_ULID,
        ):
            got = rig.call(reader, "get_form_submission", project=PROJECT, key=ref)
            assert got == (False, missing), (reader, ref)
        assert MISSING not in missing and rig.keys["secret"] not in missing


def test_lists_and_counts_leave_them_out_for_every_reader(rig: Rig) -> None:
    for reader in READERS:
        listed = rig.ok(reader, "list_form_submissions", project=PROJECT)
        assert [r["key"] for r in listed["rows"]] == [rig.keys["open"]]
        assert listed["total"] == 1
        drafts = rig.ok(reader, "list_form_submissions", project=PROJECT, state="Submitted")
        assert drafts["total"] == 1
        every = json.dumps(listed)
        for hidden in (rig.keys["secret"], rig.keys["via_subject"], rig.ids["draft"]):
            assert hidden not in every


def test_the_open_submission_reads_with_its_answers_and_no_hidden_text(rig: Rig) -> None:
    for reader in READERS:
        got = rig.ok(reader, "get_form_submission", project=PROJECT, key=rig.keys["open"])
        assert got["row"]["key"] == rig.keys["open"]
        assert got["answers"][0]["value"] == "Ladders"
        assert SECRET_TEXT not in json.dumps(got)


def test_no_draft_is_read_by_its_id_or_listed_as_a_state(rig: Rig) -> None:
    for reader in READERS:
        ok, _ = rig.call(reader, "get_form_submission", project=PROJECT, key=rig.ids["draft"])
        assert not ok
        ok, _ = rig.call(reader, "list_form_submissions", project=PROJECT, state="Draft")
        assert not ok  # no such state for an agent's list


def test_templates_list_and_read_the_published_only_the_same_for_every_reader(rig: Rig) -> None:
    seen: set[str] = set()
    for reader in READERS:
        listed = rig.ok(reader, "list_form_templates")
        assert listed["total"] == 2
        seen.add(json.dumps(listed, sort_keys=True))
        schema = rig.ok(reader, "get_form", key=rig.keys["template"])
        assert schema["type"] == "array"  # the answers: one {q, value, note} each
        assert rig.keys["unpublished"] not in json.dumps(listed)
        _, unknown = rig.call(reader, "get_form", key="TPL-9999")
        assert rig.call(reader, "get_form", key=rig.keys["unpublished"]) == (False, unknown)
    assert len(seen) == 1


def _proposals(rig: Rig) -> int:
    with open_uow(rig.env.db, readonly=True) as uow:
        return int(uow.conn().execute(text("SELECT count(*) FROM cur_proposals")).scalar_one())


def test_a_proposal_for_a_hidden_or_missing_template_or_record_is_one_refusal(rig: Rig) -> None:
    before = _proposals(rig)
    answers = [answer("topic", "Ladders")]
    for reader in READERS:
        _, no_template = rig.call(
            reader, "propose_form_submission", project=PROJECT, template_key="TPL-9999",
            answers=answers,
        )  # fmt: skip
        got = rig.call(
            reader, "propose_form_submission", project=PROJECT,
            template_key=rig.keys["unpublished"], answers=answers,
        )  # fmt: skip
        assert got == (False, no_template)
        _, no_record = rig.call(
            reader, "propose_form_submission", project=PROJECT, template_key=rig.keys["template"],
            answers=answers, subject_key="P123-NOPE-0001",
        )  # fmt: skip
        got = rig.call(
            reader, "propose_form_submission", project=PROJECT, template_key=rig.keys["template"],
            answers=answers, subject_key=rig.keys["hidden_record"],
        )  # fmt: skip
        assert got == (False, no_record)
        assert rig.keys["hidden_record"] not in no_record
    assert _proposals(rig) == before
