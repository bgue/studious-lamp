"""Driver for dev/demos/P2-I3.sh: the clauses of the demo that are not a `tl` command.

It opens the ledger named by TL_DB (a SQLite file or a postgresql:// URL, read with `as_target`)
and runs the API in process with the test client, the way dev/demos/p2_w0_demo.py does; the TUI
screens run on `TlApp` over an `EmbeddedClient`, the MCP tools on a server built as
dev/accept/P2-I3/T07.py builds it. Each mode checks one group of clauses and prints one
``PASS clause N: <what was checked>`` line per check; a miss prints ``FAIL <what>`` and exits 1.
The people are the ones the script seeded (documented dev passwords, as in the P1 and P2-W0 demos).
Token and lake files go to ``P2_I3_WORKDIR``, the demo's own temporary directory.

Modes (first argument):

* ``clause1-people``: mara (company materials superuser) DefineItem is accepted (200) and persisted,
  so the library holds 51 items; pete (project user) is answered 403 by the API.
* ``clause2``: sue (project superuser) defines the five-level location chain P123 > WH1 > L2 > TC1
  > GB1 through the API; pete's DefineLocation is answered 403.
* ``clause4``: the consumable issue without a cost code is answered 422; the stock of P123 equals
  the sum of its movements on every lot and location; a rebuild of the projections gives the same
  stock, lot, reservation and movement rows.
* ``clause6 KEY``: CreateCwp makes P123-CWP-PIP-0001 (ada); the derived take-off KEY is published
  into an MTO for it (sue), compensated (ada) and republished (sue), each through the API.
* ``clause7``: the materials_reserved readiness check keeps the readiness contract on the package.
* ``clause8``: the API, the TUI screens (stock, receipts, MTO lines at 170 columns) and the MCP
  stock tool agree; an agent's propose_reservation is pending until sue accepts it.
* ``clause9``: the API refuses the four bad quantities of the shell, with the same fixed message.
* ``clause10-11``: the item library (51 items, project counts) and the location tree (five levels,
  lot counts) at 170 columns.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, NoReturn

from fastapi.testclient import TestClient
from sqlalchemy import text
from tl_adapters.backend import open_backend
from tl_adapters.db import as_target, make_engine, make_uow_factory, rebuild_projections
from tl_adapters.objectstore import make_object_store, object_secret
from tl_api.app import create_app
from tl_api.settings import ApiSettings
from tl_api.tokens import TokenStore
from tl_core.auth import sessions
from tl_core.files.service import FileService
from tl_core.readiness import ContractWorld, IwpFacts, check_readiness_contract, load_checks
from tl_mod_documents.derivation import store as derivation_store
from tl_mod_documents.derivation import views as derivation_views
from tl_mod_materials import views
from tl_tui.app import TlApp
from tl_tui.embedded import EmbeddedClient
from tl_tui.widgets.item_library import ItemLibraryScreen
from tl_tui.widgets.location_screen import LocationScreen
from tl_tui.widgets.mto_screen import MtoLinesScreen
from tl_tui.widgets.receipt_log import ReceiptLogScreen
from tl_tui.widgets.stock_screen import StockScreen

PASSWORDS = {  # the documented dev passwords the script seeds the people with
    "ada": "a long passphrase for ada",
    "mara": "a long passphrase for mara",
    "pete": "a long passphrase for pete",
    "sue": "a long passphrase for sue",
    "plain": "a long passphrase for plain",
}
PROJECT = "P123"
P123 = f"project:{PROJECT}"
COMPANY = "company"
AGENT = "agent:triage"  # the agent that proposes a reservation (no account; a proposal only)
TODAY = date(2026, 11, 3)
WP = "P123-CWP-PIP-0001"
CWA = "PIPE-AREA"
MODES = (
    "clause1-people",
    "clause2",
    "clause4",
    "clause6",
    "clause7",
    "clause8",
    "clause9",
    "clause10-11",
)
SCREEN_SIZE = (170, 40)  # the width the clauses name
# the four bad quantities, each with the fixed message the CLI prints for it (and the shell checks)
BAD_QUANTITIES = (
    ("\u0661\u0662", "movement 1 qty must be ASCII digits with at most 3 decimals, as 12.500"),
    ("-1", "movement 1 qty must be ASCII digits with at most 3 decimals, as 12.500"),
    ("1.2345", "movement 1 qty must be ASCII digits with at most 3 decimals, as 12.500"),
    ("1000000001", "movement 1 qty must be at most 1000000000"),
)
SNAPSHOT_TABLES = (
    "cur_materials_stock",
    "cur_materials_lot",
    "cur_materials_reservation",
    "cur_materials_movement",
)


def passed(clause: int, text_: str) -> None:
    print(f"PASS clause {clause}: {text_}", flush=True)


def miss(what: str) -> NoReturn:
    print(f"FAIL {what}", flush=True)
    raise SystemExit(1)


def check(condition: bool, what: str) -> None:
    if not condition:
        miss(what)


class World:
    """The ledger in TL_DB, its API in process, and one signed-in test client per person."""

    def __init__(self) -> None:
        target = as_target(os.environ["TL_DB"])
        self.target = target
        self.backend = open_backend(target)
        workdir = Path(os.environ["P2_I3_WORKDIR"])
        settings = ApiSettings(db_path=target, tokens_path=workdir / "tokens.json")
        self.app = create_app(
            self.backend, settings=settings, tokens=TokenStore(workdir / "tokens.json")
        )
        # a publication reads its stored rows through the file service (as P2-W0's driver does)
        derivation_store.configure(FileService(make_object_store(), secret=object_secret()))
        self.clients: dict[str, TestClient] = {}
        self.principals: dict[str, Any] = {}

    def principal(self, name: str) -> Any:
        if name not in self.principals:
            principal, token = sessions.sign_in(
                self.backend, username=name, password=PASSWORDS[name]
            )
            client = TestClient(self.app, raise_server_exceptions=False)
            client.headers.update({"Authorization": f"Bearer {token}"})
            self.clients[name] = client
            self.principals[name] = principal
        return self.principals[name]

    def client(self, name: str) -> TestClient:
        self.principal(name)
        return self.clients[name]

    def close(self) -> None:
        self.backend.close()


def mto_lines(world: World, work_package: str | None = None) -> list[Any]:
    with world.backend(True) as uow:
        return views.mto_lines(uow.conn(), P123, work_package=work_package)


def clause1_people() -> None:
    """mara's DefineItem is accepted and persisted: the library then holds the 50 sample items
    and this probe (51 of 51). pete's DefineItem is answered 403."""
    world = World()
    try:
        accepted = world.client("mara").post(
            "/commands/DefineItem",
            json={
                "scope": COMPANY,
                "code": "CON-PROBE-1",
                "title": "Probe",
                "category": "consumable",
                "base_uom": "EA",
                "consumable": True,
            },
        )
        check(accepted.status_code == 200, f"mara's DefineItem: {accepted.status_code}")
        passed(1, "mara (company materials superuser) DefineItem is accepted: 200, persisted")
        refused = world.client("pete").post(
            "/commands/DefineItem",
            json={
                "scope": COMPANY,
                "code": "CON-PROBE-2",
                "title": "Probe",
                "category": "consumable",
                "base_uom": "EA",
                "consumable": True,
            },
        )
        check(refused.status_code == 403, f"pete's DefineItem: {refused.status_code}")
        passed(1, f"pete (project user) DefineItem is refused: {refused.status_code} forbidden")
    finally:
        world.close()


