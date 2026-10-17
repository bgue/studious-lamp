"""``read_pdf_info``: the properties of a PDF (P1-I3B-T10)."""

from __future__ import annotations

import logging
import random

import pytest
from extractsupport import make_pdf
from tl_extract.pdfinfo import PdfInfo, pdf_date_to_iso, read_pdf_info
from tl_extract.reading import Refusal


def refusal(raw: bytes) -> Refusal:
    with pytest.raises(Refusal) as caught:
        read_pdf_info(raw)
    return caught.value


def test_the_page_count_and_the_document_information_are_read() -> None:
    raw = make_pdf(
        {
            "Title": "Instrument index",
            "Author": "J. Okafor",
            "Producer": "Acme Docs 4.1",
            "CreationDate": "D:20240301101530+02'00'",
            "ModDate": "D:20240302Z",
        },
        pages=3,
    )
    assert read_pdf_info(raw) == PdfInfo(
        page_count=3,
        title="Instrument index",
        author="J. Okafor",
        producer="Acme Docs 4.1",
        created="2024-03-01T10:15:30+02:00",
        modified="2024-03-02",
    )


def test_a_pdf_without_an_information_dictionary_has_only_a_page_count() -> None:
    assert read_pdf_info(make_pdf(pages=2)) == PdfInfo(page_count=2)


def test_a_title_in_utf16_hex_is_decoded() -> None:
    raw = make_pdf({"Title": b"<FEFF00500075006D00700020006C006900730074>"})
    assert read_pdf_info(raw).title == "Pump list"


def test_text_is_cleaned_like_any_metadata() -> None:
    raw = make_pdf({"Title": "Bad\\000Title", "Author": "x" * 3000, "Producer": "  \\000  "})
    info = read_pdf_info(raw)
    assert info.title == "Bad Title"
    assert info.author == "x" * 1000
    assert info.producer is None


def test_a_date_that_is_not_a_date_is_none() -> None:
    raw = make_pdf({"CreationDate": "last Tuesday", "ModDate": "D:20241399"})
    info = read_pdf_info(raw)
    assert (info.created, info.modified) == (None, None)


def test_a_header_within_the_first_kilobyte_is_enough() -> None:
    assert read_pdf_info(b"\n\n\n\n" + make_pdf(pages=2)).page_count == 2


@pytest.mark.parametrize(
    "raw",
    [b"", b"hello", b"PK\x03\x04", b"\x89PNG\r\n\x1a\n", b" " * 2000 + b"%PDF-1.4\n"],
)
def test_what_is_not_a_pdf_is_refused(raw: bytes) -> None:
    error = refusal(raw)
    assert error.code == "not_pdf"
    assert error.message == "the file is not a PDF (no %PDF- header)"


def test_an_encrypted_pdf_is_refused_without_a_password_attempt() -> None:
    error = refusal(make_pdf({"Title": "Secret"}, encrypted=True))
    assert error.code == "encrypted_pdf"
    assert "Secret" not in error.message


@pytest.mark.parametrize(
    "raw",
    [
        b"%PDF-1.4\n",
        b"%PDF-1.4\n" + b"\x00\xff" * 200,
        make_pdf(pages=3)[:150],
        make_pdf(pages=3)[:-40],
        b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 1 0 R >>\nendobj\n"
        b"trailer\n<< /Root 1 0 R >>\n",
    ],
)
def test_a_damaged_pdf_is_refused_with_fixed_text(raw: bytes) -> None:
    error = refusal(raw)
    assert error.code == "broken_pdf"
    assert error.message == "the PDF is damaged and cannot be read"


def test_a_page_tree_that_points_at_itself_does_not_hang_or_raise() -> None:
    raw = make_pdf(pages=1).replace(b"/Kids [3 0 R]", b"/Kids [2 0 R]")
    try:
        info = read_pdf_info(raw)
    except Refusal as caught:
        assert caught.code == "broken_pdf"
    else:
        assert info.page_count is None or info.page_count >= 0


def test_a_pdf_with_flipped_bytes_is_read_or_refused_never_an_exception() -> None:
    base = make_pdf({"Title": "Plan", "CreationDate": "D:20240301101530Z"}, pages=4)
    rnd = random.Random(7)
    outcomes: set[str] = set()
    for i in range(150):
        data = bytearray(base)
        for _ in range(rnd.randint(1, 8)):
            data[rnd.randrange(len(data))] = rnd.randrange(256)
        raw = bytes(data[: rnd.randrange(len(data))] if i % 5 == 0 else data)
        try:
            read_pdf_info(raw)
            outcomes.add("read")
        except Refusal as caught:
            outcomes.add(caught.code)
    assert outcomes <= {"read", "broken_pdf", "not_pdf", "encrypted_pdf"}
    assert "read" in outcomes and "broken_pdf" in outcomes


def test_pypdfs_log_records_do_not_reach_pythons_last_resort_handler() -> None:
    # pypdf logs every repair; without a handler Python prints warnings to standard error
    assert any(isinstance(h, logging.NullHandler) for h in logging.getLogger("pypdf").handlers)


def test_reading_is_deterministic() -> None:
    raw = make_pdf({"Title": "T", "CreationDate": "D:2024"}, pages=2)
    assert read_pdf_info(raw) == read_pdf_info(raw)


@pytest.mark.parametrize(
    ("text", "iso"),
    [
        ("D:20240301101530+02'00'", "2024-03-01T10:15:30+02:00"),
        ("D:20240301101530-05'30'", "2024-03-01T10:15:30-05:30"),
        ("D:20240301101530+0200", "2024-03-01T10:15:30+02:00"),
        ("D:20240301101530+02", "2024-03-01T10:15:30+02:00"),
        ("D:20240301101530Z", "2024-03-01T10:15:30Z"),
        ("D:20240301101530Z00'00'", "2024-03-01T10:15:30Z"),
        ("D:20240301101530+00'00'", "2024-03-01T10:15:30Z"),
        ("D:20240301101530", "2024-03-01T10:15:30"),
        ("D:202403011015", "2024-03-01T10:15:00"),
        ("D:2024030110", "2024-03-01T10:00:00"),
        ("D:20240301", "2024-03-01"),
        ("D:202403", "2024-03"),
        ("D:2024", "2024"),
        ("20240301101530Z", "2024-03-01T10:15:30Z"),
        ("  D:20240301  ", "2024-03-01"),
        ("D:20240229", "2024-02-29"),
        ("D:20240302Z", "2024-03-02"),
    ],
)
def test_pdf_dates_become_iso_8601(text: str, iso: str) -> None:
    assert pdf_date_to_iso(text) == iso


@pytest.mark.parametrize(
    "text",
    [
        "",
        "D:",
        "D:20",
        "D:2024-03-01",
        "D:20241301",
        "D:20240001",
        "D:20240230",
        "D:20230229",
        "D:20240332",
        "D:2024030124",
        "D:202403011060",
        "D:20240301101560",
        "D:20240301101530+24'00'",
        "D:20240301101530+02'60'",
        "D:20240301101530X",
        "D:20240301101530+02'00'extra",
        "yesterday",
    ],
)
def test_text_that_is_not_a_pdf_date_is_none(text: str) -> None:
    assert pdf_date_to_iso(text) is None
