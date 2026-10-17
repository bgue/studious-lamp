"""Driver for dev/demos/P1-I3.sh: the parts of the demo that are not a `tl` command.

Modes (first argument):

* ``prepare DIR``: write the files the script feeds to `tl derive`: the schema files for
  `schema register` (built from the fixtures in schema/fixtures/document-schemas), a real PDF with
  properties, and a CSV whose cell makes a catastrophic pattern run for ever.
* ``published``: clause 5. The tags a publication made carry the provenance and the link; a
  compensation takes them back and the ledger only grew.
* ``refused``: clause 6. A user, an agent and a client that poses as a publication cannot publish.
* ``propose``: clause 6. An agent proposes the import over MCP; nothing is created.
* ``reads``: clause 7. The API, the TUI screens (F11, jobs, publish preview) and an agent's MCP
  tools agree on a derived document.

Reads TL_DB (SQLite path or postgresql:// URL), TL_DEMO_URL (the API) and, per mode,
TL_DEMO_AMY_PASSWORD, TL_DEMO_AGENT_TOKEN, TL_OBJECT_ROOT. Every expectation is an assert: a
failing demo exits non-zero. Nothing printed holds a password or a token.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import sys
from pathlib import Path
from typing import Any

PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
DEMO = ("demo", "demo")  # the documented dev account (ADR-0009 section 9)
FIXTURES = Path("schema/fixtures/document-schemas")
INDEX_KEY = "ISD-001@A/instrument-index"
EQUIPMENT_KEY = "ISD-002@A/equipment-list"


def say(text: str) -> None:
    print(f"   {text}")


def passed(clause: int | str, text: str) -> None:
    print(f"PASS {clause}: {text}")


def register_file(code: str, columns: list[dict[str, Any]], key: str) -> dict[str, Any]:
    """A `tl derive schema register` file for a fixture schema, with its publish mapping."""
    schema = json.loads((FIXTURES / f"{code}@1.0.0.schema.json").read_text())
    meta = schema["x-throughline"]
    return {
        "code": code,
        "semver": meta["version"],
        "title": meta["title"],
        "description": schema.get("description"),
        "json_schema": schema,
        "key_column": key,
        "target_kind": "tags",
        "mapping": {"target": "tags", "key_column": key, "columns": columns},
    }


def prepare(directory: str) -> None:
    import yaml
    from pypdf import PdfWriter

    out = Path(directory)
    index = register_file(
        "instrument-index",
        [
            {"column": "tag_number", "to": "number"},
            {"column": "tag_class", "to": "class"},
            {"column": "service", "to": "service"},
        ],
        "tag_number",
    )
    equipment = register_file(
        "equipment-list",
        [
            {"column": "equipment_tag", "to": "number"},
            {"column": "equipment_class", "to": "class"},
            {"column": "description", "to": "service"},
        ],
        "equipment_tag",
    )
    hostile = {
        "code": "hostile-pattern",
        "semver": "1.0.0",
        "title": "A schema whose pattern never finishes",
        "json_schema": {
            "type": "object",
            "required": ["tag"],
            "properties": {"tag": {"type": "string", "pattern": "^(a+)+$"}},
        },
        "key_column": "tag",
    }
    for name, body in (
        ("instrument-index", index),
        ("equipment-list", equipment),
        ("hostile", hostile),
    ):
        (out / f"{name}.yaml").write_text(yaml.safe_dump(body, sort_keys=False), encoding="utf-8")
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=842, height=595)
    writer.add_metadata({"/Title": "Instrument index, unit 47", "/Author": "Acme Instrumentation"})
    buffer = io.BytesIO()
    writer.write(buffer)
    (out / "isd-001-A.pdf").write_bytes(buffer.getvalue())
    (out / "hostile.csv").write_text("tag\n" + "a" * 32 + "!\n", encoding="utf-8")
    (out / "fine.csv").write_text("tag\naaa\n", encoding="utf-8")
    say(f"wrote the schema files, a 3-page PDF and two small CSV files to {out}")


def rows(sql: str, **params: Any) -> list[dict[str, Any]]:
    from sqlalchemy import text
    from tl_adapters.db import open_uow

    with open_uow(os.environ["TL_DB"], readonly=True) as uow:
        return [dict(r) for r in uow.conn().execute(text(sql), params).mappings()]


def psets_of(row: dict[str, Any]) -> dict[str, Any]:
    raw = row["psets_json"]
    return json.loads(raw) if isinstance(raw, str) else dict(raw)


def published() -> None:
    wanted = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    phase = sys.argv[3] if len(sys.argv) > 3 else "after-publish"
    tags = rows(
        "SELECT r.id, r.key, r.status, r.psets_json FROM cur_core_record r "
        "JOIN cur_engineering_tag t ON t.id = r.id ORDER BY r.key"
    )
    links = rows("SELECT status FROM cur_links WHERE relation = 'derived_from'")
    events = rows("SELECT COUNT(*) AS n FROM events")[0]["n"]
    if phase == "after-publish":
        assert len(tags) == wanted, (len(tags), wanted)
        for tag in tags:
            assert psets_of(tag)["provenance"] == {
                "source": "src.doc.ISD-001@A",
                "derived_document": INDEX_KEY,
            }, tag["key"]
        assert [link["status"] for link in links] == ["active"] * wanted
        say(
            f"{wanted} tags, each with provenance.source = src.doc.ISD-001@A "
            "and a derived_from link"
        )
        Path(os.environ["TL_DEMO_STATE"]).write_text(str(events))
        passed(5, f"publishing created {wanted} tags with provenance and a `derived from` link")
    else:
        before = int(Path(os.environ["TL_DEMO_STATE"]).read_text())
        assert {t["status"] for t in tags} == {"Deleted"} and len(tags) == wanted
        assert {link["status"] for link in links} == {"retracted"}
        assert events > before, (events, before)
        started = rows("SELECT COUNT(*) AS n FROM events WHERE event_type = 'Record.Created'")[0][
            "n"
        ]
        say(
            f"{wanted} tags Deleted, {wanted} links retracted; "
            f"the ledger grew from {before} to {events} events"
        )
        assert started >= wanted  # the creation events are all still there
        passed(
            "5b",
            "compensation rolled the batch back by the ids it recorded; "
            "the originals stay in the ledger",
        )


def post(url: str, token: str, name: str, body: dict[str, Any]) -> tuple[int, str]:
    import httpx2

    response = httpx2.post(
        f"{url}/commands/{name}", json=body, headers={"Authorization": f"Bearer {token}"}
    )
    data = response.json()
    return response.status_code, ("ok" if response.status_code == 200 else str(data["error"]))


def refused() -> None:
    from tl_api.client import ApiClient
    from tl_api.client.auth import sign_in

    url = os.environ["TL_DEMO_URL"]
    amy = sign_in(url, "amy", os.environ["TL_DEMO_AMY_PASSWORD"]).token
    boss = sign_in(url, *DEMO).token
    agent = os.environ["TL_DEMO_AGENT_TOKEN"]
    api = ApiClient(url, boss)
    try:
        derived = api.get_derived_document(PROJECT, EQUIPMENT_KEY)
    finally:
        api.close()
    publish = {
        "scope": SCOPE,
        "derived_id": derived.id,
        "expected_content_rev": derived.content_rev,
    }
    for who, token, expect in (
        ("a user", amy, (403, "forbidden")),
        ("an agent", agent, (403, "agent_must_propose")),
    ):
        got = post(url, token, "PublishDerivedTags", publish)
        assert got == expect, (who, got)
        say(f"{who}: PublishDerivedTags refused ({got[0]} {got[1]})")
    for field, value in (
        ("correlation_id", "derive:01J9Z6Q4W3X2Y1V0T9S8R7Q6PB"),
        ("source", "import:derived-" + derived.id),
    ):
        got = post(
            url,
            amy,
            "CreateRecord",
            {"scope": SCOPE, "record_type": "core.Record", "title": "pose", field: value},
        )
        assert got == (422, "reserved_identifier"), (field, got)
        say(f"a client that sets {field} to a publication's value is refused ({got[0]} {got[1]})")
    api = ApiClient(url, boss)
    try:
        assert api.get_derived_document(PROJECT, EQUIPMENT_KEY).state == "Valid"
    finally:
        api.close()
    passed(6, "a user and an agent cannot publish, and no client can pose as a publication")


def agent_session(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
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

    async def session() -> dict[str, Any]:
        async with Client(params) as mcp:
            names = {t.name for t in (await mcp.list_tools()).tools}
            assert {"propose_import", "start_extraction", "get_derived_document"} <= names
            result = await mcp.call_tool(name, arguments)
            assert not result.is_error and result.structured_content is not None, result
            return result.structured_content

    return asyncio.run(session())


def propose() -> None:
    found = agent_session("propose_import", {"project": PROJECT, "derived": EQUIPMENT_KEY})
    proposal = found["proposal"]
    assert proposal["status"] == "pending" and proposal["tool"] == "propose_import_tags"
    tags = rows("SELECT COUNT(*) AS n FROM cur_core_record WHERE key LIKE '47-P-%'")[0]["n"]
    assert tags == 0, tags
    Path(os.environ["TL_DEMO_STATE"]).write_text(proposal["proposal_id"])
    say(f"the agent's proposal {proposal['proposal_id']} is pending; nothing was created")


async def screens(db: str) -> dict[str, Any]:
    from textual.widgets import DataTable
    from tl_adapters.objectstore import make_object_store, object_secret
    from tl_core.files.service import FileService
    from tl_mod_documents.derivation import store
    from tl_tui.app import TlApp
    from tl_tui.embedded import EmbeddedClient
    from tl_tui.widgets.derived_documents import DerivedDocumentsScreen
    from tl_tui.widgets.job_monitor import JobMonitorScreen
    from tl_tui.widgets.publish_preview import PublishPreviewScreen

    store.configure(FileService(make_object_store(), secret=object_secret()))
    client = EmbeddedClient.for_target(db, actor="user:demo")
    try:
        app = TlApp(client, scope=SCOPE, actor="user:demo", is_admin=True)
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.press("f11")
            await pilot.pause()
            derived = app.screen
            assert isinstance(derived, DerivedDocumentsScreen)
            keys = [v.key for v in derived.shown]
            assert INDEX_KEY in keys and EQUIPMENT_KEY in keys, keys
            derived.query_one("#dd-table", DataTable).move_cursor(row=keys.index(INDEX_KEY))
            await pilot.pause()
            assert derived.detail is not None
            seen = {"state": derived.detail.state, "rows": derived.detail.row_count}
            await pilot.press("j")
            await pilot.pause()
            assert isinstance(app.screen, JobMonitorScreen)
            seen["jobs"] = len(app.screen.shown)
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("p")
            await pilot.pause()
            assert isinstance(app.screen, PublishPreviewScreen)
            seen["plan"] = app.screen.plan.counts if app.screen.plan else None
            return seen
    finally:
        client.close()


def reads() -> None:
    from tl_api.client import ApiClient
    from tl_api.client.auth import sign_in

    db, url = os.environ["TL_DB"], os.environ["TL_DEMO_URL"]
    api = ApiClient(url, sign_in(url, *DEMO).token)
    try:
        listed = api.list_derived_documents(PROJECT)
        say(f"API: {len(listed)} derived documents: {', '.join(d.key for d in listed)}")
        view = api.get_derived_document(PROJECT, INDEX_KEY)
        report = api.get_derived_report(PROJECT, INDEX_KEY)
        jobs = api.list_processing_jobs(PROJECT, derived=INDEX_KEY)
        plan = api.get_publish_preview(PROJECT, INDEX_KEY)
    finally:
        api.close()
    shown = asyncio.run(screens(db))
    say(f"TUI (F11, jobs, publish preview): {shown}")
    assert shown["state"] == view.state and shown["rows"] == view.row_count
    assert shown["jobs"] == len(jobs)
    mcp = agent_session("get_derived_document", {"project": PROJECT, "derived": INDEX_KEY})
    assert mcp["state"] == view.state and mcp["row_count"] == view.row_count
    stored = agent_session("validate_against_schema", {"project": PROJECT, "derived": INDEX_KEY})
    assert stored["status"] == report.status and stored["rows_checked"] == report.rows_checked
    say(
        f"MCP: {mcp['key']} is {mcp['state']} with {mcp['row_count']} rows; "
        f"stored report {stored['status']}"
    )
    assert plan.target == "tags"
    passed(7, "the API, the TUI screens and an agent's MCP tools show the same derived document")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "prepare":
        prepare(sys.argv[2])
    elif mode == "published":
        published()
    elif mode == "refused":
        refused()
    elif mode == "propose":
        propose()
    elif mode == "reads":
        reads()
    else:
        raise SystemExit(f"unknown mode {mode!r}")


if __name__ == "__main__":
    main()
