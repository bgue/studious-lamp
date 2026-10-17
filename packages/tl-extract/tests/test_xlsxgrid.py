"""``read_xlsx``: an XLSX workbook into a ``RawGrid`` (P1-I3B-T09b)."""

from __future__ import annotations

import datetime as dt
import io
import re
import time
import warnings
import zipfile

import pytest
from extractsupport import hand_xlsx, inline_row, sheet_xml, xlsx_bytes, zip_bytes
from tl_core.derivation import MAX_COLUMNS, MAX_ROWS
from tl_extract import reading
from tl_extract.options import TableOptions
from tl_extract.reading import Refusal
from tl_extract.xlsxgrid import (
    MAX_MEMBERS,
    MAX_OTHER_BYTES,
    MAX_SHARED_STRINGS_BYTES,
    MAX_TOTAL_UNCOMPRESSED,
    cell_text,
    read_xlsx,
)

OPTIONS = TableOptions()
MIB = 1024 * 1024


def refusal(raw: bytes, **options: object) -> Refusal:
    with pytest.raises(Refusal) as caught:
        read_xlsx(raw, TableOptions.model_validate(options))
    return caught.value


def hand_rows(*rows: list[str]) -> bytes:
    return hand_xlsx(sheet_xml("".join(inline_row(i, r) for i, r in enumerate(rows, start=1))))


# --- cell values as text --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (None, None),
        ("", None),
        ("abc", "abc"),
        (" padded ", " padded "),
        (True, "TRUE"),
        (False, "FALSE"),
        (0, "0"),
        (-12, "-12"),
        (2024, "2024"),
        (2024.0, "2024"),
        (2.5, "2.5"),
        (0.1 + 0.2, "0.3"),
        (1 / 3, "0.333333333333333"),
        (1e21, "1e+21"),
        (dt.date(2024, 3, 1), "2024-03-01"),
        (dt.datetime(2024, 3, 1), "2024-03-01"),
        (dt.datetime(2024, 3, 1, 13, 5, 9), "2024-03-01T13:05:09"),
        (dt.time(7, 30), "07:30:00"),
        (b"bytes", "b'bytes'"),
    ],
)
def test_cell_text(value: object, text: str | None) -> None:
    assert cell_text(value) == text


# --- a workbook written by a spreadsheet program --------------------------------------------


def test_a_workbook_becomes_records_of_text() -> None:
    raw = xlsx_bytes(
        {
            "Index": [
                ["TAG NO", "SIZE", "ISSUED", "FIT", "OK"],
                ["47-FV-1001", 4, dt.date(2024, 3, 1), 2.5, True],
                ["47-FV-1002", None, None, 2024.0, False],
            ]
        }
    )
    grid = read_xlsx(raw, OPTIONS)
    assert grid.rows == [
        ["TAG NO", "SIZE", "ISSUED", "FIT", "OK"],
        ["47-FV-1001", "4", "2024-03-01", "2.5", "TRUE"],
        ["47-FV-1002", None, None, "2024", "FALSE"],
    ]
    assert (grid.sheet, grid.sheet_names, grid.skipped_blank_rows) == ("Index", ["Index"], 0)


def test_the_first_visible_sheet_is_read_by_default_and_all_names_are_listed() -> None:
    raw = xlsx_bytes(
        {"Hidden": [["h"]], "Index": [["a"], ["1"]], "Other": [["o"]]}, hidden=["Hidden"]
    )
    grid = read_xlsx(raw, OPTIONS)
    assert grid.sheet == "Index" and grid.rows == [["a"], ["1"]]
    assert grid.sheet_names == ["Hidden", "Index", "Other"]


def test_when_every_sheet_is_hidden_the_first_is_read() -> None:
    raw = xlsx_bytes({"A": [["a"]], "B": [["b"]]}, hidden=["B"])
    assert read_xlsx(raw, OPTIONS).sheet == "A"


def test_a_sheet_can_be_chosen_by_name() -> None:
    raw = xlsx_bytes({"First": [["f"]], "Second": [["s"], ["2"]]})
    grid = read_xlsx(raw, TableOptions(sheet="Second"))
    assert grid.sheet == "Second" and grid.rows == [["s"], ["2"]]


def test_a_missing_sheet_is_refused_and_the_sheets_are_named() -> None:
    raw = xlsx_bytes({"First": [["f"]], "Second": [["s"]]})
    error = refusal(raw, sheet="second")  # names are compared exactly
    assert error.code == "sheet_not_found"
    assert error.message == "there is no sheet second; the sheets are: First, Second"


