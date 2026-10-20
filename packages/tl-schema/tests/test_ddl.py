"""Tests for the current-state DDL generator core (P0-I1-T04b)."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest
from linkml_runtime.utils.schemaview import SchemaView
from tl_schema.generators import ddl

REPO = Path(__file__).resolve().parents[3]
SCHEMA_DIR = REPO / "schema" / "core"
GOLDEN = Path(__file__).parent / "golden"

# docs/build-spec/03-repo-and-toolchain.md section 9, with comments removed and IF NOT EXISTS added
# (the projector DDL must be idempotent).
SPEC_SECTION_9_SQLITE = """
CREATE TABLE IF NOT EXISTS cur_core_record (
  id                    TEXT PRIMARY KEY,
  key                   TEXT,
  type                  TEXT NOT NULL,
  scope                 TEXT NOT NULL,
  title                 TEXT NOT NULL,
  description           TEXT,
  status                TEXT,
  psets_json            TEXT NOT NULL DEFAULT '{}',
  voided                INTEGER NOT NULL DEFAULT 0,
  version               INTEGER NOT NULL,
  last_seq              INTEGER NOT NULL,
  effective_schema_hash TEXT,
  conformance           TEXT NOT NULL DEFAULT 'ok',
  created_at            TEXT NOT NULL,
  updated_at            TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_core_record_scope_key ON cur_core_record(scope, key);
"""


def _normalise(sql: str) -> str:
    sql = re.sub(r"\s+", " ", sql).strip()
    sql = re.sub(r" ?\( ?", "(", sql)
    sql = re.sub(r" ?\) ?", ")", sql)
    return re.sub(r" ?, ?", ",", sql)


@pytest.fixture(scope="module")
def outputs() -> dict[str, str]:
    return ddl.generate(SCHEMA_DIR)


def test_only_current_state_classes_get_tables(outputs: dict[str, str]) -> None:
    assert sorted(outputs) == [
        "ddl/postgres/auth_attempt.sql",
        "ddl/postgres/auth_audit.sql",
        "ddl/postgres/auth_credential.sql",
        "ddl/postgres/auth_session.sql",
        "ddl/postgres/auth_token_secret.sql",
        "ddl/postgres/cur_account.sql",
        "ddl/postgres/cur_agent_token.sql",
        "ddl/postgres/cur_core_record.sql",
        "ddl/postgres/cur_core_record_body.sql",
        "ddl/postgres/cur_core_type_registration.sql",
        "ddl/postgres/cur_correspondence_clearance.sql",
        "ddl/postgres/cur_correspondence_contact_role.sql",
        "ddl/postgres/cur_correspondence_contract_clause.sql",
        "ddl/postgres/cur_correspondence_correspondence.sql",
        "ddl/postgres/cur_correspondence_correspondence_thread.sql",
        "ddl/postgres/cur_correspondence_party.sql",
        "ddl/postgres/cur_correspondence_response_clock.sql",
        "ddl/postgres/cur_cost_cost_snapshot.sql",
        "ddl/postgres/cur_cost_costcode.sql",
        "ddl/postgres/cur_cost_snapshot_value.sql",
        "ddl/postgres/cur_documents_derived_content.sql",
        "ddl/postgres/cur_documents_derived_document.sql",
        "ddl/postgres/cur_documents_document.sql",
        "ddl/postgres/cur_documents_document_schema.sql",
        "ddl/postgres/cur_documents_processing_job.sql",
        "ddl/postgres/cur_documents_rendition.sql",
        "ddl/postgres/cur_documents_review_cycle.sql",
        "ddl/postgres/cur_documents_reviewer.sql",
        "ddl/postgres/cur_documents_revision.sql",
        "ddl/postgres/cur_documents_transmittal.sql",
        "ddl/postgres/cur_documents_transmittal_item.sql",
        "ddl/postgres/cur_engineering_code_value.sql",
        "ddl/postgres/cur_engineering_standard.sql",
        "ddl/postgres/cur_engineering_tag.sql",
        "ddl/postgres/cur_engineering_tag_class.sql",
        "ddl/postgres/cur_feed_items.sql",
        "ddl/postgres/cur_feed_tags.sql",
        "ddl/postgres/cur_files.sql",
        "ddl/postgres/cur_link_counts.sql",
        "ddl/postgres/cur_links.sql",
        "ddl/postgres/cur_numbering.sql",
        "ddl/postgres/cur_proposals.sql",
        "ddl/postgres/cur_pset_values.sql",
        "ddl/postgres/cur_schedule_activity_ref.sql",
        "ddl/postgres/cur_schedule_schedule.sql",
        "ddl/postgres/cur_schedule_schedule_snapshot.sql",
        "ddl/postgres/cur_setting.sql",
        "ddl/postgres/cur_setting_lock.sql",
        "ddl/postgres/cur_webhook_subscription.sql",
        "ddl/postgres/cur_workflow_state.sql",
        "ddl/postgres/job_queue.sql",
        "ddl/postgres/outbox_events.sql",
        "ddl/postgres/sched_activity.sql",
        "ddl/postgres/sched_activity_code.sql",
        "ddl/postgres/sched_calendar.sql",
        "ddl/postgres/sched_relationship.sql",
        "ddl/postgres/sched_udf_value.sql",
        "ddl/postgres/sched_wbs.sql",
        "ddl/postgres/setting_effect_applied.sql",
        "ddl/postgres/tl_body_quarantine.sql",
        "ddl/postgres/v_correspondence_contract_clause.sql",
        "ddl/postgres/v_correspondence_correspondence.sql",
        "ddl/postgres/v_correspondence_correspondence_thread.sql",
        "ddl/postgres/v_correspondence_party.sql",
        "ddl/postgres/v_correspondence_response_clock.sql",
        "ddl/postgres/v_cost_cost_code.sql",
        "ddl/postgres/v_cost_cost_snapshot.sql",
        "ddl/postgres/v_documents_derived_document.sql",
        "ddl/postgres/v_documents_document.sql",
        "ddl/postgres/v_documents_document_schema.sql",
        "ddl/postgres/v_documents_processing_job.sql",
        "ddl/postgres/v_documents_rendition.sql",
        "ddl/postgres/v_documents_review_cycle.sql",
        "ddl/postgres/v_documents_revision.sql",
        "ddl/postgres/v_documents_transmittal.sql",
        "ddl/postgres/v_engineering_code_value.sql",
        "ddl/postgres/v_engineering_standard.sql",
        "ddl/postgres/v_engineering_tag.sql",
        "ddl/postgres/v_engineering_tag_class.sql",
        "ddl/postgres/v_schedule_activity_ref.sql",
        "ddl/postgres/v_schedule_schedule.sql",
        "ddl/postgres/v_schedule_schedule_snapshot.sql",
        "ddl/postgres/wh_attempt.sql",
        "ddl/postgres/wh_cursor.sql",
        "ddl/postgres/wh_delivery.sql",
        "ddl/postgres/wh_health.sql",
        "ddl/postgres/wh_secret.sql",
        "ddl/sqlite/auth_attempt.sql",
        "ddl/sqlite/auth_audit.sql",
        "ddl/sqlite/auth_credential.sql",
        "ddl/sqlite/auth_session.sql",
        "ddl/sqlite/auth_token_secret.sql",
        "ddl/sqlite/cur_account.sql",
        "ddl/sqlite/cur_agent_token.sql",
        "ddl/sqlite/cur_core_record.sql",
        "ddl/sqlite/cur_core_record_body.sql",
        "ddl/sqlite/cur_core_type_registration.sql",
        "ddl/sqlite/cur_correspondence_clearance.sql",
        "ddl/sqlite/cur_correspondence_contact_role.sql",
        "ddl/sqlite/cur_correspondence_contract_clause.sql",
        "ddl/sqlite/cur_correspondence_correspondence.sql",
        "ddl/sqlite/cur_correspondence_correspondence_thread.sql",
        "ddl/sqlite/cur_correspondence_party.sql",
        "ddl/sqlite/cur_correspondence_response_clock.sql",
        "ddl/sqlite/cur_cost_cost_snapshot.sql",
        "ddl/sqlite/cur_cost_costcode.sql",
        "ddl/sqlite/cur_cost_snapshot_value.sql",
        "ddl/sqlite/cur_documents_derived_content.sql",
        "ddl/sqlite/cur_documents_derived_document.sql",
        "ddl/sqlite/cur_documents_document.sql",
        "ddl/sqlite/cur_documents_document_schema.sql",
        "ddl/sqlite/cur_documents_processing_job.sql",
        "ddl/sqlite/cur_documents_rendition.sql",
        "ddl/sqlite/cur_documents_review_cycle.sql",
        "ddl/sqlite/cur_documents_reviewer.sql",
        "ddl/sqlite/cur_documents_revision.sql",
        "ddl/sqlite/cur_documents_transmittal.sql",
        "ddl/sqlite/cur_documents_transmittal_item.sql",
        "ddl/sqlite/cur_engineering_code_value.sql",
        "ddl/sqlite/cur_engineering_standard.sql",
        "ddl/sqlite/cur_engineering_tag.sql",
        "ddl/sqlite/cur_engineering_tag_class.sql",
        "ddl/sqlite/cur_feed_items.sql",
        "ddl/sqlite/cur_feed_tags.sql",
        "ddl/sqlite/cur_files.sql",
        "ddl/sqlite/cur_link_counts.sql",
        "ddl/sqlite/cur_links.sql",
        "ddl/sqlite/cur_numbering.sql",
        "ddl/sqlite/cur_proposals.sql",
        "ddl/sqlite/cur_pset_values.sql",
        "ddl/sqlite/cur_schedule_activity_ref.sql",
        "ddl/sqlite/cur_schedule_schedule.sql",
        "ddl/sqlite/cur_schedule_schedule_snapshot.sql",
        "ddl/sqlite/cur_setting.sql",
        "ddl/sqlite/cur_setting_lock.sql",
        "ddl/sqlite/cur_webhook_subscription.sql",
        "ddl/sqlite/cur_workflow_state.sql",
        "ddl/sqlite/job_queue.sql",
        "ddl/sqlite/outbox_events.sql",
        "ddl/sqlite/sched_activity.sql",
        "ddl/sqlite/sched_activity_code.sql",
        "ddl/sqlite/sched_calendar.sql",
        "ddl/sqlite/sched_relationship.sql",
        "ddl/sqlite/sched_udf_value.sql",
        "ddl/sqlite/sched_wbs.sql",
        "ddl/sqlite/setting_effect_applied.sql",
        "ddl/sqlite/tl_body_quarantine.sql",
        "ddl/sqlite/v_correspondence_contract_clause.sql",
        "ddl/sqlite/v_correspondence_correspondence.sql",
        "ddl/sqlite/v_correspondence_correspondence_thread.sql",
        "ddl/sqlite/v_correspondence_party.sql",
        "ddl/sqlite/v_correspondence_response_clock.sql",
        "ddl/sqlite/v_cost_cost_code.sql",
        "ddl/sqlite/v_cost_cost_snapshot.sql",
        "ddl/sqlite/v_documents_derived_document.sql",
        "ddl/sqlite/v_documents_document.sql",
        "ddl/sqlite/v_documents_document_schema.sql",
        "ddl/sqlite/v_documents_processing_job.sql",
        "ddl/sqlite/v_documents_rendition.sql",
        "ddl/sqlite/v_documents_review_cycle.sql",
        "ddl/sqlite/v_documents_revision.sql",
        "ddl/sqlite/v_documents_transmittal.sql",
        "ddl/sqlite/v_engineering_code_value.sql",
        "ddl/sqlite/v_engineering_standard.sql",
        "ddl/sqlite/v_engineering_tag.sql",
        "ddl/sqlite/v_engineering_tag_class.sql",
        "ddl/sqlite/v_schedule_activity_ref.sql",
        "ddl/sqlite/v_schedule_schedule.sql",
        "ddl/sqlite/v_schedule_schedule_snapshot.sql",
        "ddl/sqlite/wh_attempt.sql",
        "ddl/sqlite/wh_cursor.sql",
        "ddl/sqlite/wh_delivery.sql",
        "ddl/sqlite/wh_health.sql",
        "ddl/sqlite/wh_secret.sql",
    ]


def test_table_annotation_overrides_the_derived_name(outputs: dict[str, str]) -> None:
    sqlite = outputs["ddl/sqlite/cur_pset_values.sql"]
    assert sqlite.startswith("CREATE TABLE IF NOT EXISTS cur_pset_values (")
    assert "value_json TEXT" in sqlite
    assert "UNIQUE INDEX IF NOT EXISTS ux_cur_pset_values_record_path" in sqlite
    postgres = outputs["ddl/postgres/cur_pset_values.sql"]
    assert "value_json JSONB" in postgres and "value_bool BOOLEAN" in postgres


@pytest.mark.parametrize("dialect", ["sqlite", "postgres"])
def test_golden_files(outputs: dict[str, str], dialect: str) -> None:
    golden = (GOLDEN / f"cur_core_record.{dialect}.sql").read_text(encoding="utf-8")
    assert outputs[f"ddl/{dialect}/cur_core_record.sql"] == golden


def test_sqlite_reproduces_spec_section_9(outputs: dict[str, str]) -> None:
    # Section 9 shows the table and its unique index; the performance indexes (P0-I8 D13) are
    # extra CREATE INDEX statements after them.
    statements = outputs["ddl/sqlite/cur_core_record.sql"].strip().split("\n\n")
    kept = [s for s in statements if not s.startswith("CREATE INDEX")]
    assert len(kept) == 2 and len(statements) > 2
    generated = _normalise("\n\n".join(kept))
    assert generated == _normalise(SPEC_SECTION_9_SQLITE)


def test_postgres_differs_only_in_the_documented_types(outputs: dict[str, str]) -> None:
    sqlite_sql = outputs["ddl/sqlite/cur_core_record.sql"].splitlines()
    # Postgres TEXT columns also carry COLLATE "C" (bytewise order, like SQLite); the rest differs
    # only in the types below.
    pg_sql = outputs["ddl/postgres/cur_core_record.sql"].replace(' COLLATE "C"', "").splitlines()
    assert len(sqlite_sql) == len(pg_sql)
    changed = {a.split()[0] for a, b in zip(sqlite_sql, pg_sql, strict=True) if a != b}
    assert changed == {"psets_json", "voided", "version", "last_seq", "created_at", "updated_at"}
    joined = "\n".join(pg_sql)
    assert "psets_json JSONB NOT NULL DEFAULT '{}'" in joined
    assert "voided BOOLEAN NOT NULL DEFAULT FALSE" in joined
    assert "created_at TIMESTAMPTZ NOT NULL" in joined
    assert outputs["ddl/postgres/cur_core_record.sql"].count('TEXT COLLATE "C"') == 9


def test_generation_is_deterministic() -> None:
    assert ddl.generate(SCHEMA_DIR) == ddl.generate(SCHEMA_DIR)
    assert not any(str(REPO) in text for text in ddl.generate(SCHEMA_DIR).values())


def test_sqlite_ddl_executes_twice_and_enforces_unique_scope_key(outputs: dict[str, str]) -> None:
    db = sqlite3.connect(":memory:")
    script = outputs["ddl/sqlite/cur_core_record.sql"]
    db.executescript(script)
    db.executescript(script)  # idempotent
    insert = (
        "INSERT INTO cur_core_record"
        " (id, key, type, scope, title, version, last_seq, created_at, updated_at)"
        " VALUES (?, ?, 'core.Record', ?, 't', 1, 1, 'x', 'x')"
    )
    db.execute(insert, ("a", "K-1", "project:P1"))
    db.execute(insert, ("b", "K-1", "project:P2"))  # same key, other scope: fine
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(insert, ("c", "K-1", "project:P1"))
    row = db.execute(
        "SELECT psets_json, voided, conformance FROM cur_core_record WHERE id='a'"
    ).fetchone()
    assert row == ("{}", 0, "ok")


def test_snake_case() -> None:
    assert ddl.snake_case("Record") == "record"
    assert ddl.snake_case("TestPackage") == "test_package"
    assert ddl.snake_case("IWP") == "iwp"


def _schema(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "s.yaml"
    path.write_text(
        "id: https://example.org/t\nname: t\n"
        "prefixes:\n  linkml: https://w3id.org/linkml/\n  t: https://example.org/t/\n"
        "default_prefix: t\nimports:\n  - linkml:types\ndefault_range: string\n"
        "annotations:\n  tl:module: demo\n" + body,
        encoding="utf-8",
    )
    return path


def test_indexed_column_enum_int_default_and_column_override(tmp_path: Path) -> None:
    body = """
enums:
  Color:
    permissible_values:
      red:
      blue:
classes:
  Widget:
    annotations:
      tl:current_state: true
    attributes:
      id:
        identifier: true
      color:
        range: Color
        required: true
        ifabsent: string(red)
        annotations:
          tl:indexed: true
      size:
        range: integer
        ifabsent: int(3)
        annotations:
          tl:column: size_mm
  NotATable:
    attributes:
      x:
"""
    files = ddl.generate_from(_schema(tmp_path, body))
    assert sorted(files) == ["ddl/postgres/cur_demo_widget.sql", "ddl/sqlite/cur_demo_widget.sql"]
    sql = files["ddl/sqlite/cur_demo_widget.sql"]
    assert "color TEXT NOT NULL DEFAULT 'red'" in sql
    assert "size_mm INTEGER DEFAULT 3" in sql
    assert "CREATE INDEX IF NOT EXISTS ix_cur_demo_widget_color ON cur_demo_widget (color);" in sql
    assert "size_mm BIGINT DEFAULT 3" in files["ddl/postgres/cur_demo_widget.sql"]


def test_unsupported_shapes_raise(tmp_path: Path) -> None:
    multivalued = """
classes:
  Widget:
    annotations:
      tl:current_state: true
    attributes:
      id:
        identifier: true
      tags:
        multivalued: true
"""
    with pytest.raises(ddl.DdlError, match="multivalued"):
        ddl.generate_from(_schema(tmp_path, multivalued))
    class_range = """
classes:
  Other:
    attributes:
      x:
  Widget:
    annotations:
      tl:current_state: true
    attributes:
      id:
        identifier: true
      other:
        range: Other
"""
    with pytest.raises(ddl.DdlError, match="not a type or enum"):
        ddl.generate_from(_schema(tmp_path, class_range))


def test_missing_module_annotation_raises(tmp_path: Path) -> None:
    path = tmp_path / "s.yaml"
    path.write_text(
        "id: https://example.org/t\nname: t\nprefixes:\n  linkml: https://w3id.org/linkml/\n"
        "default_prefix: linkml\nimports:\n  - linkml:types\ndefault_range: string\n"
        "classes:\n  W:\n    annotations:\n      tl:current_state: true\n"
        "    attributes:\n      id:\n        identifier: true\n",
        encoding="utf-8",
    )
    view = SchemaView(str(path))
    with pytest.raises(ddl.DdlError, match="tl:module"):
        ddl.table_name(view, "W")


def test_class_index_annotations_become_composite_and_expression_indexes(tmp_path: Path) -> None:
    body = """
classes:
  Widget:
    annotations:
      tl:current_state: true
      tl:ix_scope_created:
        value: "scope, voided, created_at, id"
      tl:ix_name_last:
        value: "scope, empty_last(name), name desc, id"
    attributes:
      id:
        identifier: true
      scope:
        required: true
      name:
      voided:
        range: boolean
        required: true
      created_at:
        range: datetime
        required: true
"""
    for dialect in ("sqlite", "postgres"):
        sql = ddl.generate_from(_schema(tmp_path, body))[f"ddl/{dialect}/cur_demo_widget.sql"]
        assert (
            "CREATE INDEX IF NOT EXISTS ix_cur_demo_widget_scope_created "
            "ON cur_demo_widget (scope, voided, created_at, id);"
        ) in sql
        assert (
            "CREATE INDEX IF NOT EXISTS ix_cur_demo_widget_name_last ON cur_demo_widget "
            "(scope, (name IS NULL OR name = ''), name DESC, id);"
        ) in sql
        # names sort, so the output does not depend on the order of the annotations
        assert sql.index("ix_cur_demo_widget_name_last") < sql.index("ix_cur_demo_widget_scope")


@pytest.mark.parametrize(
    "spec",
    ["scope, nosuch", "empty_last(created_at)", "scope sideways", "scope; DROP TABLE x", "id,,"],
)
def test_a_bad_index_term_raises(tmp_path: Path, spec: str) -> None:
    body = f"""
classes:
  Widget:
    annotations:
      tl:current_state: true
      tl:ix_bad:
        value: "{spec}"
    attributes:
      id:
        identifier: true
      scope:
      created_at:
        range: datetime
"""
    with pytest.raises(ddl.DdlError):
        ddl.generate_from(_schema(tmp_path, body))


def test_an_index_name_over_63_characters_or_equal_to_a_column_index_raises(
    tmp_path: Path,
) -> None:
    long_name = "a" * 60
    for index_lines, message in (
        (f"      tl:ix_{long_name}:\n        value: scope\n", "63"),
        ("      tl:ix_scope:\n        value: scope\n", "single-column"),
    ):
        body = f"""
classes:
  Widget:
    annotations:
      tl:current_state: true
{index_lines}    attributes:
      id:
        identifier: true
      scope:
        annotations:
          tl:indexed: true
"""
        with pytest.raises(ddl.DdlError, match=message):
            ddl.generate_from(_schema(tmp_path, body))
