"""The standards document: the YAML in which an edition of the company standards is written.

One file is one edition (``co.acme.standards@1.0.0``). It lists the code lists with their values,
the mnemonics (tag prefixes), the numbering patterns and the tag classes (brief 6.4, 9 M2). Loading
a document into a ledger (``tl_mod_engineering.loader``) turns each entry into a registry record;
this module only reads and checks the YAML. The models forbid unknown keys, so a misspelt field
fails at load time instead of being ignored.

Cross-checks that need the whole document are in ``StandardsDoc.problems``: duplicate codes, a
pattern segment that names a missing code list, a class that names a missing mnemonic. Checks that
need the ledger (does the pset exist, is the list already registered) belong to the loader.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from tl_core.numbering.pattern import PatternError, parse_pattern

ValueListPolicy = Literal["closed", "extensible", "project_defined"]
Adoption = Literal["mandatory", "default", "optional"]
TagFamily = Literal["instrument", "valve", "pump", "line", "equipment", "cable", "other"]
SegmentRole = Literal["area", "mnemonic", "sequence", "other"]

#: ``co.acme.standards``: lower-case dotted words.
NAME_PATTERN = re.compile(r"[a-z][a-z0-9]*(?:\.[a-z][a-z0-9-]*)+")
VERSION_PATTERN = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")
#: A code list name, as in the package files: ``Discipline``, ``NdeMethod``.
LIST_CODE = re.compile(r"[A-Z][A-Za-z0-9]*")
#: A value code: letters, digits and ``._-`` ( ``SS316L-NACE``, ``PIP``, ``m3.h`` ).
VALUE_CODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
#: A mnemonic: letters and digits only, so it can stand in a tag number segment.
MNEMONIC_CODE = re.compile(r"[A-Z][A-Z0-9]*")
#: A pattern, class or segment name: ``tag``, ``ControlValve``, ``area``.
ENTRY_CODE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
PSET_NAME = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*(?:\.[a-z][a-z0-9]*(?:_[a-z0-9]+)*)?")
RECORD_TYPE = re.compile(r"[a-z][a-z0-9_]*\.[A-Z][A-Za-z0-9]*")


class StandardsDocError(ValueError):
    """A standards file that cannot be used. The message names the source and lists the problems."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _date(value: str | None) -> str | None:
    if value is not None and DATE_PATTERN.fullmatch(value) is None:
        raise ValueError(f"must be an ISO date (YYYY-MM-DD), got {value!r}")
    return value


class ValueDef(_Strict):
    code: str
    label: str = Field(min_length=1)
    meaning: str | None = None  # IRI of the value's meaning (brief 27.6)
    effective_from: str | None = None
    effective_to: str | None = None
    attributes: dict[str, Any] = {}

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        if VALUE_CODE.fullmatch(value) is None:
            raise ValueError(f"value code {value!r} may hold letters, digits and ._- only")
        return value

    @field_validator("effective_from", "effective_to")
    @classmethod
    def _dates(cls, value: str | None) -> str | None:
        return _date(value)


class CodeListDef(_Strict):
    label: str = Field(min_length=1)
    definition: str = Field(min_length=1)  # brief 27.6: a definition is mandatory
    value_list_policy: ValueListPolicy = "closed"
    adoption: Adoption = "default"
    owner: str | None = None  # default: the document's owner
    values: list[ValueDef] = Field(min_length=1)


class MnemonicDef(_Strict):
    code: str
    label: str = Field(min_length=1)  # what the prefix means
    definition: str | None = None
    class_hint: str | None = None  # the tag class a tag with this prefix normally has
    discipline: str | None = None  # a value of the Discipline list, when there is one

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        if MNEMONIC_CODE.fullmatch(value) is None:
            raise ValueError(f"mnemonic {value!r} must be upper-case letters and digits")
        return value


class SegmentDef(_Strict):
    """What one segment of a numbering pattern is and where its values come from."""

    role: SegmentRole
    list: str | None = None  # the value must be a code of this code list
    registry: Literal["mnemonic"] | None = None  # the value must be a registered mnemonic


