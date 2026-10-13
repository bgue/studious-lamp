"""Reading a DMS export: the mapping template and ``read_rows`` (brief 9 M1, 29.6; P1-I2-T12b).

A mapping template says which column of a legacy file is the document number, the title, the type,
the discipline, the originator, and the revision, status and date the old register shows; how to
translate its codes (``ISOMETRIC`` in the file is ``ISO`` here). It is a YAML file in the form of
``dev/seed/templates/document-register-dms-export.yaml``. ``read_rows`` applies one to the text of
a CSV file and returns an ``ImportRow`` per data row. A cell that cannot be read does not stop the
file: the row carries the problem and the plan reports it.

STUB (P1-I2-T12b): the bodies of parse_mapping and read_rows raise NotImplementedError; their
signatures, options, docstrings and the helpers are final. Each body has a STEPS comment.
Implement them, then delete this paragraph, the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

import csv
import io
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from tl_mod_documents.imports.model import ImportRow

#: What a column can be: the number is required, once; the rest are optional, once each.
TARGETS = ("number", "title", "type", "discipline", "originator", "revision", "status", "date")


class MappingError(ValueError):
    """A mapping template or a file that cannot be read. The message names the source."""


class ColumnMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str = Field(min_length=1)  # the header of the column in the file
    to: str
    values: dict[str, str] = {}  # translation of cell text (type, discipline and status only)

    @field_validator("to")
    @classmethod
    def _target(cls, value: str) -> str:
        if value not in TARGETS:
            raise ValueError(f"to must be one of {', '.join(TARGETS)}, got {value!r}")
        return value

    @model_validator(mode="after")
    def _values_fit(self) -> ColumnMap:
        if self.values and self.to not in ("type", "discipline", "status"):
            raise ValueError(f"{self.to} cannot have values")
        return self


class DocumentMapping(BaseModel):
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
    def _consistent(self) -> DocumentMapping:
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


def parse_mapping(text: str, *, source: str = "<string>") -> DocumentMapping:
    """Parse YAML text into a ``DocumentMapping``.

    Raises ``MappingError`` whose message starts with ``source``: invalid YAML, a document that is
    not a mapping, or a field that does not validate (one line each, ``<location>: <why>``).
    """
    # STEPS
    # 1. data = yaml.safe_load(text); a yaml.YAMLError is MappingError(f"{source}: invalid YAML:
    #    {exc}") (raise ... from exc).
    # 2. When data is not a dict: MappingError(f"{source}: a mapping template must be a YAML
    #    mapping").
    # 3. Return DocumentMapping.model_validate(data). A ValidationError becomes one MappingError
    #    whose message has one line per error, f"{source}: {location}: {message}", where location
    #    is the dotted `loc` of the error or "(document)" when it is empty.
    raise NotImplementedError


def load_mapping(path: Path) -> DocumentMapping:
    """Read and parse one template file. A read error becomes a ``MappingError``."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise MappingError(f"{path.name}: cannot read file: {exc}") from exc
    return parse_mapping(text, source=path.name)


def read_rows(text: str, mapping: DocumentMapping) -> list[ImportRow]:
    """The data rows of a CSV file as ``ImportRow`` values, in file order.

    A leading byte-order mark is ignored. Header cells are compared after stripping. A completely
    blank line is skipped. For each row: cells are stripped; a blank cell leaves the field unset;
    a document number that is blank, or a code the mapping's ``values`` does not know, is a problem
    of that row (the field stays unset). ``raw`` holds every cell by header, including columns the
    mapping does not mention.

    Raises ``MappingError`` when the file has no header row, lacks a column the mapping names (the
    message lists every missing column), has a column twice or is not valid CSV.
    """
    # STEPS
    # 1. reader = csv.reader(io.StringIO(text.removeprefix("﻿")),
    #    delimiter=mapping.delimiter, strict=True). header = [cell.strip() for cell in
    #    next(reader)]; StopIteration is MappingError("the file has no header row"); csv.Error is
    #    MappingError(f"the file is not readable as CSV: {exc}").
    # 2. A header name that appears twice: MappingError("the file has a column twice: " +
    #    ", ".join(sorted names)). Mapped columns the header lacks: MappingError("the file lacks
    #    the column(s): " + ", ".join(them, in the order of mapping.columns)).
    # 3. records = list(enumerate(reader, start=2)) (a csv.Error here is the "not readable as CSV"
    #    error too).
    # 4. For each (line, cells): stripped = [c.strip() for c in cells]; skip the row when no cell
    #    is non-blank; raw = {header name: stripped[i] or "" past the end of the row}.
    # 5. For each column of mapping.columns: cell = raw[column.column]. A blank cell: for the
    #    number add the problem "the document number is blank", for any other column nothing.
    #    Otherwise value = column.values[cell] when column.values is non-empty and has the cell,
    #    else problem f"{column.column}: {cell!r} is not one of the mapped values" when values is
    #    non-empty and lacks it, else the cell itself. Set the field of column.to: number,
    #    title, doc_type (to "type"), discipline, originator, legacy_revision ("revision"),
    #    legacy_status ("status"), legacy_date ("date").
    # 6. Append ImportRow(line=line, number=number or "", title=..., doc_type=..., discipline=...,
    #    originator=..., legacy_revision=..., legacy_status=..., legacy_date=..., problems=...,
    #    raw=raw).
    raise NotImplementedError
