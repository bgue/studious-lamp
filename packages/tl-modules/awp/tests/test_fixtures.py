"""The expected link of a released CWP (S6): the default registry and `tl link list`."""

from __future__ import annotations

from pathlib import Path

from awp_world import ROOT, SCOPE, World
from tl_adapters.db import open_uow
from tl_cli.main import app
from tl_core.links.expected import (
    default_expected_links,
    missing_expected_links,
    parse_expected_links,
)
from tl_core.services.links import AddLink, handle_add_link
from typer.testing import CliRunner

RELEASED = "Released for IWP development"


def test_the_default_registry_expects_what_cwp_yaml_declares() -> None:
    ours = default_expected_links().for_type("awp.CWP")
    declared = parse_expected_links((ROOT / "schema/modules/awp/cwp.yaml").read_text()).for_type(
        "awp.CWP"
    )
    assert len(ours) == 1
    assert ours == declared


def _misses(w: World, cwp: str) -> int:
    with open_uow(w.db, readonly=True) as uow:
        return len(missing_expected_links(uow, cwp, by_state=w.state(cwp)))


def test_a_requires_link_to_an_ewp_closes_the_miss_and_a_pwp_does_not(world: World) -> None:
    world.wbs_tree()
    world.areas_and_path(("A1",))
    dev, rel, pwp = (world.full_cwp("PIP", f"Rack {n}", "A1", f"1.1.{n}", "10") for n in (1, 2, 3))
    for cwp in (dev, rel, pwp):
        world.call("uma", "StartCwpDevelopment", cwp=cwp)
    assert _misses(world, dev) == 0
    for cwp in (rel, pwp):
        world.call("sue", "ReleaseCwp", cwp=cwp, expected_version=world.version(cwp))
    assert world.state(rel) == RELEASED
    assert _misses(world, rel) == 1  # released, never refused
    for cwp, kind, number in ((rel, "ewp", "EWP-1"), (pwp, "pwp", "PWP-1")):
        world.call(
            "uma",
            "RecordExternalPackage",
            package_type=kind,
            package_no=number,
            title=number,
            constraint_source=False,
        )
        to = world.id_of(number, f"awp.{kind.upper()}Ref")
        with open_uow(world.db) as uow:
            handle_add_link(
                uow,
                AddLink(
                    actor="user:uma",
                    source="test",
                    scope=SCOPE,
                    from_id=cwp,
                    to_id=to,
                    relation="requires",
                ),
            )
    assert _misses(world, rel) == 0
    assert _misses(world, pwp) == 1


def test_tl_link_list_prints_the_miss(tmp_path: Path) -> None:
    from tl_adapters.db import as_target, create_schema

    target = as_target(str(tmp_path / "s6.db"))
    create_schema(target)
    w = World(target)
    w.people()
    w.editions()
    w.wbs_tree()
    w.areas_and_path(("A1",))
    cwp = w.full_cwp("PIP", "Rack", "A1", "1.1.1", "10")
    w.call("uma", "StartCwpDevelopment", cwp=cwp)
    w.call("sue", "ReleaseCwp", cwp=cwp, expected_version=w.version(cwp))
    key = w.scalar("SELECT key FROM cur_core_record WHERE id = :i", i=cwp)
    out = (
        CliRunner()
        .invoke(
            app,
            ["link", "list", "--project", "P123", key],
            env={"TL_DB": str(tmp_path / "s6.db"), "TL_ENV": "dev"},
        )
        .output
    )
    assert "missing engineering work package (rule: requires@Released" in out
