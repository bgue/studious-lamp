"""Crafted workbooks that cost a library gigabytes cost the streaming reader milliseconds (S14).

Every file is small, every test finishes in well under a second: the bounds are proved by a limit
patched down to a few units, or by an input that would be huge only if the bound were missing.
"""

from __future__ import annotations

import datetime as dt
import time
import zipfile
from pathlib import Path

import pytest
from extractsupport import (
    CONTENT_TYPES,
    hand_xlsx,
    inline_row,
    sheet_xml,
    zip_bytes,
)
from tl_extract import xlsxxml
from tl_extract.options import TableOptions
from tl_extract.reading import Refusal
from tl_extract.xlsxgrid import COMPOUND_DOCUMENT, MAX_CENTRAL_DIRECTORY, MAX_MEMBERS, read_xlsx
from tl_extract.xlsxxml import MAX_SHEET_NAME, MAX_SHEETS, from_serial, is_date_format

OPTIONS = TableOptions()
PEAK_LIMIT = 2 * 1024 * 1024
MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def refusal(raw: bytes, **options: object) -> Refusal:
    with pytest.raises(Refusal) as caught:
        read_xlsx(raw, TableOptions.model_validate(options))
    return caught.value


def relationships(*items: tuple[str, str, str]) -> bytes:
    body = "".join(
        f'<Relationship Id="{ident}" Type="{REL}/{kind}" Target="{target}"/>'
        for ident, kind, target in items
    )
    return (
        '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/'
        f'2006/relationships">{body}</Relationships>'
    ).encode()


def workbook(sheets: str, pr: str = "") -> bytes:
    return (
        f'<?xml version="1.0"?><workbook xmlns="{MAIN}" xmlns:r="{REL}">{pr}'
        f"<sheets>{sheets}</sheets></workbook>"
    ).encode()


# --- shapes that make a general library materialise something huge --------------------------


def test_a_cell_at_the_last_column_does_not_make_a_row_sixteen_thousand_wide() -> None:
    row = '<row r="2"><c r="XFD2" t="inlineStr"><is><t>far</t></is></c></row>'
    sheet = sheet_xml(inline_row(1, ["A"]) + row + inline_row(3, ["1"]), dimension="A1:XFD3")
    started = time.monotonic()
    grid = read_xlsx(hand_xlsx(sheet), OPTIONS)
    assert grid.rows == [["A"], ["1"]] and grid.skipped_blank_rows == 1  # the far cell is not read
    assert time.monotonic() - started < 1


def test_a_hundred_thousand_empty_cells_in_one_row_cost_nothing() -> None:
    cells = "".join('<c r="A1"/>' for _ in range(100_000))
    raw = hand_xlsx(sheet_xml(f'<row r="1">{cells}</row>' + inline_row(2, ["x"])))
    started = time.monotonic()
    grid = read_xlsx(raw, OPTIONS)
    assert grid.rows == [[], ["x"]]
    assert time.monotonic() - started < 1.5


def test_the_shared_strings_are_counted_while_they_are_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(xlsxxml, "MAX_SHARED_STRINGS", 100)
    sst = f'<sst xmlns="{MAIN}">' + "<si><t>x</t></si>" * 101 + "</sst>"
    extra = {
        "xl/sharedStrings.xml": sst.encode(),
        "xl/_rels/workbook.xml.rels": relationships(
            ("rId1", "worksheet", "worksheets/sheet1.xml"),
            ("rId2", "sharedStrings", "sharedStrings.xml"),
        ),
    }
    error = refusal(hand_xlsx(sheet_xml(inline_row(1, ["A"])), extra))
    assert error.code == "too_many_cells"
    monkeypatch.setattr(xlsxxml, "MAX_SHARED_STRINGS", 101)
    assert read_xlsx(hand_xlsx(sheet_xml(inline_row(1, ["A"])), extra), OPTIONS).rows == [["A"]]


