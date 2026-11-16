"""The scaffold schema and fixtures (P2-I4B S1): tables, enums, workflow, numbering, words."""

from __future__ import annotations

import re
import tempfile
import tomllib
from pathlib import Path
from typing import Any

import pytest
from linkml_runtime.utils.schemaview import SchemaView
from tl_adapters.db import as_target, create_schema, open_uow
from tl_core.auth.access_words import load_access_words, table_word
from tl_core.numbering.allocator import allocate_key, segment_values
from tl_core.numbering.config import load_numbering
from tl_core.workflow.loader import load_workflow
from tl_schema.ddl_loader import statements
from tl_schema.generated.offline_classes import OFFLINE_CLASSES
from tl_schema.generated.type_labels import TYPE_LABELS

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = ROOT / "schema"
FIXTURES = SCHEMA / "fixtures"
MODULE = SCHEMA / "modules" / "scaffold"
SCAFFOLD = "scaffold.Scaffold"
INSPECTION = "scaffold.ScaffoldInspection"
TABLES = {SCAFFOLD: "cur_scaffold_scaffold", INSPECTION: "cur_scaffold_scaffold_inspection"}
CLASSES = {SCAFFOLD: "Scaffold", INSPECTION: "ScaffoldInspection"}

COLUMNS = {
    SCAFFOLD: [
        "id",
        "scope",
        "request_id",
        "for_record_id",
        "location_text",
        "elevation",
        "gridline",
        "load_class",
        "tag",
        "tagged_on",
        "last_inspected_on",
        "next_due_on",
        "flagged_due_on",
        "inspection_count",
        "modify_reason",
        "dismantle_reason",
        "last_seq",
    ],
    INSPECTION: [
        "id",
        "scope",
        "scaffold_id",
        "inspector",
        "inspected_on",
        "result",
        "tag",
        "note",
        "last_seq",
    ],
}
#: Text columns and their longest accepted value.
LENGTHS = {
    (SCAFFOLD, "location_text"): 120,
    (SCAFFOLD, "elevation"): 32,
    (SCAFFOLD, "gridline"): 32,
    (SCAFFOLD, "load_class"): 32,
    (SCAFFOLD, "modify_reason"): 300,
    (SCAFFOLD, "dismantle_reason"): 300,
    (INSPECTION, "inspector"): 64,
    (INSPECTION, "note"): 300,
}
DATES = [
    (SCAFFOLD, "tagged_on"),
    (SCAFFOLD, "last_inspected_on"),
    (SCAFFOLD, "next_due_on"),
    (SCAFFOLD, "flagged_due_on"),
    (INSPECTION, "inspected_on"),
]
INDEXES = {SCAFFOLD: ["for_record", "request"], INSPECTION: ["scaffold"]}
WORDS = {
    "scaffold.view": "read",
    "scaffold.register": "user",
    "scaffold.design": "user",
    "scaffold.erect": "user",
    "scaffold.inspect": "user",
    "scaffold.tag.green": "controller",
    "scaffold.release": "user",
    "scaffold.modify": "user",
    "scaffold.dismantle": "user",
    "scaffold.remove": "user",
}
EVENTS = {
    "Scaffold.Registered": "ScaffoldRegisteredPayload",
    "Scaffold.Designed": "ScaffoldDesignedPayload",
    "Scaffold.Erecting": "ScaffoldErectingPayload",
    "Scaffold.Inspected": "ScaffoldInspectedPayload",
    "Scaffold.Released": "ScaffoldReleasedPayload",
    "Scaffold.Modified": "ScaffoldModifiedPayload",
    "Scaffold.DismantleStarted": "ScaffoldDismantleStartedPayload",
    "Scaffold.Removed": "ScaffoldRemovedPayload",
    "Scaffold.InspectionDue": "ScaffoldInspectionDuePayload",
}
ALLOWED_MOVES = {
    ("Requested", "Designed"),
    ("Designed", "Erecting"),
    ("Erecting", "Inspected"),
    ("Modify", "Inspected"),
    ("Inspected", "In Use"),
    ("Inspected", "Modify"),
    ("In Use", "Modify"),
    ("Inspected", "Dismantle"),
    ("In Use", "Dismantle"),
    ("Modify", "Dismantle"),
    ("Dismantle", "Removed"),
    ("Requested", "Removed"),
    ("Designed", "Removed"),
}


