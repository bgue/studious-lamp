"""Reading a DMS export: the mapping template and ``read_rows`` (brief 9 M1, 29.6; P1-I2-T12b).

A mapping template says which column of a legacy file is the document number, the title, the type,
the discipline, the originator, and the revision, status and date the old register shows; how to
translate its codes (``ISOMETRIC`` in the file is ``ISO`` here). It is a YAML file in the form of
``dev/seed/templates/document-register-dms-export.yaml``. ``read_rows`` applies one to the text of
a CSV file and returns an ``ImportRow`` per data row. A cell that cannot be read does not stop the
file: the row carries the problem and the plan reports it.
"""

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
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise MappingError(f"{source}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise MappingError(f"{source}: a mapping template must be a YAML mapping")
    try:
        return DocumentMapping.model_validate(data)
    except ValidationError as exc:
        lines = []
        for error in exc.errors():
            location = ".".join(str(part) for part in error["loc"]) or "(document)"
            lines.append(f"{source}: {location}: {error['msg']}")
        raise MappingError("\n".join(lines)) from exc


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
    reader = csv.reader(
        io.StringIO(text.removeprefix("﻿")), delimiter=mapping.delimiter, strict=True
    )
    try:
        header = [cell.strip() for cell in next(reader)]
    except StopIteration as exc:
        raise MappingError("the file has no header row") from exc
    except csv.Error as exc:
        raise MappingError(f"the file is not readable as CSV: {exc}") from exc
    # A blank header cell names no column (a trailing comma in an export), so it never counts.
    twice = sorted({name for name in header if name and header.count(name) > 1})
    if twice:
        raise MappingError("the file has a column twice: " + ", ".join(twice))
    missing = [column.column for column in mapping.columns if column.column not in header]
    if missing:
        raise MappingError("the file lacks the column(s): " + ", ".join(missing))
    try:
        records = list(enumerate(reader, start=2))
    except csv.Error as exc:
        raise MappingError(f"the file is not readable as CSV: {exc}") from exc

    rows: list[ImportRow] = []
    for line, cells in records:
        stripped = [cell.strip() for cell in cells]
        if not any(stripped):
            continue
        raw = {name: (stripped[i] if i < len(stripped) else "") for i, name in enumerate(header)}
        number = ""
        title: str | None = None
        doc_type: str | None = None
        discipline: str | None = None
        originator: str | None = None
        legacy_revision: str | None = None
        legacy_status: str | None = None
        legacy_date: str | None = None
        problems: list[str] = []
        for column in mapping.columns:
            cell = raw[column.column]
            if not cell:
                if column.to == "number":
                    problems.append("the document number is blank")
                continue
            if column.values and cell not in column.values:
                problems.append(f"{column.column}: {cell!r} is not one of the mapped values")
                continue
            value = column.values[cell] if column.values else cell
            if column.to == "number":
                number = value
            elif column.to == "title":
                title = value
            elif column.to == "type":
                doc_type = value
            elif column.to == "discipline":
                discipline = value
            elif column.to == "originator":
                originator = value
            elif column.to == "revision":
                legacy_revision = value
            elif column.to == "status":
                legacy_status = value
            elif column.to == "date":
                legacy_date = value
        rows.append(
            ImportRow(
                line=line,
                number=number,
                title=title,
                doc_type=doc_type,
                discipline=discipline,
                originator=originator,
                legacy_revision=legacy_revision,
                legacy_status=legacy_status,
                legacy_date=legacy_date,
                problems=problems,
                raw=raw,
            )
        )
    return rows