def test_a_shared_string_is_cut_where_a_cell_is_refused_anyway() -> None:
    sst = f'<sst xmlns="{MAIN}"><si><t>' + "y" * 100_000 + "</t></si></sst>"
    row = '<row r="1"><c r="A1" t="s"><v>0</v></c></row>'
    extra = {
        "xl/sharedStrings.xml": sst.encode(),
        "xl/_rels/workbook.xml.rels": relationships(
            ("rId1", "worksheet", "worksheets/sheet1.xml"),
            ("rId2", "sharedStrings", "sharedStrings.xml"),
        ),
    }
    grid = read_xlsx(hand_xlsx(sheet_xml(row), extra), OPTIONS)
    assert len(grid.rows[0][0] or "") == xlsxxml.MAX_STRING_CHARS


def test_elements_are_counted_while_they_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(xlsxxml, "MAX_ELEMENTS", 50)
    body = "".join(inline_row(n, ["x"]) for n in range(1, 40))
    assert refusal(hand_xlsx(sheet_xml(body))).code == "unsafe_xlsx"


def test_nesting_is_bounded() -> None:
    nested = "<x>" * 100 + "</x>" * 100
    assert refusal(hand_xlsx(sheet_xml(inline_row(1, ["A"]) + nested))).code == "unsafe_xlsx"


def test_a_part_that_is_not_well_formed_is_not_a_workbook() -> None:
    assert refusal(hand_xlsx(b"<worksheet><sheetData><row></sheetData>")).code == "not_xlsx"


def test_rows_are_dropped_as_they_are_read() -> None:
    # 20 000 rows are allowed; a reader that kept every XML element would hold all of them as well
    # as the table. The peak must stay near the table, not twice it.
    import tracemalloc

    body = "".join(inline_row(n, ["x" * 30]) for n in range(1, 6_001))
    raw = hand_xlsx(sheet_xml(body))
    tracemalloc.start()
    try:
        grid = read_xlsx(raw, OPTIONS)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert len(grid.rows) == 6_000
    assert peak < PEAK_LIMIT


# --- the archive -----------------------------------------------------------------------------


def patched_directory(entries: int | None = None, size: int | None = None) -> bytes:
    raw = bytearray(hand_xlsx(sheet_xml(inline_row(1, ["A"]))))
    at = raw.rfind(b"PK\x05\x06")
    if entries is not None:
        raw[at + 8 : at + 12] = entries.to_bytes(2, "little") * 2
    if size is not None:
        raw[at + 12 : at + 16] = size.to_bytes(4, "little")
    return bytes(raw)


def test_the_entry_count_is_read_before_zipfile_loads_the_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("ZipFile must not be built for this archive")

    many = patched_directory(entries=MAX_MEMBERS + 1)
    zip64 = patched_directory(entries=0xFFFF)
    big = patched_directory(size=MAX_CENTRAL_DIRECTORY + 1)
    monkeypatch.setattr(zipfile, "ZipFile", forbidden)
    for raw in (many, zip64, big):
        assert refusal(raw).code == "zip_bomb"


def test_a_directory_that_points_past_the_end_of_the_file_is_not_a_workbook() -> None:
    assert refusal(patched_directory(size=10_000_000 - 1)).code in ("zip_bomb", "not_xlsx")
    assert refusal(patched_directory(size=100_000)).code == "not_xlsx"


def test_a_file_with_no_end_record_is_not_a_workbook() -> None:
    assert refusal(b"PK\x03\x04" + b"\x00" * 100).code == "not_xlsx"


def test_an_encrypted_or_legacy_office_document_is_named() -> None:
    error = refusal(COMPOUND_DOCUMENT + b"\x00" * 600)
    assert error.code == "encrypted_xlsx"
    assert "unprotected XLSX" in error.message


def test_a_relationship_may_not_name_a_part_that_is_not_xml_or_outside_the_archive() -> None:
    for target in ("worksheets/sheet1.dat", "../../etc/passwd.xml", "/../x.xml"):
        extra = {
            "xl/_rels/workbook.xml.rels": relationships(("rId1", "worksheet", target)),
        }
        error = refusal(hand_xlsx(sheet_xml(inline_row(1, ["A"])), extra))
        assert error.code == "unsafe_xlsx", target


