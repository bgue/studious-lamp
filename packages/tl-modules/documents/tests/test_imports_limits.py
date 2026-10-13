"""What the import refuses before it writes: field limits, size and control characters.

Supervisor tests (security check of the import path): the plan must say what apply would refuse,
a file has a size, and a control character is a problem of its row, never a crash.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from docworld import BASE, World
from pydantic import ValidationError
from tl_adapters.db import open_uow
from tl_mod_documents.handlers.documents import RegisterDocument
from tl_mod_documents.imports.apply import apply_plan
from tl_mod_documents.imports.diff import plan_import
from tl_mod_documents.imports.mapping import MappingError, parse_mapping, read_file_text, read_rows
from tl_mod_documents.imports.model import ImportRow
from tl_mod_documents.limits import (
    MAX_DESCRIPTION,
    MAX_IMPORT_BYTES,
    MAX_IMPORT_ROWS,
    MAX_LEGACY_CELL,
    MAX_NUMBER,
    MAX_TEXT,
)

SCOPE = "project:P123"
TEMPLATE = """\
name: limits
description: columns for the limit tests
columns:
  - {column: DOC, to: number}
  - {column: NAME, to: title}
  - {column: BY, to: originator}
  - {column: REV, to: revision}
  - {column: ST, to: status}
  - {column: DATED, to: date}