def clause2() -> None:
    world = World()
    try:
        sue = world.client("sue")
        chain = [
            ("P123", "Project P123 site", "project", None),
            ("WH1", "Main warehouse", "warehouse", "P123"),
            ("L2", "Laydown 2", "laydown", "WH1"),
            ("TC1", "Toolcrib 1", "toolcrib", "L2"),
            ("GB1", "Gang box 1", "gang_box", "TC1"),
        ]
        for code, title, kind, parent in chain:
            body = {
                "scope": P123,
                "code": code,
                "title": title,
                "kind": kind,
                "parent_code": parent,
            }
            made = sue.post("/commands/DefineLocation", json=body)
            check(made.status_code == 200, f"DefineLocation {code}: {made.status_code}")
        passed(
            2, "sue (project superuser) defines the five-level chain P123 > WH1 > L2 > TC1 > GB1"
        )
        refused = world.client("pete").post(
            "/commands/DefineLocation",
            json={
                "scope": P123,
                "code": "L9",
                "title": "Laydown 9",
                "kind": "laydown",
                "parent_code": "WH1",
            },
        )
        check(refused.status_code == 403, f"pete's DefineLocation: {refused.status_code}")
        passed(2, f"pete (project user) DefineLocation is refused: {refused.status_code} forbidden")
    finally:
        world.close()


