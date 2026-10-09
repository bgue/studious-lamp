"""Schema package documents: the constrained YAML subset that company and project packages use.

A package is a versioned YAML file (brief 27.1, 27.4). Three kinds exist:

* ``company``: standard psets and code lists, with enforcement (brief 6.3 layer 2).
* ``extension``: a project's extension of company psets (layer 3): tighten constraints, add
  code-list values, add custom-section properties, set defaults and labels. It cannot loosen or
  rename anything; the models forbid unknown keys, so an attempt fails at load time.
* ``project``: project custom psets (layer 4), addressed as ``prj.<name>``.

This module holds only the document models and the pure helpers that read them. Reading files is
``tl_schema.registry``; resolving a package set into an effective schema is ``tl_schema.compile``.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Enforcement = Literal["advisory", "required", "locked"]
ValueListPolicy = Literal["closed", "extensible", "project_defined"]
Adoption = Literal["mandatory", "default", "optional"]
PackageKind = Literal["company", "extension", "project"]
ConformanceMode = Literal["strict", "lenient", "strict_with_waivers"]
PropertyKind = Literal[
    "string",
    "text",
    "int",
    "decimal",
    "bool",
    "date",
    "datetime",
    "quantity",
    "ref",
    "json",
]

#: Names usable as ``range`` besides a code list name. ``enum`` is implied by naming a code list.
PROPERTY_KINDS: tuple[str, ...] = (
    "string",
    "text",
    "int",
    "decimal",
    "bool",
    "date",
    "datetime",
    "quantity",
    "ref",
    "json",
)

#: Pset, property and code-list names: lower snake case, no double underscore.
NAME_PATTERN = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")
#: Code list names: UpperCamelCase, e.g. ``MaterialCode``.
LIST_NAME_PATTERN = re.compile(r"[A-Z][A-Za-z0-9]*")
#: Package names: dotted segments, e.g. ``co.acme.engineering``, ``x.P123`` or ``prj.P123``.
PACKAGE_NAME_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]+)*")
VERSION_PATTERN = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
#: ``co.acme.engineering@3.2.0#valve_data``
PSET_REF_PATTERN = re.compile(
    r"(?P<package>[A-Za-z][A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]+)*)@(?P<version>\d+\.\d+\.\d+)"
    r"#(?P<pset>[a-z][a-z0-9_]*)"
)


class StrictModel(BaseModel):
    """Base for package documents: unknown keys are errors, so loosening attempts fail loudly."""

    model_config = ConfigDict(extra="forbid")


class CodeValue(StrictModel):
    code: str = Field(min_length=1)
    label: str = Field(min_length=1)
    crosswalk: str | None = None  # company code this value maps to (project-added values)
    meaning: str | None = None  # IRI of the value's meaning


class CodeList(StrictModel):
    description: str = Field(min_length=1)
    value_list_policy: ValueListPolicy = "closed"
    values: list[CodeValue] = []


class UnitDef(StrictModel):
    ucum: str = Field(min_length=1)


class PropertyDef(StrictModel):
    """One property of a pset (brief 6.3 general rules)."""

    label: str | None = None  # default: the humanised property name
    description: str = Field(min_length=1)  # mandatory (brief 27.6)
    range: str = "string"  # a PropertyKind, or the name of a code list (an enum property)
    unit: UnitDef | None = None
    required: bool = False  # sugar for required_in_states: ["*"]
    required_in_states: list[str] = []
    enforcement: Enforcement | None = None  # default: the pset's enforcement
    value_list_policy: ValueListPolicy | None = None  # default: the code list's policy
    materialize: bool = False
    minimum: float | None = None
    maximum: float | None = None
    pattern: str | None = None
    default: Any = None
    exact_mappings: list[str] = []

    @field_validator("unit", mode="before")
    @classmethod
    def _unit_from_string(cls, value: Any) -> Any:
        return {"ucum": value} if isinstance(value, str) else value

    @field_validator("pattern")
    @classmethod
    def _pattern_compiles(cls, value: str | None) -> str | None:
        if value is not None:
            re.compile(value)
        return value


class CustomSectionDef(StrictModel):
    allowed: bool = True
    max_properties: int | None = Field(default=None, ge=0)


class PsetDef(StrictModel):
    """A company standard pset, or a project custom pset."""

    label: str | None = None
    description: str = Field(min_length=1)
    applies_to: list[str] = ["core.Record"]
    class_filter: str | None = None  # parsed and kept; evaluated once the query language exists
    enforcement: Enforcement = "advisory"
    adoption: Adoption = "optional"
    custom_section: CustomSectionDef = CustomSectionDef()
    properties: dict[str, PropertyDef]


class TightenDef(StrictModel):
    """What an extension may change on an existing company property: only make it stricter."""

    required_in_states: list[str] | None = None  # must include every company state
    enforcement: Enforcement | None = None  # advisory to required is allowed; never downwards
    minimum: float | None = None  # may only rise
    maximum: float | None = None  # may only fall
    pattern: str | None = None  # allowed only when the company property has none


class ExtendsDef(StrictModel):
    """A project's extension of one company pset (brief 6.3 example)."""

    ref: str  # "co.acme.engineering@3.2.0#valve_data"
    tighten: dict[str, TightenDef] = {}
    add_values: dict[str, list[CodeValue]] = {}  # code list name -> values to add
    custom: dict[str, PropertyDef] = {}  # custom-section properties, addressed under "x."
    defaults: dict[str, Any] = {}
    labels: dict[str, str] = {}

    @field_validator("ref")
    @classmethod
    def _ref_shape(cls, value: str) -> str:
        if PSET_REF_PATTERN.fullmatch(value) is None:
            raise ValueError(f"ref must look like 'package@1.2.3#pset', got {value!r}")
        return value

    def target(self) -> tuple[str, str, str]:
        """``(package, version, pset)`` parsed from ``ref``."""
        match = PSET_REF_PATTERN.fullmatch(self.ref)
        assert match is not None  # checked by the validator
        return match["package"], match["version"], match["pset"]


