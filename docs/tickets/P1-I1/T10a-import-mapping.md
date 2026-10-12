# P1-I1-T10a — Tag-list mapping template and CSV reader

Status: ready
Tier: haiku
Labels: core
Depends on: P1-I1-S3 (`imports/model.py` and the module package, on `p1/i1`); no other ticket
Branch: `p1/i1-t10a-import-mapping`

## Goal
The first step of a bulk tag import: read a legacy tag list (a CSV file) with a **mapping template** (a YAML file that says which
column is the tag number, the class, the service description or a property of a property set, and how to read each cell) and
produce one `ImportRow` per data row. `imports/mapping.py` has the pydantic models of the template, the constants, and four
functions with their signatures and docstrings final and their bodies raising `NotImplementedError`: `parse_mapping`,
`load_mapping`, `_read_cell` and `read_rows`. You implement them. One provided test file (`16` test functions, 36
cases) must pass.

## Brief references (pasted)
> **Brief 9 M2 Behaviour.** Bulk import from derived documents (instrument index, line list, equipment list) with diff preview: new / changed / removed tags, property changes per pset.
>
> **Brief 29.6 Legacy loading.** Spreadsheets (weld logs, punch lists, registers, line lists, tag lists): XLSX/CSV extractor with column profiling → map (declarative, LinkML-validated mappings; crosswalks for value lists; key normalisation via Standards registry patterns) → dry-run validate → load via public commands. Nothing in the source is lost: unmapped data is kept.
>
> **Brief 29.8.** Legacy mapping template provided (per module).

