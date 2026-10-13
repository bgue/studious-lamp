"""The tag-list mapping template and ``read_rows`` (P1-I1-T10a)."""

from __future__ import annotations

from typing import Any

import pytest
import yaml
from tl_mod_engineering.imports.mapping import (
    MappingError,
    TagListMapping,
    load_mapping,
    parse_mapping,
    read_rows,
)

TEMPLATE: dict[str, Any] = {
    "name": "instrument-index",
    "description": "The instrument index export of the incumbent system.",
    "columns": [
        {"column": "TAG NO", "to": "number"},
        {"column": "SERVICE", "to": "service"},
        {"column": "CLASS", "to": "class", "values": {"CV": "ControlValve", "MV": "ManualValve"}},
        {"column": "SIZE (IN)", "to": "psets.valve_data.size_in", "type": "decimal"},
        {"column": "MFR", "to": "psets.valve_data.manufacturer"},
        {"column": "WITNESS", "to": "psets.valve_data.x.fat_witness_by"},
        {"column": "LOOPS", "to": "psets.loop_data.count", "type": "int"},
        {"column": "SIL", "to": "psets.safety_data.sil_rated", "type": "bool"},
    ],
    "ignore": ["REMARKS"],
}
HEADER = "TAG NO,SERVICE,CLASS,SIZE (IN),MFR,WITNESS,LOOPS,SIL,REMARKS,SOURCE"


def mapping(**change: Any) -> TagListMapping:
    return parse_mapping(yaml.safe_dump({**TEMPLATE, **change}))


def refused(text: str) -> str:
    with pytest.raises(MappingError) as raised:
        parse_mapping(text, source="map.yaml")
    return str(raised.value)


# --- the template --------------------------------------------------------------------------------


def test_a_template_parses_with_its_defaults() -> None:
    parsed = mapping()
    assert parsed.delimiter == "," and parsed.ignore == ["REMARKS"]
    assert [c.to for c in parsed.columns][:3] == ["number", "service", "class"]
    assert parsed.columns[3].type == "decimal" and parsed.columns[1].type == "string"


def test_load_mapping_reads_a_file_and_names_it_in_an_error(tmp_path: Any) -> None:
    good = tmp_path / "good.yaml"
    good.write_text(yaml.safe_dump(TEMPLATE), encoding="utf-8")
    assert load_mapping(good).name == "instrument-index"
    with pytest.raises(MappingError, match=r"^missing.yaml: cannot read file"):
        load_mapping(tmp_path / "missing.yaml")


def test_invalid_yaml_and_a_non_mapping_are_refused_with_the_source() -> None:
    assert refused("a: [1").startswith("map.yaml: invalid YAML")
    assert refused("- 1\n") == "map.yaml: a mapping template must be a YAML mapping"


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        ({"columns": []}, "columns"),
        ({"delimiter": ";;"}, "one character"),
        ({"delimiter": '"'}, "one character"),
        ({"columns": [{"column": "TAG NO", "to": "tag"}]}, "to must be number"),
        ({"columns": [{"column": "A", "to": "psets.Valve.size"}]}, "to must be number"),
        ({"columns": [{"column": "A", "to": "service"}]}, "exactly one column must map to number"),
        (
            {"columns": [{"column": "A", "to": "number"}, {"column": "B", "to": "number"}]},
            "exactly one column must map to number",
        ),
        (
            {
                "columns": [
                    {"column": "A", "to": "number"},
                    {"column": "B", "to": "service"},
                    {"column": "C", "to": "service"},
                ]
            },
            "two columns map to service",
        ),
        (
            {"columns": [{"column": "A", "to": "number"}, {"column": "A", "to": "service"}]},
            "column 'A' is mapped twice",
        ),
        (
            {"columns": [{"column": "A", "to": "number"}], "ignore": ["A"]},
            "both mapped and ignored",
        ),
        (
            {"columns": [{"column": "A", "to": "number", "values": {"x": "y"}}]},
            "number cannot have values",
        ),
        (
            {
                "columns": [
                    {"column": "A", "to": "number"},
                    {"column": "B", "to": "psets.v.p", "type": "int", "values": {"x": "1"}},
                ]
            },
            "values translate text",
        ),
        ({"unknown_key": 1}, "unknown_key"),
    ],
)
def test_a_template_that_is_inconsistent_is_refused(change: dict[str, Any], fragment: str) -> None:
    assert fragment in refused(yaml.safe_dump({**TEMPLATE, **change}))


# --- reading rows --------------------------------------------------------------------------------


def test_a_row_is_mapped_to_number_class_service_and_typed_psets() -> None:
    text = f'{HEADER}\n47-FV-1001,"Feed gas, control",CV,4,Acme,J. Smith,2,yes,keep out,legacy-A\n'
    (row,) = read_rows(text, mapping())
    assert (row.line, row.number) == (2, "47-FV-1001")
    assert (row.class_code, row.service) == ("ControlValve", "Feed gas, control")
    assert row.psets == {
        "valve_data": {"size_in": 4.0, "manufacturer": "Acme", "x.fat_witness_by": "J. Smith"},
        "loop_data": {"count": 2},
        "safety_data": {"sil_rated": True},
    }
    assert row.problems == []
    assert row.raw["REMARKS"] == "keep out" and row.raw["SOURCE"] == "legacy-A"


def test_blank_cells_leave_fields_unset_and_cells_are_stripped() -> None:
    text = f"{HEADER}\n  47-FV-1002  ,, ,,,,,,,\n"
    (row,) = read_rows(text, mapping())
    assert row.number == "47-FV-1002"
    assert (row.class_code, row.service, row.psets, row.problems) == (None, None, {}, [])


