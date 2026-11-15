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
    quality = {
        w: t for w, t in words.items() if w == "quality.view" or w.startswith("quality.punch.")
    }
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
    found = {e: n for e, n in found.items() if e.startswith("PunchItem.")}
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


# --- P2-INSP S1: checklists and inspections ---------------------------------------------------

CHK_TABLE = "cur_quality_checklist"
INS_TABLE = "cur_quality_inspection"
CHK_COLUMNS = [
    "id",
    "scope",
    "discipline",
    "checklist_version",
    "questions_json",
    "question_count",
    "supersedes_id",
    "published_by",
    "published_on",
    "retired_on",
    "last_seq",
]
INS_COLUMNS = [
    "id",
    "scope",
    "subject_id",
    "for_iwp_id",
    "checklist_id",
    "checklist_version",
    "point",
    "area",
    "planned_on",
    "scheduled_for",
    "inspector",
    "result",
    "done_at",
    "answers_json",
    "note",
    "recorded_by",
    "verified_by",
    "verified_on",
    "reinspection_of_id",
    "cancel_reason",
    "punch_count",
    "last_seq",
]
CHK_INDEXES = ["discipline", "supersedes"]
INS_INDEXES = ["area", "checklist", "for_iwp", "reinspection_of", "scheduled_for", "subject"]
INSP_WORDS = {
    "quality.checklist.edit": "user",
    "quality.checklist.publish": "controller",
    "quality.inspection.plan": "user",
    "quality.inspection.record": "user",
    "quality.inspection.verify": "controller",
    "quality.inspection.cancel": "controller",
}
INSP_EVENTS = {
    "Checklist.Created": (
        "ChecklistCreatedPayload",
        {"discipline", "questions", "question_count", "version", "supersedes_id"},
    ),
    "Checklist.Edited": ("ChecklistEditedPayload", {"changes"}),
    "Checklist.Published": ("ChecklistPublishedPayload", {"published_on"}),
    "Checklist.Retired": ("ChecklistRetiredPayload", {"retired_on"}),
    "Inspection.Planned": (
        "InspectionPlannedPayload",
        {"subject_id", "for_iwp_id", "point", "area", "planned_on", "reinspection_of_id"},
    ),
    "Inspection.Scheduled": (
        "InspectionScheduledPayload",
        {"checklist_id", "checklist_version", "scheduled_for", "inspector"},
    ),
    "Inspection.ResultRecorded": (
        "InspectionResultRecordedPayload",
        {"answers", "result", "done_at", "note", "punch_item_ids"},
    ),
    "Inspection.Verified": ("InspectionVerifiedPayload", {"verified_on"}),
    "Inspection.Cancelled": ("InspectionCancelledPayload", {"reason"}),
}


def _columns(table: str) -> list[str]:
    body = "\n".join(statements(table, "sqlite")).split(");", 1)[0]
    return [line.split()[0] for line in body.splitlines()[1:] if line.strip()]


def test_new_classes_tables_indexes_and_offline_classes() -> None:
    assert OFFLINE_CLASSES["quality.Checklist"] == "none"
    assert OFFLINE_CLASSES["quality.Inspection"] == "draft_only"
    assert _columns(CHK_TABLE) == CHK_COLUMNS
    assert _columns(INS_TABLE) == INS_COLUMNS
    for table, indexes in ((CHK_TABLE, CHK_INDEXES), (INS_TABLE, INS_INDEXES)):
        sql = "\n".join(statements(table, "sqlite"))
        for index in indexes:
            assert f"ix_{table}_{index} ON {table}" in sql
        assert sql.count("CREATE INDEX") == len(indexes)
        for dialect in ("sqlite", "postgres"):
            assert statements(table, dialect)
    chk = "\n".join(statements(CHK_TABLE, "sqlite"))
    assert "checklist_version INTEGER NOT NULL DEFAULT 1" in chk
    assert "questions_json TEXT NOT NULL DEFAULT '[]'" in chk
    ins = "\n".join(statements(INS_TABLE, "sqlite"))
    assert "punch_count INTEGER NOT NULL DEFAULT 0" in ins
    assert "answers_json TEXT NOT NULL DEFAULT '[]'" in ins
    for name in ("v_quality_checklist", "v_quality_inspection"):
        for dialect in ("sqlite", "postgres"):
            assert statements(name, dialect)