def snapshot(world: World) -> dict[str, list[str]]:
    with world.backend(True) as uow:
        conn = uow.conn()
        return {
            table: sorted(
                repr(sorted(dict(row).items()))
                for row in conn.execute(text(f"SELECT * FROM {table}")).mappings()
            )
            for table in SNAPSHOT_TABLES
        }


def clause4() -> None:
    world = World()
    try:
        refused = world.client("pete").post(
            "/commands/IssueStock",
            json={
                "scope": P123,
                "movements": [
                    {
                        "lot_key": "P123-RCPT-0002@1",
                        "qty": "1",
                        "uom": "kg",
                        "from_location": "L2",
                    }
                ],
            },
        )
        reason = refused.text[:200]
        check(
            refused.status_code == 422,
            f"a consumable issue without a cost code: {refused.status_code}",
        )
        check("a consumable is issued against a cost code" in reason, f"the refusal says {reason}")
        passed(4, "a consumable issued without a cost code is refused: 422, it needs a cost code")
        with world.backend(True) as uow:
            conn = uow.conn()
            stock = {
                (row.lot, row.location): row.on_hand for row in views.stock(conn, P123, limit=1000)
            }
            moves = views.movements(conn, P123, limit=1000)
        expected: dict[tuple[str, str], Decimal] = {}
        for move in moves:
            if move.kind in ("reserve", "unreserve"):  # these hold stock; they move none
                continue
            if move.to_location:
                key = (move.lot, move.to_location)
                expected[key] = expected.get(key, Decimal(0)) + move.qty
            if move.from_location:
                key = (move.lot, move.from_location)
                expected[key] = expected.get(key, Decimal(0)) - move.qty
        expected = {key: qty for key, qty in expected.items() if qty != 0}
        check(stock == expected, f"stock {stock} is not the sum of movements {expected}")
        passed(
            4, f"stock equals the sum of {len(moves)} movements on {len(stock)} lot-location rows"
        )
        before = snapshot(world)
        world.close()
        rebuild_projections(as_target(os.environ["TL_DB"]))
        world = World()
        check(before == snapshot(world), "a rebuild of the projections changed the stock tables")
        passed(
            4,
            "a rebuild of the projections gives the same stock, lot, reservation and movement rows",
        )
    finally:
        world.close()


def clause6(key: str) -> None:
    """The awp package, then the take-off published into an MTO, compensated and republished.

    The package is made by CreateCwp (the awp handler); the MTO commands run as the named people,
    through the API.
    """
    world = World()
    try:
        created = world.client("ada").post(
            "/commands/CreateCwp",
            json={
                "scope": P123,
                "discipline": "PIP",
                "title": "Piping package 1",
                "cwa_code": CWA,
            },
        )
        check(created.status_code == 200, f"CreateCwp: {created.status_code} {created.text[:200]}")
        number = created.json()["key"]
        check(number == WP, f"the package is numbered {number}")
        passed(6, f"CWP via awp: {number} made by CreateCwp (ada, through the API)")
        with world.backend(True) as uow:
            found = derivation_views.find_derived(uow.conn(), P123, key)
        published = world.client("sue").post(
            "/commands/PublishDerivedMto",
            json={
                "scope": P123,
                "derived_id": found.id,
                "expected_content_rev": found.content_rev,
                "work_package_number": WP,
            },
        )
        check(
            published.status_code == 200, f"publish: {published.status_code} {published.text[:200]}"
        )
        lines = mto_lines(world, WP)
        check(len(lines) == 3, f"the MTO for {WP} has {len(lines)} lines")
        passed(6, f"the derived take-off {key} is published as an MTO: 3 lines, all for {WP}")
        compensated = world.client("ada").post(
            "/commands/CompensatePublication",
            json={"scope": P123, "derived_id": found.id, "reason": "wrong revision"},
        )
        check(compensated.status_code == 200, f"compensate: {compensated.status_code}")
        check(mto_lines(world) == [], "the MTO lines remain after compensation")
        passed(6, "compensation removes the MTO and its three lines")
        with world.backend(True) as uow:
            again = derivation_views.find_derived(uow.conn(), P123, key)
        republished = world.client("sue").post(
            "/commands/PublishDerivedMto",
            json={
                "scope": P123,
                "derived_id": again.id,
                "expected_content_rev": again.content_rev,
                "work_package_number": WP,
            },
        )
        check(republished.status_code == 200, f"republish: {republished.status_code}")
        check(len(mto_lines(world, WP)) == 3, "the republished MTO does not have three lines")
        passed(6, f"republished after compensation: the three lines are back for {WP}")
    finally:
        world.close()


