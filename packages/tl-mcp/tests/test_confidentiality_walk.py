"""ADR-0016 at the MCP edge: every read tool, called with the names and ids of hidden records.

The ledger holds one item of each class (see ``tl_mod_correspondence.confseed``), a restricted
document, and the threads, clocks, files, links and posts that hang on them. Every read tool is
called with every combination of those names and ids as an agent and as a person; a reply may hold
the text and ids of internal records only, and a reply that repeats an id the caller sent must be
the reply for an id that names nothing. A count assertion proves the walk found the tools
(L-P1-I3-11); a tool that needs an argument the walk cannot fill fails the test, so a new tool
cannot be added unwalked.
"""

from __future__ import annotations

import asyncio
import itertools
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp_harness import SCOPE, McpHarness
from tl_adapters.db import DbTarget
from tl_adapters.objectstore.fs import FsObjectStore
from tl_core.files.service import FileService
from tl_mcp.server import build_server
from tl_mod_correspondence.confseed import TOKENS, Hidden, seed_hidden_world
from tl_mod_legacy.testing import seed_restricted_run

FAKE_ID = "01J000000000000000000000"
#: Tools that change nothing and are not walked here, and why (the proposing tools are tested in
#: test_mcp_write_tools and the correspondence tests; lake_query has its own lake test).
NOT_WALKED = {
    "lake_query": "tests/confidentiality/test_paths.py::test_the_lake",
}
MIN_TOOLS = 20


def values(hidden: Hidden) -> dict[str, list[Any]]:
    all_ids = [*hidden.ids.values(), *hidden.extra_ids.values()]
    return {
        "project": ["P123"],
        "scope": [SCOPE],
        "number": [*hidden.numbers.values(), "P123-THR-0001"],
        "record": [*all_ids, *hidden.numbers.values()],
        "record_id": all_ids,
        "derived": ["x"],
        "type_ref": ["x"],
        "code_list": ["x"],
        "from_code": ["A"],
        "to_code": ["B"],
        "q": ["", *TOKENS.values()],
        "schedule": ["MAIN", "x"],
        "activity_id": ["x"],
        "code": ["MER", "x"],
    }


def text_of(server: Any, tool: str, args: dict[str, Any]) -> str:
    try:
        result = asyncio.run(server.call_tool(tool, args))
    except ToolError as exc:
        return f"ERROR {exc}"
    return result.model_dump_json() if hasattr(result, "model_dump_json") else str(result)


@pytest.fixture
def world(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db: DbTarget
) -> Iterator[tuple[McpHarness, Hidden, FileService]]:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    store = FsObjectStore(tmp_path / "objects", secret=b"k")
    service = FileService(store, secret=b"s")
    env = McpHarness.build(tmp_path, object_store=store, files=service, target=db)
    hidden = seed_hidden_world(env.db, service, tmp_path)
    run_id, run_files = seed_restricted_run(env.db, service)
    hidden.ids["loadrun"] = run_id
    hidden.extra_ids.update({f"loadrun_{slot}_file": fid for slot, fid in run_files.items()})
    yield env, hidden, service
    env.close()


