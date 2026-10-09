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
        "ddl/postgres/cur_core_record.sql",
        "ddl/postgres/cur_files.sql",
        "ddl/postgres/cur_link_counts.sql",
        "ddl/postgres/cur_links.sql",
        "ddl/postgres/cur_numbering.sql",
        "ddl/postgres/cur_pset_values.sql",
        "ddl/postgres/cur_workflow_state.sql",
        "ddl/sqlite/cur_core_record.sql",
        "ddl/sqlite/cur_files.sql",
        "ddl/sqlite/cur_link_counts.sql",
        "ddl/sqlite/cur_links.sql",
        "ddl/sqlite/cur_numbering.sql",
        "ddl/sqlite/cur_pset_values.sql",
        "ddl/sqlite/cur_workflow_state.sql",
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
    generated = _normalise(outputs["ddl/sqlite/cur_core_record.sql"])
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
