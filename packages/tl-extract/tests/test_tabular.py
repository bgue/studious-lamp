"""``TabularExtractor``: CSV and XLSX end to end, bounds and contract (P1-I3B-T09)."""

from __future__ import annotations

import io
from collections.abc import Mapping
from pathlib import Path

import pytest
from extractsupport import (
    XLSX_TYPE,
    hand_xlsx,
    inline_row,
    run,
    run_source,
    sheet_xml,
    source_for,
    xlsx_bytes,
    zip_bytes,
)
from test_extractor_contract import check_extractor_contract
from tl_core.derivation import (
    MAX_CELL_CHARS,
    MAX_COLUMNS,
    MAX_ROWS,
    MAX_SOURCE_BYTES,
    ExtractionResult,
)
from tl_extract.tabular import TabularExtractor

EXTRACTOR = TabularExtractor()
ROOT = Path(__file__).resolve().parents[3]
LEGACY = ROOT / "dev" / "seed" / "legacy" / "instrument-index.csv"
CSV = "text/csv"


def csv_run(text: str | bytes, options: Mapping[str, object] | None = None) -> ExtractionResult:
    data = text if isinstance(text, bytes) else text.encode()
    return run(EXTRACTOR, "index.csv", CSV, data, options)


def xlsx_run(data: bytes, options: Mapping[str, object] | None = None) -> ExtractionResult:
    return run(EXTRACTOR, "book.xlsx", XLSX_TYPE, data, options)


def codes(result: ExtractionResult) -> list[str]:
    return [p.code for p in result.problems]


def test_it_passes_the_extractor_contract_on_csv_and_xlsx_samples() -> None:
    samples = [
        ("a.csv", CSV, b"A,B\n1,2\n"),
        ("a.csv", CSV, b""),
        ("a.csv", CSV, b'A\n"open\n'),
        ("a.csv", CSV, "A;B\nä;ö\n".encode()),
        ("b.xlsx", XLSX_TYPE, xlsx_bytes({"S": [["A"], ["1"]]})),
        ("b.xlsx", XLSX_TYPE, b"not a workbook"),
        ("legacy.csv", CSV, LEGACY.read_bytes()),
    ]
    check_extractor_contract(EXTRACTOR, samples)


def test_a_csv_is_read_into_columns_rows_and_profiles() -> None:
    result = csv_run(
        "TAG NO,SERVICE,SIZE\n47-FV-1001,Feed gas,4\n47-FV-1002,,6\n47-FV-1003,Feed gas,\n"
    )
    assert result.status == "ok" and result.problems == [] and result.notes == []
    assert (result.extractor, result.extractor_version) == ("tabular", "1")
    assert result.columns == ["TAG NO", "SERVICE", "SIZE"]
    assert result.rows[1] == {"TAG NO": "47-FV-1002", "SERVICE": None, "SIZE": "6"}
    profile = {p.name: p for p in result.profiles}["SERVICE"]
    assert (profile.non_empty, profile.distinct, profile.max_length) == (2, 1, 8)
    assert result.sheet is None
    assert result.metadata is not None and result.metadata.sheet_names is None


def test_the_legacy_instrument_index_is_read_with_header_hints() -> None:
    options = {
        "header_map": {
            "TAG NO": "tag_number",
            "SERVICE": "service",
            "SIZE (IN)": "size_in",
            "MFR": "manufacturer",
            "FAIL": "fail_action",
        },
        "normalise_headers": True,
    }
    result = csv_run(LEGACY.read_bytes(), options)
    assert result.status == "ok"
    assert result.columns == [
        "tag_number",
        "service",
        "type",
        "size_in",
        "material",
        "manufacturer",
        "fail_action",
        "fat_witness",
        "p_id",
        "remarks",
        "issued",
    ]
    assert len(result.rows) == 14  # the row with no tag number is still a row
    assert result.rows[0]["tag_number"] == "47-FV-1001"
    assert result.notes[0].startswith("header hints applied: TAG NO -> tag_number")


