"""The materials read routes over HTTP (T04a, T05a, S5): auth, 404s, names, bounds and a walk of
every GET route as five kinds of reader over classified records (ADR-0016)."""

from __future__ import annotations

import dataclasses
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from harness import Harness
from sqlalchemy import text
from tl_adapters.db import as_target, open_uow
from tl_core.auth import accounts, sessions
from tl_core.auth.password import prepare_password
from tl_core.modules import ConfidentialSource, load_modules, use_modules

sys.path.insert(0, str(Path(__file__).parents[2] / "tl-modules" / "materials" / "tests"))

from acc_s3 import Stocked, World  # noqa: E402

PASSWORD = "correct horse battery"
MIN_ROUTES = 12  # nine reads, the report, mto-line and item-projects
#: Who reads a restricted record: a document controller and an admin, not a user or an agent.
MAY_READ_RESTRICTED = {"bob": False, "amy": False, "ctl": True, "boss": True, "bot": False}


@dataclasses.dataclass
class Seed:
    world: World
    stocked: Stocked
    tokens: dict[str, str]
    receipt_number: str
    lot_key: str
    line_key: str
    item_code: str


def _person(uow: Any, name: str, roles: list[str]) -> None:
    accounts.create_account(
        uow,
        username=name,
        display_name=name.title(),
        kind="person",
        roles=roles,
        password=prepare_password(PASSWORD),
        by="svc:test",
    )


@pytest.fixture
def seeded(harness: Harness, tmp_path: Path) -> Seed:
    w = World(as_target(harness.db), tmp_path / "objects")
    s = Stocked(w)
    with harness.backend(False) as uow:
        for name, roles in (
            ("bob", ["user"]),
            ("amy", ["user"]),
            ("ctl", ["document_controller"]),
            ("boss", ["admin"]),
        ):
            _person(uow, name, roles)
        bot = accounts.create_account(
            uow,
            username="bot",
            display_name="Bot",
            kind="agent",
            roles=["user"],
            password=None,
            by="svc:test",
        )
        _, agent_token = accounts.issue_agent_token(
            uow,
            account_id=bot.account_id,
            label="walk",
            expires_at=datetime.now(UTC) + timedelta(days=1),
            by="svc:test",
        )
    tokens = {
        n: sessions.sign_in(harness.backend, username=n, password=PASSWORD)[1]
        for n in ("bob", "amy", "ctl", "boss")
    }
    tokens["bot"] = agent_token

    def key(record_id: str) -> str:
        return str(w.one("SELECT key FROM cur_core_record WHERE id = :i", i=record_id)["key"])

    return Seed(w, s, tokens, key(s.receipt), s.key1, key(s.line), w.code("FLG"))


@contextmanager
def classes(w: World, restricted: set[str]) -> Iterator[None]:
    """Every materials record is ``internal`` but the ``restricted`` ones."""
    with open_uow(w.target) as uow:
        uow.conn().execute(text("CREATE TABLE x_class (id TEXT PRIMARY KEY, cls TEXT)"))
        ids = [
            str(r["id"])
            for r in uow.conn()
            .execute(text("SELECT id FROM cur_core_record WHERE type LIKE 'materials.%'"))
            .mappings()
            .all()
        ]
        for record_id in ids:
            uow.conn().execute(
                text("INSERT INTO x_class VALUES (:i, :c)"),
                {"i": record_id, "c": "restricted" if record_id in restricted else "internal"},
            )
    source = ConfidentialSource(
        record_types=frozenset(
            {"materials.StockLot", "materials.Receipt", "materials.MTOLine", "materials.POLineRef"}
        ),
        table="x_class",
        id_column="id",
        class_column="cls",
    )
    changed = [
        dataclasses.replace(m, confidential=(source,)) if m.name == "materials" else m
        for m in load_modules()
    ]
    with use_modules(changed):
        yield


def routes(h: Harness) -> dict[str, str]:
    found: dict[str, str] = {}
    for path, ops in h.app.openapi()["paths"].items():
        if "/materials" in path and "get" in ops:
            found[path] = ops["get"]["operationId"]
    return found


