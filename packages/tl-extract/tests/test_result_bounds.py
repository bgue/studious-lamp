"""No extractor can produce a result the contract refuses (FANOUT D10; P1-I3B-S18).

Each test builds an input that pushes one part of a result to its bound and runs the contract's own
``check_result_shape`` over what comes out.
"""

from __future__ import annotations

from extractsupport import (
    hand_xlsx,
    inline_row,
    make_pdf,
    make_png,
    many_sheet_workbook,
    run,
    sheet_xml,
    source_for,
)
from test_extractor_contract import check_result_shape
from tl_core.derivation import (
    MAX_COLUMNS,
    MAX_MESSAGE_CHARS,
    MAX_NAME_CHARS,
    MAX_NOTES,
    MAX_PROBLEMS,
    MAX_SHEET_NAMES,
    MAX_TEXT_CHARS,
    ExtractionResult,
)
from tl_extract.ocr import OcrExtractor
from tl_extract.pdf import PdfExtractor
from tl_extract.tabular import TabularExtractor

TABULAR = TabularExtractor()


def checked(
    extractor: object, filename: str, content_type: str, data: bytes, options: object = None
) -> ExtractionResult:
    result = run(extractor, filename, content_type, data, options)  # type: ignore[arg-type]
    check_result_shape(extractor, source_for(filename, content_type, data), result)  # type: ignore[arg-type]
    return result


def test_more_problems_than_the_contract_allows_are_counted_not_listed() -> None:
    csv = "A\n" + "\x01\n" * (MAX_PROBLEMS + 500)
    result = checked(TABULAR, "a.csv", "text/csv", csv.encode())
    assert len(result.problems) == MAX_PROBLEMS and result.problems[-1].code == "more_problems"


def test_notes_about_a_wide_file_of_long_names_stay_inside_the_bound() -> None:
    names = [f"h{i}" for i in range(MAX_COLUMNS)]
    csv = ",".join(names) + "\n" + ",".join(["x"] * MAX_COLUMNS) + "\n"
    hints = {name: f"{i:03d}" + "n" * (MAX_NAME_CHARS - 3) for i, name in enumerate(names)}
    result = checked(TABULAR, "a.csv", "text/csv", csv.encode(), {"header_map": hints})
    assert result.status == "ok" and len(result.columns) == MAX_COLUMNS
    assert 0 < len(result.notes) <= MAX_NOTES
    assert all(len(note) <= MAX_TEXT_CHARS for note in result.notes)
    assert max(len(note) for note in result.notes) == MAX_TEXT_CHARS  # cut, with an ellipsis


def test_a_name_at_the_limit_stays_a_name_when_a_suffix_is_added() -> None:
    long = "n" * MAX_NAME_CHARS
    csv = f"{long},{long},{long}\n1,2,3\n"
    result = checked(TABULAR, "a.csv", "text/csv", csv.encode(), {"duplicate_headers": "suffix"})
    assert result.status == "ok" and len(set(result.columns)) == 3
    assert all(len(name) <= MAX_NAME_CHARS for name in result.columns)


def test_a_header_over_the_name_limit_is_refused() -> None:
    result = run(TABULAR, "a.csv", "text/csv", f"{'n' * (MAX_NAME_CHARS + 1)}\n1\n".encode())
    assert result.status == "failed" and [p.code for p in result.problems] == ["bad_header"]


def test_the_most_sheets_with_the_longest_names_fit() -> None:
    raw = many_sheet_workbook(MAX_SHEET_NAMES, "s" * (MAX_NAME_CHARS - 4))
    result = checked(TABULAR, "a.xlsx", "application/octet-stream", raw)
    assert result.metadata is not None and result.metadata.sheet_names is not None
    assert len(result.metadata.sheet_names) == MAX_SHEET_NAMES
    assert result.sheet is not None and len(result.sheet) <= MAX_NAME_CHARS


def test_one_sheet_too_many_is_a_refusal_not_an_oversize_result() -> None:
    raw = many_sheet_workbook(MAX_SHEET_NAMES + 1, "s")
    result = run(TABULAR, "a.xlsx", "application/octet-stream", raw)
    assert result.status == "failed" and [p.code for p in result.problems] == ["too_many_sheets"]


def test_metadata_text_is_cut_to_the_contracts_bound() -> None:
    long = "L" * 5_000
    pdf = checked(
        PdfExtractor(),
        "a.pdf",
        "application/pdf",
        make_pdf({"Title": long, "Author": long, "Producer": long}),
    )
    assert pdf.metadata is not None
    assert [
        len(t or "") for t in (pdf.metadata.title, pdf.metadata.author, pdf.metadata.producer)
    ] == [MAX_TEXT_CHARS] * 3
    png = checked(
        OcrExtractor(),
        "a.png",
        "image/png",
        make_png(text={"Title": long, "Author": long, "Software": long, "Creation Time": long}),
    )
    assert png.metadata is not None
    assert all(
        len(t or "") <= MAX_TEXT_CHARS
        for t in (
            png.metadata.title,
            png.metadata.author,
            png.metadata.producer,
            png.metadata.created,
        )
    )


def test_a_refusal_with_a_long_message_is_cut_to_the_contracts_bound() -> None:
    from tl_extract.reading import Refusal, problem

    assert len(problem("c", "m" * 5_000).message) == MAX_MESSAGE_CHARS
    assert Refusal("c", "x").code == "c"


def test_a_workbook_with_properties_at_the_bound_fits() -> None:
    core = (
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/'
        'core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f"<dc:title>{'t' * 5000}</dc:title><dc:creator>{'c' * 5000}</dc:creator>"
        "</cp:coreProperties>"
    )
    raw = hand_xlsx(sheet_xml(inline_row(1, ["A"])), {"docProps/core.xml": core.encode()})
    result = checked(TABULAR, "a.xlsx", "application/octet-stream", raw)
    assert result.metadata is not None
    assert len(result.metadata.title or "") == MAX_TEXT_CHARS
    assert len(result.metadata.author or "") == MAX_TEXT_CHARS


def test_a_result_without_any_note_or_problem_is_fine() -> None:
    checked(TABULAR, "a.csv", "text/csv", b"A\n1\n")