def test_a_semicolon_file_with_a_byte_order_mark() -> None:
    result = csv_run(b"\xef\xbb\xbfA;B\n1;2\n")
    assert result.columns == ["A", "B"] and result.notes == ["delimiter detected: semicolon"]


def test_options_reach_the_reader_and_the_table() -> None:
    text = "Instrument index\nTag,Tag\nx,y\n"
    refused = csv_run(text, {"header_row": 2})
    assert refused.status == "failed" and codes(refused) == ["duplicate_header"]
    result = csv_run(text, {"header_row": 2, "duplicate_headers": "suffix"})
    assert result.columns == ["Tag", "Tag_2"] and result.rows == [{"Tag": "x", "Tag_2": "y"}]
    assert csv_run("A|B\n1|2\n", {"delimiter": "|"}).columns == ["A", "B"]


def test_a_bad_option_fails_before_the_file_is_read() -> None:
    for options in ({"header_row": 0}, {"delimiter": "x"}):
        result = csv_run("A\n1\n", options)
        assert result.status == "failed" and codes(result) == ["bad_option"]
    unknown = csv_run("A\n1\n", {"shet": "x"})
    assert unknown.status == "failed" and codes(unknown) == ["unknown_option"]


def test_an_xlsx_is_read_with_its_sheet_and_properties() -> None:
    data = xlsx_bytes(
        {"Cover": [["x"]], "Index": [["TAG", "SIZE"], ["47-FV-1001", 4], ["47-FV-1002", 6.5]]},
        title="Instrument index",
        creator="J. Okafor",
    )
    result = xlsx_run(data, {"sheet": "Index"})
    assert result.status == "ok" and result.sheet == "Index"
    assert result.rows == [{"TAG": "47-FV-1001", "SIZE": "4"}, {"TAG": "47-FV-1002", "SIZE": "6.5"}]
    meta = result.metadata
    assert meta is not None
    assert (meta.sheet_names, meta.title, meta.author) == (
        ["Cover", "Index"],
        "Instrument index",
        "J. Okafor",
    )
    assert meta.created is not None and meta.created.endswith("Z")
    assert xlsx_run(data).sheet == "Cover"


def test_a_missing_sheet_fails_and_names_the_sheets() -> None:
    result = xlsx_run(xlsx_bytes({"Index": [["A"]]}), {"sheet": "Nope"})
    assert result.status == "failed" and codes(result) == ["sheet_not_found"]
    assert "Index" in result.problems[0].message


def test_formulas_are_values_and_links_are_not_followed() -> None:
    rows = (
        inline_row(1, ["N"])
        + '<row r="2"><c r="A2" t="str"><f>WEBSERVICE("http://example.invalid/")</f><v>stored</v></c></row>'
    )
    result = xlsx_run(hand_xlsx(sheet_xml(rows)))
    assert result.rows == [{"N": "stored"}]


def test_control_characters_and_extra_columns_are_problems_of_their_rows() -> None:
    result = csv_run("A,B,\n1,x\x01y,z\n2,ok,\n")
    assert result.status == "ok"
    assert result.rows == [{"A": "1", "B": None}, {"A": "2", "B": "ok"}]
    assert [(p.code, p.row) for p in result.problems] == [
        ("control_character", 1),
        ("extra_cells", 1),
    ]


# --- bounds ---------------------------------------------------------------------------------


def test_a_file_over_the_size_limit_is_refused_before_it_is_read() -> None:
    source = source_for("big.csv", CSV, b"A\n").model_copy(update={"size": MAX_SOURCE_BYTES + 1})
    result = run_source(EXTRACTOR, source, b"A\n")
    assert result.status == "failed" and codes(result) == ["source_too_large"]


