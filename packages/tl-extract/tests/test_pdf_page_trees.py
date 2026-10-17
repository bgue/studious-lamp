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
    "objects",
    [
        self_referencing(b""),
        self_referencing(b"/Count 7 "),
        self_referencing(b"/Count 5000000000 "),
        two_node_cycle(),
        deep_chain(5000),
    ],
    ids=["self", "self-with-count", "self-with-huge-count", "two-node-cycle", "depth-5000"],
)
def test_a_page_tree_that_loops_or_nests_deeply_ends_quickly_with_no_page_count(
    objects: list[bytes],
) -> None:
    started = time.monotonic()
    info = read_pdf_info(pdf_from_objects(objects))
    assert info.page_count is None
    assert time.monotonic() - started < 5
