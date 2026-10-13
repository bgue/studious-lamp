"""Revision schemes: how revision codes follow each other, and which scheme numbers a document.

Brief 9, M1: "Revision schemes are configurable per project and document type" (A/B/C, 0/1/2,
P1/C1). The schemes, the issue statuses (IFR, IFC, ...) with their status classes, and the
assignment of a scheme to a document type or a project are data in
``<schema dir>/documents/revision-schemes.yaml`` (``TL_SCHEMA_DIR`` or ``schema/fixtures``), read
on every call so an edited file applies at once.

A scheme turns a code into a ``position``, a tuple that orders the codes of that scheme
(``A < B < ... < Z < AA``, ``P1 < P2 < C1``), and a position into the next code. The ``ordinal``
of a revision is its count among a document's revisions and has nothing to do with the code; the
scheme only decides which codes are valid and in what order they may be used.

Letters: ``alpha`` counts like a spreadsheet column (``Z`` is followed by ``AA``) over the
letters that are not in ``skip``. ``numeric`` counts from ``start``. ``staged`` counts within a
stage (``P1``, ``P2``) and moves to the next stage on request (``C1``); a stage never goes back.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from tl_schema.registry import default_schema_dir

from tl_mod_documents.errors import (
    InvalidIssueStatusError,
    InvalidRevisionCodeError,
    UnknownSchemeError,
)

SCHEME_FILE = "documents/revision-schemes.yaml"
_CODE = re.compile(r"[A-Za-z0-9]{1,16}")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class StageDef(_Strict):
    prefix: str = Field(pattern=r"^[A-Z]{1,4}$")
    start: int = Field(default=1, ge=0, le=999)


class SchemeDef(_Strict):
    label: str = Field(min_length=1)
    kind: Literal["alpha", "numeric", "staged"]
    skip: list[str] = []
    start: str | int | None = None
    stages: list[StageDef] = []

    @field_validator("skip")
    @classmethod
    def _skip_letters(cls, value: list[str]) -> list[str]:
        for letter in value:
            if re.fullmatch(r"[A-Z]", letter) is None:
                raise ValueError(f"skip holds capital letters, got {letter!r}")
        return value


class StatusDef(_Strict):
    label: str = Field(min_length=1)
    status_class: str = Field(alias="class", min_length=1)


class ProjectAssignment(_Strict):
    default: str | None = None
    by_document_type: dict[str, str] = {}


class Assignment(_Strict):
    by_document_type: dict[str, str] = {}
    by_project: dict[str, ProjectAssignment] = {}


class SchemeFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_scheme: str
    schemes: dict[str, SchemeDef]
    statuses: dict[str, StatusDef]
    classes: list[str] = Field(min_length=1)
    assignment: Assignment = Assignment()

    def problems(self) -> list[str]:
        """Every inconsistency of the file, in a fixed order; empty when it is sound."""
        found: list[str] = []
        if self.default_scheme not in self.schemes:
            found.append(f"default_scheme {self.default_scheme!r} is not a scheme")
        for code, scheme in self.schemes.items():
            if scheme.kind == "staged" and not scheme.stages:
                found.append(f"scheme {code}: a staged scheme needs stages")
            if scheme.kind != "staged" and scheme.stages:
                found.append(f"scheme {code}: only a staged scheme has stages")
            if scheme.kind == "alpha":
                letters = [c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if c not in scheme.skip]
                if len(letters) < 2:
                    found.append(f"scheme {code}: skips too many letters")
                if scheme.start is not None and scheme.start not in letters:
                    found.append(f"scheme {code}: start {scheme.start!r} is not a usable letter")
            if scheme.kind == "numeric" and scheme.start is not None:
                if not isinstance(scheme.start, int) or scheme.start < 0:
                    found.append(f"scheme {code}: start must be a number from 0")
        if len(set(self.classes)) != len(self.classes):
            found.append("classes lists a class twice")
        for code, status in self.statuses.items():
            if status.status_class not in self.classes:
                found.append(f"status {code}: class {status.status_class!r} is not in classes")
        refs: list[tuple[str, str]] = [
            (f"assignment.by_document_type.{k}", v)
            for k, v in self.assignment.by_document_type.items()
        ]
        for project, entry in self.assignment.by_project.items():
            if entry.default is not None:
                refs.append((f"assignment.by_project.{project}.default", entry.default))
            refs += [
                (f"assignment.by_project.{project}.by_document_type.{k}", v)
                for k, v in entry.by_document_type.items()
            ]
        found += [
            f"{where}: {scheme!r} is not a scheme"
            for where, scheme in refs
            if scheme not in self.schemes
        ]
        return found


def parse_scheme_file(text: str, *, source: str = SCHEME_FILE) -> SchemeFile:
    """The file's content as a checked ``SchemeFile``. Raises ``UnknownSchemeError``."""
    try:
        data: Any = yaml.safe_load(text)
        parsed = SchemeFile.model_validate(data)
    except yaml.YAMLError as exc:
        raise UnknownSchemeError(f"{source}: invalid YAML: {exc}") from exc
    except (ValidationError, RecursionError, ValueError) as exc:
        raise UnknownSchemeError(f"{source}: {exc}") from exc
    problems = parsed.problems()
    if problems:
        raise UnknownSchemeError(f"{source}: " + "; ".join(problems))
    return parsed


