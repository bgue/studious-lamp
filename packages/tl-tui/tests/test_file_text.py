"""file_text writes a file the way a person reads it (P1-UX2-T02)."""

from __future__ import annotations

import pytest
from tl_tui.file_text import file_kind, file_line, human_size


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (-5, "0 B"),
        (0, "0 B"),
        (1, "1 B"),
        (1023, "1023 B"),
        (1024, "1.0 KB"),
        (1536, "1.5 KB"),
        (1048576, "1.0 MB"),
        (5 * 1024**3, "5.0 GB"),
        (3000 * 1024**3, "3000.0 GB"),
    ],
)
def test_human_size(n: int, expected: str) -> None:
    assert human_size(n) == expected


@pytest.mark.parametrize(
    ("content_type", "filename", "expected"),
    [
        ("application/pdf", "a.bin", "PDF document"),
        ("application/octet-stream", "Layout.PDF", "PDF document"),
        (None, "memo.docx", "Word document"),
        ("application/msword", "x", "Word document"),
        ("application/vnd.ms-excel", "x", "Excel spreadsheet"),
        ("", "book.xlsx", "Excel spreadsheet"),
        ("text/csv", "x", "CSV file"),
        ("image/png", "x", "Image"),
        (None, "scan.TIFF", "Image"),
        (None, "plan.dwg", "Drawing"),
        ("message/rfc822", "x", "Email"),
        (None, "note.msg", "Email"),
        ("application/zip", "pack.zip", "File"),
        (None, "noextension", "File"),
    ],
)
def test_file_kind(content_type: str | None, filename: str, expected: str) -> None:
    assert file_kind(content_type, filename) == expected


def test_file_line_with_pages() -> None:
    line = file_line("Piling-layout.pdf", "application/pdf", 1258291, 3)
    assert line == "Piling-layout.pdf  PDF document  1.2 MB  3 pages"


def test_file_line_one_page_and_no_pages() -> None:
    assert file_line("a.pdf", "application/pdf", 10, 1) == "a.pdf  PDF document  10 B  1 page"
    assert file_line("a.pdf", "application/pdf", 10, None) == "a.pdf  PDF document  10 B"
    assert file_line("a.pdf", "application/pdf", 10, 0) == "a.pdf  PDF document  10 B"


def test_file_line_keeps_the_name_whole() -> None:
    name = "a very long drawing name with spaces and [brackets] 2026-10-21 rev B.dwg"
    assert file_line(name, None, 2048).startswith(name + "  Drawing  2.0 KB")