def test_rows_keep_file_order_and_row_numbers_and_blank_lines_are_skipped() -> None:
    text = f"{HEADER}\n47-FV-1001,a,,,,,,,,\n\n,,,,,,,,,\n47-FV-1002,b,,,,,,,,\n"
    rows = read_rows(text, mapping())
    assert [(r.line, r.number) for r in rows] == [(2, "47-FV-1001"), (5, "47-FV-1002")]


def test_a_cell_that_cannot_be_read_is_a_problem_of_its_row_only() -> None:
    text = f"{HEADER}\n47-FV-1001,a,XX,wide,,,two,maybe,,\n47-FV-1002,b,CV,4,,,,,,\n"
    bad, good = read_rows(text, mapping())
    assert bad.problems == [
        "CLASS: 'XX' is not one of the mapped values",
        "SIZE (IN): 'wide' is not a valid decimal",
        "LOOPS: 'two' is not a valid int",
        "SIL: 'maybe' is not a valid bool",
    ]
    assert bad.class_code is None and bad.psets == {}
    assert good.problems == [] and good.psets == {"valve_data": {"size_in": 4.0}}


def test_a_blank_tag_number_is_a_problem() -> None:
    (row,) = read_rows(f"{HEADER}\n,service only,,,,,,,,\n", mapping())
    assert row.number == "" and row.problems == ["the tag number is blank"]
    assert row.service == "service only"


@pytest.mark.parametrize("char", ["\x00", "\x01", "\x1b", "\x7f"])
def test_a_control_character_is_a_problem_of_its_row_and_the_cell_is_dropped(char: str) -> None:
    """A NUL in a number or a service crashed a Postgres write; it never leaves the file now."""
    text = f"{HEADER}\n47-FV-10{char}01,Feed gas,CV,,,,,,,\n47-FV-1002,Fe{char}ed,CV,,,,,,,\n"
    first, second = read_rows(text, mapping())
    assert first.number == "" and first.problems == ["TAG NO: holds a control character"]
    assert second.service is None and second.problems == ["SERVICE: holds a control character"]


def test_a_tab_and_a_line_break_inside_a_cell_are_kept() -> None:
    (row,) = read_rows(f'{HEADER}\n47-FV-1001,"Feed\ngas\tmain",CV,,,,,,,\n', mapping())
    assert row.service == "Feed\ngas\tmain" and row.problems == []


@pytest.mark.parametrize("cell", ["inf", "nan", "1e999", "-Infinity"])
def test_a_decimal_that_is_not_a_finite_number_is_a_problem(cell: str) -> None:
    (row,) = read_rows(f"{HEADER}\nT-1,,,{cell},,,,,,\n", mapping())
    assert row.problems == [f"SIZE (IN): {cell!r} is not a valid decimal"]


def test_an_integer_with_thousands_of_digits_is_a_problem_not_a_crash() -> None:
    (row,) = read_rows(f"{HEADER}\nT-1,,,,,,{'9' * 5000},,,\n", mapping())
    assert len(row.problems) == 1 and row.problems[0].startswith("LOOPS: '99999")


@pytest.mark.parametrize(
    ("cell", "expected"),
    [("Yes", True), ("TRUE", True), ("1", True), ("n", False), ("False", False), ("0", False)],
)
def test_yes_and_no_are_read_in_any_case(cell: str, expected: bool) -> None:
    (row,) = read_rows(f"{HEADER}\nT-1,,,,,,,{cell},,\n", mapping())
    assert row.psets == {"safety_data": {"sil_rated": expected}}


def test_a_semicolon_file_and_a_byte_order_mark_are_read() -> None:
    parsed = mapping(delimiter=";")
    text = "\ufeff" + HEADER.replace(",", ";") + "\n47-FV-1001;a, b;CV;4,5;;;;;;\n"
    (row,) = read_rows(text, parsed)
    assert row.service == "a, b"
    assert row.problems == ["SIZE (IN): '4,5' is not a valid decimal"]


def test_a_short_row_reads_the_missing_cells_as_blank() -> None:
    (row,) = read_rows(f"{HEADER}\n47-FV-1001,svc\n", mapping())
    assert (row.number, row.service, row.problems) == ("47-FV-1001", "svc", [])


def test_a_file_without_a_header_or_with_a_missing_column_is_refused() -> None:
    with pytest.raises(MappingError, match="no header row"):
        read_rows("", mapping())
    with pytest.raises(MappingError) as raised:
        read_rows("TAG NO,CLASS\nT-1,CV\n", mapping())
    assert str(raised.value) == (
        "the file lacks the column(s): SERVICE, SIZE (IN), MFR, WITNESS, LOOPS, SIL"
    )


def test_a_file_that_is_not_valid_csv_is_refused() -> None:
    with pytest.raises(MappingError, match="not readable as CSV"):
        read_rows(
            f'{HEADER}\n47-FV-1001,"unterminated\n',
            mapping(),
        )


def test_a_number_class_or_service_column_must_be_text() -> None:
    for column in (
        {"column": "A", "to": "number", "type": "int"},
        {"column": "B", "to": "class", "type": "decimal"},
        {"column": "B", "to": "service", "type": "bool"},
    ):
        columns = [{"column": "A", "to": "number"}, column]
        if column["to"] == "number":
            columns = [column]
        text = yaml.safe_dump({**TEMPLATE, "columns": columns, "ignore": []})
        assert "is text; its type must be string" in refused(text)


def test_a_header_that_appears_twice_is_refused() -> None:
    header = HEADER.replace("SERVICE", "MFR")
    with pytest.raises(MappingError, match="the file has a column twice: MFR"):
        read_rows(f"{header}\n47-FV-1001,a,CV,4,Acme,,,,,\n", mapping())