def test_the_materials_get_routes_are_named_and_unique(harness: Harness) -> None:
    found = routes(harness)
    assert len(found) >= MIN_ROUTES, sorted(found)
    assert len(set(found.values())) == len(found)
    assert {
        "list_materials_stock",
        "get_materials_lot",
        "list_materials_movements",
        "list_materials_receipts",
        "get_materials_receipt",
        "list_materials_locations",
        "list_materials_po_lines",
        "list_materials_mto_lines",
        "list_materials_items",
        "get_materials_mto_line",
        "list_materials_item_projects",
        "get_materials_report",
    } <= set(found.values())


def test_no_token_is_401_and_unknown_records_are_404(harness: Harness, seeded: Seed) -> None:
    project = seeded.world.project.removeprefix("project:")
    base = f"/projects/{project}/materials"
    anon = harness.client_for(None)
    for path in (f"{base}/stock", f"{base}/receipts", "/companies/materials/items"):
        assert anon.get(path).status_code == 401, path
    reader = harness.client
    assert reader.get(f"{base}/lots/NO-SUCH-LOT").status_code == 404
    assert reader.get(f"{base}/receipts/NO-SUCH").status_code == 404
    assert reader.get(f"{base}/mto-line", params={"key": "no/such"}).status_code == 404
    assert reader.get("/companies/materials/item-projects", params={"code": "NOPE"}).json() == []
    for path in (f"{base}/stock", f"{base}/movements", f"{base}/receipts"):
        assert reader.get(path, params={"limit": 0}).status_code == 422, path
        assert reader.get(path, params={"limit": 1001}).status_code == 422, path


def test_the_routes_answer_with_the_records(harness: Harness, seeded: Seed) -> None:
    project = seeded.world.project.removeprefix("project:")
    base = f"/projects/{project}/materials"
    c = harness.client
    assert {r["lot"] for r in c.get(f"{base}/stock").json()} >= {seeded.lot_key}
    assert c.get(f"{base}/lots/{seeded.lot_key}").json()["key"] == seeded.lot_key
    assert c.get(f"{base}/receipts/{seeded.receipt_number}").json()["received_by"]
    line = c.get(f"{base}/mto-line", params={"key": seeded.line_key})
    assert line.status_code == 200 and line.json()["key"] == seeded.line_key
    ip = c.get("/companies/materials/item-projects", params={"code": seeded.item_code}).json()
    assert [r["project"] for r in ip] == [project]


def _paths(seed: Seed) -> list[tuple[str, dict[str, str]]]:
    project = seed.world.project.removeprefix("project:")
    base = f"/projects/{project}/materials"
    return [
        (f"{base}/stock", {}),
        (f"{base}/lots/{seed.lot_key}", {}),
        (f"{base}/movements", {}),
        (f"{base}/receipts", {}),
        (f"{base}/receipts/{seed.receipt_number}", {}),
        (f"{base}/locations", {}),
        (f"{base}/po-lines", {}),
        (f"{base}/mto-lines", {}),
        (f"{base}/mto-line", {"key": seed.line_key}),
        ("/companies/materials/items", {}),
        ("/companies/materials/item-projects", {"code": seed.item_code}),
    ]


@pytest.mark.parametrize("reader", sorted(MAY_READ_RESTRICTED))
def test_five_readers_walk_every_materials_get_route(
    harness: Harness, seeded: Seed, reader: str
) -> None:
    """A restricted lot, receipt and take-off line answer as ones that never existed unless the
    reader may read restricted records; a hidden marker never appears in any response."""
    s = seeded
    hidden = {s.stocked.lot1, s.stocked.lot2, s.stocked.receipt, s.stocked.line}
    markers = [s.stocked.key1, s.stocked.key2, s.receipt_number, s.line_key]
    may = MAY_READ_RESTRICTED[reader]
    client = harness.client_for(None)
    headers = {"Authorization": f"Bearer {s.tokens[reader]}"}
    with classes(s.world, hidden):
        for path, params in _paths(s):
            got = client.get(path, params=params or None, headers=headers)
            assert got.status_code in (200, 404), (reader, path, got.status_code)
            if may:
                continue
            # a 404 names the key it was asked for, as it does for an id that names nothing
            echoed = got.text
            for asked in (path.rsplit("/", 1)[-1], *params.values()):
                echoed = echoed.replace(asked, "\0")
            for marker in markers:
                assert marker not in echoed, (reader, path, marker)
        lot = client.get(_paths(s)[1][0], headers=headers)
        receipt = client.get(_paths(s)[4][0], headers=headers)
    assert (lot.status_code == 200) is may, reader
    assert (receipt.status_code == 200) is may, reader