def test_the_sheet_part_is_scanned_even_when_a_relationship_gives_it_an_odd_name() -> None:
    entity = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><worksheet/>'
    parts = {
        "[Content_Types].xml": CONTENT_TYPES,
        "xl/workbook.xml": workbook('<sheet name="S" sheetId="1" r:id="rId1"/>'),
        "xl/_rels/workbook.xml.rels": relationships(("rId1", "worksheet", "worksheets/s.xml")),
        "xl/worksheets/s.xml": entity,
    }
    assert refusal(zip_bytes(parts)).code == "unsafe_xlsx"


# --- sheets ----------------------------------------------------------------------------------


def many_sheets(count: int, name: str = "S") -> bytes:
    sheets = "".join(
        f'<sheet name="{name}{n}" sheetId="{n}" r:id="rId1"/>' for n in range(1, count + 1)
    )
    return hand_xlsx(sheet_xml(inline_row(1, ["A"])), {"xl/workbook.xml": workbook(sheets)})


def test_the_number_of_sheets_is_capped() -> None:
    assert read_xlsx(many_sheets(MAX_SHEETS), OPTIONS).sheet_names is not None
    assert refusal(many_sheets(MAX_SHEETS + 1)).code == "too_many_sheets"


def test_a_sheet_name_has_a_length_limit() -> None:
    assert read_xlsx(many_sheets(1, "n" * (MAX_SHEET_NAME - 1)), OPTIONS).sheet_names
    assert refusal(many_sheets(1, "n" * (MAX_SHEET_NAME + 1))).code == "bad_sheet_name"


def test_a_chartsheet_is_listed_but_never_read() -> None:
    sheets = (
        '<sheet name="Chart" sheetId="2" r:id="rId2"/><sheet name="Data" sheetId="1" r:id="rId1"/>'
    )
    extra = {
        "xl/workbook.xml": workbook(sheets),
        "xl/_rels/workbook.xml.rels": relationships(
            ("rId1", "worksheet", "worksheets/sheet1.xml"),
            ("rId2", "chartsheet", "chartsheets/sheet1.xml"),
        ),
        "xl/chartsheets/sheet1.xml": b"<chartsheet/>",
    }
    grid = read_xlsx(hand_xlsx(sheet_xml(inline_row(1, ["A"])), extra), OPTIONS)
    assert grid.sheet == "Data" and grid.sheet_names == ["Chart", "Data"]


# --- properties ------------------------------------------------------------------------------

CORE = (
    '<?xml version="1.0"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/'
    '2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" '
    'xmlns:dcterms="http://purl.org/dc/terms/" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">{}</cp:coreProperties>'
)


def with_core(body: str) -> bytes:
    return hand_xlsx(
        sheet_xml(inline_row(1, ["A"])), {"docProps/core.xml": CORE.format(body).encode()}
    )


def test_properties_are_what_the_file_says_and_nothing_else() -> None:
    meta = read_xlsx(
        with_core(
            "<dc:title>Index</dc:title><dc:creator>J. Okafor</dc:creator>"
            '<dcterms:created xsi:type="dcterms:W3CDTF">2024-03-01T10:15:30Z</dcterms:created>'
        ),
        OPTIONS,
    ).meta
    assert (meta.title, meta.author, meta.created, meta.modified) == (
        "Index",
        "J. Okafor",
        "2024-03-01T10:15:30Z",
        None,
    )


def test_a_date_that_is_not_a_date_and_a_missing_creator_are_none() -> None:
    meta = read_xlsx(
        with_core(
            "<dcterms:created>last Tuesday</dcterms:created><dcterms:modified>x</dcterms:modified>"
        ),
        OPTIONS,
    ).meta
    assert (meta.title, meta.author, meta.created, meta.modified) == (None, None, None, None)


