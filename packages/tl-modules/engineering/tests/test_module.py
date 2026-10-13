"""The module package, its spec, its schema and the platform agree with one another."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import tl_mod_engineering
import yaml
from tl_core.modules import ModuleSpec
from tl_core.projection.defaults import default_registry
from tl_mod_engineering import names
from tl_mod_engineering.module import spec
from tl_schema import catalog
from tl_schema.ddl_loader import statements

ROOT = Path(__file__).resolve().parents[4]
SCHEMA = ROOT / "schema" / "modules" / "engineering"

EVENT_TYPES = {
    names.STANDARD_DEFINED,
    names.STANDARD_CLOSED,
    names.CODE_VALUE_DEFINED,
    names.CODE_VALUE_CLOSED,
    names.TAG_CLASS_DEFINED,
    names.TAG_CLASS_REVISED,
    names.TAG_CLASS_CLOSED,
    names.TAG_DEFINED,
    names.TAG_RECLASSIFIED,
    names.TAG_SUPERSEDED,
}
TABLES = {
    names.STANDARD_TABLE,
    names.CODE_VALUE_TABLE,
    names.TAG_CLASS_TABLE,
    names.TAG_TABLE,
}


def schema_classes() -> dict[str, dict[str, Any]]:
    classes: dict[str, dict[str, Any]] = {}
    for path in sorted(SCHEMA.glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        classes.update(document.get("classes") or {})
    return classes


def snake(name: str) -> str:
    out = ""
    for index, char in enumerate(name):
        if char.isupper() and index:
            out += "_"
        out += char.lower()
    return out


def test_the_package_names_its_module() -> None:
    assert tl_mod_engineering.MODULE == "engineering"


def test_the_schema_header_names_the_module() -> None:
    header = (SCHEMA / "module.yaml").read_text(encoding="utf-8")
    assert "tl:module: engineering" in header


def test_the_spec_lists_the_record_types_and_projectors_of_the_module() -> None:
    produced = spec()
    assert isinstance(produced, ModuleSpec) and produced.name == "engineering"
    assert produced.record_types == names.RECORD_TYPES
    assert all(t.startswith("engineering.") for t in produced.record_types)
    projectors = produced.projectors()
    assert [p.name for p in projectors] == [
        "engineering_standard",
        "engineering_code_value",
        "engineering_tag_class",
        "engineering_tag",
    ]
    handled: set[str] = set()
    for projector in projectors:
        handled |= projector.handles
    assert handled == EVENT_TYPES


def test_the_record_types_annotated_in_the_schema_are_the_ones_the_spec_provides() -> None:
    annotated: set[str] = set()
    for definition in schema_classes().values():
        value = (definition.get("annotations") or {}).get("tl:record_types")
        if value:
            annotated |= {part.strip() for part in str(value).split(",")}
    assert annotated == names.RECORD_TYPES


def test_every_current_state_class_has_a_generated_table_the_names_module_knows() -> None:
    tables = {
        f"cur_engineering_{snake(cls)}"
        for cls, definition in schema_classes().items()
        if (definition.get("annotations") or {}).get("tl:current_state")
    }
    assert tables == TABLES
    for table in TABLES:
        for dialect in ("sqlite", "postgres"):
            assert statements(table, dialect)[0].startswith(f"CREATE TABLE IF NOT EXISTS {table}")


def test_every_event_type_of_the_module_is_in_the_event_catalog() -> None:
    assert EVENT_TYPES <= set(catalog.event_types())


def test_the_default_registry_places_the_projectors_after_the_core_ones_and_before_the_outbox() -> (
    None
):
    order = [p.name for p in default_registry().all()]
    mine = [n for n in order if n.startswith("engineering_")]
    assert len(mine) == 4
    assert order.index("feed") < order.index(mine[0])
    assert order.index(mine[-1]) < order.index("outbox")
