# P1-I2-T12b — Import: the mapping template and the file reader

Status: ready
Tier: haiku
Labels: module
Depends on: S18 on `p1/i2` (the import model, the seed template and sample file, in the tree); no other ticket
Branch: `p1/i2-t12b-import-mapping`

## Goal
A legacy DMS export can be read through a mapping template: `parse_mapping` turns YAML into a validated `DocumentMapping`, and `read_rows` turns a CSV file into `ImportRow` values, one per data row, with the problems of each row kept on the row. `packages/tl-modules/documents/src/tl_mod_documents/imports/mapping.py` has the models, `MappingError` and `load_mapping` written; `parse_mapping` and `read_rows` raise `NotImplementedError`. You implement them. One provided test file must pass.

## Brief references (pasted)
> **Brief 9 M1, 29.6.** Bulk import from the incumbent DMS document register: a mapping template says which column is which and how its codes translate; the import previews what would happen before it writes.
>
> **Existing pattern.** `tl_mod_engineering/import_.py` / `mapping.py` do the same for a legacy tag register; this one is smaller (documents only).

### Specification
- A cell that cannot be read never stops the file: the row carries the problem and the plan (another ticket) reports it. A file that cannot be read at all (no header, a missing column, a repeated column, bad CSV) raises `MappingError`.
- The messages are part of the contract; the test compares them exactly. The STEPS give them.
- `read_rows` and `parse_mapping` touch no database and no file (`load_mapping` reads the template file and is written).
- Do not change `model.py`, the template or the sample file.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-modules/documents/src/tl_mod_documents/imports/mapping.py` (the stub you complete):
```python
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
```

`packages/tl-modules/documents/src/tl_mod_documents/imports/model.py` (final; read-only):
```python
import annotationsfrom dataclasses import dataclass, field


@dataclass(frozen=True)
class ImportRow:
    """One data row of the file, after the mapping."""

    line: int  # row number of the file; the header is row 1, so the first data row is 2
    number: str  # the document number as written (stripped); empty when the cell was blank
    title: str | None
    doc_type: str | None  # the mapped document type code
    discipline: str | None  # the mapped discipline code
    originator: str | None
    legacy_revision: str | None  # the revision the old register shows, kept as a note
    legacy_status: str | None  # the status the old register shows, kept as a note
    legacy_date: str | None  # the date the old register shows, kept as a note
    problems: list[str] = field(default_factory=lambda: [])  # why the row cannot be used
    raw: dict[str, str] = field(default_factory=lambda: {})  # the row by column header

    @property
    def note(self) -> str | None:
        """The legacy columns as one sentence, for the document's description."""
        parts = [
            f"revision {self.legacy_revision}" if self.legacy_revision else None,
            f"status {self.legacy_status}" if self.legacy_status else None,
            f"dated {self.legacy_date}" if self.legacy_date else None,
        ]
        found = [p for p in parts if p]
        return "Legacy register: " + ", ".join(found) if found else None


@dataclass
class ImportPlan:
    new: list[ImportRow] = field(default_factory=lambda: [])  # would be registered
    exists: list[str] = field(default_factory=lambda: [])  # numbers the project already has
    invalid: list[ImportRow] = field(default_factory=lambda: [])  # rows that cannot be imported

    def counts(self) -> dict[str, int]:
        """``{"new": 3, "exists": 1, "invalid": 2}``."""
        return {"new": len(self.new), "exists": len(self.exists), "invalid": len(self.invalid)}
```

`dev/seed/templates/document-register-dms-export.yaml` (the template the tests use):
```yaml
# Mapping template: the document register export of the incumbent DMS (brief 9 M1, 29.6).
# Read by tl_mod_documents.imports.mapping (`tl doc import FILE --mapping THIS --project P123`).
# `dev/seed/legacy/dms-document-register.csv` is a sample file in this form. It sits beside the
# other seed templates because it is seed data of the same kind.
#
# The import registers documents. The old register's revision, status and date are kept as a note in
# the document's description; the revisions with their files come with the P1-I8 legacy loaders.
name: dms-document-register
description: >-
  The document register export of the incumbent DMS, one row per document: its number, title,
  type, discipline, originator, and the revision, status and date the old register shows.
delimiter: ","
columns:
  - {column: "DOC NO", to: number}
  - {column: "TITLE", to: title}
  - column: "DOC TYPE"
    to: type
    values:
      ISOMETRIC: ISO
      "P&ID": PID
      "GENERAL ARRANGEMENT": GA
      DATASHEET: DS
      "LOOP DIAGRAM": LD
      SPECIFICATION: SPC
      PROCEDURE: PRC
      CALCULATION: CAL
  - column: "DISCIPLINE"
    to: discipline
    values:
      PIPING: PIP
      MECHANICAL: MEC
      ELECTRICAL: ELE
      INSTRUMENTATION: INS
      CIVIL: CIV
      STRUCTURAL: STR
      PROCESS: PRO
  - {column: "ORIGINATOR", to: originator}
  - {column: "REV", to: revision}
  - column: "STATUS"
    to: status
    values:
      IFA: IFA
      IFR: IFR
      IFC: IFC
      AFC: AFC
      "AS BUILT": ASB
  - {column: "REV DATE", to: date}