def test_document_properties_are_read() -> None:
    raw = xlsx_bytes({"S": [["a"]]}, title="Instrument index", creator="J. Okafor")
    meta = read_xlsx(raw, OPTIONS).meta
    assert (meta.title, meta.author) == ("Instrument index", "J. Okafor")
    pattern = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"
    assert meta.created is not None and re.fullmatch(pattern, meta.created)
    assert meta.modified is not None and re.fullmatch(pattern, meta.modified)


def test_a_workbook_without_properties_has_none_and_nothing_is_invented() -> None:
    # openpyxl answers a missing core part with creator "openpyxl" and the time of the call
    meta = read_xlsx(hand_rows(["A"]), OPTIONS).meta
    assert (meta.title, meta.author, meta.created, meta.modified) == (None, None, None, None)


def test_properties_are_cleaned_and_cut() -> None:
    raw = xlsx_bytes({"S": [["a"]]}, title="Two\nlines  here", creator="x" * 5000)
    meta = read_xlsx(raw, OPTIONS).meta
    assert meta.title == "Two lines here"
    assert meta.author == "x" * 1000


def test_rows_above_the_header_are_kept_and_blank_rows_after_it_are_skipped() -> None:
    raw = xlsx_bytes(
        {"S": [["Instrument index"], [], ["A", "B"], ["1", "2"], [], [None, None], ["3", "4"]]}
    )
    grid = read_xlsx(raw, TableOptions(header_row=3))
    assert grid.rows == [["Instrument index"], [], ["A", "B"], ["1", "2"], ["3", "4"]]
    assert grid.skipped_blank_rows == 2


def test_trailing_empty_cells_are_dropped() -> None:
    raw = xlsx_bytes({"S": [["A", "B", None, None], ["1", None, None, None]]})
    assert read_xlsx(raw, OPTIONS).rows == [["A", "B"], ["1"]]


def test_no_workbook_library_is_used() -> None:
    from tl_extract import xlsxgrid, xlsxxml

    for module in (xlsxgrid, xlsxxml):
        assert not hasattr(module, "openpyxl")
        assert "import openpyxl" not in open(module.__file__ or "").read()


def test_a_zip_with_bytes_in_front_of_it_is_not_a_workbook() -> None:
    assert refusal(b"junk" + hand_rows(["A"])).code == "not_xlsx"


def test_a_workbook_with_no_styles_reads_without_warnings() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert read_xlsx(hand_rows(["A"], ["1"]), OPTIONS).rows == [["A"], ["1"]]


# --- formulas, links, macros ----------------------------------------------------------------


def test_a_formula_is_never_evaluated_the_stored_value_is_read() -> None:
    rows = (
        '<row r="1"><c r="A1" t="inlineStr"><is><t>N</t></is></c></row>'
        '<row r="2"><c r="A2"><f>1+1</f><v>99</v></c></row>'
        '<row r="3"><c r="A3"><f>HYPERLINK("http://example.invalid/","x")</f></c></row>'
        '<row r="4"><c r="A4"><f>\'[1]Other\'!A1</f><v>7</v></c></row>'
    )
    grid = read_xlsx(hand_xlsx(sheet_xml(rows)), OPTIONS)
    # the formula without a stored value is an empty cell, and a row of one is a blank row
    assert grid.rows == [["N"], ["99"], ["7"]]
    assert grid.skipped_blank_rows == 1


def test_links_to_other_workbooks_and_macros_are_noted_and_never_used() -> None:
    raw = hand_xlsx(
        sheet_xml(inline_row(1, ["A"])),
        {
            "xl/externalLinks/externalLink1.xml": b"<externalLink/>",
            "xl/vbaProject.bin": b"\xd0\xcf\x11\xe0 not really macros",
        },
    )
    grid = read_xlsx(raw, OPTIONS)
    assert grid.rows == [["A"]]
    assert grid.notes == [
        "the workbook links to other workbooks; the links are not followed",
        "the workbook holds macros; they are never run",
    ]


# --- not a workbook -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"hello",
        b"%PDF-1.4",
        b"PK\x03\x04 and then nonsense",
        zip_bytes({"a.txt": b"x"}),
        zip_bytes({"[Content_Types].xml": b"<Types/>"}),
        xlsx_bytes({"S": [["a"]]})[:200],
    ],
)
def test_what_is_not_a_workbook_is_refused(raw: bytes) -> None:
    error = refusal(raw)
    assert error.code == "not_xlsx"
    assert "Traceback" not in error.message and "/home" not in error.message