### Specification
- A **template** is YAML: `name`, `description`, optional `delimiter` (one character, default `,`), `columns` (each: `column` = the header in the file, `to`, optional `type` and `values`), optional `ignore` (headers the file has and the import does not want). `to` is `number`, `class`, `service` or `psets.<pset>.<property>` (a custom property is `psets.<pset>.x.<property>`). `type` is `string` (default), `decimal`, `int` or `bool`. `values` translates the text of a cell (`CV` in the file is `ControlValve`).
- The models already check the template as a whole (one `number` column, no target or header twice, no header both mapped and ignored, `values` only on text columns that are not `number` or `service`). `parse_mapping` adds YAML parsing and the error format; `read_rows` does the reading.
- **Reading a file** (`read_rows`): the first record is the header; header cells are compared after stripping; a leading byte-order mark is ignored. Every column the template maps must be in the header, else `MappingError("the file lacks the column(s): A, B")` listing them in the template's order. `raw` of a row holds *every* header of the file with its stripped cell, including columns the template does not mention (nothing in the source is lost).
- **Cells**: stripped. A blank cell leaves its field unset (`None`, or absent from `psets`). A blank `number` cell is the row problem `the tag number is blank`. A cell that cannot be read is a problem of its row and leaves the field unset; the file is still read to the end. Problem texts are in the specification of `_read_cell` and `read_rows` (the test checks them exactly).
- **Rows**: `line` counts records with the header as row 1, so the first data row is 2 (a quoted cell with a line break inside counts once). A row whose cells are all blank is skipped (its number is still used by the next row).
- Hostile input (L-P0-I8A-9): `inf`, `nan` and `1e999` are not decimals; an integer of thousands of digits makes `int()` raise `ValueError`: both are row problems, never a crash. Use `csv.reader(..., strict=True)` so a quote that is never closed is a `csv.Error`.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-modules/engineering/src/tl_mod_engineering/imports/mapping.py` (the stub you complete):
```python
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
```

`packages/tl-modules/engineering/src/tl_mod_engineering/imports/model.py`:
```python
"""The values the tag-list import passes between its steps (brief 9 M2, bulk import).

``mapping.read_rows`` turns a file into ``ImportRow`` values; ``diff.plan_import`` compares them
with the tags the project already has (``ExistingTag``) and returns an ``ImportPlan``: what would
be created, changed or left out, and which rows cannot be imported. Nothing here touches the
ledger; applying a plan is ``tl_mod_engineering.imports.apply``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ImportRow:
    """One data row of the file, after the mapping."""

    line: int  # row number of the file; the header is row 1, so the first data row is 2
    number: str  # the tag number as written (stripped); empty when the cell was blank
    class_code: str | None  # the mapped class code; None when the cell was blank
    service: str | None  # the service description (becomes the tag's title); None when blank
    psets: dict[str, dict[str, Any]]  # {"valve_data": {"size_in": 4.0}}; blank cells are absent
    problems: list[str] = field(default_factory=lambda: [])  # why the row cannot be used
    raw: dict[str, str] = field(default_factory=lambda: {})  # the row by column header


@dataclass(frozen=True)
class ExistingTag:
    """A tag the project already holds, as far as the import compares it."""

    id: str
    number: str
    class_code: str | None
    service: str  # the record title
    psets: dict[str, Any]  # the record's psets object
    version: int


@dataclass(frozen=True)
class FieldChange:
    field: str  # "class", "service" or "psets.<pset>.<property>"
    old: Any
    new: Any


@dataclass(frozen=True)
class RowChange:
    line: int
    number: str
    tag_id: str
    changes: list[FieldChange]


@dataclass
class ImportPlan:
    new: list[ImportRow] = field(default_factory=lambda: [])
    changed: list[RowChange] = field(default_factory=lambda: [])
    unchanged: list[str] = field(default_factory=lambda: [])  # tag numbers
    removed: list[ExistingTag] = field(default_factory=lambda: [])  # not in the file
    invalid: list[ImportRow] = field(default_factory=lambda: [])  # rows that cannot be imported

    def counts(self) -> dict[str, int]:
        """``{"new": 3, "changed": 1, "unchanged": 10, "removed": 0, "invalid": 2}``."""
        return {
            "new": len(self.new),
            "changed": len(self.changed),
            "unchanged": len(self.unchanged),
            "removed": len(self.removed),
            "invalid": len(self.invalid),
        }
```

## Context (read these, nothing else)
- `packages/tl-modules/engineering/src/tl_mod_engineering/imports/mapping.py` (the file you edit)
- `packages/tl-modules/engineering/src/tl_mod_engineering/imports/model.py`
- `docs/tickets/P1-I1/provided/t10a-test_import_mapping.py.txt` (the test)
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- pyright is `standard` for `packages/tl-modules`; ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing.
- Provided files live under `docs/tickets/P1-I1/provided/` as `.py.txt`; copy them into the tree byte for byte (the target names are in *Steps*). Do not edit the copies: they are already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I1/<ticket-id>.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. Remove the `STUB` paragraph from the module docstring, every `STEPS` comment and the `# ruff: noqa: F401` line when you implement a stub.
- The test counts below were counted from the provided files (`grep -c "^def test_"`); parametrized tests expand to more cases when run, and the pytest summary is the number of cases (L-P0-I8A-8).
- Never name a module `types.py`, `enum.py` or `json.py` inside a package (L-P0-I5-B1).
- Never write a hand-made `cur_*` table or change `schema/**` or anything under `generated/` unless this ticket says so.
- This ticket is pure code: no database, no ledger. `csv.reader` hands back lists of strings; `enumerate(reader, start=2)` numbers the data records.

## Allowed paths
- `packages/tl-modules/engineering/src/tl_mod_engineering/imports/mapping.py` (edit)
- `packages/tl-modules/engineering/tests/test_import_mapping.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I1/P1-I1-T10a.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I1/provided/t10a-test_import_mapping.py.txt` to `packages/tl-modules/engineering/tests/test_import_mapping.py`.
3. Implement the four functions by their STEPS comments; remove the STUB paragraph, the STEPS comments and the `ruff: noqa` line.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-modules/engineering/tests/test_import_mapping.py -q
uv run pytest packages/tl-modules -q
```
Expected: `just check` clean; 36 passed; the whole module package passes.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`).

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree.
- Stop if a test needs a change in `model.py` or in the models of `mapping.py`.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