def test_the_two_enums_and_their_values() -> None:
    view = _view("inspection.yaml")
    assert list(view.get_enum("InspectionPoint").permissible_values) == [
        "hold",
        "witness",
        "review",
        "surveillance",
    ]
    assert list(view.get_enum("InspectionOutcome").permissible_values) == [
        "accept",
        "reject",
        "conditional",
    ]
    assert view.induced_slot("point", "Inspection").range == "InspectionPoint"
    result = view.induced_slot("result", "Inspection")
    assert result.range == "InspectionOutcome" and not result.required


def test_new_slot_limits() -> None:
    chk = _view("checklist.yaml")
    ins = _view("inspection.yaml")
    version = chk.induced_slot("version", "Checklist")
    assert version.minimum_value == 1 and version.required
    assert chk.induced_slot("question_count", "Checklist").minimum_value == 0
    assert ins.induced_slot("punch_count", "Inspection").minimum_value == 0
    for view, cls, name, limit in (
        (chk, "Checklist", "discipline", 64),
        (ins, "Inspection", "area", 64),
        (ins, "Inspection", "inspector", 120),
        (ins, "Inspection", "note", 1000),
        (ins, "Inspection", "cancel_reason", 300),
    ):
        pattern = view.induced_slot(name, cls).pattern
        assert re.fullmatch(pattern, "x" * limit), name
        assert not re.fullmatch(pattern, "x" * (limit + 1)), name


def test_nine_new_events_with_their_payload_fields() -> None:
    view = _view("events.yaml")
    found: dict[str, str] = {}
    for name in view.schema.classes:
        event = _annotation(view.get_class(name), "tl:event_type")
        if event is not None and not event.startswith("PunchItem."):
            found[event] = name
    assert found == {e: c for e, (c, _) in INSP_EVENTS.items()}
    for cls_name, fields in INSP_EVENTS.values():
        slots = {s.name: s for s in view.class_induced_slots(cls_name)}
        assert set(slots) - {"record_id", "feed_policy", "at"} == fields, cls_name
        assert slots["record_id"].required
        assert slots["feed_policy"].equals_string == "none" and slots["feed_policy"].required


def test_new_events_valid_time_and_json_tags() -> None:
    view = _view("events.yaml")
    for cls_name, _ in INSP_EVENTS.values():
        slots = {s.name: s for s in view.class_induced_slots(cls_name)}
        if cls_name in ("InspectionResultRecordedPayload", "InspectionVerifiedPayload"):
            assert "at" not in slots
            continue
        assert _annotation(slots["at"], "tl:valid_time") == "at", cls_name
    recorded = {s.name: s for s in view.class_induced_slots("InspectionResultRecordedPayload")}
    verified = {s.name: s for s in view.class_induced_slots("InspectionVerifiedPayload")}
    assert _annotation(recorded["done_at"], "tl:valid_time") == "at"
    assert _annotation(verified["verified_on"], "tl:valid_time") == "at"
    for name in ("answers", "punch_item_ids"):
        assert _annotation(recorded[name], "tl:json") == "True"
    created = {s.name: s for s in view.class_induced_slots("ChecklistCreatedPayload")}
    assert _annotation(created["questions"], "tl:json") == "True"


def _moves(file: str) -> tuple[Any, set[tuple[str, str]]]:
    definition = load_workflow(FIXTURES / "workflows" / file)
    return definition, {(s, t.to) for t in definition.transitions for s in t.from_states}


