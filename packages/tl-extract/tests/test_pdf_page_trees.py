"""Page trees that loop or nest deeply cannot make the PDF reader loop or recurse (P1-I3B-S9)."""

from __future__ import annotations

import time

import pytest
from extractsupport import pdf_from_objects
from tl_extract.pdfinfo import read_pdf_info

CATALOG = b"<< /Type /Catalog /Pages 2 0 R >>"


def self_referencing(count: bytes) -> list[bytes]:
    return [CATALOG, b"<< /Type /Pages /Kids [2 0 R] " + count + b">>"]


def two_node_cycle() -> list[bytes]:
    return [
        CATALOG,
        b"<< /Type /Pages /Kids [3 0 R] >>",
        b"<< /Type /Pages /Kids [2 0 R] /Parent 2 0 R >>",
    ]


def deep_chain(depth: int) -> list[bytes]:
    nodes = [f"<< /Type /Pages /Kids [{i + 1} 0 R] >>".encode() for i in range(2, depth + 2)]
    return [CATALOG, *nodes, b"<< /Type /Page >>"]


@pytest.mark.parametrize(
    ("objects", "count", "problems"),
    [
        (self_referencing(b""), None, []),
        (self_referencing(b"/Count 7 "), 7, []),  # the page count is what /Count says, no more
        (self_referencing(b"/Count 5000000000 "), None, ["bad_page_count"]),
        (self_referencing(b"/Count -1 "), None, ["bad_page_count"]),
        (self_referencing(b"/Count (seven) "), None, []),
        (two_node_cycle(), None, []),
        (deep_chain(5000), None, []),
    ],
    ids=["self", "self-with-count", "huge-count", "negative-count", "text-count", "cycle", "deep"],
)
def test_the_page_count_is_the_root_pages_count_and_no_page_tree_is_walked(
    objects: list[bytes], count: int | None, problems: list[str]
) -> None:
    started = time.monotonic()
    info = read_pdf_info(pdf_from_objects(objects))
    assert (info.page_count, [code for code, _ in info.problems]) == (count, problems)
    assert time.monotonic() - started < 2