class PatternDef(_Strict):
    code: str
    label: str = Field(min_length=1)
    definition: str = Field(min_length=1)
    record_type: str
    template: str  # ``{area}-{mnemonic}-{seq:4}``; see tl_core.numbering.pattern
    segments: dict[str, SegmentDef]  # by name: each field of the template, and ``seq``
    allocate: bool = False  # True: the numbering service hands out the sequence
    gap_free: bool = True
    scope: str = "project:*"
    reserved: list[tuple[int, int]] = []

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        if ENTRY_CODE.fullmatch(value) is None:
            raise ValueError(f"pattern code {value!r} may hold letters, digits and _ only")
        return value

    @field_validator("record_type")
    @classmethod
    def _record_type(cls, value: str) -> str:
        if RECORD_TYPE.fullmatch(value) is None:
            raise ValueError(f"record type {value!r} must look like 'engineering.Tag'")
        return value


class TagClassDef(_Strict):
    code: str
    label: str = Field(min_length=1)
    definition: str = Field(min_length=1)
    family: TagFamily
    required_psets: list[str] = []
    itr_templates: list[str] = []
    mnemonics: list[str] = []

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        if ENTRY_CODE.fullmatch(value) is None:
            raise ValueError(f"class code {value!r} may hold letters, digits and _ only")
        return value

    @field_validator("required_psets")
    @classmethod
    def _psets(cls, value: list[str]) -> list[str]:
        for name in value:
            if PSET_NAME.fullmatch(name) is None:
                raise ValueError(f"pset name {name!r} must be lower snake case")
        return value


class StandardsDoc(_Strict):
    standards: str  # the name of the standards, ``co.acme.standards``
    version: str
    title: str | None = None
    description: str = Field(min_length=1)
    owner: str = Field(min_length=1)  # a role or actor that stewards the standards
    effective_from: str | None = None
    code_lists: dict[str, CodeListDef] = {}
    mnemonics: list[MnemonicDef] = []
    numbering_patterns: list[PatternDef] = []
    tag_classes: list[TagClassDef] = []

    @field_validator("standards")
    @classmethod
    def _name(cls, value: str) -> str:
        if NAME_PATTERN.fullmatch(value) is None:
            raise ValueError(
                f"name {value!r} must be lower-case dotted words, like co.acme.standards"
            )
        return value

    @field_validator("version")
    @classmethod
    def _version(cls, value: str) -> str:
        if VERSION_PATTERN.fullmatch(value) is None:
            raise ValueError(f"version must be MAJOR.MINOR.PATCH, got {value!r}")
        return value

    @field_validator("effective_from")
    @classmethod
    def _start(cls, value: str | None) -> str | None:
        return _date(value)

    @field_validator("code_lists")
    @classmethod
    def _list_names(cls, value: dict[str, CodeListDef]) -> dict[str, CodeListDef]:
        for name in value:
            if LIST_CODE.fullmatch(name) is None:
                raise ValueError(f"code list name {name!r} must be UpperCamelCase")
        return value

    @property
    def edition(self) -> str:
        """``co.acme.standards@1.0.0``: what every entry of the document records as its edition."""
        return f"{self.standards}@{self.version}"

    def problems(self) -> list[str]:
        """Every inconsistency across the document, in a fixed order; empty when it is sound."""
        found: list[str] = []
        found += _duplicates("mnemonic", [m.code for m in self.mnemonics])
        found += _duplicates("numbering pattern", [p.code for p in self.numbering_patterns])
        found += _duplicates("tag class", [c.code for c in self.tag_classes])
        for name, code_list in self.code_lists.items():
            found += _duplicates(f"value of {name}", [v.code for v in code_list.values])
            for value in code_list.values:
                if value.effective_from and value.effective_to:
                    if value.effective_to < value.effective_from:
                        found.append(f"{name}.{value.code}: effective_to is before effective_from")
        mnemonic_codes = {m.code for m in self.mnemonics}
        for mnemonic in self.mnemonics:
            if mnemonic.discipline is not None and "Discipline" in self.code_lists:
                known = {v.code for v in self.code_lists["Discipline"].values}
                if mnemonic.discipline not in known:
                    found.append(
                        f"mnemonic {mnemonic.code}: discipline {mnemonic.discipline!r} "
                        "is not a value of Discipline"
                    )
        for pattern in self.numbering_patterns:
            found += _pattern_problems(pattern, set(self.code_lists))
        class_codes = {c.code for c in self.tag_classes}
        for tag_class in self.tag_classes:
            for code in tag_class.mnemonics:
                if code not in mnemonic_codes:
                    found.append(f"tag class {tag_class.code}: mnemonic {code!r} is not defined")
        for mnemonic in self.mnemonics:
            if mnemonic.class_hint is not None and mnemonic.class_hint not in class_codes:
                found.append(
                    f"mnemonic {mnemonic.code}: class_hint {mnemonic.class_hint!r} "
                    "is not a tag class of the document"
                )
        return found


