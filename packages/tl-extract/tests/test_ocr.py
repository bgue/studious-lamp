"""``OcrExtractor``: real image properties, no OCR (P1-I3B-T11)."""

from __future__ import annotations

import pytest
from extractsupport import make_jpeg, make_pdf, make_png, make_tiff, run, run_source, source_for
from test_extractor_contract import check_extractor_contract
from tl_core.derivation import MAX_SOURCE_BYTES, ExtractionResult
from tl_extract.ocr import OcrExtractor

EXTRACTOR = OcrExtractor()


def image_run(filename: str, content_type: str, data: bytes) -> ExtractionResult:
    return run(EXTRACTOR, filename, content_type, data)


def test_it_passes_the_extractor_contract() -> None:
    samples = [
        ("a.png", "image/png", make_png()),
        ("a.jpg", "image/jpeg", make_jpeg()),
        ("a.tif", "image/tiff", make_tiff()),
        ("a.png", "image/png", b"not an image"),
        ("a.png", "image/png", make_png()[:20]),
        ("a.png", "image/png", b""),
    ]
    check_extractor_contract(EXTRACTOR, samples)


@pytest.mark.parametrize(
    ("filename", "content_type", "data", "fmt"),
    [
        ("scan.png", "image/png", make_png(800, 600), "png"),
        ("scan.jpg", "image/jpeg", make_jpeg(800, 600), "jpeg"),
        ("scan.tif", "image/tiff", make_tiff(800, 600), "tiff"),
    ],
)
def test_the_format_and_size_are_real_and_the_content_is_stubbed(
    filename: str, content_type: str, data: bytes, fmt: str
) -> None:
    result = image_run(filename, content_type, data)
    assert result.status == "metadata_only"
    assert (result.extractor, result.extractor_version) == ("ocr", "2")
    assert result.rows == [] and result.columns == [] and result.problems == []
    assert result.notes == [
        "content extraction stubbed (ADR-0008 decision 8): no text in the image was read"
    ]
    assert result.metadata is not None
    assert (result.metadata.size, result.metadata.content_type) == (len(data), content_type)
    meta = result.metadata
    assert (meta.image_format, meta.width, meta.height) == (fmt, 800, 600)


def test_header_text_becomes_metadata() -> None:
    data = make_png(
        text={"Title": "Plot plan", "Author": "J. Okafor", "Software": "ScanTool 2"},
        time=(2024, 3, 2, 8, 5, 9),
    )
    meta = image_run("plan.png", "image/png", data).metadata
    assert meta is not None
    assert (meta.title, meta.author, meta.producer, meta.modified) == (
        "Plot plan",
        "J. Okafor",
        "ScanTool 2",
        "2024-03-02T08:05:09Z",
    )
    assert meta.page_count is None and meta.created is None


def test_the_bytes_decide_the_format_not_the_name() -> None:
    result = image_run("scan.png", "image/png", make_jpeg(30, 20))
    assert result.status == "metadata_only"
    meta = result.metadata
    assert meta is not None
    assert (meta.image_format, meta.width, meta.height) == ("jpeg", 30, 20)


def test_a_huge_declared_size_costs_nothing() -> None:
    result = image_run("map.png", "image/png", make_png(60_000, 80_000))
    assert result.status == "metadata_only"
    meta = result.metadata
    assert meta is not None
    assert (meta.image_format, meta.width, meta.height) == ("png", 60_000, 80_000)


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"", "not_an_image"),
        (b"GIF89a\x01\x00\x01\x00", "not_an_image"),
        (make_pdf(), "not_an_image"),
        (make_png()[:20], "broken_image"),
        (make_jpeg()[:6], "broken_image"),
        (b"II+\x00\x08\x00\x00\x00" + b"\x00" * 20, "unsupported_image"),
    ],
)
def test_a_file_that_is_not_a_readable_image_is_a_failed_result(data: bytes, code: str) -> None:
    result = image_run("scan.png", "image/png", data)
    assert result.status == "failed" and [p.code for p in result.problems] == [code]


def test_a_file_over_the_size_limit_is_refused_before_it_is_read() -> None:
    source = source_for("big.png", "image/png", b"x").model_copy(
        update={"size": MAX_SOURCE_BYTES + 1}
    )
    result = run_source(EXTRACTOR, source, b"x")
    assert result.status == "failed" and [p.code for p in result.problems] == ["source_too_large"]


def test_the_same_bytes_give_the_same_result_and_it_survives_json() -> None:
    data = make_tiff(text={305: "ScanTool 2"})
    first, second = (image_run("a.tif", "image/tiff", data) for _ in range(2))
    assert first == second
    assert ExtractionResult.model_validate_json(first.model_dump_json()) == first
