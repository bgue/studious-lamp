"""Reading a tag list: the mapping template and ``read_rows`` (brief 9 M2, 29.6; P1-I1-T10a).

A mapping template says which column of a legacy file is the tag number, the class, the service
description or a property of a property set, how to read its cells (text, decimal, integer, yes or
no) and how to translate its codes (``CV`` in the file is ``ControlValve`` here). It is a YAML file
in the form of ``dev/seed/templates/tag-list-instrument-index.yaml``. ``read_rows`` applies one to
the text of a CSV file and returns an ``ImportRow`` per data row. A cell that cannot be read does
not stop the file: the row carries the problem and the diff reports it.
"""

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
        if self.to in ("number", "class", "service") and self.type != "string":
            raise ValueError(f"{self.to} is text; its type must be string")
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
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise MappingError(f"{source}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise MappingError(f"{source}: a mapping template must be a YAML mapping")
    try:
        return TagListMapping.model_validate(data)
    except ValidationError as exc:
        lines = []
        for error in exc.errors():
            location = ".".join(str(part) for part in error["loc"]) or "(document)"
            lines.append(f"{source}: {location}: {error['msg']}")
        raise MappingError("\n".join(lines)) from exc


def load_mapping(path: Path) -> TagListMapping:
    """Read and parse one template file. A read error becomes a ``MappingError``."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise MappingError(f"{path.name}: cannot read file: {exc}") from exc
    return parse_mapping(text, source=path.name)


def _read_cell(column: ColumnMap, cell: str) -> tuple[Any, str | None]:
    """``(value, problem)`` for one non-blank cell: exactly one of the two is ``None``."""
    if column.type == "string":
        if column.values:
            if cell in column.values:
                return column.values[cell], None
            return None, f"{column.column}: {cell!r} is not one of the mapped values"
        return cell, None
    problem = f"{column.column}: {cell[:40]!r} is not a valid {column.type}"
    try:
        if column.type == "bool":
            if cell.lower() in _TRUE:
                return True, None
            if cell.lower() in _FALSE:
                return False, None
            return None, problem
        if column.type == "int":
            return int(cell), None
        number = float(cell)
    except (ValueError, OverflowError):
        return None, problem
    if math.isfinite(number):
        return number, None
    return None, problem


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
    reader = csv.reader(
        io.StringIO(text.removeprefix("\ufeff")), delimiter=mapping.delimiter, strict=True
    )
    try:
        header = [cell.strip() for cell in next(reader)]
    except StopIteration as exc:
        raise MappingError("the file has no header row") from exc
    except csv.Error as exc:
        raise MappingError(f"the file is not readable as CSV: {exc}") from exc
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
    for number, cells in records:
        stripped = [cell.strip() for cell in cells]
        if not any(stripped):
            continue
        raw = {name: (stripped[i] if i < len(stripped) else "") for i, name in enumerate(header)}
        tag: str = ""
        class_code: str | None = None
        service: str | None = None
        psets: dict[str, dict[str, Any]] = {}
        problems: list[str] = []
        for column in mapping.columns:
            cell = raw[column.column]
            if not cell:
                if column.to == "number":
                    problems.append("the tag number is blank")
                continue
            value, problem = _read_cell(column, cell)
            if problem is not None:
                problems.append(problem)
                continue
            if column.to == "number":
                tag = value
            elif column.to == "class":
                class_code = value
            elif column.to == "service":
                service = value
            else:
                # ColumnMap has already checked that the target is a pset target.
                pset = PSET_TARGET.fullmatch(column.to)
                if pset is None:
                    raise MappingError(f"{column.to!r} is not a pset target")
                psets.setdefault(pset.group(1), {})[pset.group(2)] = value
        rows.append(
            ImportRow(
                line=number,
                number=tag,
                class_code=class_code,
                service=service,
                psets=psets,
                problems=problems,
                raw=raw,
            )
        )
    return rows
