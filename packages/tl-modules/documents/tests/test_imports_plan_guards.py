"""Rows the file reader cannot produce but a caller can build (P1-I2, guard after T12c)."""

from __future__ import annotations

from docworld import World
from tl_adapters.db import open_uow
from tl_mod_documents.imports.diff import plan_import
from tl_mod_documents.imports.model import ImportRow


def row(**more: object) -> ImportRow:
    fields: dict[str, object] = {
        "line": 2,
        "number": "",
        "title": "A title",
        "doc_type": None,
        "discipline": None,
        "originator": None,
        "legacy_revision": None,
        "legacy_status": None,
        "legacy_date": None,
    }
    fields.update(more)
    return ImportRow(**fields)  # type: ignore[arg-type]


def test_a_row_with_no_number_and_no_problems_is_invalid_not_new(world: World) -> None:
    with open_uow(world.db, readonly=True) as uow:
        found = plan_import(uow.conn(), "project:P123", [row()])
    assert found.counts() == {"new": 0, "exists": 0, "invalid": 1}
    assert found.invalid[0].problems == ["the document number is blank"]


def test_the_blank_number_reason_is_said_once(world: World) -> None:
    flagged = row(problems=["the document number is blank"])
    with open_uow(world.db, readonly=True) as uow:
        found = plan_import(uow.conn(), "project:P123", [flagged])
    assert found.invalid[0].problems == ["the document number is blank"]
