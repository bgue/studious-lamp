"""The quality schema and fixtures (P2-PUNCH S1): table, workflow, numbering, words, events."""

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
from tl_schema.generated.type_labels import TYPE_LABELS

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = ROOT / "schema"
FIXTURES = SCHEMA / "fixtures"
QUALITY = SCHEMA / "modules" / "quality"
TYPE = "quality.PunchItem"
TABLE = "cur_quality_punch_item"

COLUMNS = [
    "id",
    "scope",
    "area",
    "system",
    "due_on",
    "category",
    "assignee",
    "raised_by",
    "source_id",
    "cleared_by",
    "cleared_on",
    "clear_note",
    "verified_by",
    "verified_on",
    "reopen_count",
    "last_reopen_reason",
    "void_reason",
    "last_seq",
]
#: Text columns and their longest accepted value.
LENGTHS = {
    "area": 64,
    "system": 64,
    "assignee": 120,
    "raised_by": 64,
    "cleared_by": 64,
    "verified_by": 64,
    "clear_note": 300,
    "verified_on": 10,
    "last_reopen_reason": 300,
    "void_reason": 300,
}
INDEXES = ["area", "due_on", "source", "system"]
WORDS = {
    "quality.view": "read",
    "quality.punch.raise": "user",
    "quality.punch.edit": "user",
    "quality.punch.clear": "user",
    "quality.punch.verify": "controller",
    "quality.punch.reopen": "controller",
    "quality.punch.void": "controller",
}
EVENTS = {
    "PunchItem.Raised": "PunchItemRaisedPayload",
    "PunchItem.Edited": "PunchItemEditedPayload",
    "PunchItem.Cleared": "PunchItemClearedPayload",
    "PunchItem.Verified": "PunchItemVerifiedPayload",
    "PunchItem.Reopened": "PunchItemReopenedPayload",
    "PunchItem.Voided": "PunchItemVoidedPayload",
}
ALLOWED_MOVES = {
    ("Open", "Cleared"),
    ("Cleared", "Verified"),
    ("Cleared", "Open"),
    ("Verified", "Open"),
    ("Open", "Void"),
    ("Cleared", "Void"),
}


def _view(name: str) -> Any:
    return SchemaView(str(QUALITY / name))


def _slot(name: str) -> Any:
    return _view("punch_item.yaml").induced_slot(name, "PunchItem")


def _annotation(obj: Any, tag: str) -> str | None:
    annotations: Any = getattr(obj, "annotations", None)
    if annotations is None or tag not in annotations:
        return None
    return str(annotations[tag].value)


def test_type_label_and_offline_class() -> None:
    assert TYPE_LABELS[TYPE] == "Punch item"
    assert OFFLINE_CLASSES[TYPE] == "draft_only"


def test_table_columns_in_order_and_indexes() -> None:
    sql = "\n".join(statements(TABLE, "sqlite"))
    body = sql.split(");", 1)[0]
    columns = [line.split()[0] for line in body.splitlines()[1:] if line.strip()]
    assert columns == COLUMNS
    for index in INDEXES:
        assert f"ix_{TABLE}_{index} ON {TABLE}" in sql
    assert sql.count("CREATE INDEX") == 4
    assert "category TEXT NOT NULL DEFAULT 'B'" in sql
    assert "reopen_count INTEGER NOT NULL DEFAULT 0" in sql
    for dialect in ("sqlite", "postgres"):
        assert statements("v_quality_punch_item", dialect)


@pytest.mark.parametrize(("column", "limit"), sorted(LENGTHS.items()))
def test_text_columns_have_their_length_limit(column: str, limit: int) -> None:
    slot = _slot(column)
    if column == "verified_on":
        pattern = _slot("verified_on").pattern
        assert re.fullmatch(pattern, "2026-12-03") and not re.fullmatch(pattern, "2026-12-033")
        return
    pattern = slot.pattern
    assert re.fullmatch(pattern, "x" * limit), column
    assert not re.fullmatch(pattern, "x" * (limit + 1)), column


def test_category_enum_is_a_b_c_default_b() -> None:
    enum = _view("punch_item.yaml").get_enum("PunchCategory")
    assert list(enum.permissible_values) == ["A", "B", "C"]
    slot = _slot("category")
    assert slot.range == "PunchCategory" and slot.required


