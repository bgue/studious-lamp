"""Crafted PDFs that cost a reader minutes or gigabytes cost this one milliseconds (S13).

Every file here is a few hundred kilobytes at most, and every test finishes well inside a second.
"""

from __future__ import annotations

import re
import time
import tracemalloc

import pytest
from extractsupport import make_pdf, pdf_from_objects, pdf_with_object_stream
from tl_extract import pdfinfo
from tl_extract.pdfinfo import (
    MAX_LENGTH_VALUES,
    MAX_OBJSTM,
    MAX_SIZE,
    MAX_XREF_SECTIONS,
    PYPDF_LIMIT,
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
    raw = pdf_with_object_stream(padding=PYPDF_LIMIT + MIB)
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
    assert read_pdf_info(pdf_with_object_stream(padding=MIB)).page_count == 1


def test_too_many_object_streams_are_refused() -> None:
    raw = make_pdf(pages=1)
    assert refusal(raw.replace(b"%%EOF", b"/ObjStm " * (MAX_OBJSTM + 1) + b"%%EOF")).code == (
        "pdf_too_complex"
    )
    check_pdf_bytes(b"%PDF-1.5\n" + b"/ObjStm " * MAX_OBJSTM)


@pytest.mark.parametrize(
    "token", [b"startxref ", b"/Prev ", b"/XRef ", b"/Pr#65v ", b"/#50rev ", b"/#58#52ef "]
)
def test_too_many_cross_reference_sections_are_refused(token: bytes) -> None:
    raw = make_pdf().replace(b"%%EOF", token * (MAX_XREF_SECTIONS + 1) + b"%%EOF")
    assert refusal(raw).code == "pdf_too_complex"
    check_pdf_bytes(b"%PDF-1.4\n" + token * MAX_XREF_SECTIONS)


def test_a_size_that_promises_millions_of_objects_is_refused() -> None:
    raw = re.sub(rb"/Size \d+", b"/Size %d" % (MAX_SIZE + 1), make_pdf())
    assert refusal(raw).code == "pdf_too_complex"
    check_pdf_bytes(re.sub(rb"/Size \d+", b"/Size %d" % MAX_SIZE, make_pdf()))


def test_an_xref_stream_that_expands_past_the_limit_is_refused_cheaply() -> None:
    raw = pdf_with_object_stream(xref_padding=PYPDF_LIMIT + MIB)
    assert len(raw) < 20_000
    started = time.monotonic()
    assert refusal(raw).code == "damaged_pdf"
    assert time.monotonic() - started < 1
    assert read_pdf_info(pdf_with_object_stream(xref_padding=MIB // 4)).page_count == 1


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


def test_a_47_megabyte_title_is_refused_by_the_work_budget_not_read() -> None:
    raw = make_pdf({"Title": "T" * 3_000_000})  # 3 MB is five times the budget; 47 MB the same
    tracemalloc.start()
    started = time.monotonic()
    try:
        error = refusal(raw)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert error.code == "pdf_too_complex"
    assert time.monotonic() - started < 3
    assert peak < 8 * MIB  # not a hundred bytes of state per character


@pytest.mark.parametrize("kind", ["literal", "hex", "nested", "escaped"])
def test_every_shape_of_a_long_string_is_refused_the_same_way(kind: str) -> None:
    body = {
        "literal": b"(" + b"A" * 2_000_000 + b")",
        "hex": b"<" + b"41" * 1_000_000 + b">",
        "nested": b"(" + b"(a)" * 700_000 + b")",
        "escaped": b"(" + b"\\)" * 1_000_000 + b")",
    }[kind]
    raw = make_pdf({"Title": "x"}).replace(b"(x)", body)
    started = time.monotonic()
    assert refusal(raw).code in ("pdf_too_complex", "damaged_pdf")
    assert time.monotonic() - started < 3


def test_the_work_budget_bounds_a_huge_array_in_the_page_tree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def tree(refs: int) -> bytes:
        kids = b"[" + b"3 0 R " * refs + b"]"
        return pdf_from_objects(
            [
                b"<< /Type /Catalog /Pages 2 0 R >>",
                b"<< /Type /Pages /Count 1 /Kids " + kids + b" >>",
                b"<< /Type /Page >>",
            ]
        )

    monkeypatch.setattr(pdfinfo, "MAX_STREAM_OPS", 20_000)
    assert read_pdf_info(tree(200)).page_count == 1
    started = time.monotonic()
    assert refusal(tree(40_000)).code == "pdf_too_complex"
    assert time.monotonic() - started < 1


def test_a_title_under_the_budget_is_read_and_cut() -> None:
    info = read_pdf_info(make_pdf({"Title": "T" * 100_000}))
    assert info.title == "T" * 1000


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


# --- the third review: everything pypdf can do with the file is charged -----------------------


def with_broken_xref(entries: int) -> bytes:
    """A PDF whose classic cross-reference table is ``entries`` lines of garbage. pypdf's repair
    path copies the whole file once per bad line, even when it reads strictly."""
    body = make_pdf()
    head = body[: body.index(b"xref\n")]
    xref_at = len(head)
    table = f"xref\n0 {entries}\n".encode() + b"aaaaaaaaaa aaaaa n \n" * entries
    trailer = f"trailer\n<< /Size {entries} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode()
    return head + table + trailer


def test_a_table_of_bad_entries_reaches_the_repair_path_and_is_refused() -> None:
    raw = with_broken_xref(2000)
    assert len(raw) < 60_000
    started = time.monotonic()
    assert refusal(raw).code == "pdf_too_complex"
    assert time.monotonic() - started < 1


def stream_of(data: bytes, monkeypatch: pytest.MonkeyPatch) -> pdfinfo._BudgetStream:  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(pdfinfo, "STREAM_BYTE_FACTOR", 1)
    monkeypatch.setattr(pdfinfo, "STREAM_BYTE_ALLOWANCE", 0)
    return pdfinfo._BudgetStream(data)  # pyright: ignore[reportPrivateUsage]


DATA = (b"x" * 59 + b"\n") * 4  # four lines of 60 bytes: the budget is 240


@pytest.mark.parametrize(
    "operation",
    [
        lambda s: s.read(),
        lambda s: s.read(60),
        lambda s: s.read1(60),
        lambda s: s.readline(),
        lambda s: s.readinto(bytearray(60)),
        lambda s: next(s),
        lambda s: list(s),
    ],
    ids=["read-all", "read-n", "read1", "readline", "readinto", "next", "iterate"],
)
def test_every_way_of_reading_the_file_is_charged_by_its_bytes(
    operation: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    op = operation  # type: ignore[assignment]
    stream = stream_of(DATA, monkeypatch)
    for _ in range(4):  # whatever reads 60 bytes at a time uses up the 240 exactly...
        stream.seek(0)
        stream.bytes_left = len(DATA)
        op(stream)  # type: ignore[operator]
    stream.seek(0)
    stream.bytes_left = 100
    with pytest.raises(pdfinfo._OutOfBudget):  # pyright: ignore[reportPrivateUsage]
        for _ in range(3):  # ...and the third of 60 bytes is past 100
            op(stream)  # type: ignore[operator]


@pytest.mark.parametrize("method", ["getbuffer", "getvalue", "readlines"])
def test_getting_the_whole_file_at_once_is_not_allowed(
    method: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    stream = stream_of(DATA, monkeypatch)
    with pytest.raises(pdfinfo._OutOfBudget):  # pyright: ignore[reportPrivateUsage]
        getattr(stream, method)()


def test_operations_are_counted_as_well_as_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pdfinfo, "MAX_STREAM_OPS", 3)
    stream = pdfinfo._BudgetStream(b"abcdef")  # pyright: ignore[reportPrivateUsage]
    stream.read(1)
    stream.seek(0)
    stream.readline()
    with pytest.raises(pdfinfo._OutOfBudget):  # pyright: ignore[reportPrivateUsage]
        stream.read(1)


def test_a_file_that_is_read_whole_once_is_within_the_byte_budget() -> None:
    stream = pdfinfo._BudgetStream(b"x" * 1000)  # pyright: ignore[reportPrivateUsage]
    assert len(stream.read()) == 1000
    stream.seek(0)
    assert len(stream.read()) == 1000
