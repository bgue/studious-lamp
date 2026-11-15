"""The forms schema and fixtures (P2-FORMS S2): tables, enums, events, workflows, numbering."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any

import pytest
import yaml
from linkml_runtime.utils.schemaview import SchemaView
from tl_adapters.db import as_target, create_schema, open_uow
from tl_core.numbering.allocator import allocate_key, segment_values
from tl_core.numbering.config import load_numbering
from tl_core.workflow.loader import load_workflow
from tl_schema.ddl_loader import statements
from tl_schema.generated.offline_classes import OFFLINE_CLASSES
from tl_schema.generators.ddl_types import Dialect

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = ROOT / "schema"
FIXTURES = SCHEMA / "fixtures"
FORMS = SCHEMA / "modules" / "forms"
GENERATED = Path(__file__).resolve().parents[1] / "src" / "tl_schema" / "generated"

HASH = "ab" * 32
TABLES = {
    "forms.Template": "cur_forms_template",
    "forms.Submission": "cur_forms_submission",
    "forms.IntakeCode": "cur_forms_intake_code",
    "forms.IntakeItem": "cur_forms_intake_item",
}
BODY = "forms_intake_body"
CLASSES = {
    "template.yaml": "Template",
    "submission.yaml": "Submission",
    "intake_code.yaml": "IntakeCode",
    "intake_item.yaml": "IntakeItem",
    "intake_body.yaml": "IntakeBody",
}
COLUMNS = {
    "cur_forms_template": [
        "id",
        "scope",
        "template_version",
        "format_version",
        "form_fields_json",
        "field_count",
        "content_hash",
        "supersedes_id",
        "bound_record_type",
        "answer_class",
        "intake",
        "purpose",
        "accepts_as_json",
        "published_on",
        "retired_on",
        "last_seq",
    ],
    "cur_forms_submission": [
        "id",
        "scope",
        "template_id",
        "template_version",
        "template_hash",
        "subject_id",
        "answers_json",
        "answer_class",
        "draft_saves",
        "author",
        "submitted_on",
        "reviewed_by",
        "reviewed_on",
        "review_note",
        "void_reason",
        "last_seq",
    ],
    "cur_forms_intake_code": [
        "id",
        "scope",
        "code_hash",
        "template_id",
        "template_version",
        "template_hash",
        "context_id",
        "context_type",
        "heading",
        "controller_role",
        "issued_by",
        "issued_at",
        "expires_on",
        "revoked_at",
        "revoked_by",
        "last_seq",
    ],
    "cur_forms_intake_item": [
        "id",
        "scope",
        "code_id",
        "template_id",
        "template_version",
        "template_hash",
        "body_mac",
        "body_bytes",
        "received_at",
        "accepted_as",
        "accepted_by",
        "accepted_on",
        "on_behalf_of_claim_json",
        "rejected_reason",
        "rejected_by",
        "purged_at",
        "last_seq",
    ],
    BODY: ["item_id", "code_id", "salt", "body", "received_at"],
}
#: Each event: the payload class and the slots besides `record_id` and `feed_policy`.
EVENTS: dict[str, tuple[str, set[str]]] = {
    "Template.Created": (
        "TemplateCreatedPayload",
        {
            "format_version",
            "form_fields",
            "field_count",
            "version",
            "supersedes_id",
            "bound_record_type",
            "answer_class",
            "intake",
            "purpose",
            "accepts_as",
        },
    ),
    "Template.Edited": ("TemplateEditedPayload", {"changes"}),
    "Template.Published": ("TemplatePublishedPayload", {"published_on", "content_hash"}),
    "Template.Retired": ("TemplateRetiredPayload", {"retired_on"}),
    "Submission.DraftSaved": (
        "SubmissionDraftSavedPayload",
        {
            "template_id",
            "template_version",
            "template_hash",
            "subject_id",
            "answers",
            "answer_class",
            "save_no",
        },
    ),
    "Submission.DraftDiscarded": ("SubmissionDraftDiscardedPayload", set()),
    "Submission.Submitted": (
        "SubmissionSubmittedPayload",
        {
            "template_id",
            "template_version",
            "template_hash",
            "subject_id",
            "answers",
            "answer_class",
            "submitted_on",
        },
    ),
    "Submission.Accepted": ("SubmissionAcceptedPayload", {"note"}),
    "Submission.Returned": ("SubmissionReturnedPayload", {"note"}),
    "Submission.Voided": ("SubmissionVoidedPayload", {"reason"}),
    "IntakeCode.Issued": (
        "IntakeCodeIssuedPayload",
        {
            "code_hash",
            "template_id",
            "template_version",
            "template_hash",
            "context_id",
            "context_type",
            "heading",
            "controller_role",
            "expires_on",
        },
    ),
    "IntakeCode.Revoked": ("IntakeCodeRevokedPayload", {"reason"}),
    "IntakeItem.Received": (
        "IntakeItemReceivedPayload",
        {
            "item_id",
            "code_id",
            "template_id",
            "template_version",
            "template_hash",
            "body_mac",
            "body_bytes",
            "received_at",
        },
    ),
    "IntakeItem.Accepted": (
        "IntakeItemAcceptedPayload",
        {"accepted_as", "on_behalf_of_claim", "cause_event_id"},
    ),
    "IntakeItem.Rejected": ("IntakeItemRejectedPayload", {"reason"}),
    "IntakeItem.Purged": ("IntakeItemPurgedPayload", {"purged_at"}),
}
JSON_SLOTS = {
    "TemplateCreatedPayload": {"form_fields", "accepts_as"},
    "TemplateEditedPayload": {"changes"},
    "SubmissionDraftSavedPayload": {"answers"},
    "SubmissionSubmittedPayload": {"answers"},
    "IntakeItemAcceptedPayload": {"on_behalf_of_claim"},
}
FORBIDDEN = {"code", "token", "url", "salt", "body"}


def _sqlite(table: str) -> str:
    return "\n".join(statements(table, "sqlite"))


def _columns(table: str, dialect: Dialect = "sqlite") -> list[str]:
    body = "\n".join(statements(table, dialect)).split(");", 1)[0]
    return [line.split()[0] for line in body.splitlines()[1:] if line.strip()]


def _view(name: str) -> Any:
    return SchemaView(str(FORMS / name))


def _annotation(obj: Any, tag: str) -> str | None:
    annotations: Any = getattr(obj, "annotations", None)
    if annotations is None or tag not in annotations:
        return None
    return str(annotations[tag].value)


def _event_schema(event: str) -> dict[str, Any]:
    path = GENERATED / "catalog" / "schemas" / f"{event}.v1.json"
    whole = json.loads(path.read_text())
    return whole["properties"]["data"]["properties"]["detail"]


def _enum_of(prop: dict[str, Any]) -> list[str]:
    """The enum of a payload property, whether it is required or nullable (`anyOf`)."""
    for part in prop.get("anyOf", [prop]):
        if "enum" in part:
            return list(part["enum"])
    raise AssertionError(prop)


def test_five_classes_five_tables_and_their_columns() -> None:
    for table, columns in COLUMNS.items():
        for dialect in ("sqlite", "postgres"):
            assert _columns(table, dialect) == columns, (table, dialect)
    for record_type, table in TABLES.items():
        assert f"CREATE TABLE IF NOT EXISTS {table}" in _sqlite(table), record_type
    assert f"CREATE TABLE IF NOT EXISTS {BODY}" in _sqlite(BODY)
    for name, cls in CLASSES.items():
        assert cls in _view(name).all_classes(), cls


def test_the_indexes() -> None:
    sql = {t: _sqlite(t) for t in COLUMNS}
    code = sql["cur_forms_intake_code"]
    assert (
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_forms_intake_code_code_hash "
        "ON cur_forms_intake_code (code_hash)" in code
    )
    assert "ON cur_forms_intake_code (context_id)" in code
    assert "ON cur_forms_template (content_hash)" in sql["cur_forms_template"]
    assert "ON cur_forms_template (supersedes_id)" in sql["cur_forms_template"]
    assert "ON cur_forms_submission (template_id)" in sql["cur_forms_submission"]
    assert "ON cur_forms_submission (subject_id)" in sql["cur_forms_submission"]
    assert "ON cur_forms_intake_item (code_id)" in sql["cur_forms_intake_item"]
    assert "ON cur_forms_intake_item (received_at)" in sql["cur_forms_intake_item"]
    body = sql[BODY]
    assert "UNIQUE INDEX IF NOT EXISTS ux_forms_intake_body_item_id" in body
    assert "ON forms_intake_body (item_id)" in body
    assert "ON forms_intake_body (code_id)" in body
    assert "ON forms_intake_body (received_at)" in body
    for table in COLUMNS:
        postgres = "\n".join(statements(table, "postgres"))
        assert postgres.count("INDEX") == sql[table].count("INDEX"), table


def test_the_json_columns_are_json_in_both_dialects() -> None:
    pg = {t: "\n".join(statements(t, "postgres")) for t in COLUMNS}
    assert "form_fields_json JSONB" in pg["cur_forms_template"]
    assert "accepts_as_json JSONB" in pg["cur_forms_template"]
    assert "answers_json JSONB" in pg["cur_forms_submission"]
    assert "on_behalf_of_claim_json JSONB" in pg["cur_forms_intake_item"]


def test_the_four_enums_and_their_values() -> None:
    template = _view("template.yaml")
    item = _view("intake_item.yaml")

    def values(view: Any, name: str) -> list[str]:
        return list(view.get_enum(name).permissible_values)

    assert values(template, "AnswerClass") == ["internal", "restricted", "privileged"]
    assert values(template, "IntakeFlag") == ["public"]
    assert values(template, "IntakePurpose") == ["request", "sign_on"]
    assert values(item, "IntakeRejectReason") == ["spam", "duplicate", "not_ours", "unclear"]
    props = _event_schema("Template.Created")["properties"]
    assert _enum_of(props["answer_class"]) == ["internal", "restricted", "privileged"]
    assert _enum_of(props["intake"]) == ["public"]
    assert _enum_of(props["purpose"]) == ["request", "sign_on"]
    reason = _event_schema("IntakeItem.Rejected")["properties"]["reason"]
    assert _enum_of(reason) == ["spam", "duplicate", "not_ours", "unclear"]


def test_template_slot_bounds() -> None:
    view = _view("template.yaml")
    version = view.induced_slot("version", "Template")
    assert (version.minimum_value, version.required) == (1, True)
    assert _annotation(version, "tl:column") == "template_version"
    fmt = view.induced_slot("format_version", "Template")
    assert (fmt.minimum_value, fmt.maximum_value) == (1, 2)
    assert view.induced_slot("field_count", "Template").minimum_value == 0
    fields = view.induced_slot("form_fields", "Template")
    assert fields.required and _annotation(fields, "tl:json") == "True"
    assert view.induced_slot("content_hash", "Template").pattern == "^[0-9a-f]{64}$"
    assert view.induced_slot("bound_record_type", "Template").pattern == "^.{1,64}$"
    assert _annotation(view.induced_slot("accepts_as", "Template"), "tl:json") == "True"
    saves = _view("submission.yaml").induced_slot("draft_saves", "Submission")
    assert (saves.minimum_value, saves.required) == (0, True)
    assert _view("intake_code.yaml").induced_slot("expires_on", "IntakeCode").required
    body = _view("intake_body.yaml").induced_slot("body", "IntakeBody")
    assert body.pattern == "^[\\s\\S]{1,8192}$"
    assert _view("intake_body.yaml").induced_slot("salt", "IntakeBody").pattern == "^[0-9a-f]{32}$"


def test_offline_classes() -> None:
    assert OFFLINE_CLASSES["forms.Template"] == "none"
    assert OFFLINE_CLASSES["forms.Submission"] == "draft_only"
    assert OFFLINE_CLASSES["forms.IntakeCode"] == "none"
    assert OFFLINE_CLASSES["forms.IntakeItem"] == "none"
    # the operational table is no record type, so it has no entry of its own
    assert not [t for t in OFFLINE_CLASSES if t.endswith("IntakeBody")]


def test_sixteen_event_types_with_their_payload_fields() -> None:
    assert len(EVENTS) == 16
    view = SchemaView(str(FORMS / "events.yaml"))
    for event, (cls, slots) in EVENTS.items():
        schema = _event_schema(event)
        props = set(schema["properties"])
        assert props == slots | {"record_id", "feed_policy"}, event
        assert "record_id" in schema["required"], event
        assert schema["properties"]["feed_policy"]["const"] == "none", event
        induced = {s.name: s for s in view.class_induced_slots(cls)}
        assert _annotation(view.get_class(cls), "tl:event_type") == event
        for name in JSON_SLOTS.get(cls, set()):
            assert _annotation(induced[name], "tl:json") == "True", (cls, name)
        for slot in induced.values():  # nothing is tagged as valid time (ADR-0026)
            assert _annotation(slot, "tl:valid_time") is None, (cls, slot.name)


def test_the_four_workflows() -> None:
    for file, moves, record_type, initial, final in (
        (
            "forms-template.yaml",
            {("Draft", "Published"), ("Published", "Retired"), ("Draft", "Retired")},
            "forms.Template",
            "Draft",
            ["Retired"],
        ),
        (
            "forms-submission.yaml",
            {
                ("Draft", "Submitted"),
                ("Returned", "Submitted"),
                ("Submitted", "Accepted"),
                ("Submitted", "Returned"),
                ("Submitted", "Voided"),
                ("Accepted", "Voided"),
                ("Returned", "Voided"),
                ("Draft", "Discarded"),
            },
            "forms.Submission",
            "Draft",
            ["Discarded", "Voided"],  # an accepted form can only be voided
        ),
        (
            "forms-intake-code.yaml",
            {("Active", "Revoked")},
            "forms.IntakeCode",
            "Active",
            ["Revoked"],
        ),
        (
            "forms-intake-item.yaml",
            {("Pending", "Accepted"), ("Pending", "Rejected")},
            "forms.IntakeItem",
            "Pending",
            ["Accepted", "Rejected"],
        ),
    ):
        definition = load_workflow(FIXTURES / "workflows" / file)
        found = {(s, t.to) for t in definition.transitions for s in t.from_states}
        assert definition.record_type == record_type, file
        assert definition.initial_state == initial, file
        assert found == moves, file
        sources = {s for t in definition.transitions for s in t.from_states}
        assert sorted(n for n in definition.state_names() if n not in sources) == final, file
        assert all(t.guards == [] for t in definition.transitions), file


def test_the_refused_moves() -> None:
    def moves(file: str) -> set[tuple[str, str]]:
        d = load_workflow(FIXTURES / "workflows" / file)
        return {(s, t.to) for t in d.transitions for s in t.from_states}

    sub = moves("forms-submission.yaml")
    for bad in (("Submitted", "Draft"), ("Discarded", "Draft"), ("Accepted", "Submitted")):
        assert bad not in sub, bad
    assert ("Draft", "Accepted") not in sub and ("Draft", "Voided") not in sub
    assert not {m for m in sub if m[0] in ("Discarded", "Voided")}
    assert not {m for m in moves("forms-intake-code.yaml") if m[0] == "Revoked"}
    item = moves("forms-intake-item.yaml")
    assert not {m for m in item if m[0] in ("Accepted", "Rejected")}


@pytest.mark.parametrize(
    ("type_code", "record_type", "scope", "template"),
    [
        ("TPL", "forms.Template", "company", "{type}-{seq:4}"),
        ("FRM", "forms.Submission", "project:P123", "{project}-{type}-{seq:4}"),
    ],
)
def test_numbering_patterns_allocate(
    type_code: str, record_type: str, scope: str, template: str
) -> None:
    patterns = load_numbering(FIXTURES / "numbering" / "patterns.yaml")
    pattern = patterns.find(scope, record_type)
    assert pattern is not None and pattern.type_code == type_code
    assert pattern.template == template and pattern.gap_free
    for kind in ("forms.IntakeCode", "forms.IntakeItem"):
        assert patterns.find(scope, kind) is None
    with tempfile.TemporaryDirectory() as tmp:
        target = as_target(Path(tmp) / "ledger.db")
        create_schema(target)
        with open_uow(target) as uow:
            key = allocate_key(
                uow,
                pattern=pattern,
                scope=scope,
                values=segment_values(pattern, scope),
                record_id=None,
                record_type=record_type,
                actor="user:seed",
                source="test",
            ).key
    assert key == ("TPL-0001" if type_code == "TPL" else "P123-FRM-0001")


def test_a_submission_with_no_project_has_no_company_pattern_yet() -> None:
    patterns = load_numbering(FIXTURES / "numbering" / "patterns.yaml")
    assert patterns.find("company", "forms.Submission") is None


def test_no_slot_is_named_code_token_url_salt_or_body() -> None:
    for file in (*CLASSES, "events.yaml"):
        view = _view(file)
        for name in view.schema.classes:  # this file's own classes, not the imported core ones
            for slot in view.class_induced_slots(name):
                if slot.name in FORBIDDEN:
                    assert (name, slot.name) in {("IntakeBody", "salt"), ("IntakeBody", "body")}
    for table, columns in COLUMNS.items():
        bad = set(columns) & FORBIDDEN
        assert bad == ({"salt", "body"} if table == BODY else set()), table
    for event in EVENTS:
        assert not set(_event_schema(event)["properties"]) & FORBIDDEN, event


def test_the_received_payload_has_no_text_slot() -> None:
    schema = _event_schema("IntakeItem.Received")
    for name, prop in schema["properties"].items():
        if name in ("record_id", "feed_policy"):
            continue
        assert prop.get("type") != "object" and prop.get("type") != "array", name
        if name == "body_bytes":
            assert prop["type"] == "integer"
        elif name == "received_at":
            assert prop.get("format") == "date-time"
        else:
            assert name in {
                "item_id",
                "code_id",
                "template_id",
                "template_version",
                "template_hash",
                "body_mac",
            }, name


# ---- fixtures ------------------------------------------------------------------------------

KEYS_1 = ["id", "text", "kind", "required", "unit", "min", "max", "choices", "fails_when"]
KEYS_2 = [*KEYS_1, "section", "help", "visible_when"]
KINDS = {"yes_no_na", "number", "text", "choice", "multi", "date", "photo"}
DOC_KEYS = {
    "title",
    "format_version",
    "bound_record_type",
    "answer_class",
    "intake",
    "purpose",
    "accepts_as",
    "fields",
}
TEMPLATES = FIXTURES / "forms" / "templates"
GENERAL = ["toolbox-talk", "job-hazard-assessment", "pre-use-check"]
INTAKE = ["scaffold-request", "toolbox-sign-on"]
ID_2 = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


def _load(path: Path) -> dict[str, Any]:
    doc = yaml.safe_load(path.read_text())
    assert isinstance(doc, dict)
    return doc


def _paths() -> list[Path]:
    return [TEMPLATES / f"{n}.yaml" for n in GENERAL] + [
        TEMPLATES / "intake" / f"{n}.yaml" for n in INTAKE
    ]


@pytest.mark.parametrize("path", _paths(), ids=lambda p: p.stem)
def test_a_fixture_parses_with_unique_field_ids(path: Path) -> None:
    doc = _load(path)
    assert set(doc) == DOC_KEYS
    assert doc["format_version"] == 2 and doc["title"]
    fields = doc["fields"]
    ids = [f["id"] for f in fields]
    assert len(ids) == len(set(ids))
    for f in fields:
        assert list(f) == KEYS_2 and ID_2.fullmatch(f["id"]) and f["kind"] in KINDS
    answer_class = doc["answer_class"]
    assert answer_class in (None, "internal", "restricted", "privileged")


@pytest.mark.parametrize("name", GENERAL)
def test_a_general_fixture_is_a_form_of_five_to_twelve_fields(name: str) -> None:
    doc = _load(TEMPLATES / f"{name}.yaml")
    fields = doc["fields"]
    assert 5 <= len(fields) <= 12
    assert doc["intake"] is None and doc["purpose"] is None and doc["accepts_as"] is None
    assert sum(1 for f in fields if f["visible_when"] is not None) == 1
    assert any(f["section"] for f in fields) and any(f["help"] for f in fields)
    kinds = {f["kind"] for f in fields}
    assert {"text", "date"} <= kinds
    if name != "pre-use-check":
        assert "photo" not in kinds


def test_the_three_general_fixtures_use_every_named_kind() -> None:
    kinds: set[str] = set()
    for name in GENERAL:
        kinds |= {f["kind"] for f in _load(TEMPLATES / f"{name}.yaml")["fields"]}
    assert {"yes_no_na", "choice", "multi", "date", "text"} <= kinds


@pytest.mark.parametrize("name", INTAKE)
def test_an_intake_fixture_keeps_to_the_public_profile(name: str) -> None:
    doc = _load(TEMPLATES / "intake" / f"{name}.yaml")
    assert doc["intake"] == "public"
    assert doc["purpose"] in ("request", "sign_on")
    assert isinstance(doc["accepts_as"], list) and doc["accepts_as"]
    assert len(doc["fields"]) <= 8
    for f in doc["fields"]:
        assert f["kind"] in ("text", "choice", "number"), f["id"]
        assert f["visible_when"] is None


def test_every_fixture_passes_the_forms_rules() -> None:
    from tl_core.forms import rules

    for path in _paths():
        doc = _load(path)
        problems = rules.validate_questions(doc["fields"], fmt=doc["format_version"])
        if doc["intake"] == "public":
            problems += rules.intake_problems(
                doc["fields"], purpose=doc["purpose"], accepts_as=doc["accepts_as"]
            )
        assert problems == [], (path.name, problems)
        assert len(rules.content_hash(doc["fields"], fmt=doc["format_version"])) == 64
