"""Tests for the table-driven LinkML to SQL type mapping (P0-I1-T04a)."""

import decimal

import pytest
from tl_schema.generators.ddl_types import TYPE_TABLE, Dialect, column_type, sql_literal

DIALECTS: tuple[Dialect, ...] = ("sqlite", "postgres")

# Expected output, written out by hand from the ticket table (not derived from TYPE_TABLE).
# name, sqlite, postgres
EXPECTED_COLUMN_TYPES: list[tuple[str, str, str]] = [
    ("string", "TEXT", "TEXT"),
    ("uri", "TEXT", "TEXT"),
    ("uriorcurie", "TEXT", "TEXT"),
    ("curie", "TEXT", "TEXT"),
    ("ncname", "TEXT", "TEXT"),
    ("objectidentifier", "TEXT", "TEXT"),
    ("nodeidentifier", "TEXT", "TEXT"),
    ("jsonpointer", "TEXT", "TEXT"),
    ("jsonpath", "TEXT", "TEXT"),
    ("sparqlpath", "TEXT", "TEXT"),
    ("enum", "TEXT", "TEXT"),
    ("integer", "INTEGER", "BIGINT"),
    ("boolean", "INTEGER", "BOOLEAN"),
    ("float", "REAL", "REAL"),
    ("double", "REAL", "DOUBLE PRECISION"),
    ("decimal", "NUMERIC", "NUMERIC"),
    ("date", "TEXT", "DATE"),
    ("datetime", "TEXT", "TIMESTAMPTZ"),
    ("time", "TEXT", "TIME"),
    ("date_or_datetime", "TEXT", "TEXT"),
]

COLUMN_TYPE_CASES: list[tuple[str, Dialect, str]] = [
    (name, dialect, sqlite if dialect == "sqlite" else postgres)
    for name, sqlite, postgres in EXPECTED_COLUMN_TYPES
    for dialect in DIALECTS
]


def test_expected_table_names_match_type_table() -> None:
    assert {name for name, _, _ in EXPECTED_COLUMN_TYPES} == set(TYPE_TABLE)
    assert len(TYPE_TABLE) == 20


@pytest.mark.parametrize(("name", "dialect", "expected"), COLUMN_TYPE_CASES)
def test_column_type_maps_table_row(name: str, dialect: Dialect, expected: str) -> None:
    assert column_type(name, dialect) == expected


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize("linkml_type", ["integer", "string", "nonsense"])
def test_column_type_json_ignores_linkml_type(linkml_type: str, dialect: Dialect) -> None:
    expected = "TEXT" if dialect == "sqlite" else "JSONB"
    assert column_type(linkml_type, dialect, json=True) == expected


def test_column_type_unknown_name_raises() -> None:
    with pytest.raises(ValueError, match="nonsense"):
        column_type("nonsense", "sqlite")


def test_sql_literal_unknown_name_raises() -> None:
    with pytest.raises(ValueError, match="nonsense"):
        sql_literal("nonsense", "x", "sqlite")


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize(
    ("linkml_type", "value", "expected"),
    [
        ("string", "ok", "'ok'"),
        ("string", "it's", "'it''s'"),
        ("enum", "ok", "'ok'"),
        ("date", "2026-10-09", "'2026-10-09'"),
        ("integer", 0, "0"),
        ("integer", -42, "-42"),
        ("double", 1.5, "1.5"),
        ("double", 2, "2.0"),
        ("float", 0.25, "0.25"),
        ("decimal", decimal.Decimal("1.50"), "1.50"),
        ("decimal", 3, "3"),
        ("string", None, "NULL"),
        ("integer", None, "NULL"),
    ],
)
def test_sql_literal_scalar_rules(
    linkml_type: str, value: object, expected: str, dialect: Dialect
) -> None:
    assert sql_literal(linkml_type, value, dialect) == expected


@pytest.mark.parametrize(
    ("dialect", "expected"),
    [("sqlite", "0"), ("postgres", "FALSE")],
)
def test_sql_literal_boolean_false(dialect: Dialect, expected: str) -> None:
    assert sql_literal("boolean", False, dialect) == expected


@pytest.mark.parametrize(
    ("dialect", "expected"),
    [("sqlite", "1"), ("postgres", "TRUE")],
)
def test_sql_literal_boolean_true(dialect: Dialect, expected: str) -> None:
    assert sql_literal("boolean", True, dialect) == expected


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize("linkml_type", ["string", "integer", "boolean", "date"])
def test_sql_literal_json_empty_object(linkml_type: str, dialect: Dialect) -> None:
    assert sql_literal(linkml_type, {}, dialect, json=True) == "'{}'"


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize("linkml_type", ["string", "integer"])
def test_sql_literal_json_sorts_keys_and_doubles_quotes(linkml_type: str, dialect: Dialect) -> None:
    value = {"b": 1, "a": "x'y"}
    assert sql_literal(linkml_type, value, dialect, json=True) == '\'{"a":"x\'\'y","b":1}\''


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize(
    ("linkml_type", "value"),
    [
        ("integer", True),
        ("integer", 1.0),
        ("boolean", 1),
        ("boolean", "true"),
        ("double", True),
        ("double", "1.5"),
        ("decimal", True),
        ("decimal", "1.5"),
        ("string", 1),
        ("date", 20261009),
        ("enum", 7),
    ],
)
def test_sql_literal_wrong_python_type_raises(
    linkml_type: str, value: object, dialect: Dialect
) -> None:
    with pytest.raises(TypeError):
        sql_literal(linkml_type, value, dialect)
