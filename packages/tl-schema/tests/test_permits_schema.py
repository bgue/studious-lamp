"""The permits schema and fixtures (P2-PTW S1): tables, enums, events, workflows, numbering."""

from __future__ import annotations

import re
import tempfile
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

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = ROOT / "schema"
FIXTURES = SCHEMA / "fixtures"
PERMITS = SCHEMA / "modules" / "permits"

CLASSES = {
    "permits.Permit": ("cur_permits_permit", "permit.yaml", "Permit"),
    "permits.Isolation": ("cur_permits_isolation", "isolation.yaml", "Isolation"),
    "permits.GasTest": ("cur_permits_gas_test", "gas_test.yaml", "GasTest"),
}
INDEXES = {
    "cur_permits_permit": ["area", "for_record", "permit_type", "valid_until"],
    "cur_permits_isolation": ["point_record"],
    "cur_permits_gas_test": ["permit", "taken_at"],
}
ENUMS = {
    "permit.yaml": (
        "PermitType",
        ["hot_work", "confined_space", "work_at_height", "excavation", "isolation", "general"],
    ),
    "isolation.yaml": ("EnergyKind", ["electrical", "mechanical", "process", "other"]),
    "gas_test.yaml": ("GasResult", ["pass", "fail"]),
}
EVENTS = {
    "Permit.Requested": {
        "permit_type",
        "for_record_id",
        "area",
        "location_text",
        "holder",
        "needed_from",
        "needed_until",
    },
    "Permit.Approved": set(),
    "Permit.Rejected": {"reason"},
    "Permit.Issued": {"issued_at", "valid_until", "precautions"},
    "Permit.Revalidated": {"at", "valid_until"},
    "Permit.Suspended": {"reason", "gas_test_id"},
    "Permit.Resumed": {"at", "valid_until"},
    "Permit.HandedBack": {"note"},
    "Permit.Closed": set(),
    "Permit.Cancelled": {"reason"},
    "Permit.Lapsed": {"valid_until"},
    "Permit.IsolationLinked": {"isolation_id"},
    "Permit.IsolationUnlinked": {"isolation_id"},
    "Isolation.Applied": {
        "point_text",
        "point_record_id",
        "energy",
        "method",
        "lock_number",
        "tag_number",
        "applied_at",
    },
    "Isolation.Verified": {"verified_at"},
    "Isolation.Removed": {"removed_at"},
    "GasTest.Recorded": {
        "permit_id",
        "taken_at",
        "tester",
        "instrument_text",
        "o2_pct",
        "lel_pct",
        "h2s_ppm",
        "co_ppm",
        "result",
        "note",
    },
}
#: The one slot of each event that carries the valid-time tag (ADR-0026).
VALID_TIME = {
    "Permit.Issued": "issued_at",
    "Permit.Revalidated": "at",
    "Permit.Resumed": "at",
    "Isolation.Applied": "applied_at",
    "Isolation.Verified": "verified_at",
    "Isolation.Removed": "removed_at",
    "GasTest.Recorded": "taken_at",
}
PERMIT_MOVES = {
    ("Requested", "Approved"),
    ("Requested", "Rejected"),
    ("Approved", "Active"),
    ("Active", "Active"),
    ("Active", "Suspended"),
    ("Suspended", "Active"),
    ("Active", "Handed back"),
    ("Suspended", "Handed back"),
    ("Handed back", "Closed"),
    ("Requested", "Cancelled"),
    ("Approved", "Cancelled"),
}
ISOLATION_MOVES = {("Applied", "Verified"), ("Applied", "Removed"), ("Verified", "Removed")}
WORDS = {
    "permits.view": "read",
    "permits.request": "user",
    "permits.revalidate": "user",
    "permits.suspend": "user",
    "permits.handback": "user",
    "permits.isolation.apply": "user",
    "permits.gastest.record": "user",
    "permits.approve": "controller",
    "permits.issue": "controller",
    "permits.resume": "controller",
    "permits.close": "controller",
    "permits.isolation.verify": "controller",
}


