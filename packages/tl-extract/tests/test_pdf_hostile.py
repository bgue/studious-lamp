"""Crafted PDFs that cost a reader minutes or gigabytes cost this one milliseconds (S13).

Every file here is a few hundred kilobytes at most, and every test finishes well inside a second.
"""

from __future__ import annotations

import time
import tracemalloc

import pytest
from extractsupport import make_pdf, pdf_from_objects, pdf_with_object_stream
from tl_extract.pdfinfo import (
    MAX_LENGTH_VALUES,
    MAX_OBJSTM,
    MAX_STARTXREF,
    MAX_STRING_BYTES,
    check_pdf_bytes,
    read_pdf_info,
)
from tl_extract.reading import Refusal

MIB = 1024 * 1024


def refusal(raw: bytes) -> Refusal:
    with pytest.raises(Refusal) as caught:
        read_pdf_info(raw)
    return caught.value


def test_the_object_stream_builder_makes_a_pdf_pypdf_reads() -> None:
    assert read_pdf_info(pdf_with_object_stream()).page_count == 1


def test_an_object_stream_that_expands_past_the_limit_is_refused_cheaply() -> None:
    raw = pdf_with_object_stream(padding=24 * MIB)
    assert len(raw) < 100_000
    tracemalloc.start()
    started = time.monotonic()
    try:
        error = refusal(raw)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert error.code == "damaged_pdf"
    assert time.monotonic() - started < 2
    assert peak < 32 * MIB  # not the 24 MiB it expands to, times copies


def test_the_page_count_does_not_decode_the_pages() -> None:
    # a page tree of 3 pages in an object stream: Count is read, no /Kids is followed
    assert read_pdf_info(pdf_with_object_stream(padding=2 * MIB)).page_count == 1


def test_too_many_object_streams_are_refused() -> None:
    raw = make_pdf(pages=1)
    assert refusal(raw.replace(b"%%EOF", b"/ObjStm " * (MAX_OBJSTM + 1) + b"%%EOF")).code == (
        "pdf_too_complex"
    )
    check_pdf_bytes(b"%PDF-1.5\n" + b"/ObjStm " * MAX_OBJSTM)


def test_too_many_cross_reference_sections_are_refused() -> None:
    assert refusal(make_pdf() + b"startxref\n0\n%%EOF\n" * MAX_STARTXREF).code == "pdf_too_complex"


def test_too_many_length_entries_are_refused() -> None:
    with pytest.raises(Refusal) as caught:
        check_pdf_bytes(b"%PDF-1.4\n" + b"/Length 1\n" * (MAX_LENGTH_VALUES + 1))
    assert caught.value.code == "pdf_too_complex"


def test_a_stream_longer_than_the_file_is_refused() -> None:
    raw = make_pdf(pages=1).replace(
        b"endobj\n", b"endobj\n5 0 obj\n<< /Length 999999999 >>\nstream\nxx\nendstream\nendobj\n", 1
    )
    assert refusal(raw).code == "damaged_pdf"


def test_an_indirect_length_is_not_a_size() -> None:
    check_pdf_bytes(b"%PDF-1.4\n<< /Length 9 0 R >>\n")


@pytest.mark.parametrize("kind", ["literal", "hex", "escaped"])
def test_a_string_of_a_megabyte_is_refused_without_being_read(kind: str) -> None:
    body = {
        "literal": b"(" + b"A" * (MAX_STRING_BYTES + 10) + b")",
        "hex": b"<" + b"41" * (MAX_STRING_BYTES // 2 + 10) + b">",
        "escaped": b"(" + b"\\)" * (MAX_STRING_BYTES + 10) + b")",
    }[kind]
    raw = make_pdf({"Title": "x"}).replace(b"(x)", body)
    started = time.monotonic()
    assert refusal(raw).code == "pdf_too_complex"
    assert time.monotonic() - started < 1


def test_a_string_just_under_the_limit_is_read_and_cut_to_a_title() -> None:
    raw = make_pdf({"Title": "T" * (MAX_STRING_BYTES - 10)})
    started = time.monotonic()
    info = read_pdf_info(raw)
    assert info.title == "T" * 1000
    assert time.monotonic() - started < 3


@pytest.mark.parametrize("pattern", [b"(", b"()", b"(\\", b"<", b"(a)(b)"])
def test_the_scan_is_linear_on_adversarial_text(pattern: bytes) -> None:
    raw = pattern * (4 * MIB // len(pattern))
    started = time.monotonic()
    try:
        check_pdf_bytes(raw)
    except Refusal:
        pass
    assert time.monotonic() - started < 1.5


def test_pypdfs_log_records_never_reach_the_root_logger(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    caplog.set_level(logging.DEBUG)
    with pytest.raises(Refusal):
        read_pdf_info(make_pdf(pages=3)[:150])
    read_pdf_info(pdf_from_objects([b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages >>"]))
    assert [r for r in caplog.records if r.name.startswith("pypdf")] == []


def test_the_loggers_state_is_restored() -> None:
    import logging

    logger = logging.getLogger("pypdf")
    before = (logger.level, logger.propagate)
    read_pdf_info(make_pdf())
    assert (logger.level, logger.propagate) == before