def test_properties_are_read_the_same_every_time() -> None:
    raw = with_core("<dc:title>T</dc:title>")
    assert read_xlsx(raw, OPTIONS) == read_xlsx(raw, OPTIONS)


# --- values ----------------------------------------------------------------------------------

STYLES = (
    f'<?xml version="1.0"?><styleSheet xmlns="{MAIN}">'
    '<numFmts count="2"><numFmt numFmtId="164" formatCode="yyyy\\-mm\\-dd\\ hh:mm"/>'
    '<numFmt numFmtId="165" formatCode="0.0 &quot;days&quot;"/></numFmts>'
    '<cellXfs count="5"><xf numFmtId="0"/><xf numFmtId="14"/><xf numFmtId="164"/>'
    '<xf numFmtId="165"/><xf numFmtId="21"/></cellXfs></styleSheet>'
)


def styled(cells: str, pr: str = "") -> bytes:
    extra: dict[str, bytes] = {
        "xl/styles.xml": STYLES.encode(),
        "xl/_rels/workbook.xml.rels": relationships(
            ("rId1", "worksheet", "worksheets/sheet1.xml"), ("rId2", "styles", "styles.xml")
        ),
    }
    if pr:
        extra["xl/workbook.xml"] = workbook('<sheet name="S" sheetId="1" r:id="rId1"/>', pr)
    return hand_xlsx(sheet_xml(f'<row r="1">{cells}</row>'), extra)


def serial(moment: dt.datetime, epoch: dt.datetime = dt.datetime(1899, 12, 30)) -> float:
    return (moment - epoch).total_seconds() / 86_400


def test_numbers_in_a_date_format_are_dates_and_others_are_numbers() -> None:
    day = serial(dt.datetime(2024, 3, 1))
    noon = serial(dt.datetime(2024, 3, 1, 13, 0, 0))
    cells = (
        f'<c r="A1" s="1"><v>{int(day)}</v></c>'
        f'<c r="B1" s="2"><v>{noon!r}</v></c>'
        f'<c r="C1" s="0"><v>{int(day)}</v></c>'
        '<c r="D1" s="3"><v>4.5</v></c>'
        '<c r="E1" s="4"><v>0.5</v></c>'
    )
    assert read_xlsx(styled(cells), OPTIONS).rows == [
        ["2024-03-01", "2024-03-01T13:00:00", str(int(day)), "4.5", "12:00:00"]
    ]


def test_the_1904_date_system_is_honoured() -> None:
    value = int(serial(dt.datetime(2024, 3, 1), dt.datetime(1904, 1, 1)))
    cells = f'<c r="A1" s="1"><v>{value}</v></c>'
    assert read_xlsx(styled(cells, pr='<workbookPr date1904="1"/>'), OPTIONS).rows == [
        ["2024-03-01"]
    ]


def test_the_cell_types_of_the_format() -> None:
    cells = (
        '<c r="A1" t="e"><v>#DIV/0!</v></c>'
        '<c r="B1" t="str"><f>"x"&amp;"y"</f><v>xy</v></c>'
        '<c r="C1" t="b"><v>1</v></c>'
        '<c r="D1" t="d"><v>2024-03-01</v></c>'
        '<c r="E1" t="n"/>'
        '<c r="F1" t="inlineStr"><is><r><t>a</t></r><r><t>b</t></r><rPh><t>PH</t></rPh></is></c>'
        '<c r="G1"><f>SUM(A1:A9)</f></c>'
        f'<c r="H1"><v>{"9" * 5000}</v></c>'
        '<c r="I1"><v>1.5e3</v></c>'
    )
    row = read_xlsx(hand_xlsx(sheet_xml(f'<row r="1">{cells}</row>')), OPTIONS).rows[0]
    assert row[:6] == ["#DIV/0!", "xy", "TRUE", "2024-03-01", None, "ab"]
    assert row[6] is None  # a formula without a stored value is empty, and is never evaluated
    assert row[7] == "9" * 40  # a number of thousands of digits is kept as short text
    assert row[8] == "1500"


