"""Correspondence domain definitions: parse, check and look up (brief 9 M10, "Domain definition").

A domain (General, Document control, later Technical, Commercial, Legal ...) is a YAML file in
``<schema dir>/correspondence/domains/``: its subtypes, workflow, numbering, required property
sets, default clocks, routing, confidentiality default, feed policy, integration policy, letter
templates and the words triage looks for. The format is the LinkML class ``CorrespondenceDomain``
(``schema/modules/correspondence/domain.yaml``; its generated JSON Schema is
``json_schema/correspondence.domain.schema.json``) and the models below mirror it field by field;
a test keeps the two equal. A definition is data: nothing in it is run, and no value of it is
used as SQL, a file name or a role grant. ``routing`` roles are information for people, never an
authorisation (access is the access word of each command, ADR-0013).

``parse_domain`` reads one file (size, YAML and shape bounded). ``check_domain`` adds the checks
that need the rest of the system: the workflow and numbering pattern exist, the register source
is one the module has, clocks and templates refer to subtypes that exist. ``DomainSet`` holds the
checked definitions and answers "which definition governs this scope": a project override beats
the company default, and among equals the highest ``semver`` wins.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable
from pathlib import Path
from typing import Final, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from tl_core.numbering.config import NumberingRegistry
from tl_core.workflow.loader import WorkflowRegistry
from tl_schema.registry import default_schema_dir

from tl_mod_correspondence.limits import MAX_DURATION_DAYS, MAX_WARNINGS

MAX_FILE_BYTES: Final = 256 * 1024
MAX_SUBTYPES: Final = 30
MAX_CLOCKS_PER_SUBTYPE: Final = 5
MAX_TEMPLATES: Final = 20
MAX_KEYWORDS: Final = 100
MAX_PSETS: Final = 20
MAX_TEXT: Final = 2000
_CODE = re.compile(r"[a-z][a-z0-9_]{0,31}")
_TEMPLATE_CODE = re.compile(r"[a-z][a-z0-9-]{0,63}")
_SCOPE = re.compile(r"company|project:[A-Za-z0-9_.-]{1,64}")
_SEMVER = re.compile(r"(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})")
_PSET = re.compile(r"[a-z][a-z0-9_]{0,63}")
_CLAUSE = re.compile(r"[A-Za-z0-9_.-]{1,64}/[A-Za-z0-9_.()-]{1,64}")
_WORD = re.compile(r"[a-z0-9][a-z0-9 _.-]{0,59}")

ConfidentialityClass = Literal["internal", "restricted", "privileged"]
FeedPolicy = Literal["full", "minimal", "none"]
ClockTrigger = Literal["receipt", "issue"]
ClockKind = Literal["response_from_them", "response_from_us", "time_bar"]
DayType = Literal["calendar", "working"]


class DomainError(ValueError):
    """A domain file or definition that cannot be used. The message names the source."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class ClockTemplate(_Strict):
    label: str = Field(min_length=1, max_length=200)
    trigger: ClockTrigger
    kind: ClockKind
    duration_days: int = Field(ge=1, le=MAX_DURATION_DAYS)
    day_type: DayType
    warn_days: tuple[int, ...] = Field(default=(), max_length=MAX_WARNINGS)
    clause: str | None = None

    @field_validator("warn_days")
    @classmethod
    def _warn(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if len(set(value)) != len(value) or any(w < 1 for w in value):
            raise ValueError("warn_days are distinct whole numbers of at least 1")
        return tuple(sorted(value, reverse=True))

    @field_validator("clause")
    @classmethod
    def _clause(cls, value: str | None) -> str | None:
        if value is not None and _CLAUSE.fullmatch(value) is None:
            raise ValueError("a clause is <contract>/<clause number>")
        return value


def _words(values: tuple[str, ...], what: str) -> tuple[str, ...]:
    if len(values) > MAX_KEYWORDS or len(set(values)) != len(values):
        raise ValueError(f"{what}: at most {MAX_KEYWORDS}, each once")
    for word in values:
        if _WORD.fullmatch(word) is None:
            raise ValueError(f"{what}: {word!r} is not a lower-case word or phrase")
    return values


class DomainSubtype(_Strict):
    code: str
    label: str = Field(min_length=1, max_length=200)
    response_required: bool = False
    clocks: tuple[ClockTemplate, ...] = Field(default=(), max_length=MAX_CLOCKS_PER_SUBTYPE)
    keywords: tuple[str, ...] = ()

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        if _CODE.fullmatch(value) is None:
            raise ValueError("a code is lower case: a letter, then letters, digits or _")
        return value

    @field_validator("keywords")
    @classmethod
    def _kw(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _words(value, "keywords")


class DomainRouting(_Strict):
    receive_roles: tuple[str, ...] = Field(default=(), max_length=20)
    review_roles: tuple[str, ...] = Field(default=(), max_length=20)
    approve_roles: tuple[str, ...] = Field(default=(), max_length=20)
    party_roles: tuple[str, ...] = Field(default=(), max_length=20)


class DomainIntegration(_Strict):
    webhook_modes: tuple[Literal["thin", "delta", "full"], ...] = Field(default=(), max_length=3)
    portal_response: bool = False


class LetterTemplate(_Strict):
    code: str
    label: str = Field(min_length=1, max_length=200)
    subtype: str
    header: str | None = Field(default=None, max_length=MAX_TEXT)
    footer: str | None = Field(default=None, max_length=MAX_TEXT)

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        if _TEMPLATE_CODE.fullmatch(value) is None:
            raise ValueError("a template code is lower case letters, digits and -")
        return value


class DomainDefinition(_Strict):
    code: str
    name: str = Field(min_length=1, max_length=200)
    semver: str
    scope: str
    description: str | None = Field(default=None, max_length=MAX_TEXT)
    subtypes: tuple[DomainSubtype, ...] = Field(min_length=1, max_length=MAX_SUBTYPES)
    default_subtype: str
    workflow_ref: str = Field(min_length=1, max_length=200)
    numbering_pattern: str = Field(min_length=1, max_length=200)
    required_psets: tuple[str, ...] = Field(default=(), max_length=MAX_PSETS)
    routing: DomainRouting | None = None
    confidentiality_default: ConfidentialityClass
    feed_policy: FeedPolicy
    integration: DomainIntegration | None = None
    templates: tuple[LetterTemplate, ...] = Field(default=(), max_length=MAX_TEMPLATES)
    triage_keywords: tuple[str, ...] = ()
    item_source: str | None = Field(default=None, max_length=100)

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        if _CODE.fullmatch(value) is None:
            raise ValueError("a code is lower case: a letter, then letters, digits or _")
        return value

    @field_validator("semver")
    @classmethod
    def _semver(cls, value: str) -> str:
        if _SEMVER.fullmatch(value) is None:
            raise ValueError("semver is major.minor.patch")
        return value

    @field_validator("scope")
    @classmethod
    def _scope(cls, value: str) -> str:
        if _SCOPE.fullmatch(value) is None:
            raise ValueError("scope is company or project:<id>")
        return value

    @field_validator("required_psets")
    @classmethod
    def _psets(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value) or any(_PSET.fullmatch(p) is None for p in value):
            raise ValueError("required_psets are distinct pset names")
        return value

    @field_validator("triage_keywords")
    @classmethod
    def _kw(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _words(value, "triage_keywords")

    def subtype(self, code: str) -> DomainSubtype | None:
        return next((s for s in self.subtypes if s.code == code), None)

    def semver_key(self) -> tuple[int, int, int]:
        major, minor, patch = (int(part) for part in self.semver.split("."))
        return major, minor, patch


def parse_domain(text: str, *, source: str = "<string>") -> DomainDefinition:
    """Parse one domain file. Raises ``DomainError`` starting with ``source``."""
    if len(text.encode("utf-8", errors="replace")) > MAX_FILE_BYTES:
        raise DomainError(f"{source}: the file is larger than {MAX_FILE_BYTES} bytes")
    try:
        data = yaml.safe_load(text)
    except (yaml.YAMLError, RecursionError, ValueError) as exc:
        raise DomainError(f"{source}: the file is not readable YAML") from exc
    if not isinstance(data, dict):
        raise DomainError(f"{source}: a domain file must be a YAML mapping")
    try:
        return DomainDefinition.model_validate(_lists_to_tuples(data))
    except ValidationError as exc:
        lines = [
            f"{source}: {'.'.join(str(p) for p in e['loc']) or '(document)'}: {e['msg']}"
            for e in exc.errors()
        ]
        raise DomainError("\n".join(lines)) from exc


def _lists_to_tuples(value: object) -> object:
    """Strict models take tuples; YAML gives lists. Convert lists (and only lists)."""
    if isinstance(value, dict):
        return {k: _lists_to_tuples(v) for k, v in value.items()}
    if isinstance(value, list):
        return tuple(_lists_to_tuples(v) for v in value)
    return value


def check_domain(
    domain: DomainDefinition,
    *,
    workflows: WorkflowRegistry,
    numbering: NumberingRegistry,
    sources: Collection[str],
    source: str = "<domain>",
) -> list[str]:
    """The meaning errors of a structurally valid definition; empty when it is sound.

    Reported: a repeated subtype code; ``default_subtype`` that is not a subtype; a template
    whose subtype does not exist or whose code repeats; a clock warning past the clock's length;
    a ``workflow_ref`` that no workflow has; a ``numbering_pattern`` that no pattern has; an
    ``item_source`` that is not in ``sources``.
    """
    problems: list[str] = []
    codes = [s.code for s in domain.subtypes]
    for code in sorted({c for c in codes if codes.count(c) > 1}):
        problems.append(f"{source}: subtype {code!r} is defined twice")
    if domain.default_subtype not in codes:
        problems.append(f"{source}: default_subtype {domain.default_subtype!r} is not a subtype")
    template_codes = [t.code for t in domain.templates]
    for code in sorted({c for c in template_codes if template_codes.count(c) > 1}):
        problems.append(f"{source}: template {code!r} is defined twice")
    for template in domain.templates:
        if template.subtype not in codes:
            problems.append(
                f"{source}: template {template.code!r} is for unknown subtype {template.subtype!r}"
            )
    for subtype in domain.subtypes:
        for clock in subtype.clocks:
            if any(w > clock.duration_days for w in clock.warn_days):
                problems.append(
                    f"{source}: a clock of {subtype.code!r} warns earlier than it is long"
                )
    if not any(d.id == domain.workflow_ref for d in workflows.all()):
        problems.append(f"{source}: no workflow {domain.workflow_ref!r}")
    if not any(p.id == domain.numbering_pattern for p in numbering.all()):
        problems.append(f"{source}: no numbering pattern {domain.numbering_pattern!r}")
    if domain.item_source is not None and domain.item_source not in sources:
        problems.append(f"{source}: no register source {domain.item_source!r}")
    return problems


class DomainSet:
    """Checked definitions, looked up by code and scope."""

    def __init__(self, definitions: Iterable[DomainDefinition] = ()) -> None:
        self._all: list[DomainDefinition] = []
        for definition in definitions:
            self.add(definition)

    def add(self, definition: DomainDefinition) -> None:
        key = (definition.code, definition.scope, definition.semver)
        if any((d.code, d.scope, d.semver) == key for d in self._all):
            raise DomainError(
                f"domain {definition.code} {definition.semver} "
                f"({definition.scope}) is defined twice"
            )
        self._all.append(definition)

    def all(self) -> list[DomainDefinition]:
        return list(self._all)

    def codes(self) -> list[str]:
        return sorted({d.code for d in self._all})

    def find(self, code: str, scope: str) -> DomainDefinition | None:
        """The definition for ``code`` in ``scope``: the project's own beats the company's.

        Candidates have scope ``scope`` or ``company``. An exact-scope candidate beats a company
        one; among equals the highest ``semver`` (compared as numbers) wins.
        """
        candidates = [d for d in self._all if d.code == code and d.scope in (scope, "company")]
        if not candidates:
            return None
        return max(candidates, key=lambda d: (d.scope == scope, d.semver_key()))

    def for_scope(self, scope: str) -> list[DomainDefinition]:
        """One definition per code, as ``find`` would answer, sorted by code."""
        found = (self.find(code, scope) for code in self.codes())
        return [d for d in found if d is not None]


def load_domains(
    directory: Path | None = None,
    *,
    workflows: WorkflowRegistry,
    numbering: NumberingRegistry,
    sources: Collection[str],
) -> DomainSet:
    """Every ``*.yaml`` file of ``<directory>/correspondence/domains``, parsed and checked.

    ``directory`` defaults to the schema directory. A missing folder gives an empty set. The first
    file with a problem raises ``DomainError`` listing all of that file's problems. Files are read
    in name order.
    """
    folder = (directory or default_schema_dir()) / "correspondence" / "domains"
    result = DomainSet()
    if not folder.is_dir():
        return result
    for path in sorted(folder.glob("*.yaml"), key=lambda p: p.name):
        try:
            raw = path.read_bytes()[: MAX_FILE_BYTES + 1]
            text = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise DomainError(f"{path.name}: cannot read the file") from exc
        definition = parse_domain(text, source=path.name)
        problems = check_domain(
            definition,
            workflows=workflows,
            numbering=numbering,
            sources=sources,
            source=path.name,
        )
        if problems:
            raise DomainError("\n".join(problems))
        result.add(definition)
    return result
