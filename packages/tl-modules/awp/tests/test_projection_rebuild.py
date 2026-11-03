"""A rebuild of the projections equals the incrementally built tables (S3, S4, S5)."""

from __future__ import annotations

from awp_world import World
from tl_adapters.db import open_uow, rebuild_projections
from tl_mod_awp import rollup
from tl_mod_awp.worker import build_worker

TABLES = (
    ("cur_awp_wbs_node", "id"),
    ("cur_awp_wbs_allocation", "row_id"),
    ("cur_awp_path", "id"),
    ("cur_awp_path_step", "row_id"),
    ("cur_awp_cwa", "id"),
    ("cur_awp_cwp", "id"),
    ("cur_awp_cwp_allocation", "row_id"),
    ("cur_awp_ewp_ref", "id"),
    ("cur_awp_pwp_ref", "id"),
    ("cur_awp_rollup", "row_id"),
    ("cur_core_record", "id"),
    ("cur_links", "link_id"),
)


def _snapshot(w: World) -> dict[str, list[dict[str, object]]]:
    return {t: w.rows(f"SELECT * FROM {t} ORDER BY {order}") for t, order in TABLES}


def test_rebuild_equals_the_incremental_tables(world: World) -> None:
    world.seed()
    world.call(
        "uma",
        "RecordExternalPackage",
        package_type="ewp",
        package_no="EWP-1",
        title="T",
        constraint_source=True,
    )
    world.call(
        "sue",
        "MoveCwaInPath",
        cwa_code="A4",
        to_position=1,
        reason_code="Access",
        expected_version=1,
    )
    cwa = world.id_of("A4", "awp.CWA")
    world.call("sue", "ReviseCwa", cwa=cwa, title="Fourth area")
    with open_uow(world.db) as uow:
        rollup.request(uow, "project:P123")
    with build_worker(world.db) as worker:
        assert worker.runner.run_once() is not None
    before = _snapshot(world)
    assert len(before["cur_awp_cwp"]) == 6
    assert len(before["cur_awp_ewp_ref"]) == 1
    assert len(before["cur_awp_wbs_node"]) == 9
    assert len(before["cur_awp_path_step"]) == 8
    assert len(before["cur_awp_rollup"]) > 0
    rebuild_projections(world.db)
    assert _snapshot(world) == before