def test_a_stream_of_another_size_than_stated_is_refused() -> None:
    source = source_for("a.csv", CSV, b"A\n1\n")
    for data in (b"A\n1\nextra", b"A\n"):
        result = run_source(EXTRACTOR, source, data)
        assert result.status == "failed" and codes(result) == ["size_mismatch"]


def test_too_many_rows_and_columns_and_a_long_cell_are_refused_not_truncated() -> None:
    rows = csv_run("A\n" + "x\n" * (MAX_ROWS + 1))
    assert (rows.status, codes(rows), rows.rows) == ("failed", ["too_many_rows"], [])
    wide = csv_run(",".join(f"c{i}" for i in range(MAX_COLUMNS + 1)) + "\n1\n")
    assert (wide.status, codes(wide), wide.columns) == ("failed", ["too_many_columns"], [])
    long = csv_run("A\nok\n" + "x" * (MAX_CELL_CHARS + 1) + "\n")
    assert (long.status, codes(long), long.problems[0].row) == ("failed", ["cell_too_long"], 2)


def test_exactly_at_the_limits_is_read() -> None:
    assert len(csv_run("A\n" + "x\n" * MAX_ROWS).rows) == MAX_ROWS
    assert len(csv_run(",".join(f"c{i}" for i in range(MAX_COLUMNS)) + "\n").columns) == MAX_COLUMNS
    assert csv_run("A\n" + "x" * MAX_CELL_CHARS + "\n").status == "ok"


def test_an_xlsx_zip_bomb_and_an_entity_bomb_are_failed_results() -> None:
    bomb = hand_xlsx(sheet_xml(""), {"xl/sharedStrings.xml": b"<sst>" + b" " * (33 * 1024 * 1024)})
    assert codes(xlsx_run(bomb)) == ["sheet_too_large"]
    entity = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><worksheet/>'
    assert codes(xlsx_run(hand_xlsx(entity))) == ["unsafe_xlsx"]


# --- malformed input ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "data", "code"),
    [
        ("a.csv", b"\x00\xff" * 64, "not_utf8"),
        ("a.csv", b'A,B\n1,"never closed\n', "malformed_csv"),
        ("a.csv", b"", "no_header"),
        ("a.csv", b",,\n1,2,3\n", "no_header"),
        ("a.csv", b"A,B,A\n1,2,3\n", "duplicate_header"),
        ("a.xlsx", b"", "not_xlsx"),
        ("a.xlsx", b"PK\x03\x04junk", "not_xlsx"),
        ("a.xlsx", zip_bytes({"a.txt": b"x"}), "not_xlsx"),
        ("a.xlsx", b"A,B\n1,2\n", "not_xlsx"),
    ],
)
def test_malformed_input_is_a_failed_result_with_a_code(
    filename: str, data: bytes, code: str
) -> None:
    result = run(EXTRACTOR, filename, "application/octet-stream", data)
    assert result.status == "failed"
    assert codes(result) == [code]
    assert result.rows == [] and result.columns == []
    assert result.metadata is not None and result.metadata.size == len(data)


# --- determinism ----------------------------------------------------------------------------


def test_the_same_bytes_give_the_same_result_and_it_survives_json() -> None:
    xlsx = xlsx_bytes({"S": [["A", "B"], ["1", None], ["2", "x"]]}, title="T")
    for name, content_type, data in (
        ("a.csv", CSV, LEGACY.read_bytes()),
        ("a.xlsx", XLSX_TYPE, xlsx),
    ):
        first = run(EXTRACTOR, name, content_type, data)
        second = run(EXTRACTOR, name, content_type, data)
        assert first == second
        assert ExtractionResult.model_validate_json(first.model_dump_json()) == first


def test_the_stream_is_read_once_and_not_closed() -> None:
    data = b"A\n1\n"
    stream = io.BytesIO(data)
    EXTRACTOR.extract(source_for("a.csv", CSV, data), stream, {})
    assert not stream.closed