def load_scheme_file(path: Path | None = None) -> SchemeFile:
    """Read the scheme file of the schema directory (or ``path``). Raises ``UnknownSchemeError``."""
    target = path if path is not None else default_schema_dir() / SCHEME_FILE
    try:
        text = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        # the error text of the OS holds the full path; name the file and the kind of failure only
        raise UnknownSchemeError(
            f"cannot read the revision scheme file {target.name} ({type(exc).__name__})"
        ) from exc
    return parse_scheme_file(text, source=target.name)


Position = tuple[int, ...]


@dataclass(frozen=True)
class Scheme:
    """One scheme, ready to use. Build it with :func:`scheme_by_code`."""

    code: str
    label: str
    definition: SchemeDef

    @property
    def kind(self) -> str:
        return self.definition.kind

    # --- alpha ---------------------------------------------------------------------------------

    def _letters(self) -> list[str]:
        return [c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if c not in self.definition.skip]

    def _alpha_position(self, code: str) -> int | None:
        letters = self._letters()
        if not code or any(ch not in letters for ch in code):
            return None
        value = 0
        for ch in code:
            value = value * len(letters) + letters.index(ch) + 1
        return value

    def _alpha_code(self, position: int) -> str:
        letters = self._letters()
        out = ""
        while position > 0:
            position, rest = divmod(position - 1, len(letters))
            out = letters[rest] + out
        return out

    # --- the public surface --------------------------------------------------------------------

    def position(self, code: str) -> Position | None:
        """Where ``code`` stands in the scheme, or ``None`` when it is not a code of it."""
        if _CODE.fullmatch(code) is None:
            return None
        kind = self.definition.kind
        if kind == "alpha":
            at = self._alpha_position(code)
            first = self._alpha_position(str(self.definition.start or self._letters()[0]))
            return None if at is None or first is None or at < first else (at,)
        if kind == "numeric":
            if not code.isascii() or not code.isdigit() or (len(code) > 1 and code[0] == "0"):
                return None
            start = int(self.definition.start or 0)
            return (int(code),) if int(code) >= start else None
        for index, stage in enumerate(self.definition.stages):
            number = code[len(stage.prefix) :]
            if (
                code.startswith(stage.prefix)
                and number.isascii()
                and number.isdigit()
                and (len(number) == 1 or number[0] != "0")
                and int(number) >= stage.start
            ):
                return (index, int(number))
        return None

    def first_code(self) -> str:
        """The code of a document's first revision."""
        kind = self.definition.kind
        if kind == "alpha":
            return str(self.definition.start or self._letters()[0])
        if kind == "numeric":
            return str(int(self.definition.start or 0))
        stage = self.definition.stages[0]
        return f"{stage.prefix}{stage.start}"

    def next_code(self, previous: str | None, *, stage: str | None = None) -> str:
        """The code that follows ``previous`` (``None``: the first). ``stage`` starts a new stage.

        Raises ``InvalidRevisionCodeError`` when ``previous`` is not a code of the scheme, when
        ``stage`` is given for a scheme with no stages, or when it names the current stage or an
        earlier one.
        """
        if previous is None:
            if stage is not None:
                return self._stage_start(stage, after=None)
            return self.first_code()
        at = self.position(previous)
        if at is None:
            raise InvalidRevisionCodeError(
                f"{previous!r} is not a code of the {self.code} scheme ({self.label})"
            )
        kind = self.definition.kind
        if stage is not None:
            return self._stage_start(stage, after=at)
        if kind == "alpha":
            return self._alpha_code(at[0] + 1)
        if kind == "numeric":
            return str(at[0] + 1)
        prefix = self.definition.stages[at[0]].prefix
        return f"{prefix}{at[1] + 1}"

    def _stage_start(self, stage: str, *, after: Position | None) -> str:
        if self.definition.kind != "staged":
            raise InvalidRevisionCodeError(f"the {self.code} scheme has no stages")
        names = [s.prefix for s in self.definition.stages]
        if stage not in names:
            raise InvalidRevisionCodeError(
                f"{stage!r} is not a stage of the {self.code} scheme ({', '.join(names)})"
            )
        index = names.index(stage)
        if after is not None and index <= after[0]:
            raise InvalidRevisionCodeError(
                f"stage {stage!r} is not after the current stage {names[after[0]]!r}"
            )
        chosen = self.definition.stages[index]
        return f"{chosen.prefix}{chosen.start}"

    def validate_after(self, code: str, previous: str | None) -> None:
        """Raise ``InvalidRevisionCodeError`` unless ``code`` follows ``previous`` in the scheme."""
        at = self.position(code)
        if at is None:
            raise InvalidRevisionCodeError(
                f"{code!r} is not a code of the {self.code} scheme ({self.label}); "
                f"the first is {self.first_code()!r}"
            )
        if previous is None:
            return
        before = self.position(previous)
        if before is not None and at <= before:
            raise InvalidRevisionCodeError(f"{code!r} does not come after {previous!r}")