@pytest.mark.parametrize("actor", ["agent:triage", "user:bob"])
def test_no_read_tool_shows_what_the_actor_may_not_read(
    world: tuple[McpHarness, Hidden, FileService], actor: str, tmp_path: Path
) -> None:
    env, hidden, _ = world
    server = build_server(env.factory, actor=actor, lake_dir=tmp_path / "lake")
    tools = {t.name: t for t in asyncio.run(server.list_tools())}
    reading = {
        name: t
        for name, t in tools.items()
        if t.annotations is not None and t.annotations.read_only_hint
    }
    assert len(reading) >= MIN_TOOLS
    assert {"list_correspondence", "get_correspondence", "get_record", "list_documents"} <= set(
        reading
    )
    assert set(NOT_WALKED) <= set(reading)
    cands = values(hidden)
    bad_tokens = [t for k, t in TOKENS.items() if k != "open"]
    bad_ids = [
        v
        for k, v in {**hidden.ids, **hidden.extra_ids}.items()
        if not k.startswith(("open", "transmittal"))
    ]
    bad_ids += [hidden.ids["document"]]
    calls = 0
    for name, tool in sorted(reading.items()):
        if name in NOT_WALKED:
            continue
        props = list(tool.input_schema.get("properties", {}))
        required = tool.input_schema.get("required") or []
        for param in required:
            assert param in cands, f"{name}: add values for the argument {param!r}"
        names = [p for p in props if p in cands]
        for combo in itertools.islice(itertools.product(*(cands[p] for p in names)), 80):
            args = dict(zip(names, combo, strict=True))
            if "q" in args and args["q"] == "":
                args.pop("q")
            reply = text_of(server, name, args)
            calls += 1
            assert "internal error" not in reply.lower(), (name, args, reply[:200])
            for marker in [*bad_tokens, *bad_ids]:
                if marker not in reply:
                    continue
                asked = repr(args)
                assert marker in asked, (actor, name, args, marker)
                fake = FAKE_ID if marker in bad_ids else "NOSUCHTOKEN"
                fake_args = {
                    k: (v.replace(marker, fake) if isinstance(v, str) else v)
                    for k, v in args.items()
                }
                other = text_of(server, name, fake_args)
                assert reply.replace(marker, fake) == other, (actor, name, args, marker)
    assert calls > 100  # the walk really made the calls
    # and what the actor may read is there, so the check can fail
    seen = text_of(server, "list_correspondence", {"project": "P123"})
    assert hidden.numbers["open"] in seen and TOKENS["restricted"] not in seen
    assert hidden.numbers["restricted"] not in seen and hidden.numbers["privileged"] not in seen
    assert hidden.numbers["bogus"] not in seen


def resource_text(server: Any, uri: str) -> str:
    try:
        result = asyncio.run(server.read_resource(uri))
    except Exception as exc:  # a refusal is an answer, and it must not depend on the record
        return f"ERROR {type(exc).__name__}: {exc}"
    return "".join(str(getattr(part, "content", part)) for part in result)


@pytest.mark.parametrize("actor", ["agent:triage", "user:bob"])
def test_no_resource_shows_what_the_actor_may_not_read(
    world: tuple[McpHarness, Hidden, FileService], actor: str, tmp_path: Path
) -> None:
    env, hidden, _ = world
    server = build_server(env.factory, actor=actor, lake_dir=tmp_path / "lake")
    templates = asyncio.run(server.list_resource_templates())
    fixed = asyncio.run(server.list_resources())
    assert {"tl://record/{scope}/{key}"} <= {str(t.uri_template) for t in templates}
    assert len(templates) + len(fixed) >= 4  # the walk found the resources (L-P1-I3-11)
    bad_tokens = [t for k, t in TOKENS.items() if k != "open"]
    bad_ids = [
        v
        for k, v in {**hidden.ids, **hidden.extra_ids}.items()
        if not k.startswith(("open", "transmittal"))
    ]
    keys = [*hidden.numbers.values(), *hidden.ids.values(), FAKE_ID]
    bad_ids = [i for i in bad_ids if i not in (hidden.ids["open"], hidden.ids["open_document"])]
    uris = [str(r.uri) for r in fixed]
    for template in templates:
        text = str(template.uri_template)
        if "{key}" in text:
            uris += [text.replace("{scope}", "project:P123").replace("{key}", k) for k in keys]
        elif "{record_type}" in text:
            uris += [
                text.replace("{scope}", "project:P123").replace("{record_type}", "x") for _ in (0,)
            ]
        elif "{type_ref}" in text:
            uris.append(text.replace("{type_ref}", "x"))
    calls = 0
    for uri in uris:
        reply = resource_text(server, uri)
        calls += 1
        for marker in [
            *bad_tokens,
            *bad_ids,
            *[
                hidden.numbers[k]
                for k in (
                    "restricted",
                    "privileged",
                    "bogus",
                    "document",
                    "commercial",
                    "secret_rfi",
                )
            ],
        ]:
            if marker not in reply:
                continue
            assert marker in uri, (actor, uri, marker)
            fake = FAKE_ID
            other = resource_text(server, uri.replace(marker, fake))
            assert reply.replace(marker, fake) == other, (actor, uri, marker)
    assert calls >= 8
    seen = resource_text(server, f"tl://record/project:P123/{hidden.numbers['open']}")
    assert hidden.numbers["open"] in seen or "open" in seen.lower()
