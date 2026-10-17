"""``PdfExtractor``: real metadata, stubbed content (P1-I3B-T10)."""

from __future__ import annotations

from extractsupport import make_pdf, make_png, run, run_source, source_for
from test_extractor_contract import check_extractor_contract
from tl_core.derivation import MAX_SOURCE_BYTES, ExtractionResult
from tl_extract.pdf import PdfExtractor

EXTRACTOR = PdfExtractor()
PDF = "application/pdf"
INFO = {
    "Title": "Instrument index",
    "Author": "J. Okafor",
    "Producer": "Acme Docs 4.1",
    "CreationDate": "D:20240301101530Z",
    "ModDate": "D:20240302",
}


def pdf_run(data: bytes) -> ExtractionResult:
    return run(EXTRACTOR, "ISD-001.pdf", PDF, data)


def test_it_passes_the_extractor_contract() -> None:
    samples = [
        ("a.pdf", PDF, make_pdf(INFO, pages=3)),
        ("a.pdf", PDF, make_pdf()),
        ("a.pdf", PDF, make_pdf(encrypted=True)),
        ("a.pdf", PDF, b"%PDF-1.4\n"),
        ("a.pdf", PDF, b"not a pdf"),
        ("a.pdf", PDF, b""),
    ]
    check_extractor_contract(EXTRACTOR, samples)


def test_the_metadata_is_real_and_the_content_is_stubbed() -> None:
    result = pdf_run(make_pdf(INFO, pages=3))
    assert result.status == "metadata_only"
    assert (result.extractor, result.extractor_version) == ("pdf", "1")
    assert (
        result.rows == []
        and result.columns == []
        and result.profiles == []
        and result.problems == []
    )
    meta = result.metadata
    assert meta is not None
    assert (meta.page_count, meta.title, meta.author, meta.producer) == (
        3,
        "Instrument index",
        "J. Okafor",
        "Acme Docs 4.1",
    )
    assert (meta.created, meta.modified) == ("2024-03-01T10:15:30Z", "2024-03-02")
    assert (meta.content_type, meta.sheet_names) == (PDF, None)
    assert result.notes == [
        "content extraction stubbed (ADR-0008 decision 8): "
        "the text and tables of the PDF was not read"
    ]


def test_a_pdf_without_information_still_reports_its_pages() -> None:
    result = pdf_run(make_pdf(pages=2))
    assert result.status == "metadata_only"
    assert result.metadata is not None and result.metadata.page_count == 2
    assert result.metadata.title is None


def test_an_encrypted_pdf_is_a_failed_result() -> None:
    result = pdf_run(make_pdf(encrypted=True))
    assert result.status == "failed"
    assert [p.code for p in result.problems] == ["encrypted_pdf"]
    assert result.metadata is not None and result.metadata.page_count is None


def test_a_damaged_pdf_a_non_pdf_and_another_format_are_failed_results() -> None:
    for data, code in (
        (make_pdf(pages=3)[:100], "broken_pdf"),
        (b"%PDF-1.4\n" + b"\x00\xff" * 100, "broken_pdf"),
        (b"just text", "not_pdf"),
        (make_png(), "not_pdf"),
        (b"", "not_pdf"),
    ):
        result = pdf_run(data)
        assert result.status == "failed" and [p.code for p in result.problems] == [code]
        assert "Traceback" not in result.problems[0].message


def test_a_file_over_the_size_limit_is_refused_before_it_is_read() -> None:
    source = source_for("big.pdf", PDF, b"x").model_copy(update={"size": MAX_SOURCE_BYTES + 1})
    result = run_source(EXTRACTOR, source, b"x")
    assert result.status == "failed" and [p.code for p in result.problems] == ["source_too_large"]


def test_the_same_bytes_give_the_same_result_and_it_survives_json() -> None:
    data = make_pdf(INFO, pages=2)
    first, second = pdf_run(data), pdf_run(data)
    assert first == second
    assert ExtractionResult.model_validate_json(first.model_dump_json()) == first
