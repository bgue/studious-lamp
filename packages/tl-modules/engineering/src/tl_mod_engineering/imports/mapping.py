"""Reading a tag list: the mapping template and ``read_rows`` (brief 9 M2, 29.6; P1-I1-T10a).

A mapping template says which column of a legacy file is the tag number, the class, the service
description or a property of a property set, how to read its cells (text, decimal, integer, yes or
no) and how to translate its codes (``CV`` in the file is ``ControlValve`` here). It is a YAML file
in the form of ``dev/seed/templates/tag-list-instrument-index.yaml``. ``read_rows`` applies one to
the text of a CSV file and returns an ``ImportRow`` per data row. A cell that cannot be read does
not stop the file: the row carries the problem and the diff reports it.

STUB (P1-I1-T10a): ``parse_mapping``, ``load_mapping``, ``_read_cell`` and ``read_rows`` raise
NotImplementedError; the models, the signatures and the docstrings are final. Each body has a
STEPS comment. Implement them, then delete this paragraph, the STEPS comments and the
``ruff: noqa`` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

import csv
import io
import math
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from tl_mod_engineering.imports.model import ImportRow

#: ``to:`` of a property column: ``psets.valve_data.size_in`` or ``psets.valve_data.x.fat_by``.
PSET_TARGET = re.compile(r"psets\.([a-z][a-z0-9_]*)\.((?:x\.)?[a-z][a-z0-9_]*)")
TARGETS = ("number", "class", "service")
_TRUE = frozenset({"yes", "y", "true", "t", "1"})
_FALSE = frozenset({"no", "n", "false", "f", "0"})


class MappingError(ValueError):
    """A mapping template or a file that cannot be read. The message names the source."""


class ColumnMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str = Field(min_length=1)  # the header of the column in the file
    to: str  # "number", "class", "service" or "psets.<pset>.<property>"
    type: Literal["string", "decimal", "int", "bool"] = "string"
    values: dict[str, str] = {}  # translation of cell text; used with "class" and string targets

    @field_validator("to")
    @classmethod
    def _target(cls, value: str) -> str:
        if value not in TARGETS and PSET_TARGET.fullmatch(value) is None:
            raise ValueError(
                f"to must be number, class, service or psets.<pset>.<property>, got {value!r}"
            )
        return value

    @model_validator(mode="after")
    def _values_fit(self) -> ColumnMap:
        if self.values and self.type != "string":
            raise ValueError("values translate text; a decimal, int or bool column has none")
        if self.values and self.to in ("number", "service"):
            raise ValueError(f"{self.to} cannot have values")
        return self


class TagListMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    delimiter: str = ","
    columns: list[ColumnMap] = Field(min_length=1)
    ignore: list[str] = []  # columns the file has and the import does not want

    @field_validator("delimiter")
    @classmethod
    def _delimiter(cls, value: str) -> str:
        if len(value) != 1 or value in ('"', "\n", "\r"):
            raise ValueError("delimiter must be one character other than a quote or a newline")
        return value

    @model_validator(mode="after")
    def _consistent(self) -> TagListMapping:
        targets = [c.to for c in self.columns]
        if targets.count("number") != 1:
            raise ValueError("exactly one column must map to number")
        for target in sorted({t for t in targets if targets.count(t) > 1}):
            raise ValueError(f"two columns map to {target}")
        headers = [c.column for c in self.columns]
        for header in sorted({h for h in headers if headers.count(h) > 1}):
            raise ValueError(f"column {header!r} is mapped twice")
        for header in self.ignore:
            if header in headers:
                raise ValueError(f"column {header!r} is both mapped and ignored")
        return self


def parse_mapping(text: str, *, source: str = "<string>") -> TagListMapping:
    """Parse YAML text into a ``TagListMapping``.

    Raises ``MappingError`` whose message starts with ``source``: invalid YAML, a document that is
    not a mapping, or a field that does not validate (one line each, ``<location>: <why>``).
    """
    # STEPS
    # 1. data = yaml.safe_load(text). A yaml.YAMLError becomes
    #    MappingError(f"{source}: invalid YAML: {exc}") (raise ... from exc).
    # 2. If data is not a dict:
    #    MappingError(f"{source}: a mapping template must be a YAML mapping").
    # 3. TagListMapping.model_validate(data). A ValidationError becomes one MappingError whose
    #    message has one line per error: f"{source}: {location}: {message}", where location is the
    #    error's "loc" parts joined with "." (or "(document)" when empty) and message is its "msg".
    raise NotImplementedError


def load_mapping(path: Path) -> TagListMapping:
    """Read and parse one template file. A read error becomes a ``MappingError``."""
    # STEPS
    # 1. Read the file as UTF-8; an OSError or UnicodeDecodeError becomes
    #    MappingError(f"{path.name}: cannot read file: {exc}") (raise ... from exc).
    # 2. return parse_mapping(text, source=path.name).
    raise NotImplementedError


def _read_cell(column: ColumnMap, cell: str) -> tuple[Any, str | None]:
    """``(value, problem)`` for one non-blank cell: exactly one of the two is ``None``."""
    # STEPS
    # 1. type "string": with column.values, a cell found in it gives (column.values[cell], None);
    #    a cell not found gives
    #    (None, f"{column.column}: {cell!r} is not one of the mapped values").
    #    Without values the cell itself is the value.
    # 2. type "bool": cell.lower() in _TRUE gives True, in _FALSE gives False; anything else is a
    #    problem. type "int": int(cell). type "decimal": float(cell), which must be finite
    #    (math.isfinite), else it is a problem.
    # 3. The problem text for 2 is f"{column.column}: {cell[:40]!r} is not a valid {column.type}".
    #    Catch ValueError and OverflowError around the conversions (an integer of 5,000 digits
    #    raises ValueError).
    raise NotImplementedError


def read_rows(text: str, mapping: TagListMapping) -> list[ImportRow]:
    """The data rows of a CSV file as ``ImportRow`` values, in file order.

    A leading byte-order mark is ignored. Header cells are compared after stripping. A completely
    blank line is skipped. For each row: cells are stripped; a blank cell leaves the field unset;
    a tag number that is blank, a code the mapping's ``values`` does not know, or a cell that is not
    of its column's type is a problem of that row (the field stays unset). ``raw`` holds every
    cell by header, including columns the mapping does not mention.

    Raises ``MappingError`` when the file has no header row, lacks a column the mapping names (the
    message lists every missing column) or is not valid CSV (an unterminated quote).
    """
    # STEPS
    # 1. reader = csv.reader(io.StringIO(text.removeprefix("\ufeff")), delimiter=mapping.delimiter,
    #    strict=True). header = [cell.strip() for cell in next(reader)]; an empty file
    #    (StopIteration) is MappingError("the file has no header row").
    # 2. missing = the mapping's column headers not in header, in the mapping's order. If any:
    #    MappingError("the file lacks the column(s): " + ", ".join(missing)).
    # 3. Read all records with records = list(enumerate(reader, start=2)); a csv.Error becomes
    #    MappingError(f"the file is not readable as CSV: {exc}").
    # 4. For each (number, cells): skip it when every cell is blank after stripping. raw = every
    #    header to its stripped cell ("" when the row is short).
    # 5. For each mapped column in the mapping's order, take its cell from raw. A blank cell sets
    #    nothing, except that a blank cell of the "number" column adds the problem
    #    "the tag number is blank". A non-blank cell goes through _read_cell: a problem is added to
    #    the row's problems and nothing is set; otherwise the value goes to the number (tag),
    #    class_code, service, or psets[<pset>][<property>] named by column.to. For a pset target
    #    use PSET_TARGET.fullmatch(column.to): group 1 is the pset, group 2 the property key
    #    (which may be "x.name").
    # 6. Append ImportRow(line=number, number=tag, class_code=..., service=..., psets=...,
    #    problems=..., raw=raw). Return the rows in file order.
    raise NotImplementedError
