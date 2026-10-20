"""Replaying the ledger gives the tables the commands made (restore and rebuild, brief 24)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from tl_adapters.db import rebuild_projections
from tl_core.util import utcnow
from tl_mod_schemareg.handlers.adoption import AdoptSchemaPackage
from tl_mod_schemareg.handlers.packages import DeprecateSchemaPackage
from tl_mod_schemareg.handlers.waivers import ApproveWaiver, RequestWaiver, RevokeWaiver
from tl_mod_schemareg.testing import ADMIN, AUTHOR, RegistryWorld, publish_version

TABLES = (
    ("cur_schemareg_schema_package", "id"),
    ("cur_schemareg_adoption", "id"),
    ("cur_schemareg_waiver", "id"),
    ("cur_core_record", "id"),
)


def snapshot(world: RegistryWorld) -> dict[str, list[dict[str, Any]]]:
    return {t: world.rows(f"SELECT * FROM {t} ORDER BY {order}") for t, order in TABLES}


def test_a_rebuild_reproduces_every_registry_table(world: RegistryWorld) -> None:
    first = publish_version(world, "3.3.0")
    publish_version(world, "3.4.0")
    world.do(
        AdoptSchemaPackage, ADMIN, project="P999", package="co.acme.engineering", version="3.3.0"
    )
    world.do(DeprecateSchemaPackage, ADMIN, package_id=first.stream_id, reason="Replaced.")
    expires = (utcnow().date() + timedelta(days=20)).isoformat()
    waiver = world.do(
        RequestWaiver,
        AUTHOR,
        project="P999",
        path="psets.valve_data.size_in",
        reason="Legacy.",
        expires=expires,
    )
    world.do(ApproveWaiver, ADMIN, waiver_id=waiver.stream_id)
    other = world.do(
        RequestWaiver,
        AUTHOR,
        project="P999",
        path="psets.valve_data.tag_no",
        reason="Legacy.",
        expires=expires,
    )
    world.do(RevokeWaiver, ADMIN, waiver_id=other.stream_id, reason="No.")
    before = snapshot(world)
    assert len(before["cur_schemareg_schema_package"]) == 2
    assert len(before["cur_schemareg_waiver"]) == 2
    rebuild_projections(world.db)
    assert snapshot(world) == before