class WaiverDef(StrictModel):
    """Relaxes one property on one project (brief 6.3); a ledgered record in a later increment."""

    path: str  # "psets.valve_data.size_in"
    reason: str = Field(min_length=1)
    approver: str = Field(min_length=1)
    expires: date | None = None


class ConformanceDef(StrictModel):
    mode: ConformanceMode = "strict"
    lenient_until: date | None = None  # a lenient period is time-limited
    waivers: list[WaiverDef] = []


class PackageDoc(StrictModel):
    """One package version."""

    package: str
    version: str
    kind: PackageKind
    title: str | None = None
    description: str = Field(min_length=1)
    project: str | None = None  # required for extension and project packages
    depends: dict[str, str] = {}  # package name -> exact version
    code_lists: dict[str, CodeList] = {}
    psets: dict[str, PsetDef] = {}
    extends: list[ExtendsDef] = []
    conformance: ConformanceDef | None = None

    @field_validator("package")
    @classmethod
    def _package_name(cls, value: str) -> str:
        if PACKAGE_NAME_PATTERN.fullmatch(value) is None:
            raise ValueError(f"invalid package name {value!r}")
        return value

    @field_validator("version")
    @classmethod
    def _version_shape(cls, value: str) -> str:
        if VERSION_PATTERN.fullmatch(value) is None:
            raise ValueError(f"version must be MAJOR.MINOR.PATCH, got {value!r}")
        return value

    @model_validator(mode="after")
    def _kind_rules(self) -> PackageDoc:
        if self.kind == "company":
            if self.project is not None:
                raise ValueError("a company package must not name a project")
            if self.extends:
                raise ValueError("a company package cannot extend psets")
            if self.conformance is not None:
                raise ValueError("a company package cannot set project conformance")
        else:
            if self.project is None:
                raise ValueError(f"a {self.kind} package must name its project")
        if self.kind == "extension" and self.psets:
            raise ValueError("an extension package declares 'extends', not 'psets'")
        if self.kind == "project" and self.extends:
            raise ValueError("a project package declares 'psets', not 'extends'")
        for name in self.psets:
            _check_name(name, RESERVED_PSET_NAMES)
        for list_name in self.code_lists:
            if LIST_NAME_PATTERN.fullmatch(list_name) is None:
                raise ValueError(f"code list name {list_name!r} must be UpperCamelCase")
        for pset in self.psets.values():
            for prop in pset.properties:
                _check_name(prop, RESERVED_PROPERTY_NAMES)
        return self

    def key(self) -> str:
        """``name@version``."""
        return f"{self.package}@{self.version}"


#: Pset names that collide with value-layer path markers (``psets.x``, ``psets.prj.*`` ...).
RESERVED_PSET_NAMES = frozenset({"x", "prj", "enrich", "src"})
#: Property names that collide with the custom-section key.
RESERVED_PROPERTY_NAMES = frozenset({"x"})


def _check_name(name: str, reserved: frozenset[str] = frozenset()) -> None:
    if NAME_PATTERN.fullmatch(name) is None or "__" in name:
        raise ValueError(f"name {name!r} must be lower snake case without a double underscore")
    if name in reserved:
        raise ValueError(f"name {name!r} is reserved")


def version_tuple(version: str) -> tuple[int, int, int]:
    """``"3.2.0"`` becomes ``(3, 2, 0)``; raises ``ValueError`` for anything else."""
    match = VERSION_PATTERN.fullmatch(version)
    if match is None:
        raise ValueError(f"version must be MAJOR.MINOR.PATCH, got {version!r}")
    return int(match[1]), int(match[2]), int(match[3])