def _view(name: str) -> Any:
    return SchemaView(str(MODULE / name))


def _slot(record_type: str, name: str) -> Any:
    return _view("scaffold.yaml").induced_slot(name, CLASSES[record_type])


def _annotation(obj: Any, tag: str) -> str | None:
    annotations: Any = getattr(obj, "annotations", None)
    if annotations is None or tag not in annotations:
        return None
    return str(annotations[tag].value)


def test_type_labels_and_offline_class_none_for_both() -> None:
    assert TYPE_LABELS[SCAFFOLD] == "Scaffold"
    assert TYPE_LABELS[INSPECTION] == "Scaffold inspection"
    assert OFFLINE_CLASSES[SCAFFOLD] == OFFLINE_CLASSES[INSPECTION] == "none"


@pytest.mark.parametrize("record_type", [SCAFFOLD, INSPECTION])
def test_table_columns_in_order_and_indexes(record_type: str) -> None:
    table = TABLES[record_type]
    sql = "\n".join(statements(table, "sqlite"))
    body = sql.split(");", 1)[0]
    columns = [line.split()[0] for line in body.splitlines()[1:] if line.strip()]
    assert columns == COLUMNS[record_type]
    for index in INDEXES[record_type]:
        assert f"ix_{table}_{index} ON {table}" in sql
    assert sql.count("CREATE INDEX") == len(INDEXES[record_type])
    for dialect in ("sqlite", "postgres"):
        assert statements(table, dialect) and statements(f"v_{table[4:]}", dialect)


def test_inspection_count_default_and_required_columns() -> None:
    sql = "\n".join(statements(TABLES[SCAFFOLD], "sqlite"))
    assert "inspection_count INTEGER NOT NULL DEFAULT 0" in sql
    assert "request_id TEXT NOT NULL" in sql and "for_record_id TEXT," in sql
    inspection = "\n".join(statements(TABLES[INSPECTION], "sqlite"))
    for column in ("scaffold_id", "inspector", "inspected_on", "result", "tag"):
        assert f"{column} TEXT NOT NULL" in inspection
    assert "note TEXT," in inspection


@pytest.mark.parametrize(("key", "limit"), sorted(LENGTHS.items()))
def test_text_columns_have_their_length_limit(key: tuple[str, str], limit: int) -> None:
    pattern = _slot(*key).pattern
    assert re.fullmatch(pattern, "x" * limit), key
    assert not re.fullmatch(pattern, "x" * (limit + 1)), key


@pytest.mark.parametrize(("record_type", "column"), DATES)
def test_dates_are_iso_dates(record_type: str, column: str) -> None:
    pattern = _slot(record_type, column).pattern
    assert re.fullmatch(pattern, "2026-12-31")
    assert not re.fullmatch(pattern, "31/12/2026")


def test_enums_and_the_counts() -> None:
    view = _view("scaffold.yaml")
    assert list(view.get_enum("TagColour").permissible_values) == ["green", "yellow", "red"]
    assert list(view.get_enum("InspectionResult").permissible_values) == [
        "pass",
        "conditional",
        "fail",
    ]
    assert _slot(SCAFFOLD, "tag").range == "TagColour" and not _slot(SCAFFOLD, "tag").required
    assert _slot(INSPECTION, "tag").range == "TagColour" and _slot(INSPECTION, "tag").required
    assert _slot(INSPECTION, "result").range == "InspectionResult"
    count = _slot(SCAFFOLD, "inspection_count")
    assert count.range == "integer" and count.minimum_value == 0 and count.required


def test_workflow_moves_and_the_one_terminal_state() -> None:
    definition = load_workflow(FIXTURES / "workflows" / "scaffold-scaffold.yaml")
    assert definition.record_type == SCAFFOLD
    assert definition.initial_state == "Requested"
    assert definition.state_names() == [
        "Requested",
        "Designed",
        "Erecting",
        "Inspected",
        "In Use",
        "Modify",
        "Dismantle",
        "Removed",
    ]
    moves = {(s, t.to) for t in definition.transitions for s in t.from_states}
    assert moves == ALLOWED_MOVES
    for refused in (("Erecting", "In Use"), ("Requested", "Inspected"), ("Removed", "Requested")):
        assert refused not in moves
    sources = {s for t in definition.transitions for s in t.from_states}
    assert [n for n in definition.state_names() if n not in sources] == ["Removed"]
    assert all(t.guards == [] for t in definition.transitions)
    assert {t.name for t in definition.transitions} == {
        "design",
        "erect",
        "pass",
        "release",
        "modify",
        "dismantle",
        "remove",
    }


