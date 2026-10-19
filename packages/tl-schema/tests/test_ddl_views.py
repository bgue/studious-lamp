"""The flat per-type views `v_<module>_<class>` of module record classes (ADR-0010 condition)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from linkml_runtime.utils.schemaview import SchemaView
from tl_schema.generators import ddl
from tl_schema.generators.ddl_types import Dialect

REPO = Path(__file__).resolve().parents[3]

BODY = """
classes:
  Widget:
    annotations:
      tl:current_state: true
      tl:record_types: "demo.Widget"
    attributes:
      id:
        identifier: true
      scope:
        required: true
      size:
        range: integer
      tags:
        annotations:
          tl:json: true
      last_seq:
        range: integer
        required: true
  Plain:
    annotations:
      tl:current_state: true
    attributes:
      id:
        identifier: true
"""


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


def test_only_a_class_with_record_types_gets_a_view_and_only_in_a_module(tmp_path: Path) -> None:
    path = _schema(tmp_path, BODY)
    in_module = ddl.generate_from(path, "demo")
    assert sorted(in_module) == [
        "ddl/postgres/cur_demo_plain.sql",
        "ddl/postgres/cur_demo_widget.sql",
        "ddl/postgres/v_demo_widget.sql",
        "ddl/sqlite/cur_demo_plain.sql",
        "ddl/sqlite/cur_demo_widget.sql",
        "ddl/sqlite/v_demo_widget.sql",
    ]
    assert not [name for name in ddl.generate_from(path) if "/v_" in name]  # the core makes none


@pytest.mark.parametrize("dialect", ["sqlite", "postgres"])
def test_the_view_joins_the_envelope_to_the_typed_columns(tmp_path: Path, dialect: Dialect) -> None:
    sql = ddl.generate_from(_schema(tmp_path, BODY), "demo")[f"ddl/{dialect}/v_demo_widget.sql"]
    head = "CREATE VIEW IF NOT EXISTS" if dialect == "sqlite" else "CREATE OR REPLACE VIEW"
    assert sql.startswith(f"{head} v_demo_widget AS\nSELECT\n")
    assert "  r.type AS record_type,\n" in sql and "  r.title AS title,\n" in sql
    assert "  t.size AS size,\n" in sql and "  t.tags_json AS tags_json\n" in sql
    assert "FROM cur_demo_widget AS t\nJOIN cur_core_record AS r ON r.id = t.id;" in sql
    for repeated in ("t.id ", "t.scope", "t.last_seq"):
        assert repeated not in sql  # the envelope supplies them


def test_a_typed_column_may_not_shadow_an_envelope_column(tmp_path: Path) -> None:
    body = BODY.replace("      size:\n        range: integer\n", "      title:\n")
    with pytest.raises(ddl.DdlError, match="clashes with the envelope"):
        ddl.generate_from(_schema(tmp_path, body), "demo")


def test_view_ddl_refuses_a_class_without_record_types(tmp_path: Path) -> None:
    view = SchemaView(str(_schema(tmp_path, BODY)))
    assert ddl.view_name(view, "Plain") is None
    with pytest.raises(ddl.DdlError, match="no tl:record_types"):
        ddl.view_ddl(view, "Plain", "sqlite")


def test_the_view_runs_on_sqlite_and_applying_it_twice_is_harmless(tmp_path: Path) -> None:
    files = ddl.generate_from(_schema(tmp_path, BODY), "demo")
    conn = sqlite3.connect(":memory:")
    envelope = ddl.generate(REPO / "schema" / "core")["ddl/sqlite/cur_core_record.sql"]
    conn.executescript(envelope)
    for _ in range(2):
        conn.executescript(files["ddl/sqlite/cur_demo_widget.sql"])
        conn.executescript(files["ddl/sqlite/v_demo_widget.sql"])
    conn.execute(
        "INSERT INTO cur_core_record (id, key, type, scope, title, version, last_seq, created_at, "
        "updated_at) VALUES ('w1', 'W-1', 'demo.Widget', 'project:P1', 'A widget', 1, 1, 'x', 'x')"
    )
    conn.execute(
        "INSERT INTO cur_demo_widget (id, scope, size, last_seq) VALUES ('w1', 'project:P1', 7, 1)"
    )
    row = conn.execute(
        "SELECT key, title, record_type, size, tags_json FROM v_demo_widget"
    ).fetchone()
    assert row == ("W-1", "A widget", "demo.Widget", 7, None)


def test_every_record_class_of_the_committed_modules_has_a_view() -> None:
    files = ddl.generate(REPO / "schema" / "core")
    views = sorted(name.split("/")[-1][:-4] for name in files if "/sqlite/v_" in name)
    assert views == [
        "v_correspondence_contract_clause",
        "v_correspondence_correspondence",
        "v_correspondence_correspondence_thread",
        "v_correspondence_party",
        "v_correspondence_response_clock",
        "v_cost_cost_code",
        "v_cost_cost_snapshot",
        "v_documents_derived_document",
        "v_documents_document",
        "v_documents_document_schema",
        "v_documents_processing_job",
        "v_documents_rendition",
        "v_documents_review_cycle",
        "v_documents_revision",
        "v_documents_transmittal",
        "v_engineering_code_value",
        "v_engineering_standard",
        "v_engineering_tag",
        "v_engineering_tag_class",
        "v_schedule_activity_ref",
        "v_schedule_schedule",
        "v_schedule_schedule_snapshot",
    ]