"""
HEAD = "DOC,NAME,BY,REV,ST,DATED\n"


def rows(body: str) -> list[ImportRow]:
    return read_rows(HEAD + body, parse_mapping(TEMPLATE))


def plan(world: World, found: list[ImportRow]) -> Any:
    with open_uow(world.db, readonly=True) as uow:
        return plan_import(uow.conn(), SCOPE, found)


def row(**more: Any) -> ImportRow:
    fields: dict[str, Any] = {
        "line": 2,
        "number": "ISO-1",
        "title": "A title",
        "doc_type": None,
        "discipline": None,
        "originator": None,
        "legacy_revision": None,
        "legacy_status": None,
        "legacy_date": None,
    }
    fields.update(more)
    return ImportRow(**fields)


# --- LOW-1: the plan says what apply would refuse -------------------------------------------------


@pytest.mark.parametrize(
    ("fields", "start"),
    [
        ({"title": "t" * (MAX_TEXT + 1)}, "title: "),
        ({"number": "N" * (MAX_NUMBER + 1)}, "number: "),
        ({"originator": "o" * (MAX_TEXT + 1)}, "originator: "),
        ({"doc_type": "d" * (MAX_NUMBER + 1)}, "doc_type: "),
        ({"discipline": "d" * (MAX_NUMBER + 1)}, "discipline: "),
        (
            {"legacy_revision": "r" * 4000, "legacy_status": "s" * 4000, "legacy_date": "d" * 4000},
            "description: ",
        ),
    ],
)
def test_the_plan_refuses_what_the_command_would_for_length(
    world: World, fields: dict[str, Any], start: str
) -> None:
    found = plan(world, [row(**fields)])
    assert found.counts() == {"new": 0, "exists": 0, "invalid": 1}
    assert [p.startswith(start) for p in found.invalid[0].problems] == [True]
    assert found.invalid[0].line == 2


def test_the_limits_are_the_models_own_so_a_row_at_the_limit_is_new(world: World) -> None:
    ok = row(title="t" * MAX_TEXT, number="N" * MAX_NUMBER, originator="o" * MAX_TEXT)
    assert plan(world, [ok]).counts() == {"new": 1, "exists": 0, "invalid": 0}
    too_long = row(title="t" * (MAX_TEXT + 1))
    assert plan(world, [too_long]).counts()["invalid"] == 1  # one over, from the same model


def test_a_long_title_does_not_stop_skip_invalid_from_importing_the_rest(world: World) -> None:
    found = plan(world, [row(number="ISO-1", title="t" * 600), row(number="ISO-2", line=3)])
    assert [r.number for r in found.invalid] == ["ISO-1"] and [r.number for r in found.new] == [
        "ISO-2"
    ]
    with open_uow(world.db) as uow:
        made = apply_plan(uow, SCOPE, found, actor="user:admin", job="long", skip_invalid=True)
    assert len(made) == 1 and world.document("ISO-2")


def test_a_legacy_cell_that_would_swell_the_note_is_a_row_problem() -> None:
    long = "x" * (MAX_LEGACY_CELL + 1)
    found = rows(f"ISO-1,Title,Acme,{long},IFC,2020-01-01\n")
    assert found[0].legacy_revision is None
    assert found[0].problems == [f"REV: longer than {MAX_LEGACY_CELL} characters"]
    fit = rows(f"ISO-1,Title,Acme,{'x' * MAX_LEGACY_CELL},IFC,2020-01-01\n")
    assert fit[0].problems == [] and len(fit[0].note or "") < MAX_DESCRIPTION


# --- LOW-2: size ----------------------------------------------------------------------------------


def test_a_file_with_too_many_rows_is_refused_with_the_limit() -> None:
    body = "".join(f"ISO-{n},T,,,,\n" for n in range(MAX_IMPORT_ROWS))
    assert len(rows(body)) == MAX_IMPORT_ROWS
    with pytest.raises(MappingError, match=f"more than {MAX_IMPORT_ROWS} rows"):
        rows(body + "ISO-X,T,,,,\n")


def test_a_file_over_the_byte_limit_is_refused_before_it_is_read(tmp_path: Path) -> None:
    big = tmp_path / "big.csv"
    with big.open("wb") as handle:
        handle.truncate(MAX_IMPORT_BYTES + 1)
    with pytest.raises(
        MappingError, match=r"big\.csv: the file is \d+ bytes; an import takes at most 5 MiB"
    ):
        read_file_text(big)
    with pytest.raises(MappingError, match="larger than 5 MiB"):
        read_rows("x" * (MAX_IMPORT_BYTES + 1), parse_mapping(TEMPLATE))
    small = tmp_path / "small.csv"
    small.write_text(HEAD + "ISO-1,T,,,,\n", encoding="utf-8")
    assert read_file_text(small).startswith("DOC,NAME")
    small.write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(MappingError, match=r"small\.csv: cannot read file"):
        read_file_text(small)


# --- LOW-3: control characters --------------------------------------------------------------------


@pytest.mark.parametrize("char", ["\x00", "\x01", "\x1b", "\x7f"])
def test_a_control_character_is_a_problem_of_its_row_and_the_cell_is_dropped(char: str) -> None:
    found = rows(f"ISO-1,Bad{char}title,Acme,,,\nISO-2,Fine,Acme,,,\n")
    assert found[0].title is None and found[0].problems == ["NAME: holds a control character"]
    assert found[1].problems == [] and found[1].title == "Fine"


def test_a_nul_in_the_document_number_does_not_become_a_number() -> None:
    found = rows("ISO-\x001,Title,,,,\n")
    assert found[0].number == "" and found[0].problems == ["DOC: holds a control character"]


def test_a_number_on_two_lines_or_with_a_tab_is_refused_but_a_title_may_wrap() -> None:
    found = rows('"ISO-1\n2",Title,,,,\n"ISO\t3",Title,,,,\nISO-4,"Two\nlines\there",,,,\n')
    assert found[0].problems == ["DOC: a document number must be on one line"]
    assert found[1].problems == ["DOC: a document number must be on one line"]
    assert found[2].problems == [] and found[2].title == "Two\nlines\there"


def test_the_command_refuses_a_number_with_a_line_break_or_a_control_character() -> None:
    for number in ("ISO\n1", "ISO\t1", "ISO\x7f1"):
        with pytest.raises(ValidationError, match="control character"):
            RegisterDocument(**BASE, number=number, title="x")


def test_a_nul_anywhere_in_a_register_command_is_a_validation_error() -> None:
    for field in ("number", "title", "description", "originator", "doc_type"):
        values: dict[str, Any] = {"number": "ISO-1", "title": "x", field: "a\x00b"}
        with pytest.raises(ValidationError):
            RegisterDocument(**BASE, **values)


def test_a_preview_with_a_nul_cell_does_not_reach_the_database_driver(world: World) -> None:
    """On Postgres a NUL in a query parameter raised an unhandled driver error with the SQL."""
    found = plan(world, rows("ISO-\x001,Title,,,,\nISO-2,Ok\x00,,,,\nISO-3,Fine,,,,\n"))
    assert found.counts() == {"new": 1, "exists": 0, "invalid": 2}
    assert [r.line for r in found.invalid] == [2, 3]
    # a row built by hand with a NUL in the number is judged without a query too
    assert plan(world, [row(number="ISO-\x001")]).counts()["invalid"] == 1
