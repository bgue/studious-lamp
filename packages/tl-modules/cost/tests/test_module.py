"""The package imports, its schema header names the module, and the platform finds it."""

from __future__ import annotations

import re
from pathlib import Path

import tl_mod_cost
from tl_core.modules import load_modules, module_record_types
from tl_core.projection.defaults import default_registry
from tl_mod_cost.commands import API_COMMANDS
from tl_mod_cost.module import projectors, spec
from tl_mod_cost.names import RECORD_TYPES

ROOT = Path(__file__).resolve().parents[4]
SCHEMA = ROOT / "schema" / "modules" / "cost"


def test_the_package_names_its_module() -> None:
    assert tl_mod_cost.MODULE == "cost"
    assert "tl:module: cost" in (SCHEMA / "module.yaml").read_text(encoding="utf-8")


def test_the_platform_loads_the_module_through_its_entry_point() -> None:
    assert "cost" in [m.name for m in load_modules()]
    assert RECORD_TYPES <= module_record_types()


def test_the_module_projectors_are_registered_after_the_core_ones_and_before_the_outbox() -> None:
    names = [p.name for p in default_registry().all()]
    assert names[-1] == "outbox"
    mine = [p.name for p in projectors()]
    assert all(name in names for name in mine)
    assert names.index("cost_cost_code") > names.index("core_record")


def test_the_record_types_match_the_schema_annotations() -> None:
    found: set[str] = set()
    for path in SCHEMA.glob("*.yaml"):
        found |= set(re.findall(r'tl:record_types: "([^"]+)"', path.read_text(encoding="utf-8")))
    assert found == set(spec().record_types) == set(RECORD_TYPES)


def test_every_cost_event_type_is_handled_by_exactly_one_projector() -> None:
    owners: dict[str, list[str]] = {}
    for projector in projectors():
        for event_type in projector.handles:
            owners.setdefault(event_type, []).append(projector.name)
    assert all(len(names) == 1 for names in owners.values())
    catalogued: set[str] = set()
    for path in SCHEMA.glob("*events.yaml"):
        catalogued |= set(re.findall(r"tl:event_type: (\S+)", path.read_text(encoding="utf-8")))
    assert catalogued == set(owners)


def test_importing_a_snapshot_is_the_admins_and_nothing_else_is_offered() -> None:
    assert [(c.model.__name__, c.access) for c in API_COMMANDS] == [("ImportCostSnapshot", "admin")]


def test_the_table_columns_match_the_measure_names() -> None:
    from tl_mod_cost.names import MEASURE_COLUMNS

    text = (SCHEMA / "cost_code.yaml").read_text(encoding="utf-8")
    for column in MEASURE_COLUMNS:
        assert f"      {column}:\n" in text
    assert len(MEASURE_COLUMNS) == 15