def test_reopen_count_is_a_non_negative_integer() -> None:
    slot = _slot("reopen_count")
    assert slot.range == "integer" and slot.minimum_value == 0 and slot.required


def test_dates_are_iso_dates() -> None:
    for name in ("due_on", "cleared_on", "verified_on"):
        pattern = _slot(name).pattern
        assert re.fullmatch(pattern, "2026-12-31")
        assert not re.fullmatch(pattern, "31/12/2026")


def test_workflow_moves_and_terminal_state() -> None:
    definition = load_workflow(FIXTURES / "workflows" / "quality-punch-item.yaml")
    assert definition.record_type == TYPE
    assert definition.initial_state == "Open"
    assert definition.state_names() == ["Open", "Cleared", "Verified", "Void"]
    moves = {(s, t.to) for t in definition.transitions for s in t.from_states}
    assert moves == ALLOWED_MOVES
    for refused in (("Open", "Verified"), ("Verified", "Void"), ("Void", "Open")):
        assert refused not in moves
    sources = {s for t in definition.transitions for s in t.from_states}
    assert [n for n in definition.state_names() if n not in sources] == ["Void"]
    assert all(t.guards == [] for t in definition.transitions)


def test_numbering_pattern_is_gap_free_and_allocates() -> None:
    patterns = load_numbering(FIXTURES / "numbering" / "patterns.yaml")
    pattern = patterns.find("project:P123", TYPE)
    assert pattern is not None and pattern.type_code == "PUN"
    assert pattern.gap_free is True
    assert pattern.template == "{project}-{type}-{seq:4}"
    assert pattern.id == TYPE
    with tempfile.TemporaryDirectory() as tmp:
        target = as_target(Path(tmp) / "ledger.db")
        create_schema(target)
        keys: list[str] = []
        for _ in range(2):
            with open_uow(target) as uow:
                keys.append(
                    allocate_key(
                        uow,
                        pattern=pattern,
                        scope="project:P123",
                        values=segment_values(pattern, "project:P123"),
                        record_id=None,
                        record_type=TYPE,
                        actor="user:seed",
                        source="test",
                    ).key
                )
    assert keys == ["P123-PUN-0001", "P123-PUN-0002"]


def test_exactly_seven_quality_words_with_their_table_words() -> None:
    words = load_access_words()
    quality = {w: t for w, t in words.items() if w.startswith("quality.")}
    assert quality == WORDS
    assert len(quality) == 7
    for word, table in WORDS.items():
        assert table_word(word) == table


def test_every_event_has_a_type_the_record_id_and_feed_policy_none() -> None:
    view = _view("events.yaml")
    found: dict[str, str] = {}
    for name in view.schema.classes:
        cls = view.get_class(name)
        event = _annotation(cls, "tl:event_type")
        if event is not None:
            found[event] = name
    assert found == EVENTS
    for name in EVENTS.values():
        slots = {s.name: s for s in view.class_induced_slots(name)}
        assert slots["record_id"].required
        assert slots["feed_policy"].equals_string == "none" and slots["feed_policy"].required


def test_every_event_at_is_valid_time_tagged() -> None:
    view = _view("events.yaml")
    for cls_name in EVENTS.values():
        slot = {s.name: s for s in view.class_induced_slots(cls_name)}["at"]
        assert _annotation(slot, "tl:valid_time") == "at", cls_name
        assert slot.range == "datetime", cls_name
    for cls_name in ("PunchItemClearedPayload", "PunchItemVerifiedPayload"):
        assert {s.name: s for s in view.class_induced_slots(cls_name)}["at"].required
    for cls_name in (
        "PunchItemRaisedPayload",
        "PunchItemEditedPayload",
        "PunchItemReopenedPayload",
        "PunchItemVoidedPayload",
    ):
        assert not {s.name: s for s in view.class_induced_slots(cls_name)}["at"].required
    due_on = {s.name: s for s in view.class_induced_slots("PunchItemRaisedPayload")}["due_on"]
    assert _annotation(due_on, "tl:valid_time") is None


def test_the_valid_time_baseline_has_no_quality_line() -> None:
    baseline = (ROOT / "tests" / "tools" / "valid_time_baseline.toml").read_text()
    assert "tl_mod_quality_events" not in baseline
