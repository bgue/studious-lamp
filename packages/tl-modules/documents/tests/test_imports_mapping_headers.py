"""Blank and repeated header cells of a DMS export (P1-I2, supervisor decision after T12b)."""

from __future__ import annotations

import pytest
from tl_mod_documents.imports.mapping import MappingError, parse_mapping, read_rows

TEMPLATE = """\
name: small
description: a small template
columns:
  - {column: DOC, to: number}
  - {column: NAME, to: title}
"""


def test_unnamed_columns_are_ignored_even_when_there_are_several() -> None:
    """Exports often end every line with commas: two blank header cells are not a duplicate."""
    mapping = parse_mapping(TEMPLATE)
    rows = read_rows("DOC,NAME,,\nISO-1,First,,\nISO-2,Second,x,y\n", mapping)
    assert [(r.number, r.title, r.problems) for r in rows] == [
        ("ISO-1", "First", []),
        ("ISO-2", "Second", []),
    ]


def test_a_named_column_twice_is_still_refused() -> None:
    with pytest.raises(MappingError, match="the file has a column twice: NAME"):
        read_rows("DOC,NAME,NAME\nISO-1,a,b\n", parse_mapping(TEMPLATE))