# Columns the file has that the import does not want.
ignore: ["FILE PATH", "CHECKED BY", "REMARKS"]
```

`dev/seed/legacy/dms-document-register.csv` (first lines):
```text
DOC NO,TITLE,DOC TYPE,DISCIPLINE,ORIGINATOR,REV,STATUS,REV DATE,FILE PATH,CHECKED BY,REMARKS
ISO-0101,"Isometric, line 47-P-101",ISOMETRIC,PIPING,Acme Piping,C,IFC,2024-02-12,\\dms\p123\iso\ISO-0101_C.pdf,R. Singh,
ISO-0102,"Isometric, line 47-P-102",ISOMETRIC,PIPING,Acme Piping,B,IFC,2024-02-12,\\dms\p123\iso\ISO-0102_B.pdf,R. Singh,
PID-0001,P&ID feed gas section,P&ID,PROCESS,Acme Process,D,AFC,2024-01-20,\\dms\p123\pid\PID-0001_D.pdf,L. Moreau,Hold 3 open
PID-0002,P&ID flare header,P&ID,PROCESS,Acme Process,A,IFR,2024-03-02,\\dms\p123\pid\PID-0002_A.pdf,,
```

## Context (read these, nothing else)
- `packages/tl-modules/documents/src/tl_mod_documents/imports/mapping.py` (the file you edit)
- `packages/tl-modules/documents/src/tl_mod_documents/imports/model.py` (final)
- `dev/seed/templates/document-register-dms-export.yaml` and `dev/seed/legacy/dms-document-register.csv`
- `packages/tl-modules/engineering/src/tl_mod_engineering/import_/mapping.py` or the nearest equivalent (the same job for tags; style)
- `docs/tickets/P1-I2/provided/t12b-test_imports_mapping.py.txt` (the test)
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing. pyright is `standard` for `packages/tl-modules`, `tl-cli`, `tl-api`; strict for `tl_core`, `tl_schema`, `tl_adapters`.
- Provided files live under `docs/tickets/P1-I2/provided/` as `.py.txt`; copy them into the tree byte for byte (the target names are in *Steps*). Do not edit the copies: they are already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I2/<ticket-id>.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. Remove the `STUB` paragraph from the module docstring, every `STEPS` comment and the `# ruff: noqa: F401` line when you implement a stub.
- The test counts below were counted from the provided files (`grep -c "^def test_"`); parametrized tests expand to more cases when run, and the pytest summary is the number of cases (L-P0-I8A-8). A test that does not use the `db`, `world` or `engine` fixtures runs once under `--adapters sqlite,postgres`; one that does runs once per adapter (L-P1-I1-6).
- Never name a module `types.py`, `enum.py` or `json.py` inside a package (L-P0-I5-B1).
- Never write a hand-made `cur_*`, `hist_*` or `v_*` object, and never change `schema/**` or anything under `generated/` unless this ticket says so.
- `just test-parity` takes about 70 minutes for the whole repository (L-P1-I1-10): run only the scoped commands in *Acceptance* (a ticket whose tests do not use the database fixtures has no Postgres command), never the whole parity suite.
- Start Postgres with `sudo pg_ctlcluster 16 main start` if it is not running; `TL_PG_URL` is `postgresql://postgres:postgres@localhost:5432/tl_test`.
- A YAML key `NO` parses as the boolean False (the Norway problem); quote such keys in test templates. The seed template names its columns so that this cannot happen.
- Tests without the `world`/`db` fixtures run once under `--adapters sqlite,postgres`.
- `pyright` is `standard` for `packages/tl-modules`: annotate `list[...]` and `dict[...]` variables you start empty.

## Allowed paths
- `packages/tl-modules/documents/src/tl_mod_documents/imports/mapping.py` (edit)
- `packages/tl-modules/documents/tests/test_imports_mapping.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I2/P1-I2-T12b.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I2/provided/t12b-test_imports_mapping.py.txt` to `packages/tl-modules/documents/tests/test_imports_mapping.py`.
3. Implement `parse_mapping`, then `read_rows`, by their STEPS comments; remove the STUB paragraph, the STEPS comments and the `ruff: noqa` line.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-modules/documents/tests/test_imports_mapping.py -q
TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test uv run pytest packages/tl-modules/documents/tests/test_imports_mapping.py -q --adapters sqlite,postgres
uv run pytest packages/tl-modules/documents -q
```
Expected: `just check` clean; 8 test functions pass (on SQLite and again on Postgres); the whole package passes.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus: the decisive lines of the parity run (the `--adapters sqlite,postgres` command in Acceptance).

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree.
- Stop if a test needs a change outside the Allowed paths.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