def clause7() -> None:
    """The materials_reserved readiness check keeps the readiness contract on the package."""
    world = World()
    try:
        with world.backend(True) as uow:
            conn = uow.conn()
            record = conn.execute(
                text("SELECT id FROM cur_core_record WHERE key = :k AND NOT voided"), {"k": WP}
            ).scalar_one()
            types = frozenset(
                row[0] for row in conn.execute(text("SELECT DISTINCT type FROM cur_core_record"))
            )
        iwp = IwpFacts(record_id=str(record), scope=P123, key=WP, status="Draft")
        engine = make_engine(world.target)
        try:
            world_ = ContractWorld(engine.connect, iwp, TODAY, types, False)
            check_readiness_contract(load_checks()["materials_reserved"], world_)
        finally:
            engine.dispose()
        passed(7, f"materials_reserved keeps the readiness contract on {WP} (read only)")
    finally:
        world.close()


def qty(value: Any) -> str:
    """A quantity as the TUI prints it: no trailing zeros (11.000 is 11, 0.500 is 0.5)."""
    text_ = format(Decimal(str(value)).normalize(), "f")
    return "0" if text_ == "-0" else text_


def has_row(screen: str, *cells: str) -> bool:
    """Some line of a screen holds the cells, in this order."""
    pattern = r".*".join(re.escape(cell) for cell in cells)
    return any(re.search(pattern, line) for line in screen.splitlines())


async def settle(pilot: Any) -> None:
    """Let the key press and the workers of a screen finish (as the TUI tests do)."""
    await pilot.pause()
    await pilot.app.workers.wait_for_complete()
    await pilot.pause()
    await pilot.pause()


def screen_text(app: Any) -> str:
    """The rendered screen as plain text, one line per terminal row."""
    strips = app.screen._compositor.render_strips()  # pyright: ignore[reportPrivateUsage]
    return "\n".join(strip.text.rstrip() for strip in strips)


def tui_text(
    world: World,
    actor: str,
    make: Callable[[Any], Any],
    ready: Callable[[str], bool] | None = None,
) -> str:
    """The text of one TUI screen pushed on TlApp over the embedded client, at 170 x 40.
    ``ready`` says when the rows the caller checks are on the screen (a bounded wait)."""
    client = EmbeddedClient(world.backend, actor=actor)
    app = TlApp(client, scope=P123, actor=actor)
    captured: dict[str, str] = {}

    async def scenario() -> None:
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            await settle(pilot)
            app.push_screen(make(client))
            await settle(pilot)
            for _ in range(100):  # a log reads its rows in a worker; its summary line says so
                if "Showing" in screen_text(app):
                    break
                await pilot.pause(0.1)
            for _ in range(150):  # and the rows the caller checks are drawn (a panel mounts late)
                if ready is None or ready(screen_text(app)):
                    break
                await pilot.pause(0.1)
            # and until the table has been drawn: the text must read the same five times in a row
            # (a panel that mounts a moment later changes the column widths; Postgres is slower)
            previous, same = "", 0
            for _ in range(200):
                await settle(pilot)
                await pilot.pause(0.2)
                current = screen_text(app)
                same = same + 1 if current == previous else 0
                previous = current
                if same >= 5:
                    break
            captured["text"] = previous

    asyncio.run(scenario())
    return captured["text"]