def test_checklist_workflow() -> None:
    definition, moves = _moves("quality-checklist.yaml")
    assert definition.record_type == "quality.Checklist"
    assert definition.initial_state == "Draft"
    assert moves == {("Draft", "Published"), ("Published", "Retired"), ("Draft", "Retired")}
    sources = {s for t in definition.transitions for s in t.from_states}
    assert [n for n in definition.state_names() if n not in sources] == ["Retired"]
    assert ("Retired", "Draft") not in moves and ("Published", "Draft") not in moves
    assert all(t.guards == [] for t in definition.transitions)


def test_inspection_workflow() -> None:
    definition, moves = _moves("quality-inspection.yaml")
    assert definition.record_type == "quality.Inspection"
    assert definition.initial_state == "Planned"
    assert moves == {
        ("Planned", "Scheduled"),
        ("Scheduled", "Scheduled"),
        ("Scheduled", "Done"),
        ("Done", "Verified"),
        ("Planned", "Cancelled"),
        ("Scheduled", "Cancelled"),
    }
    assert ("Done", "Planned") not in moves and ("Planned", "Done") not in moves
    sources = {s for t in definition.transitions for s in t.from_states}
    assert sorted(n for n in definition.state_names() if n not in sources) == [
        "Cancelled",
        "Verified",
    ]
    assert all(t.guards == [] for t in definition.transitions)


@pytest.mark.parametrize(
    ("type_code", "record_type"), [("CHK", "quality.Checklist"), ("INS", "quality.Inspection")]
)
def test_new_numbering_patterns_allocate(type_code: str, record_type: str) -> None:
    patterns = load_numbering(FIXTURES / "numbering" / "patterns.yaml")
    pattern = patterns.find("project:P123", record_type)
    assert pattern is not None and pattern.type_code == type_code
    assert pattern.template == "{project}-{type}-{seq:4}"
    with tempfile.TemporaryDirectory() as tmp:
        target = as_target(Path(tmp) / "ledger.db")
        create_schema(target)
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
    assert key == f"P123-{type_code}-0001"


def test_six_new_access_words_and_the_punch_words_unchanged() -> None:
    words = load_access_words()
    quality = {w: t for w, t in words.items() if w.startswith("quality.")}
    assert quality == {**WORDS, **INSP_WORDS}
    assert len(quality) == 13
    for word, table in INSP_WORDS.items():
        assert table_word(word) == table


def test_the_three_fixtures_parse() -> None:
    import yaml

    files = sorted((FIXTURES / "quality" / "checklists").glob("*.yaml"))
    assert [f.stem for f in files] == ["flange-makeup", "hydrotest-precheck", "scaffold-handover"]
    kinds = {"yes_no_na", "number", "text", "choice"}
    fails = set()
    for file in files:
        data = yaml.safe_load(file.read_text())
        questions = data["questions"]
        assert 6 <= len(questions) <= 10, file.name
        ids = [q["id"] for q in questions]
        assert len(ids) == len(set(ids)), file.name
        for q in questions:
            assert set(q) == {
                "id",
                "text",
                "kind",
                "required",
                "unit",
                "min",
                "max",
                "choices",
                "fails_when",
            }
            assert q["kind"] in kinds, (file.name, q["id"])
            fails.add(q["fails_when"])
    assert fails == {None, "no", "out_of_range"}
    all_kinds = {q["kind"] for f in files for q in yaml.safe_load(f.read_text())["questions"]}
    assert all_kinds == kinds


def test_the_required_for_iwp_setting_exists() -> None:
    import yaml

    data = yaml.safe_load((SCHEMA / "settings" / "platform.yaml").read_text())
    found = [s for s in data["settings"] if s["key"] == "quality.inspections.required_for_iwp"]
    assert len(found) == 1
    setting = found[0]
    assert setting["type"] == "bool" and setting["default"] is False
    assert setting["scopes"] == ["platform", "company", "project"] and setting["lockable"] is True