@pytest.mark.parametrize(
    ("number_format_id", "code", "expected"),
    [
        (14, None, True),
        (22, None, True),
        (46, None, True),
        (0, None, False),
        (164, "yyyy-mm-dd hh:mm", True),
        (164, "[h]:mm:ss", True),
        (164, "General", False),
        (164, "0.00", False),
        (164, '0.0 "days"', False),
        (164, "[Red]0.0", False),
        (164, "#,##0_);(#,##0)", False),
        (164, "dd/mm/yyyy", True),
        (164, '"Date: "dd', True),
    ],
)
def test_which_number_formats_show_a_date(
    number_format_id: int, code: str | None, expected: bool
) -> None:
    assert is_date_format(number_format_id, code) is expected


def test_from_serial() -> None:
    assert from_serial(1, False) == dt.datetime(1900, 1, 1)
    assert from_serial(59, False) == dt.datetime(1900, 2, 28)
    assert from_serial(61, False) == dt.datetime(1900, 3, 1)
    assert from_serial(45352.5, False) == dt.datetime(2024, 3, 1, 12, 0)
    assert from_serial(0.25, False) == dt.time(6, 0)
    assert from_serial(0, True) == dt.time(0, 0)
    assert from_serial(-1, False) is None
    assert from_serial(3_000_000, False) is None
    assert from_serial(45352.0000001, False) == dt.datetime(2024, 3, 1)


def test_a_sheet_without_data_is_empty() -> None:
    assert read_xlsx(hand_xlsx(sheet_xml("")), OPTIONS).rows == []
    assert read_xlsx(hand_xlsx(b'<worksheet xmlns="' + MAIN.encode() + b'"/>'), OPTIONS).rows == []


# --- the second review: memory that grows with elements nobody asked for ----------------------


def junk_after_the_data(count: int) -> bytes:
    body = '<row r="1"><c r="A1" t="inlineStr"><is><t>A</t></is></c></row>'
    sheet = (
        f'<?xml version="1.0"?><worksheet xmlns="{MAIN}"><sheetData>{body}</sheetData>'
        + '<x a="1"/>' * count
        + "</worksheet>"
    )
    return hand_xlsx(sheet.encode())


def test_elements_are_detached_as_they_are_read_so_memory_stays_flat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tracemalloc

    monkeypatch.setattr(xlsxxml, "MAX_FOREIGN", 10_000_000)
    raw = junk_after_the_data(60_000)
    tracemalloc.start()
    try:
        grid = read_xlsx(raw, OPTIONS)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert grid.rows == [["A"]]
    assert peak < PEAK_LIMIT  # 60 000 attached elements would be about 10 MiB


def test_elements_a_worksheet_does_not_have_are_counted_and_refused() -> None:
    started = time.monotonic()
    assert refusal(junk_after_the_data(xlsxxml.MAX_FOREIGN + 10)).code == "unsafe_xlsx"
    assert time.monotonic() - started < 1.5


def test_attributes_count_toward_the_element_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(xlsxxml, "MAX_ELEMENTS", 100)
    cell = "<c " + " ".join(f'a{i}="1"' for i in range(60)) + "/>"
    assert refusal(hand_xlsx(sheet_xml(f'<row r="1">{cell}{cell}</row>'))).code == "unsafe_xlsx"


