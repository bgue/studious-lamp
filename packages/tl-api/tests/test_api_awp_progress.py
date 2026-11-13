"""P2-I5-T11a1: the progress, roll-up, KPI, count and hash reads of the awp module, over the HTTP
routes as the viewer ``vera`` reads them (the ``Rig`` and ``seed_awp`` of test_api_awp)."""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from harness import Harness
from sqlalchemy import text
from test_api_awp import BASE, MADE_UP_ID, Rig, seed_awp
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core import modules as core_modules
from tl_core.modules import ConfidentialSource
from tl_mod_awp.handlers.signoff import iwp_record_hash
from tl_mod_awp.iwp_counts import iwp_counts
from tl_mod_awp.kpis import KPI_NAMES
from tl_mod_awp.names import IWP
from tl_mod_awp.progress.rollup import progress_rollup

SCOPE = "project:P123"
CLASS_TABLE = "pr_iwp_class"
COUNT_KEYS = {"number", "state_since", "ready_ok", "ready_total", "evaluated", "open_blocking"}
PROGRESS_KEYS = {"number", "pct", "edition", "items", "notes"}
ITEM_KEYS = {"key", "pct", "steps", "hours"}
ROLLUP_KEYS = {"scope", "as_of_seq", "cwps", "nodes", "lines", "notes"}
KPI_KEYS = {"name", "value", "numerator", "denominator", "detail"}
HASH_KEYS = {"number", "record_hash"}


@pytest.fixture(scope="module")
def rig(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    """The S4 seed with rollup rows, two IWPs of the project (one restricted to the lowest
    clearance, so ``vera`` cannot open it) and the restricted one's number."""
    h = Harness.build(tmp_path_factory.mktemp("api-awp-progress"))
    original = core_modules.confidential_sources
    try:
        world = seed_awp(h, rollup=True)
        target = h.target or h.db
        shown = str(world.iwp("Rack shown", planned_start="2026-12-01", foreman="user:uma"))
        hidden = str(world.iwp("Rack hidden", discipline="PIP"))
        ids = [str(r["id"]) for r in world.rows("SELECT id FROM cur_awp_iwp")]
        with open_uow(target) as uow:
            conn = uow.conn()
            conn.execute(text(f"CREATE TABLE {CLASS_TABLE} (id TEXT PRIMARY KEY, cls TEXT)"))
            for row_id in ids:
                cls = "restricted" if row_id == hidden else "internal"
                conn.execute(
                    text(f"INSERT INTO {CLASS_TABLE} (id, cls) VALUES (:i, :c)"),
                    {"i": row_id, "c": cls},
                )
        source = ConfidentialSource(
            record_types=frozenset({IWP}),
            table=CLASS_TABLE,
            id_column="id",
            class_column="cls",
        )
        cf.confidential_sources = lambda: [*original(), source]  # type: ignore[attr-defined]
        yield {
            "rig": Rig(h, world),
            "world": world,
            "target": target,
            "shown": shown,
            "hidden": hidden,
            "shown_no": number(world, shown),
            "hidden_no": number(world, hidden),
        }
    finally:
        cf.confidential_sources = original  # type: ignore[attr-defined]
        h.close()


def number(world: Any, iwp: str) -> str:
    return str(world.scalar("SELECT key FROM cur_core_record WHERE id = :i", i=iwp))


def test_each_route_answers_with_the_declared_keys_only(rig: dict[str, Any]) -> None:
    r: Rig = rig["rig"]
    counts = r.ok("/iwps/counts")
    assert isinstance(counts, list) and counts
    assert all(set(row) == COUNT_KEYS for row in counts)
    assert rig["hidden_no"] not in {row["number"] for row in counts}  # hidden: absent
    assert rig["shown_no"] in {row["number"] for row in counts}

    progress = r.ok(f"/iwps/{rig['shown_no']}/progress")
    assert set(progress) == PROGRESS_KEYS
    assert all(set(item) == ITEM_KEYS for item in progress["items"])

    rollup = r.ok("/progress/rollup")
    assert set(rollup) == ROLLUP_KEYS

    kpis = r.ok("/kpis")
    assert all(set(tile) == KPI_KEYS for tile in kpis)

    digest = r.ok(f"/iwps/{rig['shown_no']}/hash")
    assert set(digest) == HASH_KEYS


def test_counts_is_not_taken_by_the_number_route(rig: dict[str, Any]) -> None:
    response = rig["rig"].get("/iwps/counts")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_unknown_and_hidden_progress_are_the_same_404(rig: dict[str, Any]) -> None:
    r: Rig = rig["rig"]
    hidden = r.get(f"/iwps/{rig['hidden_no']}/progress")
    missing = r.get(f"/iwps/{MADE_UP_ID}/progress")
    assert hidden.status_code == missing.status_code == 404
    assert hidden.text.replace(rig["hidden_no"], "K") == missing.text.replace(MADE_UP_ID, "K")
    assert sorted(hidden.headers) == sorted(missing.headers)

    hidden_hash = r.get(f"/iwps/{rig['hidden_no']}/hash")
    missing_hash = r.get(f"/iwps/{MADE_UP_ID}/hash")
    assert hidden_hash.status_code == missing_hash.status_code == 404
    assert hidden_hash.text.replace(rig["hidden_no"], "K") == missing_hash.text.replace(
        MADE_UP_ID, "K"
    )


def test_rollup_lines_add_up_to_the_reader_figures(rig: dict[str, Any]) -> None:
    body = rig["rig"].ok("/progress/rollup")
    with open_uow(rig["target"], readonly=True) as uow:
        found = progress_rollup(uow.conn(), SCOPE, viewer=cf.current_viewer())
    assert sum(Decimal(str(ln["earned_hours"])) for ln in body["lines"]) == sum(
        (ln.earned_hours for ln in found.lines), Decimal(0)
    )
    assert body["as_of_seq"] == found.as_of_seq


def test_kpis_return_the_two_tiles_in_order(rig: dict[str, Any]) -> None:
    kpis = rig["rig"].ok("/kpis")
    assert [tile["name"] for tile in kpis] == list(KPI_NAMES)


def test_hash_equals_the_sign_off_record_hash(rig: dict[str, Any]) -> None:
    digest = rig["rig"].ok(f"/iwps/{rig['shown_no']}/hash")
    assert digest["number"] == rig["shown_no"]
    with open_uow(rig["target"], readonly=True) as uow:
        assert digest["record_hash"] == iwp_record_hash(uow.conn(), rig["shown"])


def test_counts_match_the_module_reader(rig: dict[str, Any]) -> None:
    body = rig["rig"].ok("/iwps/counts")
    with open_uow(rig["target"], readonly=True) as uow:
        expected = [r.model_dump() for r in iwp_counts(uow.conn(), SCOPE)]
    assert body == expected


def test_no_token_is_401_on_every_route(rig: dict[str, Any]) -> None:
    r: Rig = rig["rig"]
    for path in [
        "/iwps/counts",
        f"/iwps/{rig['shown_no']}/progress",
        "/progress/rollup",
        "/kpis",
        f"/iwps/{rig['shown_no']}/hash",
    ]:
        assert r.anonymous.get(f"{BASE}{path}").status_code == 401, path
