"""The package imports, its schema header names the module, and the platform finds it."""

from __future__ import annotations

import re
from pathlib import Path

import tl_mod_schedule
from tl_core.modules import load_modules, module_record_types
from tl_core.projection.defaults import default_registry
from tl_mod_schedule.commands import API_COMMANDS
from tl_mod_schedule.module import projectors, spec
from tl_mod_schedule.names import RECORD_TYPES, TYPED_TABLES
from tl_xer.typed import TABLE_COLUMNS

ROOT = Path(__file__).resolve().parents[4]
SCHEMA = ROOT / "schema" / "modules" / "schedule"


def test_the_package_names_its_module() -> None:
    assert tl_mod_schedule.MODULE == "schedule"
    assert "tl:module: schedule" in (SCHEMA / "module.yaml").read_text(encoding="utf-8")


def test_the_platform_loads_the_module_through_its_entry_point() -> None:
    assert "schedule" in [m.name for m in load_modules()]
    assert RECORD_TYPES <= module_record_types()


def test_the_module_projectors_are_registered_after_the_core_ones_and_before_the_outbox() -> None:
    names = [p.name for p in default_registry().all()]
    assert names[-1] == "outbox"
    mine = [p.name for p in projectors()]
    assert all(name in names for name in mine)
    assert names.index("schedule_schedule") > names.index("core_record")


def test_the_record_types_match_the_schema_annotations() -> None:
    found: set[str] = set()
    for path in SCHEMA.glob("*.yaml"):
        found |= set(re.findall(r'tl:record_types: "([^"]+)"', path.read_text(encoding="utf-8")))
    assert found == set(spec().record_types) == set(RECORD_TYPES)


def test_every_schedule_event_type_is_handled_by_exactly_one_projector() -> None:
    owners: dict[str, list[str]] = {}
    for projector in projectors():
        for event_type in projector.handles:
            owners.setdefault(event_type, []).append(projector.name)
    assert all(len(names) == 1 for names in owners.values())
    catalogued: set[str] = set()
    for path in SCHEMA.glob("*events.yaml"):
        catalogued |= set(re.findall(r"tl:event_type: (\S+)", path.read_text(encoding="utf-8")))
    assert catalogued == set(owners)


def test_the_access_of_each_command_is_pinned() -> None:
    assert {c.model.__name__: c.access for c in API_COMMANDS} == {
        "DefineSchedule": "controller",
        "OpenScheduleSnapshot": "user",
        "StartScheduleSnapshot": "user",
        "PublishScheduleSnapshot": "controller",
        "VoidScheduleSnapshot": "controller",
        "LinkActivity": "user",
    }


def test_the_typed_tables_of_the_schema_hold_every_column_the_reader_produces() -> None:
    text = (SCHEMA / "snapshot_tables.yaml").read_text(encoding="utf-8")
    for key, table in TYPED_TABLES.items():
        assert f"tl:table: {table}\n" in text
        for column in TABLE_COLUMNS[key]:
            assert re.search(rf"^      {column}:$", text, re.M), (table, column)


def test_an_agent_may_propose_publishing_and_nothing_else() -> None:
    [proposal] = spec().proposable
    assert proposal.tool == "propose_publish_schedule_snapshot"
    assert proposal.access == "controller"