def _view(name: str) -> Any:
    return SchemaView(str(PERMITS / name))


def _annotation(obj: Any, tag: str) -> str | None:
    annotations: Any = getattr(obj, "annotations", None)
    if annotations is None or tag not in annotations:
        return None
    return str(annotations[tag].value)


def _events() -> dict[str, str]:
    view = _view("events.yaml")
    found: dict[str, str] = {}
    for name in view.schema.classes:
        event = _annotation(view.get_class(name), "tl:event_type")
        if event is not None:
            found[event] = name
    return found


def test_three_classes_with_their_tables_and_offline_class_none() -> None:
    for record_type, (table, file, cls) in CLASSES.items():
        assert OFFLINE_CLASSES[record_type] == "none", record_type
        assert _annotation(_view(file).get_class(cls), "tl:table") == table
        sql = "\n".join(statements(table, "sqlite"))
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
        for dialect in ("sqlite", "postgres"):
            assert statements(table.replace("cur_", "v_"), dialect)
    assert len(CLASSES) == 3


@pytest.mark.parametrize(("table", "indexes"), sorted(INDEXES.items()))
def test_indexes(table: str, indexes: list[str]) -> None:
    sql = "\n".join(statements(table, "sqlite"))
    for index in indexes:
        assert f"ix_{table}_{index} ON {table}" in sql
    assert sql.count("CREATE INDEX") == len(indexes)


def test_permit_columns_and_defaults() -> None:
    sql = "\n".join(statements("cur_permits_permit", "sqlite"))
    assert "permit_type TEXT NOT NULL" in sql
    assert "precautions_json TEXT NOT NULL DEFAULT '[]'" in sql
    assert "revalidation_count INTEGER NOT NULL DEFAULT 0" in sql
    for column in ("valid_until", "lapse_flagged_for", "issued_at", "last_revalidated_at"):
        assert f"  {column} TEXT" in sql
    view = _view("permit.yaml")
    assert view.induced_slot("revalidation_count", "Permit").minimum_value == 0
    gas = _view("gas_test.yaml")
    for name in ("o2_pct", "lel_pct", "h2s_ppm", "co_ppm"):
        slot = gas.induced_slot(name, "GasTest")
        assert slot.range == "decimal" and slot.minimum_value == 0 and not slot.required


LENGTHS = {
    ("permit.yaml", "Permit"): {
        "area": 64,
        "location_text": 120,
        "holder": 120,
        "suspend_reason": 300,
        "handback_note": 300,
        "reject_reason": 300,
        "cancel_reason": 300,
    },
    ("isolation.yaml", "Isolation"): {
        "point_text": 120,
        "method": 120,
        "lock_number": 32,
        "tag_number": 32,
    },
    ("gas_test.yaml", "GasTest"): {"tester": 120, "instrument_text": 64, "note": 300},
}


@pytest.mark.parametrize(
    ("file", "cls", "column", "limit"),
    [(f, c, col, n) for (f, c), cols in LENGTHS.items() for col, n in sorted(cols.items())],
)
def test_text_columns_have_their_length_limit(file: str, cls: str, column: str, limit: int) -> None:
    pattern = _view(file).induced_slot(column, cls).pattern
    assert re.fullmatch(pattern, "x" * limit), column
    assert not re.fullmatch(pattern, "x" * (limit + 1)), column


@pytest.mark.parametrize(("file", "enum"), sorted(ENUMS.items()))
def test_enums_and_their_values(file: str, enum: tuple[str, list[str]]) -> None:
    name, values = enum
    assert list(_view(file).get_enum(name).permissible_values) == values


def test_seventeen_event_types_with_their_payload_fields() -> None:
    found = _events()
    assert set(found) == set(EVENTS) and len(found) == 17
    view = _view("events.yaml")
    for event, fields in EVENTS.items():
        slots = {s.name: s for s in view.class_induced_slots(found[event])}
        assert fields <= set(slots), event
        assert slots["record_id"].required, event
        assert slots["feed_policy"].equals_string == "none" and slots["feed_policy"].required