def _duplicates(what: str, codes: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for code in codes:
        if code in seen and f"duplicate {what} {code!r}" not in out:
            out.append(f"duplicate {what} {code!r}")
        seen.add(code)
    return out


def _pattern_problems(pattern: PatternDef, lists: set[str]) -> list[str]:
    """Problems of one pattern: the template must parse and the segments must match its fields."""
    try:
        parsed = parse_pattern(pattern.template)
    except PatternError as exc:
        return [f"numbering pattern {pattern.code}: template {pattern.template!r}: {exc}"]
    found: list[str] = []
    expected = {*parsed.fields, "seq"}
    for name in sorted(expected - set(pattern.segments)):
        found.append(f"numbering pattern {pattern.code}: segment {name!r} has no definition")
    for name in sorted(set(pattern.segments) - expected):
        found.append(f"numbering pattern {pattern.code}: segment {name!r} is not in the template")
    seq = pattern.segments.get("seq")
    if seq is not None and seq.role != "sequence":
        found.append(f"numbering pattern {pattern.code}: segment 'seq' must have the role sequence")
    roles = [s.role for n, s in pattern.segments.items() if n != "seq"]
    if "sequence" in roles:
        found.append(f"numbering pattern {pattern.code}: only 'seq' may have the role sequence")
    for role in ("area", "mnemonic"):
        if roles.count(role) > 1:
            found.append(f"numbering pattern {pattern.code}: more than one segment has role {role}")
    for name, segment in sorted(pattern.segments.items()):
        if segment.list is not None and segment.list not in lists:
            found.append(
                f"numbering pattern {pattern.code}: segment {name!r} names the code list "
                f"{segment.list!r}, which the document does not define"
            )
        if segment.list is not None and segment.registry is not None:
            found.append(
                f"numbering pattern {pattern.code}: segment {name!r} names a list and a registry"
            )
    return found


def parse_standards(text: str, *, source: str = "<string>") -> StandardsDoc:
    """Parse YAML text into a checked ``StandardsDoc``.

    Raises ``StandardsDocError`` whose message starts with ``source`` for: invalid YAML, a document
    that is not a mapping, a field that does not validate (one line each, ``<location>: <why>``),
    or any problem ``StandardsDoc.problems`` finds.
    """
    try:
        data: Any = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise StandardsDocError(f"{source}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise StandardsDocError(f"{source}: a standards file must be a YAML mapping")
    try:
        doc = StandardsDoc.model_validate(data)
    except ValidationError as exc:
        lines = [
            f"{source}: {'.'.join(str(part) for part in e['loc']) or '(document)'}: {e['msg']}"
            for e in exc.errors()
        ]
        raise StandardsDocError("\n".join(lines)) from exc
    problems = doc.problems()
    if problems:
        raise StandardsDocError("\n".join(f"{source}: {problem}" for problem in problems))
    return doc


def load_standards_file(path: Path) -> StandardsDoc:
    """Read and parse one file. A read error becomes a ``StandardsDocError`` naming the file."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise StandardsDocError(f"{path.name}: cannot read file: {exc}") from exc
    return parse_standards(text, source=path.name)