def test_the_97_kilobyte_file_that_took_gigabytes_fails_quickly_under_a_memory_limit(
    tmp_path: Path,
) -> None:
    """4.9 million elements after the data: about 100 KB of file that grew a tree without bound."""
    import subprocess
    import sys
    import textwrap

    path = tmp_path / "bomb.xlsx"
    path.write_bytes(junk_after_the_data(4_900_000))
    assert path.stat().st_size < 200_000
    script = textwrap.dedent(
        """
        import hashlib, io, resource, sys
        resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))
        from tl_core.derivation import SourceFile
        from tl_extract.tabular import TabularExtractor
        raw = open(sys.argv[1], "rb").read()
        source = SourceFile(file_id="f", filename="a.xlsx", content_type="x/y", size=len(raw),
                            sha256=hashlib.sha256(raw).hexdigest(), source_ref="r")
        result = TabularExtractor().extract(source, io.BytesIO(raw), {})
        print(result.status, [p.code for p in result.problems])
        """
    )
    done = subprocess.run(
        [sys.executable, "-I", "-c", script, str(path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-500:]
    assert done.stdout.strip() == "failed ['unsafe_xlsx']"


def test_a_shared_string_index_the_workbook_lacks_is_refused() -> None:
    for index in ("99", "-1", "1e3", "٣"):
        row = f'<row r="1"><c r="A1" t="s"><v>{index}</v></c></row>'
        assert refusal(hand_xlsx(sheet_xml(row))).code == "bad_shared_string", index


@pytest.mark.parametrize(
    "reference", ["", "1A", "A", "A0x", "AAAA1", "XFE1", "A99999999", "\u0661"]
)
def test_a_cell_reference_that_is_not_one_is_refused(reference: str) -> None:
    row = f'<row r="1"><c r="{reference}" t="inlineStr"><is><t>x</t></is></c></row>'
    code = "bad_cell_ref"
    if reference == "":
        row = row.replace('r=""', "")  # no reference at all is positional, and fine
        assert read_xlsx(hand_xlsx(sheet_xml(row)), OPTIONS).rows == [["x"]]
        return
    assert refusal(hand_xlsx(sheet_xml(row))).code == code


@pytest.mark.parametrize("number", ["99999999999999999999", "0x10", "-1", "1e3", "٣", "1.5"])
def test_a_row_number_that_is_not_a_row_is_refused_without_echoing_it(number: str) -> None:
    error = refusal(hand_xlsx(sheet_xml(f'<row r="{number}"><c r="A1"/></row>')))
    assert error.code == "bad_row_number" and number not in error.message


def test_the_last_row_of_a_sheet_is_a_row() -> None:
    row = f'<row r="{xlsxxml.MAX_SHEET_ROW}"><c r="A{xlsxxml.MAX_SHEET_ROW}"/></row>'
    started = time.monotonic()
    assert read_xlsx(hand_xlsx(sheet_xml(inline_row(1, ["A"]) + row)), OPTIONS).rows == [["A"]]
    assert time.monotonic() - started < 1


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("5", 5),
        ("-5", -5),
        ("+5", 5),
        ("5.", 5.0),
        (".5", 0.5),
        ("1e3", 1000.0),
        ("1E-2", 0.01),
        (" 7 ", 7),
        ("1_000", "1_000"),
        ("nan", "nan"),
        ("inf", "inf"),
        ("-Infinity", "-Infinity"),
        ("١٢٣", "١٢٣"),
        ("0x10", "0x10"),
        ("1e", "1e"),
        ("", ""),
        ("5" * 500, "5" * 40),
    ],
)
def test_numbers_are_plain_decimals_and_nothing_else(text: str, value: object) -> None:
    assert xlsxxml.number_value(text) == value


def test_a_sheet_that_takes_too_long_to_read_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(xlsxxml, "MAX_SHEET_SECONDS", -1.0)
    body = "".join(inline_row(n, ["x"]) for n in range(1, 4_000))
    assert refusal(hand_xlsx(sheet_xml(body))).code == "sheet_too_slow"


def test_a_part_that_claims_more_than_deflate_can_do_is_a_lie() -> None:
    raw = bytearray(hand_xlsx(sheet_xml(inline_row(1, ["A"])), {"xl/media/x.bin": b"\x00" * 2000}))
    # the declared uncompressed size sits 24 bytes into the part's central-directory header
    header = next(
        at
        for at in range(len(raw))
        if raw[at : at + 4] == b"PK\x01\x02" and raw[at + 46 : at + 60] == b"xl/media/x.bin"
    )
    raw[header + 24 : header + 28] = (3_000_000).to_bytes(4, "little")
    assert refusal(bytes(raw)).code == "zip_bomb"