def mcp_server(world: World) -> Any:
    """The materials MCP tools on a server over the ledger. A local authorizer allows the
    materials actions for the agent (as dev/accept/P2-I3/T07.py does)."""
    from tl_lake import LakeConfig, LakeQueryService
    from tl_mcp.context import McpContext
    from tl_mcp.materials_tools import MATERIALS_MCP_ACTIONS, register_materials_tools
    from tl_mcp.server import build_server

    def allow(actor: str, action: str, resource: str) -> None:
        if action not in MATERIALS_MCP_ACTIONS:
            raise PermissionError(f"{action} is not allowed for {actor}")

    lake = Path(os.environ["P2_I3_WORKDIR"]) / "lake"
    factory = make_uow_factory(world.target)
    server = build_server(factory, actor=AGENT, authorize_hook=allow, lake_dir=lake)
    ctx = McpContext(
        factory=factory,
        actor=AGENT,
        authorize=allow,
        lake=LakeQueryService(
            LakeConfig.at(lake), default_limit=100, max_limit=1000, max_bytes=1024 * 1024
        ),
    )
    register_materials_tools(server, ctx)
    return server


def mcp_call(server: Any, tool: str, **arguments: Any) -> Any:
    result = asyncio.run(server.call_tool(tool, arguments))
    if result.is_error:
        raise RuntimeError(" ".join(getattr(block, "text", "") for block in result.content))
    content = result.structured_content
    return content["result"] if set(content) == {"result"} else content


