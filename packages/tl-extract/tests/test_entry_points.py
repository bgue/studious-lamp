"""The plugins are found by entry point and exactly one of them accepts a given file (P1-I3B-S4)."""

from __future__ import annotations

from importlib.metadata import entry_points

import pytest
from extractsupport import XLSX_TYPE, source_for
from tl_core.derivation import EXTRACTOR_ENTRY_POINT, Extractor
from tl_extract.ocr import OcrExtractor
from tl_extract.pdf import PdfExtractor
from tl_extract.tabular import TabularExtractor


def loaded() -> dict[str, Extractor]:
    found = {}
    for point in entry_points(group=EXTRACTOR_ENTRY_POINT):
        if point.value.startswith("tl_extract."):
            found[point.name] = point.load()()
    return found


def test_the_three_extractors_are_registered_under_the_group() -> None:
    plugins = loaded()
    assert sorted(plugins) == ["ocr", "pdf", "tabular"]
    assert isinstance(plugins["tabular"], TabularExtractor)
    assert isinstance(plugins["pdf"], PdfExtractor)
    assert isinstance(plugins["ocr"], OcrExtractor)
    for name, plugin in plugins.items():
        assert isinstance(plugin, Extractor)
        assert plugin.name == name and plugin.version


@pytest.mark.parametrize(
    ("filename", "content_type", "who"),
    [
        ("index.csv", "text/csv", "tabular"),
        ("index.tsv", "text/tab-separated-values", "tabular"),
        ("book.xlsx", XLSX_TYPE, "tabular"),
        ("book.XLSX", "application/octet-stream", "tabular"),
        ("scan.pdf", "application/pdf", "pdf"),
        ("ISD-001.A", "application/pdf", "pdf"),
        ("scan.png", "image/png", "ocr"),
        ("scan.jpg", "image/jpeg", "ocr"),
        ("scan.jpeg", "application/octet-stream", "ocr"),
        ("scan.tif", "image/tiff", "ocr"),
        ("scan.tiff", "image/tiff", "ocr"),
        ("report.pdf", "text/csv", "pdf"),
        ("old.xls", "application/vnd.ms-excel", None),
        ("notes.txt", "text/plain", None),
        ("model.ifc", "application/octet-stream", None),
        ("garbage.bin", "application/octet-stream", None),
        ("noext", "", None),
    ],
)
def test_at_most_one_extractor_accepts_a_file(
    filename: str, content_type: str, who: str | None
) -> None:
    source = source_for(filename, content_type, b"x")
    accepting = sorted(name for name, plugin in loaded().items() if plugin.accepts(source))
    assert accepting == ([who] if who else [])