def test_an_inspection_has_no_workflow() -> None:
    names = {p.name for p in (FIXTURES / "workflows").glob("scaffold-*.yaml")}
    assert names == {"scaffold-scaffold.yaml"}


@pytest.mark.parametrize(
    ("record_type", "code", "key"),
    [(SCAFFOLD, "SCF", "P123-SCF-0001"), (INSPECTION, "SCI", "P123-SCI-0001")],
)
def test_numbering_patterns_are_gap_free_and_allocate(
    record_type: str, code: str, key: str
) -> None:
    patterns = load_numbering(FIXTURES / "numbering" / "patterns.yaml")
    pattern = patterns.find("project:P123", record_type)
    assert pattern is not None and pattern.type_code == code
    assert pattern.gap_free is True and pattern.id == record_type
    assert pattern.template == "{project}-{type}-{seq:4}"
    with tempfile.TemporaryDirectory() as tmp:
        target = as_target(Path(tmp) / "ledger.db")
        create_schema(target)
        with open_uow(target) as uow:
            made = allocate_key(
                uow,
                pattern=pattern,
                scope="project:P123",
                values=segment_values(pattern, "project:P123"),
                record_id=None,
                record_type=record_type,
                actor="user:seed",
                source="test",
            )
    assert made.key == key


def test_exactly_ten_scaffold_words_with_their_table_words() -> None:
    words = load_access_words()
    scaffold = {w: t for w, t in words.items() if w.startswith("scaffold.")}
    assert scaffold == WORDS
    assert len(scaffold) == 10
    for word, table in WORDS.items():
        assert table_word(word) == table
    assert [w for w, t in WORDS.items() if t == "controller"] == ["scaffold.tag.green"]


def test_every_event_has_a_type_the_record_id_and_feed_policy_none() -> None:
    view = _view("events.yaml")
    found: dict[str, str] = {}
    for name in view.schema.classes:
        event = _annotation(view.get_class(name), "tl:event_type")
        if event is not None:
            found[event] = name
    assert found == EVENTS
    for name in EVENTS.values():
        slots = {s.name: s for s in view.class_induced_slots(name)}
        assert slots["record_id"].required
        assert slots["feed_policy"].equals_string == "none" and slots["feed_policy"].required


def test_the_inspected_event_fields() -> None:
    slots = {
        s.name: s for s in _view("events.yaml").class_induced_slots("ScaffoldInspectedPayload")
    }
    for name in ("inspection_id", "result", "tag", "inspected_on", "next_due_on"):
        assert slots[name].required, name
    assert slots["result"].range == "InspectionResult" and slots["tag"].range == "TagColour"
    due = {
        s.name: s for s in _view("events.yaml").class_induced_slots("ScaffoldInspectionDuePayload")
    }
    assert due["due_on"].required and due["state"].required


def test_every_event_tags_an_optional_at_as_valid_time_and_the_baseline_has_no_scaffold_line() -> (
    None
):
    view = _view("events.yaml")
    for cls_name in EVENTS.values():
        slots = {s.name: s for s in view.class_induced_slots(cls_name)}
        tagged = [n for n, s in slots.items() if _annotation(s, "tl:valid_time") is not None]
        assert tagged == ["at"], cls_name
        assert slots["at"].range == "datetime" and not slots["at"].required, cls_name
    inspected = {s.name: s for s in view.class_induced_slots("ScaffoldInspectedPayload")}
    for plan in ("next_due_on", "inspected_on"):
        assert _annotation(inspected[plan], "tl:valid_time") is None
    due = {s.name: s for s in view.class_induced_slots("ScaffoldInspectionDuePayload")}
    assert _annotation(due["due_on"], "tl:valid_time") is None
    baseline = tomllib.loads((ROOT / "tests" / "tools" / "valid_time_baseline.toml").read_text())
    assert not [k for k in baseline["classes"] if k.startswith("tl_mod_scaffold_events.")]