def test_a_workbook_without_a_worksheet_is_refused() -> None:
    workbook = (
        b'<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/'
        b'2006/main"><sheets/></workbook>'
    )
    raw = hand_xlsx(sheet_xml(""), {"xl/workbook.xml": workbook})
    assert refusal(raw).code == "no_sheet"


# --- zip bombs and hostile archives ---------------------------------------------------------


def test_a_part_that_expands_past_its_limit_is_refused_before_it_is_read() -> None:
    bomb = b"<sst>" + b" " * (MAX_SHARED_STRINGS_BYTES + 1)
    raw = hand_xlsx(sheet_xml(""), {"xl/sharedStrings.xml": bomb})
    assert len(raw) < 100_000  # it is small on disk
    error = refusal(raw)
    assert error.code == "zip_bomb"


def test_parts_that_together_expand_past_the_total_are_refused() -> None:
    chunk = b"\x00" * MAX_OTHER_BYTES
    count = MAX_TOTAL_UNCOMPRESSED // len(chunk) + 1
    extra = {f"xl/media/part{i}.bin": chunk for i in range(count)}
    assert refusal(hand_xlsx(sheet_xml(""), extra)).code == "zip_bomb"


def test_too_many_parts_are_refused() -> None:
    extra = {f"xl/media/p{i}.bin": b"" for i in range(MAX_MEMBERS)}
    assert refusal(hand_xlsx(sheet_xml(""), extra)).code == "zip_bomb"


def test_an_encrypted_part_is_refused() -> None:
    raw = bytearray(hand_xlsx(sheet_xml("")))
    start = 0
    while (at := raw.find(b"PK\x01\x02", start)) != -1:  # the general purpose flag of each entry
        raw[at + 8] |= 0x01
        start = at + 4
    assert refusal(bytes(raw)).code == "encrypted_file"


@pytest.mark.parametrize("name", ["../evil.xml", "/abs.xml", "xl/../../evil.xml"])
def test_a_part_with_an_unsafe_name_is_refused(name: str) -> None:
    raw = hand_xlsx(sheet_xml(""), {name: b"<x/>"})
    assert refusal(raw).code == "not_xlsx"


# --- XML tricks -----------------------------------------------------------------------------

BILLION = (
    b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
    b'<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">]>'
)


def test_a_document_type_with_entities_is_refused() -> None:
    body = b'<worksheet><sheetData><row r="1"><c r="A1"><v>&lol2;</v></c></row></sheetData>'
    sheet = BILLION + body + b"</worksheet>"
    error = refusal(hand_xlsx(sheet))
    assert error.code == "unsafe_xlsx"
    assert "lol" not in error.message


@pytest.mark.parametrize(
    "marker", [b"<!DOCTYPE x>", b'<!ENTITY a "b">', b'<!DOCTYPE x SYSTEM "file:///etc/passwd">']
)
@pytest.mark.parametrize(
    "part",
    [
        "xl/workbook.xml",
        "xl/worksheets/sheet1.xml",
        "xl/_rels/workbook.xml.rels",
        "docProps/core.xml",
    ],
)
def test_a_declaration_in_any_xml_part_is_refused(part: str, marker: bytes) -> None:
    base = hand_xlsx(sheet_xml(inline_row(1, ["A"])))
    with zipfile.ZipFile(io.BytesIO(base)) as archive:
        parts = {n: archive.read(n) for n in archive.namelist()}
    parts[part] = b"<?xml version='1.0'?>" + marker + parts.get(part, b"<r/>")
    assert refusal(zip_bytes(parts)).code == "unsafe_xlsx"


def test_a_declaration_that_straddles_a_read_chunk_is_still_found() -> None:
    prolog = b"<?xml version='1.0'?><!--"
    pad = b" " * (64 * 1024 - len(prolog) - 3 - 4)  # the marker starts 4 bytes before the edge
    sheet = prolog + pad + b"--><!DOCTYPE x><worksheet/>"
    assert sheet.index(b"<!DOCTYPE") == 64 * 1024 - 4  # four bytes in the first chunk
    assert refusal(hand_xlsx(sheet)).code == "unsafe_xlsx"


@pytest.mark.parametrize("encoding", ["utf-16", "utf-16-le", "utf-16-be"])
def test_xml_in_utf16_is_refused_because_it_could_hide_a_declaration(encoding: str) -> None:
    sheet = "<?xml version='1.0'?><!DOCTYPE x><worksheet/>".encode(encoding)
    assert refusal(hand_xlsx(sheet)).code == "unsafe_xlsx"


def test_a_dtd_text_in_a_cell_is_just_text() -> None:
    raw = xlsx_bytes({"S": [["note"], ["a <!DOCTYPE b> sample"]]})
    assert read_xlsx(raw, OPTIONS).rows == [["note"], ["a <!DOCTYPE b> sample"]]