def scheme_by_code(config: SchemeFile, code: str) -> Scheme:
    """The scheme named ``code``. Raises ``UnknownSchemeError``."""
    found = config.schemes.get(code)
    if found is None:
        raise UnknownSchemeError(
            f"no revision scheme {code!r} (have: {', '.join(sorted(config.schemes))})"
        )
    return Scheme(code=code, label=found.label, definition=found)


def scheme_code_for(config: SchemeFile, scope: str, doc_type: str | None) -> str:
    """The scheme that numbers a document of ``doc_type`` in ``scope``.

    The first of: this project and the document type, this project, the document type, the
    default.
    """
    project = config.assignment.by_project.get(scope)
    if project is not None and doc_type is not None and doc_type in project.by_document_type:
        return project.by_document_type[doc_type]
    if project is not None and project.default is not None:
        return project.default
    if doc_type is not None and doc_type in config.assignment.by_document_type:
        return config.assignment.by_document_type[doc_type]
    return config.default_scheme


def status_class(config: SchemeFile, issue_status: str) -> str:
    """The status class of ``issue_status``. Raises ``InvalidIssueStatusError``."""
    found = config.statuses.get(issue_status)
    if found is None:
        raise InvalidIssueStatusError(
            f"{issue_status!r} is not an issue status (have: {', '.join(config.statuses)})"
        )
    return found.status_class
