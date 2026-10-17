"""The cost module over HTTP and through the client: reads, the admin's import (P1-I4)."""

from __future__ import annotations

from typing import Any

import pytest
from harness import Harness
from test_api_schedule import Cast
from tl_adapters.db import open_uow
from tl_mod_cost import views
from tl_mod_cost.errors import CostCodeNotFoundError, CostImportRefusedError
from tl_mod_cost.handlers.snapshots import ImportCostSnapshot
from tl_mod_cost.testing import CostWorld, row

P = "/projects/P123"
SCOPE = "project:P123"
BASE: dict[str, Any] = {"actor": "user:boss", "source": "test", "scope": SCOPE}


@pytest.fixture
def cast(harness: Harness) -> Cast:
    return Cast(harness)


@pytest.fixture
def world(harness: Harness) -> CostWorld:
    made = CostWorld(harness.db)
    made.import_snapshot(
        [
            row("4210", "Piping", hours_budget=1000, hours_actual=400),
            row("4210-PIP", "Pipe installation", "4210", hours_budget=600, uom="in-dia"),
            row("5100", "Electrical", amount_budget=90000),
        ],
        period="2026-06",
        as_of="2026-06-30",
    )
    made.import_snapshot(
        [row("4210-PIP", hours_budget=600, hours_actual=150)], period="2026-07", as_of="2026-07-31"
    )
    return made


READS = (f"{P}/cost-snapshots", f"{P}/cost-codes", f"{P}/cost-codes/4210-PIP")


def test_a_person_and_an_agent_can_read_and_nobody_unsigned_can(
    cast: Cast, world: CostWorld
) -> None:
    for path in READS:
        assert cast.clients["bob"].get(path).status_code == 200, path
        assert cast.agent.get(path).status_code == 200, path
        assert cast.anonymous.get(path).status_code == 401, path


def test_codes_snapshots_and_one_code_with_its_history(cast: Cast, world: CostWorld) -> None:
    bob = cast.clients["bob"]
    codes = bob.get(f"{P}/cost-codes").json()
    assert [c["code"] for c in codes] == ["4210", "4210-PIP", "5100"]
    assert codes[1]["figures"]["hours_actual"] == 150 and codes[1]["period"] == "2026-07"
    assert [c["code"] for c in bob.get(f"{P}/cost-codes", params={"parent": "4210"}).json()] == [
        "4210-PIP"
    ]
    assert [c["code"] for c in bob.get(f"{P}/cost-codes", params={"q": "electr"}).json()] == [
        "5100"
    ]
    one = bob.get(f"{P}/cost-codes/4210-PIP").json()
    assert [h["period"] for h in one["history"]] == ["2026-06", "2026-07"]
    assert bob.get(f"{P}/cost-codes/4210").json()["children"] == ["4210-PIP"]
    snapshots = bob.get(f"{P}/cost-snapshots").json()
    assert [(s["key"], s["row_count"]) for s in snapshots] == [("2026-07@1", 1), ("2026-06@1", 3)]
    missing = bob.get(f"{P}/cost-codes/9999")
    assert (missing.status_code, missing.json()["error"]) == (404, "cost_code_not_found")
    assert bob.get(f"{P}/cost-codes", params={"limit": 0}).status_code == 422


def test_the_client_returns_what_the_embedded_views_return(
    harness: Harness, cast: Cast, world: CostWorld
) -> None:
    api = cast.api("bob")
    with open_uow(harness.db, readonly=True) as uow:
        conn = uow.conn()
        assert api.list_cost_codes("P123") == views.cost_codes(conn, SCOPE)
        assert api.list_cost_codes("P123", parent="4210", q="pipe", limit=5) == views.cost_codes(
            conn, SCOPE, parent="4210", search="pipe", limit=5
        )
        assert api.get_cost_code("P123", "4210-PIP") == views.cost_code_detail(
            conn, SCOPE, "4210-PIP"
        )
        assert api.list_cost_snapshots("P123") == views.cost_snapshots(conn, SCOPE)
    with pytest.raises(CostCodeNotFoundError):
        api.get_cost_code("P123", "9999")


def test_the_admin_imports_a_snapshot_over_http_and_nobody_else_does(
    cast: Cast, world: CostWorld
) -> None:
    command = ImportCostSnapshot(
        **BASE,
        period="2026-08",
        as_of="2026-08-31",
        rows=[row("4210-PIP", hours_budget=600, hours_actual=300)],
    )
    for who in ("bob", "dora"):
        status = cast.clients[who].post(
            "/commands/ImportCostSnapshot", json=command.model_dump(mode="json", exclude={"actor"})
        )
        assert status.status_code == 403, who
    made = cast.api("boss").import_cost_snapshot(command)
    assert made.key == "2026-08@1"
    assert cast.api("bob").get_cost_code("P123", "4210-PIP").history[-1].period == "2026-08"


def test_a_refused_import_carries_its_issues(cast: Cast, world: CostWorld) -> None:
    command = ImportCostSnapshot(
        **BASE,
        period="2026-08",
        as_of="2026-08-31",
        rows=[row("NEW-1", "Child", "MISSING-PARENT", hours_budget=1)],
    )
    with pytest.raises(CostImportRefusedError) as caught:
        cast.api("boss").import_cost_snapshot(command)
    assert caught.value.issues and "MISSING-PARENT" in " ".join(caught.value.issues)


def test_a_command_body_over_the_limit_is_refused_before_it_is_read(cast: Cast) -> None:
    body = {"scope": SCOPE, "period": "2026-08", "as_of": "2026-08-31", "pad": "x" * (1 << 21)}
    refused = cast.clients["boss"].post("/commands/ImportCostSnapshot", json=body)
    assert (refused.status_code, refused.json()["error"]) == (413, "payload_too_large")