# --- limits ---------------------------------------------------------------------------------


def test_exactly_the_row_limit_is_read_and_one_more_is_refused() -> None:
    body = inline_row(1, ["A"]) + "".join(inline_row(i, ["x"]) for i in range(2, MAX_ROWS + 2))
    assert len(read_xlsx(hand_xlsx(sheet_xml(body)), OPTIONS).rows) == MAX_ROWS + 1
    body += inline_row(MAX_ROWS + 2, ["x"])
    error = refusal(hand_xlsx(sheet_xml(body)))
    assert error.code == "too_many_rows" and str(MAX_ROWS) in error.message


def test_a_record_is_cut_after_the_column_limit_plus_one() -> None:
    wide = [f"c{i}" for i in range(MAX_COLUMNS + 50)]
    raw = xlsx_bytes({"S": [wide, wide]})
    rows = read_xlsx(raw, OPTIONS).rows
    assert [len(r) for r in rows] == [MAX_COLUMNS + 1] * 2
    assert rows[0][-1] == f"c{MAX_COLUMNS}"


def formatted_blank_rows(first: int, last: int) -> str:
    return "".join(f'<row r="{n}"><c r="A{n}"/></row>' for n in range(first, last + 1))


def test_blank_rows_formatted_down_the_sheet_after_the_data_are_harmless() -> None:
    body = inline_row(1, ["A"]) + inline_row(2, ["1"]) + formatted_blank_rows(3, 5000)
    grid = read_xlsx(hand_xlsx(sheet_xml(body, dimension="A1:A5000")), OPTIONS)
    assert grid.rows == [["A"], ["1"]]
    assert grid.skipped_blank_rows == 4998 and grid.notes == []


def test_data_after_a_long_run_of_blank_rows_is_refused_not_dropped() -> None:
    body = inline_row(1, ["A"]) + inline_row(2, ["1"]) + formatted_blank_rows(3, 1500)
    error = refusal(hand_xlsx(sheet_xml(body + inline_row(1600, ["late"]))))
    assert error.code == "too_many_blank_rows"
    assert "1500" not in error.message and "blank rows" in error.message


def test_a_far_gap_between_rows_is_a_run_of_blank_rows_too_and_costs_nothing() -> None:
    body = inline_row(1, ["A"]) + inline_row(2, ["1"]) + inline_row(1_000_000, ["late"])
    started = time.monotonic()
    assert refusal(hand_xlsx(sheet_xml(body, dimension="A1:A1000000"))).code == (
        "too_many_blank_rows"
    )
    assert time.monotonic() - started < 1


def test_blank_rows_that_never_run_to_the_limit_do_not_end_the_reading() -> None:
    body = (
        inline_row(1, ["A"])
        + inline_row(2, ["1"])
        + inline_row(700, ["2"])  # 697 blank rows before it
        + inline_row(1400, ["3"])  # and 699 more
    )
    grid = read_xlsx(hand_xlsx(sheet_xml(body)), OPTIONS)
    assert grid.rows == [["A"], ["1"], ["2"], ["3"]] and grid.notes == []
    assert grid.skipped_blank_rows == 1396


def test_a_long_gap_of_blank_rows_between_data_is_not_the_end_if_it_is_short() -> None:
    body = inline_row(1, ["A"]) + inline_row(2, ["1"]) + inline_row(900, ["2"])
    grid = read_xlsx(hand_xlsx(sheet_xml(body)), OPTIONS)
    assert grid.rows == [["A"], ["1"], ["2"]] and grid.notes == []
    assert grid.skipped_blank_rows == 897


def test_too_many_cells_is_refused_while_reading(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reading, "MAX_CELLS", 4)  # data cells; the header is free
    assert len(read_xlsx(hand_rows(["a", "b"], ["1", "2"], ["3", "4"]), OPTIONS).rows) == 3
    assert refusal(hand_rows(["a", "b"], ["1", "2"], ["3", "4"], ["5"])).code == "too_many_cells"


def test_a_long_cell_is_returned_whole_for_the_table_to_refuse() -> None:
    long = "x" * 20_000
    assert read_xlsx(xlsx_bytes({"S": [["A"], [long]]}), OPTIONS).rows == [["A"], [long]]


def test_reading_is_deterministic() -> None:
    raw = xlsx_bytes({"S": [["A", "B"], ["1", 2]]}, title="T")
    assert read_xlsx(raw, OPTIONS) == read_xlsx(raw, OPTIONS)