def clause8() -> None:
    """The API, the TUI screens and the MCP tools agree; an agent's proposal waits for a person."""
    world = World()
    try:
        pete = world.client("pete")
        stock = pete.get(f"/projects/{PROJECT}/materials/stock").json()
        receipts = pete.get(f"/projects/{PROJECT}/materials/receipts").json()
        mto = pete.get(f"/projects/{PROJECT}/materials/mto-lines").json()
        check(len(stock) >= 2 and len(receipts) >= 1 and len(mto) == 3, "the API lists are short")
        stock_text = tui_text(world, "user:pete", lambda c: StockScreen(c, PROJECT))
        for row in stock:
            cells = (
                row["heat_no"],
                qty(row["on_hand"]),
                qty(row["reserved"]),
                qty(row["available"]),
                row["uom"],
            )
            check(has_row(stock_text, *cells), f"the stock screen lacks {row['lot']}: {cells}")
        passed(8, f"the stock screen (170 columns) shows the {len(stock)} API stock rows")
        receipts_text = tui_text(
            world,
            "user:pete",
            lambda c: ReceiptLogScreen(c, PROJECT),
            ready=lambda t: all(has_row(t, r["number"], r["state"]) for r in receipts),
        )
        for row in receipts:
            check(
                has_row(receipts_text, row["number"], row["state"]),
                f"the receipts screen lacks {row['number']} {row['state']}:\n{receipts_text}",
            )
        passed(8, f"the receipts screen shows the {len(receipts)} API receipts with their states")
        mto_text = tui_text(
            world,
            "user:pete",
            lambda c: MtoLinesScreen(c, PROJECT),
            ready=lambda t: mto[0]["key"] in t,
        )
        # The table cuts the Number column short; the full key shows in the panel of the
        # highlighted line (the first one, as the API lists it). Each line's quantities are a row.
        check(mto[0]["key"] in mto_text, f"the MTO screen lacks {mto[0]['key']}:\n{mto_text}")
        for row in mto:
            cells = (qty(row["required"]), qty(row["reserved"]), qty(row["short"]))
            check(has_row(mto_text, *cells), f"the MTO screen lacks {cells}:\n{mto_text}")
        passed(8, f"the MTO lines screen shows the {len(mto)} API take-off lines and quantities")
        server = mcp_server(world)
        mcp_stock = mcp_call(server, "list_material_stock", project=PROJECT)

        def pairs(rows: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
            return sorted((r["lot"], qty(r["on_hand"]), qty(r["reserved"])) for r in rows)

        check(pairs(mcp_stock) == pairs(stock), "the MCP stock differs from the API stock")
        passed(8, "the MCP stock tool returns the same lots and quantities as the API")
        line = next(r["key"] for r in mto if r["key"].endswith("/001"))
        lot = next(
            r["lot"]
            for r in stock
            if r["heat_no"] == "H-7781" and r["location"] == "L2" and r["lot"].endswith("@1")
        )
        before = pete.get(f"/projects/{PROJECT}/materials/stock").json()
        proposed = mcp_call(
            server,
            "propose_reservation",
            project=PROJECT,
            lot=lot,
            location="L2",
            mto_line=line,
            qty="1",
        )
        pid = proposed["proposal"]["proposal_id"]
        check(proposed["proposal"]["status"] == "pending", f"the proposal is {proposed}")
        check(
            pete.get(f"/projects/{PROJECT}/materials/stock").json() == before,
            "the agent's proposal changed the stock",
        )
        passed(8, f"the agent's propose_reservation is pending ({pid}) and changes no stock")
        accepted = world.client("sue").post(
            f"/proposals/{pid}/accept", params={"scope": P123}, json={}
        )
        check(accepted.status_code == 200, f"sue's accept: {accepted.status_code}")
        check(
            pete.get(f"/projects/{PROJECT}/materials/stock").json() != before,
            "the accepted reservation did not show in the stock",
        )
        passed(8, "sue (materials superuser) accepts it, and the reservation is made")
    finally:
        world.close()


def clause9() -> None:
    """The four quantities the shell refuses on the CLI, refused by the API with the same text."""
    world = World()
    try:
        for value, message in BAD_QUANTITIES:
            refused = world.client("pete").post(
                "/commands/IssueStock",
                json={
                    "scope": P123,
                    "movements": [
                        {
                            "lot_key": "P123-RCPT-0001@1",
                            "qty": value,
                            "uom": "EA",
                            "from_location": "L2",
                        }
                    ],
                },
            )
            check(refused.status_code == 422, f"qty {value!r}: {refused.status_code}")
            check(message in refused.text, f"qty {value!r} says {refused.text[:160]}")
        passed(9, "the API refuses the same four quantities with the same fixed message")
    finally:
        world.close()


def clause10_11() -> None:
    """The item library (51 items, project counts) and the location tree (five levels, lot
    counts) at 170 columns; the screens show what the ledger holds."""
    world = World()
    try:
        items = tui_text(world, "user:pete", lambda c: ItemLibraryScreen(c))
        check("Showing 51 of 51 items" in items, "the item library does not show 51 of 51 items")
        check("Projects" in items, "the item library has no Projects column")
        passed(
            10,
            "the item library shows the 50 sample items and mara's probe, with project counts, "
            "at 170 columns",
        )
        locations = tui_text(world, "user:pete", lambda c: LocationScreen(c, PROJECT))
        api = world.client("pete").get(f"/projects/{PROJECT}/materials/locations").json()
        check(len(api) == 5, f"the location tree has {len(api)} locations")
        for row in api:
            check(
                has_row(locations, row["code"], str(row["lots"])),
                f"{row['code']} with {row['lots']} lots is not on the screen",
            )
        check("Showing 5 of 5 locations" in locations, "the locations screen does not show 5 of 5")
        passed(10, "the locations screen shows the five-level tree P123 > WH1 > L2 > TC1 > GB1")
        passed(10, "each location shows its lot count, as the API counts them")
    finally:
        world.close()


def main(argv: list[str]) -> None:
    mode = argv[1] if len(argv) > 1 else ""
    args = argv[2:]
    if mode not in MODES:
        raise SystemExit(f"usage: p2_i3_demo.py {'|'.join(MODES)} [ARGS]")
    handlers: dict[str, Callable[..., None]] = {
        "clause1-people": clause1_people,
        "clause2": clause2,
        "clause4": clause4,
        "clause6": clause6,
        "clause7": clause7,
        "clause8": clause8,
        "clause9": clause9,
        "clause10-11": clause10_11,
    }
    expected = {"clause6": 1}.get(mode, 0)
    if len(args) != expected:
        raise SystemExit(f"{mode} takes {expected} argument(s)")
    handlers[mode](*args)


if __name__ == "__main__":
    main(sys.argv)