def test_valid_time_is_tagged_on_one_slot_per_event() -> None:
    view = _view("events.yaml")
    found = _events()
    for event, cls in found.items():
        tagged = [
            s.name
            for s in view.class_induced_slots(cls)
            if _annotation(s, "tl:valid_time") is not None
        ]
        assert tagged == [VALID_TIME.get(event, "at")], event
    slots = {s.name: s for s in view.class_induced_slots(found["Permit.Issued"])}
    assert _annotation(slots["valid_until"], "tl:valid_time") is None
    assert slots["issued_at"].required and slots["precautions"].required


def test_the_baseline_names_no_permits_class() -> None:
    baseline = (ROOT / "tests" / "tools" / "valid_time_baseline.toml").read_text()
    assert "tl_mod_permits" not in baseline


def _moves(name: str) -> tuple[Any, set[tuple[str, str]]]:
    definition = load_workflow(FIXTURES / "workflows" / name)
    return definition, {(s, t.to) for t in definition.transitions for s in t.from_states}


def test_permit_workflow_moves() -> None:
    definition, moves = _moves("permits-permit.yaml")
    assert definition.record_type == "permits.Permit"
    assert definition.initial_state == "Requested"
    assert definition.state_names() == [
        "Requested",
        "Approved",
        "Active",
        "Suspended",
        "Handed back",
        "Closed",
        "Rejected",
        "Cancelled",
    ]
    assert moves == PERMIT_MOVES
    assert {t.name for t in definition.transitions} == {
        "approve",
        "reject",
        "issue",
        "revalidate",
        "suspend",
        "resume",
        "hand_back",
        "close",
        "cancel",
    }
    for refused in (
        ("Requested", "Active"),
        ("Suspended", "Closed"),
        ("Handed back", "Active"),
        ("Approved", "Rejected"),
    ):
        assert refused not in moves
    sources = {s for s, _ in moves}
    assert [n for n in definition.state_names() if n not in sources] == [
        "Closed",
        "Rejected",
        "Cancelled",
    ]
    assert all(t.guards == [] for t in definition.transitions)
    assert "Lapsed" not in definition.state_names()


def test_isolation_workflow_moves() -> None:
    definition, moves = _moves("permits-isolation.yaml")
    assert definition.record_type == "permits.Isolation"
    assert definition.initial_state == "Applied"
    assert definition.state_names() == ["Applied", "Verified", "Removed"]
    assert moves == ISOLATION_MOVES
    assert not {s for s, _ in moves} & {"Removed"}
    assert all(t.guards == [] for t in definition.transitions)


def test_numbering_patterns_allocate_the_three_keys() -> None:
    patterns = load_numbering(FIXTURES / "numbering" / "patterns.yaml")
    expected = {"permits.Permit": "PTW", "permits.Isolation": "ISL", "permits.GasTest": "GAS"}
    with tempfile.TemporaryDirectory() as tmp:
        target = as_target(Path(tmp) / "ledger.db")
        create_schema(target)
        for record_type, code in expected.items():
            pattern = patterns.find("project:P123", record_type)
            assert pattern is not None and pattern.type_code == code
            assert pattern.template == "{project}-{type}-{seq:4}" and pattern.id == record_type
            with open_uow(target) as uow:
                key = allocate_key(
                    uow,
                    pattern=pattern,
                    scope="project:P123",
                    values=segment_values(pattern, "project:P123"),
                    record_id=None,
                    record_type=record_type,
                    actor="user:seed",
                    source="test",
                ).key
            assert key == f"P123-{code}-0001"


def test_exactly_twelve_permits_words_with_their_table_words() -> None:
    permits = {w: t for w, t in load_access_words().items() if w.startswith("permits.")}
    assert permits == WORDS and len(permits) == 12
    for word, table in WORDS.items():
        assert table_word(word) == table
